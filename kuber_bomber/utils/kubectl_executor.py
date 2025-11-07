"""
Executor Centralizado de Kubectl
===============================

Executor centralizado para comandos kubectl que funciona tanto em modo local
quanto remoto (AWS) via SSH.
"""

import subprocess
from typing import Dict, List, Optional, Any


class KubectlExecutor:
    """
    Executor centralizado para comandos kubectl.
    
    Gerencia execução de comandos kubectl tanto localmente (com --context)
    quanto remotamente via SSH para AWS.
    """
    
    def __init__(self, aws_config: Optional[dict] = None):
        """
        Inicializa o executor.
        
        Args:
            aws_config: Configuração AWS para conexão remota
        """
        self.aws_config = aws_config
        self.is_aws_mode = aws_config is not None
        
        # Importar config aqui para evitar imports circulares
        from .config import get_config
        self.config = get_config(aws_mode=self.is_aws_mode)
    
    def execute_kubectl(self, args: List[str]) -> Dict[str, Any]:
        """
        Executa comando kubectl.
        
        Args:
            args: Argumentos do comando kubectl
            
        Returns:
            Dict com success, output, error
        """
        if self.is_aws_mode and self.aws_config:
            result = self._execute_kubectl_remote(args)
        else:
            result = self._execute_kubectl_local(args)
        
        # Padronizar formato de retorno
        return {
            'success': result['returncode'] == 0,
            'output': result['stdout'],
            'error': result['stderr']
        }
    
    def _execute_kubectl_remote(self, args: List[str]) -> Dict[str, Any]:
        """Executa kubectl via SSH (modo AWS)."""
        if not self.aws_config:
            return {'returncode': 1, 'stdout': '', 'stderr': 'AWS config not available'}
            
        kubectl_cmd = ['sudo', 'kubectl'] + args
        
        # Usar configuração SSH do aws_config
        ssh_key = self.aws_config.get('ssh_key', '~/.ssh/vockey.pem')
        ssh_user = self.aws_config.get('ssh_user', 'ubuntu')
        ssh_host = self.aws_config.get('ssh_host')
        
        ssh_cmd = [
            'ssh', '-i', ssh_key,
            '-o', 'StrictHostKeyChecking=no',
            f"{ssh_user}@{ssh_host}"
        ] + [' '.join(kubectl_cmd)]
        
        result = subprocess.run(ssh_cmd, capture_output=True, text=True)
        
        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
    
    def _execute_kubectl_local(self, args: List[str]) -> Dict[str, Any]:
        """Executa kubectl localmente com contexto."""
        kubectl_cmd = ['kubectl'] + args + ['--context', self.config.context]
        
        try:
            result = subprocess.run(kubectl_cmd, capture_output=True, text=True, check=True)
            return {
                'returncode': 0,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        except subprocess.CalledProcessError as e:
            return {
                'returncode': e.returncode,
                'stdout': e.stdout if e.stdout else "",
                'stderr': e.stderr if e.stderr else str(e)
            }
    
    def get_pods(self) -> List[str]:
        """
        Obtém lista de pods usando aplicações configuradas.
        
        Returns:
            Lista de nomes de pods
        """
        if self.is_aws_mode and self.aws_config:
            # Modo AWS - buscar pods por nome contendo as aplicações
            # Primeiro buscar todos os pods e depois filtrar por nome
            result = self.execute_kubectl(['get', 'pods', '-o', 'name'])
            if not result['success']:
                return []
            
            # Filtrar pods que contenham os nomes das aplicações conhecidas
            all_pods = result['output'].strip().split('\n')
            app_names = ['bar-app', 'foo-app', 'test-app']
            pods = []
            
            for pod_line in all_pods:
                if pod_line.startswith('pod/'):
                    pod_name = pod_line.replace('pod/', '')
                    # Verificar se o pod pertence a alguma aplicação conhecida
                    if any(app in pod_name for app in app_names):
                        pods.append(pod_name)
            
            return pods
        else:
            # Modo local
            result = self.execute_kubectl([
                'get', 'pods', '-l', 'app in (foo,bar,test)', 
                '-o', 'jsonpath={.items[*].metadata.name}'
            ])
            
            if not result['success']:
                return []
            
            pods = result['output'].strip().split()
            return [pod for pod in pods if pod]  # Filtrar strings vazias
    
    def get_nodes(self) -> List[str]:
        """
        Obtém lista de nós.
        
        Returns:
            Lista de nomes de nós
        """
        result = self.execute_kubectl(['get', 'nodes', '-o', 'jsonpath={.items[*].metadata.name}'])
        
        if not result['success']:
            return []
        
        nodes = result['output'].strip().split()
        return [node for node in nodes if node]
    
    def get_services(self) -> List[str]:
        """
        Obtém lista de serviços.
        
        Returns:
            Lista de nomes de serviços
        """
        result = self.execute_kubectl(['get', 'services', '-o', 'jsonpath={.items[*].metadata.name}'])
        
        if not result['success']:
            return []
        
        services = result['output'].strip().split()
        return [service for service in services if service]


def get_kubectl_executor(aws_config: Optional[dict] = None) -> KubectlExecutor:
    """
    Factory function para criar uma instância do KubectlExecutor.
    
    Args:
        aws_config: Configuração AWS opcional
        
    Returns:
        Instância configurada do KubectlExecutor
    """
    return KubectlExecutor(aws_config)