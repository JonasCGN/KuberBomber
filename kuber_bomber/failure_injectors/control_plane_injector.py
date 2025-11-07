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
from typing import Tuple, Optional
from ..utils.config import get_config
from ..utils.kubectl_executor import KubectlExecutor
from ..monitoring.system_monitor import SystemMonitor


class ControlPlaneInjector:
    """
    Injetor de falhas para componentes do Control Plane.
    
    Implementa métodos de falha para os componentes críticos:
    - API Server
    - Controller Manager
    - Scheduler
    - etcd
    """
    
    def __init__(self, aws_config: Optional[dict] = None):
        """Inicializa o injetor de falhas do control plane."""
        self.aws_config = aws_config
        self.is_aws_mode = aws_config is not None
        self.config = get_config(aws_mode=self.is_aws_mode)
        self.kubectl = KubectlExecutor(aws_config=aws_config if self.is_aws_mode else None)
        self.system_monitor = SystemMonitor(aws_config=aws_config)
    
    def _get_control_plane_target(self, target: Optional[str] = None) -> str:
        """
        Obtém o nome do control plane automaticamente ou usa o fornecido.
        
        Args:
            target: Nome específico do control plane (opcional)
            
        Returns:
            Nome do control plane a ser usado
        """
        if target:
            return target
        
        # Descobrir automaticamente
        discovered_cp = self.system_monitor.get_control_plane_node()
        if discovered_cp:
            return discovered_cp
        
        raise ValueError("Nenhum control plane foi descoberto automaticamente. Especifique manualmente com target='nome-do-node'")
    
    def kill_kube_apiserver(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mata o processo kube-apiserver (static pod reinicia automaticamente).
        
        Args:
            target: Nome do nó control plane (opcional - será descoberto automaticamente)
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        # Descobrir target automaticamente se não fornecido
        actual_target = self._get_control_plane_target(target)
        
        command = f"docker exec {actual_target} pkill -9 -f kube-apiserver"
        print(f"🎯 Executando: {command}")
        print(f"⚡ Matando kube-apiserver no {actual_target}...")
        
        try:
            # Usar docker exec para Kind com -f para match full command line
            result = subprocess.run([
                'docker', 'exec', actual_target, 'pkill', '-9', '-f', 'kube-apiserver'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ kube-apiserver morto (static pod irá reiniciar)")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Processo finalizado: {e}")
            return True, command  # Sucesso mesmo com erro (processo morreu)
    
    def kill_kube_controller_manager(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mata o processo kube-controller-manager (static pod reinicia automaticamente).
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        if target is None:
            target = self._get_control_plane_target()
            if not target:
                return False, "Não foi possível descobrir control plane automaticamente"
                
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
    
    def kill_kube_scheduler(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mata o processo kube-scheduler (static pod reinicia automaticamente).
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        if target is None:
            target = self._get_control_plane_target()
            if not target:
                return False, "Não foi possível descobrir control plane automaticamente"
                
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
    
    def kill_etcd(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mata o processo etcd (static pod reinicia automaticamente).
        CUIDADO: Cluster ficará "mudo" temporariamente.
        
        Args:
            target: Nome do nó control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        if target is None:
            target = self._get_control_plane_target()
            if not target:
                return False, "Não foi possível descobrir control plane automaticamente"
                
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
    
    def kill_kubelet(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mata o processo kubelet em um nó (reinicia automaticamente em Kind).
        
        Args:
            target: Nome do nó (worker ou control plane)
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        if target is None:
            # Para kubelet, podemos usar qualquer nó (worker ou control plane)
            target = self._get_control_plane_target()
            if not target:
                # Se não achou control plane, tentar worker node
                from kuber_bomber.monitoring.system_monitor import SystemMonitor
                monitor = SystemMonitor()
                worker_nodes = monitor.get_worker_nodes()
                if worker_nodes:
                    target = worker_nodes[0]
                else:
                    return False, "Não foi possível descobrir nó para kubelet automaticamente"
                    
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
                result = self.kubectl.execute_kubectl([
                    'delete', 'pod', '-n', 'kube-system',
                    '-l', 'k8s-app=kube-proxy',
                    '--field-selector', f'spec.nodeName={target}',
                    '--force',  # Forçar remoção
                    '--grace-period=0',  # Sem período de espera
                    '--timeout=15s'  # Timeout mais curto
                ])
            else:
                result = self.kubectl.execute_kubectl([
                    'delete', 'pod', '-n', 'kube-system',
                    '-l', 'k8s-app=kube-proxy',
                    '--force',  # Forçar remoção
                    '--grace-period=0',  # Sem período de espera
                    '--timeout=15s'  # Timeout mais curto
                ])
            
            # Verificar se houve erro no comando
            if not result['success']:
                print(f"⚠️ Comando falhou")
                print(f"   Error: {result.get('error', 'Unknown error')}")
                # Mesmo com erro, pode ter funcionado (ex: pod não encontrado ou já em terminating)
                error_msg = result.get('error', '').lower()
                if any(msg in error_msg for msg in ["not found", "terminating", "being deleted"]):
                    print(f"ℹ️ Pod kube-proxy já está sendo removido ou não encontrado")
                    return True, command
                return False, command
            
            print(f"✅ kube-proxy pod(s) deletado(s) (DaemonSet irá recriar)")
            return True, command
            
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
            # Verificar se é erro comum que pode ser ignorado
            error_msg = str(e).lower()
            if any(msg in error_msg for msg in ["not found", "terminating", "being deleted"]):
                print(f"ℹ️ Erro ignorável - pod provavelmente já sendo removido")
                return True, command
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
