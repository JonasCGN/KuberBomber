"""
Injetor de Falhas em Nós
=======================

Módulo para injeção de falhas em nós do Kubernetes (worker nodes e control plane).
"""

import subprocess
from typing import Tuple, Optional
from ..utils.config import get_config


class NodeFailureInjector:
    """
    Injetor de falhas para nós Kubernetes.
    
    Implementa métodos de falha em worker nodes e control plane,
    especialmente para ambientes Kind (Docker).
    """
    
    def __init__(self):
        """Inicializa o injetor de falhas em nós."""
        self.config = get_config()
    
    def kill_worker_node_processes(self, target: str) -> Tuple[bool, str]:
        """
        Mata todos os processos de um worker node (via docker restart em Kind).
        
        Args:
            target: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker restart {target}"
        print(f"🔄 Executando: {command}")
        print(f"🖥️ Matando todos os processos do worker node {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'restart', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Todos os processos do worker node {target} foram mortos e reiniciados")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def kill_control_plane_processes(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mata todos os processos do control plane (via docker restart em Kind).
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        if target is None:
            from kuber_bomber.monitoring.system_monitor import SystemMonitor
            monitor = SystemMonitor()
            target = monitor.get_control_plane_node()
            if not target:
                return False, "Não foi possível descobrir control plane automaticamente"
                
        command = f"docker restart {target}"
        print(f"💀 Executando: {command}")
        print(f"🎛️ Matando todos os processos do control plane {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'restart', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Todos os processos do control plane {target} foram mortos e reiniciados")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def stop_worker_node(self, target: str) -> Tuple[bool, str]:
        """
        Para completamente um worker node.
        
        Args:
            target: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker stop {target}"
        print(f"⛔ Executando: {command}")
        print(f"🖥️ Parando worker node {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'stop', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Worker node {target} parado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def start_worker_node(self, target: str) -> Tuple[bool, str]:
        """
        Inicia um worker node parado.
        
        Args:
            target: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker start {target}"
        print(f"▶️ Executando: {command}")
        print(f"🖥️ Iniciando worker node {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'start', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Worker node {target} iniciado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def pause_worker_node(self, target: str) -> Tuple[bool, str]:
        """
        Pausa um worker node (congela processos).
        
        Args:
            target: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker pause {target}"
        print(f"⏸️ Executando: {command}")
        print(f"🖥️ Pausando worker node {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'pause', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Worker node {target} pausado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def unpause_worker_node(self, target: str) -> Tuple[bool, str]:
        """
        Despausa um worker node.
        
        Args:
            target: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker unpause {target}"
        print(f"▶️ Executando: {command}")
        print(f"🖥️ Despausando worker node {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'unpause', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Worker node {target} despausado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def simulate_network_partition(self, target: str) -> Tuple[bool, str]:
        """
        Simula partição de rede no nó.
        
        Args:
            target: Nome do nó
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        # Bloquear tráfego de rede para simular partição
        command = f"docker exec {target} iptables -A INPUT -j DROP"
        print(f"🌐 Executando: {command}")
        print(f"🔌 Simulando partição de rede no nó {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'exec', target, 'iptables', '-A', 'INPUT', '-j', 'DROP'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Partição de rede simulada no nó {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def restore_network(self, target: str) -> Tuple[bool, str]:
        """
        Restaura conectividade de rede do nó.
        
        Args:
            target: Nome do nó
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker exec {target} iptables -F"
        print(f"🌐 Executando: {command}")
        print(f"🔌 Restaurando conectividade de rede no nó {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'exec', target, 'iptables', '-F'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Conectividade de rede restaurada no nó {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command

    def shutdown_worker_node(self, target: str) -> Tuple[bool, str]:
        """
        Desliga completamente um worker node (docker stop).
        
        Args:
            target: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker stop {target}"
        print(f"⛔ Executando: {command}")
        print(f"🖥️ Desligando worker node {target} completamente...")
        
        try:
            result = subprocess.run([
                'docker', 'stop', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Worker node {target} desligado completamente")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao desligar {target}: {e}")
            return False, command

    def start_worker_node(self, target: str) -> Tuple[bool, str]:
        """
        Liga um worker node desligado (docker start).
        
        Args:
            target: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker start {target}"
        print(f"▶️ Executando: {command}")
        print(f"🖥️ Ligando worker node {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'start', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Worker node {target} ligado com sucesso")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao ligar {target}: {e}")
            return False, command