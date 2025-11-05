"""
Monitor de Sistema
=================

Módulo para monitoramento de componentes do sistema Kubernetes.
"""

import json
from typing import List, Optional
from ..utils.config import get_config
from ..utils.kubectl_executor import get_kubectl_executor


class SystemMonitor:
    """
    Monitor de sistema para componentes Kubernetes.
    
    Monitora pods, nós e outros recursos do sistema.
    """
    
    def __init__(self, aws_config: Optional[dict] = None):
        """
        Inicializa o monitor de sistema.
        
        Args:
            aws_config: Configuração AWS para conexão remota
        """
        self.aws_config = aws_config
        self.is_aws_mode = aws_config is not None
        self.config = get_config(aws_mode=self.is_aws_mode)
        self.kubectl = get_kubectl_executor(aws_config)
    
    def get_pods(self) -> List[str]:
        """
        Obtém lista de pods das aplicações.
        
        Returns:
            Lista com nomes dos pods encontrados
        """
        try:
            pods = self.kubectl.get_pods()
            print(f"📋 Pods encontrados: {pods}")
            return pods
            
        except Exception as e:
            print(f"❌ Erro ao obter pods: {e}")
            return []
    
    def get_worker_nodes(self) -> List[str]:
        """
        Obtém lista de worker nodes.
        
        Returns:
            Lista com nomes dos worker nodes
        """
        try:
            nodes = self.kubectl.get_nodes()
            
            # Filtrar apenas worker nodes (excluir control plane)
            worker_nodes = []
            for node in nodes:
                result = self.kubectl.execute_kubectl([
                    'get', 'node', node, 
                    '-o', 'jsonpath={.metadata.labels.node-role\.kubernetes\.io/control-plane}'
                ])
                
                # Se não tem o label de control-plane, é worker node
                if result['success'] and not result['output'].strip():
                    worker_nodes.append(node)
            
            return worker_nodes
            
        except Exception as e:
            print(f"❌ Erro ao obter worker nodes: {e}")
            return []
    
    def show_pod_status(self, highlight_pod: Optional[str] = None):
        """
        Mostra status dos pods com destaque opcional.
        
        Args:
            highlight_pod: Nome do pod para destacar
        """
        try:
            result = self.kubectl.execute_kubectl(['get', 'pods', '-o', 'wide'])
            
            if not result['success']:
                print(f"❌ Erro ao obter status dos pods: {result['error']}")
                return
            
            print("📋 === STATUS DOS PODS ===")
            lines = result['output'].strip().split('\n')
            for line in lines:
                if highlight_pod and highlight_pod in line:
                    print(f"🎯 {line}")  # Destacar o pod alvo
                else:
                    print(f"   {line}")
            print()
            
        except Exception as e:
            print(f"❌ Erro ao obter status dos pods: {e}")
    
    def show_node_status(self):
        """Mostra status dos nós."""
        try:
            result = self.kubectl.execute_kubectl(['get', 'nodes', '-o', 'wide'])
            
            if not result['success']:
                print(f"❌ Erro ao obter status dos nós: {result['error']}")
                return
            
            print("� === STATUS DOS NÓS ===")
            lines = result['output'].strip().split('\n')
            for line in lines:
                print(f"   {line}")
            print()
            
        except Exception as e:
            print(f"❌ Erro ao obter status dos nós: {e}")
    
    def get_pod_logs(self, pod_name: str, lines: int = 50) -> str:
        """
        Obtém logs de um pod específico.
        
        Args:
            pod_name: Nome do pod
            lines: Número de linhas de log
            
        Returns:
            Logs do pod
        """
        try:
            result = self.kubectl.execute_kubectl([
                'logs', pod_name, '--tail', str(lines)
            ])
            
            if not result['success']:
                return f"❌ Erro ao obter logs do pod {pod_name}: {result['error']}"
            
            return result['output']
            
        except Exception as e:
            return f"❌ Erro ao obter logs do pod {pod_name}: {e}"
    
    def describe_pod(self, pod_name: str) -> str:
        """
        Descreve um pod específico.
        
        Args:
            pod_name: Nome do pod
            
        Returns:
            Descrição do pod
        """
        try:
            result = self.kubectl.execute_kubectl(['describe', 'pod', pod_name])
            
            if not result['success']:
                return f"❌ Erro ao descrever pod {pod_name}: {result['error']}"
            
            return result['output']
            
        except Exception as e:
            return f"❌ Erro ao descrever pod {pod_name}: {e}"
    
    def get_control_plane_node(self) -> Optional[str]:
        """
        Obtém o nome do nó control plane.
        
        Returns:
            Nome do nó control plane ou None se não encontrado
        """
        try:
            # Tentar obter control plane automaticamente
            result = self.kubectl.execute_kubectl([
                'get', 'nodes', '-l', 'node-role.kubernetes.io/control-plane',
                '-o', 'jsonpath={.items[0].metadata.name}'
            ])
            
            if result['success']:
                control_plane = result['output'].strip()
                if control_plane:
                    return control_plane
            
            # Fallback: tentar master label
            result = self.kubectl.execute_kubectl([
                'get', 'nodes', '-l', 'node-role.kubernetes.io/master',
                '-o', 'jsonpath={.items[0].metadata.name}'
            ])
            
            if result['success']:
                control_plane = result['output'].strip()
                if control_plane:
                    return control_plane
            
            # Fallback: procurar por qualquer node com control-plane no nome
            result = self.kubectl.execute_kubectl(['get', 'nodes', '-o', 'json'])
            
            if result['success']:
                nodes_data = json.loads(result['output'])
                
                for node in nodes_data.get('items', []):
                    node_name = node['metadata']['name']
                    if any(term in node_name.lower() for term in ['control-plane', 'master', 'controlplane']):
                        return node_name
            
            # Se chegou até aqui, não conseguiu descobrir automaticamente
            print("❌ Nenhum control plane descoberto automaticamente")
            return None
            
        except Exception as e:
            print(f"❌ Erro ao descobrir control plane automaticamente: {e}")
            return None
    
    def check_cluster_health(self) -> dict:
        """
        Verifica saúde geral do cluster.
        
        Returns:
            Dicionário com status do cluster
        """
        health_status = {
            'cluster_accessible': False,
            'control_plane_ready': False,
            'worker_nodes_ready': 0,
            'total_nodes': 0,
            'pods_running': 0,
            'total_pods': 0
        }
        
        try:
            # Verificar acesso ao cluster
            result = self.kubectl.execute_kubectl(['cluster-info'])
            
            health_status['cluster_accessible'] = result['success']
            
            if health_status['cluster_accessible']:
                # Verificar nós
                result = self.kubectl.execute_kubectl(['get', 'nodes', '--no-headers'])
                
                if result['success']:
                    node_lines = result['output'].strip().split('\n')
                    health_status['total_nodes'] = len([line for line in node_lines if line])
                    
                    ready_nodes = 0
                    for line in node_lines:
                        if 'Ready' in line and 'NotReady' not in line:
                            ready_nodes += 1
                            if 'control-plane' in line or 'master' in line:
                                health_status['control_plane_ready'] = True
                    
                    health_status['worker_nodes_ready'] = ready_nodes
                
                # Verificar pods
                result = self.kubectl.execute_kubectl(['get', 'pods', '--all-namespaces', '--no-headers'])
                
                if result['success']:
                    pod_lines = result['output'].strip().split('\n')
                    health_status['total_pods'] = len([line for line in pod_lines if line])
                    
                    running_pods = 0
                    for line in pod_lines:
                        if 'Running' in line:
                            running_pods += 1
                    
                    health_status['pods_running'] = running_pods
            
        except Exception as e:
            print(f"⚠️ Erro ao verificar saúde do cluster: {e}")
        
        return health_status
    
    def print_cluster_health(self):
        """Imprime status de saúde do cluster."""
        print("🏥 === SAÚDE DO CLUSTER ===")
        
        health = self.check_cluster_health()
        
        # Cluster
        emoji = "✅" if health['cluster_accessible'] else "❌"
        print(f"{emoji} Cluster acessível: {health['cluster_accessible']}")
        
        # Control plane
        emoji = "✅" if health['control_plane_ready'] else "❌"
        print(f"{emoji} Control plane pronto: {health['control_plane_ready']}")
        
        # Worker nodes
        ready_ratio = f"{health['worker_nodes_ready']}/{health['total_nodes']}"
        emoji = "✅" if health['worker_nodes_ready'] == health['total_nodes'] else "⚠️"
        print(f"{emoji} Worker nodes prontos: {ready_ratio}")
        
        # Pods
        pod_ratio = f"{health['pods_running']}/{health['total_pods']}"
        if health['total_pods'] > 0:
            pod_percentage = (health['pods_running'] / health['total_pods']) * 100
            emoji = "✅" if pod_percentage > 80 else "⚠️" if pod_percentage > 50 else "❌"
            print(f"{emoji} Pods executando: {pod_ratio} ({pod_percentage:.1f}%)")
        else:
            print("⚠️ Pods executando: 0/0")
        
        print("="*40)
