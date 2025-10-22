"""
Injetor de Falhas em Pods
========================

Módulo para injeção de falhas em pods do Kubernetes.
"""

import subprocess
from typing import Tuple
from ..utils.config import get_config


class PodFailureInjector:
    """
    Injetor de falhas para pods Kubernetes.
    
    Implementa diferentes métodos de falha em pods como kill de processos,
    delete de pods, etc.
    """
    
    def __init__(self):
        """Inicializa o injetor de falhas em pods."""
        self.config = get_config()
    
    def kill_all_processes(self, target: str) -> Tuple[bool, str]:
        """
        Mata todos os processos em um pod.
        
        Args:
            target: Nome do pod alvo
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"kubectl exec {target} --context={self.config.context} -- sh -c 'kill -9 -1'"
        print(f"💀 Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'exec', target, '--context', self.config.context, '--', 
                'sh', '-c', 'kill -9 -1'
            ], capture_output=True, text=True)
            
            print(f"✅ Comando executado no pod {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def kill_init_process(self, target: str) -> Tuple[bool, str]:
        """
        Mata o processo init (PID 1) do container.
        
        Args:
            target: Nome do pod alvo
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"kubectl exec {target} --context={self.config.context} -- kill -9 1"
        print(f"🔌 Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'exec', target, '--context', self.config.context, '--', 
                'kill', '-9', '1'
            ], capture_output=True, text=True)
            
            print(f"✅ Comando executado no pod {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def delete_pod(self, target: str) -> Tuple[bool, str]:
        """
        Deleta um pod (será recriado pelo ReplicaSet).
        
        Args:
            target: Nome do pod alvo
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"kubectl delete pod {target} --context={self.config.context}"
        print(f"🗑️ Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'delete', 'pod', target, '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Pod {target} deletado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def restart_pod(self, target: str) -> Tuple[bool, str]:
        """
        Reinicia um pod forçando sua recriação.
        
        Args:
            target: Nome do pod alvo
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        # Obter o nome do deployment
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pod', target, '--context', self.config.context,
                '-o', 'jsonpath={.metadata.ownerReferences[0].name}'
            ], capture_output=True, text=True, check=True)
            
            owner_name = result.stdout.strip()
            
            # Fazer rollout restart
            command = f"kubectl rollout restart deployment/{owner_name} --context={self.config.context}"
            print(f"🔄 Executando: {command}")
            
            result = subprocess.run([
                'kubectl', 'rollout', 'restart', f'deployment/{owner_name}', 
                '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Rollout restart executado para deployment {owner_name}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            # Fallback para delete pod
            return self.delete_pod(target)
    
    def corrupt_pod_filesystem(self, target: str) -> Tuple[bool, str]:
        """
        Corrompe o sistema de arquivos do pod removendo arquivos críticos.
        
        Args:
            target: Nome do pod alvo
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"kubectl exec {target} --context={self.config.context} -- sh -c 'rm -rf /tmp/* /var/tmp/*'"
        print(f"💣 Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'exec', target, '--context', self.config.context, '--', 
                'sh', '-c', 'rm -rf /tmp/* /var/tmp/*'
            ], capture_output=True, text=True)
            
            print(f"✅ Comando de corrupção executado no pod {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def simulate_memory_pressure(self, target: str) -> Tuple[bool, str]:
        """
        Simula pressão de memória no pod.
        
        Args:
            target: Nome do pod alvo
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"kubectl exec {target} --context={self.config.context} -- sh -c 'dd if=/dev/zero of=/dev/null bs=1M count=1000 &'"
        print(f"🧠 Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'exec', target, '--context', self.config.context, '--', 
                'sh', '-c', 'dd if=/dev/zero of=/dev/null bs=1M count=1000 &'
            ], capture_output=True, text=True)
            
            print(f"✅ Pressão de memória simulada no pod {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command