"""
Limitador de pods por worker node baseado no ConfigSimples.

Este módulo implementa a funcionalidade para limitar o número de pods 
nos worker nodes com base nas configurações do ConfigSimples.
"""

import subprocess
import json
from typing import Dict, List, Tuple, Optional
from ..core.config_simples import ConfigSimples


class PodLimiter:
    """
    Gerencia a limitação de pods por worker node baseado no ConfigSimples.
    """
    
    def __init__(self, config_simples: Optional[ConfigSimples] = None):
        """
        Inicializa o limitador de pods.
        
        Args:
            config_simples: Configuração com limites de pods por worker
        """
        self.config_simples = config_simples or ConfigSimples()
        
    def get_node_pod_limit(self, node_name: str) -> int:
        """
        Obtém o limite de pods para um worker node específico.
        
        Args:
            node_name: Nome do worker node
            
        Returns:
            Número máximo de pods permitidos (excluindo pods do sistema)
        """
        if isinstance(self.config_simples.worker_nodes_config, dict):
            return self.config_simples.worker_nodes_config.get(node_name, 1)
        else:
            # Se for int, todos os workers têm o mesmo limite
            return int(self.config_simples.worker_nodes_config)
    
    def get_current_pods_on_node(self, node_name: str) -> Tuple[List[str], List[str]]:
        """
        Obtém pods atuais em um worker node, separando sistema e aplicação.
        
        Args:
            node_name: Nome do worker node
            
        Returns:
            Tuple com (pods_sistema, pods_aplicacao)
        """
        try:
            # Obter todos os pods do nó
            cmd = [
                'kubectl', 'get', 'pods', '--all-namespaces', 
                '--field-selector', f'spec.nodeName={node_name}',
                '-o', 'json'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                print(f"❌ Erro ao obter pods do nó {node_name}: {result.stderr}")
                return [], []
            
            pods_data = json.loads(result.stdout)
            
            # Separar pods do sistema de pods de aplicação
            system_pods = []
            app_pods = []
            
            system_namespaces = {
                'kube-system', 'kube-public', 'kube-node-lease',
                'local-path-storage', 'metallb-system', 'default'
            }
            
            for pod in pods_data.get('items', []):
                pod_name = pod['metadata']['name']
                namespace = pod['metadata']['namespace']
                
                if namespace in system_namespaces:
                    system_pods.append(pod_name)
                else:
                    app_pods.append(pod_name)
                    
            return system_pods, app_pods
            
        except Exception as e:
            print(f"❌ Erro ao verificar pods em {node_name}: {e}")
            return [], []
    
    def check_pod_limits(self) -> Dict[str, Dict]:
        """
        Verifica se todos os worker nodes respeitam os limites de pods.
        
        Returns:
            Dict com status de cada worker node
        """
        status = {}
        
        for worker_name in self.config_simples.get_worker_nodes():
            limit = self.get_node_pod_limit(worker_name)
            system_pods, app_pods = self.get_current_pods_on_node(worker_name)
            
            status[worker_name] = {
                'limit': limit,
                'system_pods': len(system_pods),
                'app_pods': len(app_pods),
                'total_pods': len(system_pods) + len(app_pods),
                'within_limit': len(app_pods) <= limit,
                'system_pod_names': system_pods,
                'app_pod_names': app_pods
            }
            
        return status
    
    def enforce_pod_limits(self) -> Dict[str, bool]:
        """
        Aplica os limites de pods removendo pods de aplicação em excesso.
        
        Returns:
            Dict com resultado da aplicação dos limites por worker
        """
        results = {}
        status = self.check_pod_limits()
        
        for worker_name, worker_status in status.items():
            if not worker_status['within_limit']:
                # Remover pods em excesso
                excess_count = len(worker_status['app_pod_names']) - worker_status['limit']
                pods_to_remove = worker_status['app_pod_names'][:excess_count]
                
                print(f"🚫 Worker {worker_name}: {len(worker_status['app_pod_names'])} pods > limite {worker_status['limit']}")
                print(f"   Removendo {excess_count} pods: {pods_to_remove}")
                
                removal_success = self._remove_pods(pods_to_remove)
                results[worker_name] = removal_success
            else:
                print(f"✅ Worker {worker_name}: {len(worker_status['app_pod_names'])} pods <= limite {worker_status['limit']}")
                results[worker_name] = True
                
        return results
    
    def _remove_pods(self, pod_names: List[str]) -> bool:
        """
        Remove uma lista de pods.
        
        Args:
            pod_names: Lista de nomes de pods para remover
            
        Returns:
            True se todos os pods foram removidos com sucesso
        """
        try:
            for pod_name in pod_names:
                # Tentar obter namespace do pod
                cmd = [
                    'kubectl', 'get', 'pod', pod_name, '--all-namespaces',
                    '-o', 'jsonpath={.metadata.namespace}'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if result.returncode != 0:
                    print(f"❌ Não foi possível obter namespace do pod {pod_name}")
                    continue
                    
                namespace = result.stdout.strip()
                
                # Deletar o pod
                delete_cmd = ['kubectl', 'delete', 'pod', pod_name, '-n', namespace, '--force']
                delete_result = subprocess.run(delete_cmd, capture_output=True, text=True, timeout=30)
                
                if delete_result.returncode == 0:
                    print(f"  ✅ Pod {pod_name} removido")
                else:
                    print(f"  ❌ Falha ao remover pod {pod_name}: {delete_result.stderr}")
                    
            return True
            
        except Exception as e:
            print(f"❌ Erro ao remover pods: {e}")
            return False
    
    def print_pod_status(self):
        """
        Exibe status atual dos pods em todos os worker nodes.
        """
        print("\n📊 Status de pods nos worker nodes:")
        print("=" * 60)
        
        status = self.check_pod_limits()
        
        for worker_name, worker_status in status.items():
            status_icon = "✅" if worker_status['within_limit'] else "🚫"
            
            print(f"{status_icon} {worker_name}:")
            print(f"   Limite: {worker_status['limit']} pods de aplicação")
            print(f"   Sistema: {worker_status['system_pods']} pods")
            print(f"   Aplicação: {worker_status['app_pods']} pods")
            print(f"   Total: {worker_status['total_pods']} pods")
            
            if worker_status['app_pod_names']:
                print(f"   Pods de aplicação: {', '.join(worker_status['app_pod_names'])}")
            print()