"""
Limitador de pods por worker node baseado no ConfigSimples.

Este módulo implementa a funcionalidade para limitar o número de pods 
nos worker nodes com base nas configurações do ConfigSimples.
"""

import subprocess
import json
from typing import Dict, List, Tuple, Optional
from ..core.config_simples import ConfigSimples
from .kubectl_executor import KubectlExecutor


class PodLimiter:
    """
    Gerencia a limitação de pods por worker node baseado no ConfigSimples.
    """
    
    def __init__(self, config_simples: Optional[ConfigSimples] = None, kubectl_executor: Optional[KubectlExecutor] = None):
        """
        Inicializa o limitador de pods.
        
        Args:
            config_simples: Configuração com limites de pods por worker
            kubectl_executor: Executor de kubectl (local ou AWS)
        """
        self.config_simples = config_simples or ConfigSimples()
        self.kubectl_executor = kubectl_executor or KubectlExecutor()
        
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
    
    def _discover_application_names(self) -> set:
        """
        Descobre automaticamente os nomes das aplicações baseado nos pods no namespace default.
        
        Returns:
            Set com nomes das aplicações descobertas
        """
        try:
            # Obter pods do namespace default usando kubectl_executor
            result = self.kubectl_executor.execute_kubectl(['get', 'pods', '-n', 'default', '-o', 'json'])
            
            if not result['success']:
                print(f"❌ Erro ao obter pods do namespace default: {result['error']}")
                return set()
            
            pods_data = json.loads(result['output'])
            discovered_apps = set()
            
            for pod in pods_data.get('items', []):
                pod_name = pod['metadata']['name']
                
                # Extrair nome da aplicação do pod (ex: "bar-app" de "bar-app-6664549c89-n7kz2")
                if '-' in pod_name:
                    app_name = pod_name.split('-')[0] + '-app'  # Assumindo padrão "app-name-hash-id"
                    if app_name.endswith('-app-app'):  # Evitar duplicação de "-app"
                        app_name = app_name[:-4]  # Remove o "-app" extra
                    discovered_apps.add(app_name)
                    
            return discovered_apps
            
        except Exception as e:
            print(f"❌ Erro ao descobrir aplicações: {e}")
            return set()

    def get_current_pods_on_node(self, node_name: str) -> Tuple[List[str], List[Dict]]:
        """
        Obtém pods atuais em um worker node, separando sistema e aplicação.
        
        Args:
            node_name: Nome do worker node
            
        Returns:
            Tuple com (pods_sistema, pods_aplicacao_com_namespace)
            onde pods_aplicacao_com_namespace é lista de dicts com {'name': str, 'namespace': str}
        """
        try:
            # Obter todos os pods do nó usando kubectl_executor
            result = self.kubectl_executor.execute_kubectl([
                'get', 'pods', '--all-namespaces', 
                '--field-selector', f'spec.nodeName={node_name}',
                '-o', 'json'
            ])
            
            if not result['success']:
                print(f"❌ Erro ao obter pods do nó {node_name}: {result['error']}")
                return [], []
            
            pods_data = json.loads(result['output'])
            
            # Separar pods do sistema de pods de aplicação
            system_pods = []
            app_pods = []
            
            # Namespaces de sistema - EXCLUINDO 'default' que contém as aplicações
            system_namespaces = {
                'kube-system', 'kube-public', 'kube-node-lease',
                'local-path-storage', 'metallb-system', 'ingress-nginx',
                'kubernetes-dashboard', 'monitoring'
            }
            
            # Descobrir aplicações automaticamente
            discovered_apps = self._discover_application_names()
            
            for pod in pods_data.get('items', []):
                pod_name = pod['metadata']['name']
                namespace = pod['metadata']['namespace']
                
                # Pods de aplicação são aqueles no namespace 'default' 
                # que correspondem às aplicações descobertas automaticamente
                if namespace == 'default':
                    # Verificar se é uma aplicação real baseado na descoberta automática
                    is_application = any(app_name in pod_name for app_name in discovered_apps)
                    
                    if is_application:
                        app_pods.append({'name': pod_name, 'namespace': namespace})
                    else:
                        system_pods.append(pod_name)
                elif namespace in system_namespaces:
                    system_pods.append(pod_name)
                else:
                    # Qualquer outro namespace que não seja sistema é considerado aplicação
                    # mas priorizamos os pods do 'default' que são as aplicações reais
                    system_pods.append(pod_name)
                    
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
            
            # Extrair apenas nomes para compatibilidade
            app_pod_names = [pod['name'] if isinstance(pod, dict) else pod for pod in app_pods]
            
            status[worker_name] = {
                'limit': limit,
                'system_pods': len(system_pods),
                'app_pods': len(app_pods),
                'total_pods': len(system_pods) + len(app_pods),
                'within_limit': len(app_pods) <= limit,
                'system_pod_names': system_pods,
                'app_pod_names': app_pod_names,
                'app_pods_with_namespace': app_pods  # Manter info completa
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
                excess_count = len(worker_status['app_pods_with_namespace']) - worker_status['limit']
                pods_to_remove = worker_status['app_pods_with_namespace'][:excess_count]
                
                print(f"🚫 Worker {worker_name}: {len(worker_status['app_pods_with_namespace'])} pods > limite {worker_status['limit']}")
                pod_names = [pod['name'] if isinstance(pod, dict) else pod for pod in pods_to_remove]
                print(f"   Removendo {excess_count} pods: {pod_names}")
                
                removal_success = self._remove_pods_with_namespace(pods_to_remove)
                results[worker_name] = removal_success
            else:
                print(f"✅ Worker {worker_name}: {len(worker_status['app_pods_with_namespace'])} pods <= limite {worker_status['limit']}")
                results[worker_name] = True
                
        return results
    
    def _remove_pods_with_namespace(self, pods_with_namespace: List[Dict]) -> bool:
        """
        Remove uma lista de pods usando informação de namespace.
        
        Args:
            pods_with_namespace: Lista de dicts com 'name' e 'namespace'
            
        Returns:
            True se todos os pods foram removidos com sucesso
        """
        try:
            for pod_info in pods_with_namespace:
                if isinstance(pod_info, dict):
                    pod_name = pod_info['name']
                    namespace = pod_info['namespace']
                else:
                    # Fallback para strings simples
                    pod_name = pod_info
                    namespace = 'default'
                
                # Deletar o pod usando kubectl_executor
                result = self.kubectl_executor.execute_kubectl(['delete', 'pod', pod_name, '-n', namespace, '--force', '--grace-period=0'])
                
                if result['success']:
                    print(f"  ✅ Pod {pod_name} (namespace: {namespace}) removido")
                else:
                    print(f"  ❌ Falha ao remover pod {pod_name}: {result['error']}")
                    
            return True
            
        except Exception as e:
            print(f"❌ Erro ao remover pods: {e}")
            return False
    
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
                # Tentar obter namespace do pod usando kubectl_executor
                result = self.kubectl_executor.execute_kubectl([
                    'get', 'pod', pod_name, '--all-namespaces',
                    '-o', 'jsonpath={.metadata.namespace}'
                ])
                
                if not result['success']:
                    print(f"❌ Não foi possível obter namespace do pod {pod_name}")
                    continue
                    
                namespace = result['output'].strip()
                
                # Deletar o pod usando kubectl_executor
                delete_result = self.kubectl_executor.execute_kubectl(['delete', 'pod', pod_name, '-n', namespace, '--force'])
                
                if delete_result['success']:
                    print(f"  ✅ Pod {pod_name} removido")
                else:
                    print(f"  ❌ Falha ao remover pod {pod_name}: {delete_result['error']}")
                    
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