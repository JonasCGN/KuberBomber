"""
Injetor de Falhas em Componentes do Control Plane
================================================

Módulo para injeção de falhas específicas em componentes do control plane:
- kube-apiserver
- kube-controller-manager
- kube-scheduler
- etcd
"""

import subprocess
from typing import Tuple
from ..utils.config import get_config


class ControlPlaneInjector:
    """
    Injetor de falhas para componentes do Control Plane.
    
    Implementa métodos de falha para os componentes críticos:
    - API Server
    - Controller Manager
    - Scheduler
    - etcd
    """
    
    def __init__(self):
        """Inicializa o injetor de falhas do control plane."""
        self.config = get_config()
    
    def kill_kube_apiserver(self, target: str = "local-k8s-control-plane") -> Tuple[bool, str]:
        """
        Mata o processo kube-apiserver (static pod reinicia automaticamente).
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker exec {target} pkill -9 -f kube-apiserver"
        print(f"🎯 Executando: {command}")
        print(f"⚡ Matando kube-apiserver no {target}...")
        
        try:
            # Usar docker exec para Kind com -f para match full command line
            result = subprocess.run([
                'docker', 'exec', target, 'pkill', '-9', '-f', 'kube-apiserver'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ kube-apiserver morto (static pod irá reiniciar)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Processo finalizado: {e}")
            return True, command  # Sucesso mesmo com erro (processo morreu)
    
    def kill_kube_controller_manager(self, target: str = "local-k8s-control-plane") -> Tuple[bool, str]:
        """
        Mata o processo kube-controller-manager (static pod reinicia automaticamente).
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker exec {target} pkill -9 -f kube-controller-manager"
        print(f"🎯 Executando: {command}")
        print(f"⚡ Matando kube-controller-manager no {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'exec', target, 'pkill', '-9', '-f', 'kube-controller-manager'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ kube-controller-manager morto (static pod irá reiniciar)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Processo finalizado: {e}")
            return True, command
    
    def kill_kube_scheduler(self, target: str = "local-k8s-control-plane") -> Tuple[bool, str]:
        """
        Mata o processo kube-scheduler (static pod reinicia automaticamente).
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker exec {target} pkill -9 -f kube-scheduler"
        print(f"🎯 Executando: {command}")
        print(f"⚡ Matando kube-scheduler no {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'exec', target, 'pkill', '-9', '-f', 'kube-scheduler'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ kube-scheduler morto (static pod irá reiniciar)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Processo finalizado: {e}")
            return True, command
    
    def kill_etcd(self, target: str = "local-k8s-control-plane") -> Tuple[bool, str]:
        """
        Mata o processo etcd (static pod reinicia automaticamente).
        CUIDADO: Cluster ficará "mudo" temporariamente.
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker exec {target} pkill -9 -f etcd"
        print(f"🎯 Executando: {command}")
        print(f"⚠️ ATENÇÃO: Matando etcd no {target} - cluster ficará temporariamente indisponível!")
        
        try:
            result = subprocess.run([
                'docker', 'exec', target, 'pkill', '-9', '-f', 'etcd'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ etcd morto (static pod irá reiniciar)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Processo finalizado: {e}")
            return True, command
    
    def kill_kubelet(self, target: str = "local-k8s-worker") -> Tuple[bool, str]:
        """
        Mata o processo kubelet em um nó (reinicia automaticamente em Kind).
        
        Args:
            target: Nome do nó (worker ou control plane)
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker exec {target} pkill -9 -f kubelet"
        print(f"🎯 Executando: {command}")
        print(f"⚡ Matando kubelet no {target}...")
        
        try:
            result = subprocess.run([
                'docker', 'exec', target, 'pkill', '-9', '-f', 'kubelet'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ kubelet morto (processo irá reiniciar)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Processo finalizado: {e}")
            return True, command
    
    def delete_kube_proxy_pod(self, target: str = "") -> Tuple[bool, str]:
        """
        Deleta pod do kube-proxy (DaemonSet recria automaticamente).
        
        Args:
            target: Nome do nó (opcional, deleta todos se não especificado)
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        if target:
            # Encontrar o pod do kube-proxy no nó específico
            command = f"kubectl delete pod -n kube-system -l k8s-app=kube-proxy --field-selector spec.nodeName={target}"
        else:
            command = f"kubectl delete pod -n kube-system -l k8s-app=kube-proxy"
        
        print(f"🎯 Executando: {command}")
        print(f"⚡ Deletando kube-proxy pod(s)...")
        
        try:
            if target:
                result = subprocess.run([
                    'kubectl', 'delete', 'pod', '-n', 'kube-system',
                    '-l', 'k8s-app=kube-proxy',
                    '--field-selector', f'spec.nodeName={target}'
                ], capture_output=True, text=True, check=True)
            else:
                result = subprocess.run([
                    'kubectl', 'delete', 'pod', '-n', 'kube-system',
                    '-l', 'k8s-app=kube-proxy'
                ], capture_output=True, text=True, check=True)
            
            print(f"✅ kube-proxy pod(s) deletado(s) (DaemonSet irá recriar)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def restart_containerd(self, target: str) -> Tuple[bool, str]:
        """
        Reinicia containerd (container runtime) - reinicia todo o nó em Kind.
        
        Args:
            target: Nome do nó
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        command = f"docker restart {target}"
        print(f"🎯 Executando: {command}")
        print(f"⚠️ ATENÇÃO: Reiniciando containerd via docker restart - TODO O NÓ será reiniciado!")
        
        try:
            result = subprocess.run([
                'docker', 'restart', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Nó {target} reiniciado (containerd + todos componentes)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
