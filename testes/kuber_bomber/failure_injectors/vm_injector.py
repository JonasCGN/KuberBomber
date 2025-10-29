"""
VM Failure Injector para simular falhas de VM/container de worker nodes.
Permite desligar e religar VMs de worker nodes para medir MTTR real.
"""

import subprocess
import time
import logging
import random
from typing import List, Optional, Dict
try:
    import docker
except ImportError:
    print("Docker library not found. Install with: pip install docker")
    docker = None


class VmFailureInjector:
    """Injector para falhas de VM/container de worker nodes."""
    
    def __init__(self, cluster_name: str = "local-k8s"):
        self.cluster_name = cluster_name
        if docker is None:
            raise ImportError("Docker library required. Install with: pip install docker")
        self.docker_client = docker.from_env()
        self.logger = logging.getLogger(__name__)
        
        # Mapear worker nodes para containers
        self.worker_containers = self._discover_worker_containers()
    
    def _select_random_target(self, targets: List[str]) -> str:
        """Seleciona um alvo aleatório da lista."""
        return random.choice(targets)
    
    def _discover_worker_containers(self) -> Dict[str, str]:
        """Descobre containers dos worker nodes do cluster."""
        containers = {}
        try:
            # Listar containers do kind cluster
            all_containers = self.docker_client.containers.list(all=True)
            
            for container in all_containers:
                container_name = container.name
                # Identificar worker nodes do kind
                if (self.cluster_name in container_name and 
                    'worker' in container_name and
                    'control-plane' not in container_name):
                    
                    # Extrair nome do node (ex: local-k8s-worker -> local-k8s-worker)
                    node_name = container_name
                    containers[node_name] = container.id
                    
                    self.logger.info(f"Descoberto worker node: {node_name} -> {container.id[:12]}")
            
            if not containers:
                self.logger.warning(f"Nenhum worker node encontrado para cluster {self.cluster_name}")
            
            return containers
            
        except Exception as e:
            self.logger.error(f"Erro ao descobrir worker containers: {e}")
            return {}
    
    def get_worker_nodes(self) -> List[str]:
        """Retorna lista de worker nodes disponíveis."""
        return list(self.worker_containers.keys())
    
    def shutdown_worker_node(self, node_name: Optional[str] = None) -> Dict:
        """
        Desliga um worker node (para a VM/container).
        
        Args:
            node_name: Nome do worker node. Se None, escolhe aleatoriamente.
            
        Returns:
            Dict com informações da falha injetada.
        """
        if not node_name:
            available_nodes = self.get_worker_nodes()
            if not available_nodes:
                raise RuntimeError("Nenhum worker node disponível para shutdown")
            node_name = self._select_random_target(available_nodes)
        
        if node_name not in self.worker_containers:
            raise ValueError(f"Worker node {node_name} não encontrado")
        
        container_id = self.worker_containers[node_name]
        
        try:
            # Parar o container do worker node
            container = self.docker_client.containers.get(container_id)
            
            self.logger.info(f"Desligando worker node: {node_name} (container: {container_id[:12]})")
            
            start_time = time.time()
            container.stop(timeout=10)  # Forçar parada após 10s
            
            # Verificar se realmente parou
            container.reload()
            if container.status != 'exited':
                self.logger.warning(f"Container {node_name} não parou completamente")
            
            failure_info = {
                'failure_type': 'shutdown_worker_node',
                'target': node_name,
                'container_id': container_id,
                'timestamp': start_time,
                'duration': time.time() - start_time,
                'status': 'injected',
                'method': 'docker_stop'
            }
            
            self.logger.info(f"Worker node {node_name} desligado com sucesso")
            return failure_info
            
        except Exception as e:
            self.logger.error(f"Erro ao desligar worker node {node_name}: {e}")
            raise RuntimeError(f"Falha ao injetar shutdown em {node_name}: {e}")
    
    def startup_worker_node(self, node_name: str) -> Dict:
        """
        Liga um worker node (inicia a VM/container).
        
        Args:
            node_name: Nome do worker node para religar.
            
        Returns:
            Dict com informações da recuperação.
        """
        if node_name not in self.worker_containers:
            raise ValueError(f"Worker node {node_name} não encontrado")
        
        container_id = self.worker_containers[node_name]
        
        try:
            container = self.docker_client.containers.get(container_id)
            
            self.logger.info(f"Religando worker node: {node_name} (container: {container_id[:12]})")
            
            start_time = time.time()
            container.start()
            
            # Aguardar container ficar pronto
            self._wait_for_container_ready(container, timeout=120)
            
            recovery_info = {
                'recovery_type': 'startup_worker_node',
                'target': node_name,
                'container_id': container_id,
                'timestamp': start_time,
                'duration': time.time() - start_time,
                'status': 'recovered',
                'method': 'docker_start'
            }
            
            self.logger.info(f"Worker node {node_name} religado com sucesso")
            return recovery_info
            
        except Exception as e:
            self.logger.error(f"Erro ao religar worker node {node_name}: {e}")
            raise RuntimeError(f"Falha ao religar {node_name}: {e}")
    
    def _wait_for_container_ready(self, container, timeout: int = 120):
        """Aguarda container ficar pronto para receber conexões."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                container.reload()
                if container.status == 'running':
                    # Aguardar um pouco mais para serviços internos subirem
                    time.sleep(5)
                    
                    # Verificar se kubelet está respondendo
                    if self._check_kubelet_health(container):
                        return True
                        
                time.sleep(2)
                
            except Exception as e:
                self.logger.warning(f"Erro verificando container: {e}")
                time.sleep(2)
        
        raise TimeoutError(f"Container não ficou pronto em {timeout}s")
    
    def _check_kubelet_health(self, container) -> bool:
        """Verifica se kubelet está respondendo no container."""
        try:
            # Verificar se processo kubelet está rodando
            exec_result = container.exec_run(
                "pgrep kubelet",
                stdout=True,
                stderr=True
            )
            
            return exec_result.exit_code == 0
            
        except Exception as e:
            self.logger.warning(f"Erro verificando kubelet: {e}")
            return False
    
    def get_node_status(self, node_name: str) -> Dict:
        """Retorna status atual de um worker node."""
        if node_name not in self.worker_containers:
            return {'status': 'unknown', 'error': 'Node not found'}
        
        container_id = self.worker_containers[node_name]
        
        try:
            container = self.docker_client.containers.get(container_id)
            container.reload()
            
            return {
                'node_name': node_name,
                'container_id': container_id,
                'container_status': container.status,
                'container_running': container.status == 'running',
                'created': container.attrs.get('Created'),
                'started_at': container.attrs.get('State', {}).get('StartedAt'),
                'finished_at': container.attrs.get('State', {}).get('FinishedAt')
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'node_name': node_name,
                'container_id': container_id
            }
    
    def list_worker_nodes_status(self) -> List[Dict]:
        """Lista status de todos os worker nodes."""
        return [self.get_node_status(node) for node in self.get_worker_nodes()]
    
    def force_kill_worker_node(self, node_name: str) -> Dict:
        """
        Força a parada de um worker node (equivalente a puxar cabo de energia).
        
        Args:
            node_name: Nome do worker node.
            
        Returns:
            Dict com informações da falha.
        """
        if node_name not in self.worker_containers:
            raise ValueError(f"Worker node {node_name} não encontrado")
        
        container_id = self.worker_containers[node_name]
        
        try:
            container = self.docker_client.containers.get(container_id)
            
            self.logger.info(f"Forçando parada do worker node: {node_name}")
            
            start_time = time.time()
            container.kill()  # SIGKILL - parada forçada
            
            failure_info = {
                'failure_type': 'force_kill_worker_node',
                'target': node_name,
                'container_id': container_id,
                'timestamp': start_time,
                'duration': time.time() - start_time,
                'status': 'injected',
                'method': 'docker_kill'
            }
            
            self.logger.info(f"Worker node {node_name} forçadamente parado")
            return failure_info
            
        except Exception as e:
            self.logger.error(f"Erro ao forçar parada de {node_name}: {e}")
            raise RuntimeError(f"Falha ao forçar parada de {node_name}: {e}")


if __name__ == "__main__":
    # Teste do injector
    logging.basicConfig(level=logging.INFO)
    
    injector = VmFailureInjector()
    
    print("Worker nodes disponíveis:")
    for node in injector.get_worker_nodes():
        status = injector.get_node_status(node)
        print(f"  {node}: {status['container_status']}")
    
    # Teste de shutdown/startup (descomente para testar)
    # worker_node = injector.get_worker_nodes()[0] if injector.get_worker_nodes() else None
    # if worker_node:
    #     print(f"\nTestando shutdown/startup do {worker_node}...")
    #     
    #     # Shutdown
    #     shutdown_info = injector.shutdown_worker_node(worker_node)
    #     print(f"Shutdown: {shutdown_info}")
    #     
    #     time.sleep(10)  # Aguardar
    #     
    #     # Startup
    #     startup_info = injector.startup_worker_node(worker_node)
    #     print(f"Startup: {startup_info}")