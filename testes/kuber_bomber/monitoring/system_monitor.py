"""
Monitor de Sistema
=================

Módulo para monitoramento de componentes do sistema Kubernetes.
"""

import subprocess
from typing import List, Optional
from ..utils.config import get_config


class SystemMonitor:
    """
    Monitor de sistema para componentes Kubernetes.
    
    Monitora pods, nós e outros recursos do sistema.
    """
    
    def __init__(self):
        """Inicializa o monitor de sistema."""
        self.config = get_config()
    
    def get_pods(self) -> List[str]:
        """
        Obtém lista de pods das aplicações.
        
        Returns:
            Lista com nomes dos pods encontrados
        """
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pods', '-l', 'app in (foo,bar,test)', 
                '-o', 'jsonpath={.items[*].metadata.name}', '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            pods = result.stdout.strip().split()
            pods = [pod for pod in pods if pod]  # Filtrar strings vazias
            print(f"📋 Pods encontrados: {pods}")
            return pods
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter pods: {e}")
            return []
    
    def get_worker_nodes(self) -> List[str]:
        """
        Obtém lista de worker nodes.
        
        Returns:
            Lista com nomes dos worker nodes
        """
        try:
            result = subprocess.run([
                'kubectl', 'get', 'nodes', '-l', '!node-role.kubernetes.io/control-plane',
                '-o', 'jsonpath={.items[*].metadata.name}', '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            nodes = result.stdout.strip().split()
            nodes = [node for node in nodes if node]  # Filtrar strings vazias
            return nodes
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter worker nodes: {e}")
            return []
    
    def show_pod_status(self, highlight_pod: Optional[str] = None):
        """
        Mostra status dos pods com kubectl get pods.
        
        Args:
            highlight_pod: Pod específico para destacar (opcional)
        """
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pods', '--context', self.config.context, '-o', 'wide'
            ], capture_output=True, text=True, check=True)
            
            print("📋 === STATUS DOS PODS ===")
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if highlight_pod and highlight_pod in line:
                    print(f"🎯 {line}")  # Destacar o pod alvo
                else:
                    print(f"   {line}")
            print()
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter status dos pods: {e}")
    
    def show_node_status(self):
        """Mostra status dos nós."""
        try:
            result = subprocess.run([
                'kubectl', 'get', 'nodes', '--context', self.config.context, '-o', 'wide'
            ], capture_output=True, text=True, check=True)
            
            print("🖥️ === STATUS DOS NÓS ===")
            lines = result.stdout.strip().split('\n')
            for line in lines:
                print(f"   {line}")
            print()
            
        except subprocess.CalledProcessError as e:
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
            result = subprocess.run([
                'kubectl', 'logs', pod_name, '--context', self.config.context, 
                '--tail', str(lines)
            ], capture_output=True, text=True, check=True)
            
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter logs do pod {pod_name}: {e}")
            return ""
    
    def describe_pod(self, pod_name: str) -> str:
        """
        Obtém descrição detalhada de um pod.
        
        Args:
            pod_name: Nome do pod
            
        Returns:
            Descrição do pod
        """
        try:
            result = subprocess.run([
                'kubectl', 'describe', 'pod', pod_name, '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao descrever pod {pod_name}: {e}")
            return ""
    
    def get_control_plane_node(self) -> str:
        """
        Obtém o nome do nó control plane.
        
        Returns:
            Nome do nó control plane ou string padrão
        """
        try:
            result = subprocess.run([
                'kubectl', 'get', 'nodes', '-l', 'node-role.kubernetes.io/control-plane',
                '-o', 'jsonpath={.items[0].metadata.name}', '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            control_plane = result.stdout.strip()
            return control_plane if control_plane else "local-k8s-control-plane"
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter control plane: {e}")
            return "local-k8s-control-plane"  # Fallback para Kind
    
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
            result = subprocess.run([
                'kubectl', 'cluster-info', '--context', self.config.context
            ], capture_output=True, text=True, timeout=10)
            
            health_status['cluster_accessible'] = result.returncode == 0
            
            if health_status['cluster_accessible']:
                # Verificar nós
                result = subprocess.run([
                    'kubectl', 'get', 'nodes', '--context', self.config.context,
                    '--no-headers'
                ], capture_output=True, text=True, check=True)
                
                node_lines = result.stdout.strip().split('\n')
                health_status['total_nodes'] = len([line for line in node_lines if line])
                
                ready_nodes = 0
                for line in node_lines:
                    if 'Ready' in line and 'NotReady' not in line:
                        ready_nodes += 1
                        if 'control-plane' in line or 'master' in line:
                            health_status['control_plane_ready'] = True
                
                health_status['worker_nodes_ready'] = ready_nodes
                
                # Verificar pods
                result = subprocess.run([
                    'kubectl', 'get', 'pods', '--all-namespaces', '--context', self.config.context,
                    '--no-headers'
                ], capture_output=True, text=True, check=True)
                
                pod_lines = result.stdout.strip().split('\n')
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