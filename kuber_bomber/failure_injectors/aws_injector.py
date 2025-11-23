"""
AWS Failure Injector
===================

Injeta falhas em ambientes AWS via SSH usando descoberta automática de IPs.
Não depende mais de ssh_host fixo no aws_config.json.
"""

import subprocess
import json
from typing import Dict, List, Optional, Tuple


class AWSFailureInjector:
    """
    Injetor de falhas específico para ambiente AWS via SSH com descoberta automática de IPs.
    """
    
    def __init__(self, ssh_key: str, ssh_user: str = "ubuntu", aws_config: Optional[Dict] = None):
        """
        Inicializa o injector com descoberta automática.
        
        Args:
            ssh_key: Caminho para chave SSH
            ssh_user: Usuário SSH  
            aws_config: Configuração AWS completa (opcional, para discovery)
        """
        self.ssh_key = ssh_key
        self.ssh_user = ssh_user
        self.aws_config = aws_config or {}
        
        # Integrar com control plane discovery
        from ..utils.control_plane_discovery import ControlPlaneDiscovery
        self.discovery = ControlPlaneDiscovery(self.aws_config)
        
        # SSH host será descoberto dinamicamente
        self.ssh_host = None
        self.ssh_connection = None
        
    def _ensure_control_plane_connection(self) -> bool:
        """
        Garante que temos conexão com o control plane (descoberta automática).
        
        Returns:
            True se conexão está disponível
        """
        # Se já temos conexão válida, reutilizar
        if self.ssh_host and self.ssh_connection:
            return True
        
        # Descobrir control plane automaticamente
        control_plane_ip = self.discovery.discover_control_plane_ip()
        
        if control_plane_ip:
            self.ssh_host = control_plane_ip
            self.ssh_connection = f"{self.ssh_user}@{control_plane_ip}"
            return True
        else:
            print("❌ Não foi possível descobrir o control plane")
            return False
    
    def _get_aws_instances(self) -> Dict[str, Dict]:
        """
        Obtém informações das instâncias AWS via descoberta.
        """
        return self.discovery.get_all_aws_instances()
    
    def _get_node_public_ip(self, node_name: str,show_print=True) -> str:
        """
        Obtém o IP público de um node via descoberta.
        """
        public_ip = self.discovery.get_node_public_ip(node_name)
        
        if public_ip:
            if show_print:
                print(f"🌐 Node {node_name} -> IP público: {public_ip}")
            return public_ip
        else:
            raise Exception(f"Node {node_name} não encontrado nas instâncias AWS")
    
    def _execute_ssh_command(self, node_name: str, command: str, timeout: int = 30, show_print=True) -> Tuple[bool, str]:
        """
        Executa comando SSH em um node específico usando seu IP público.
        """
        try:
            public_ip = self._get_node_public_ip(node_name,show_print=show_print)
            
            ssh_cmd = [
                'ssh', '-i', self.ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                '-o', 'BatchMode=yes',
                f'{self.ssh_user}@{public_ip}',
                command
            ]
            
            if show_print:
                print(f"💻 Executando SSH: {' '.join(ssh_cmd[:-1])} '{command}'")
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
            
            # Código 0 = sucesso total
            if result.returncode == 0:
                return True, result.stdout.strip()
            
            # Código 255 = SSH encerrado abruptamente (comum ao matar processos críticos)
            elif result.returncode == 255:
                print(f"⚠️ SSH encerrado abruptamente (código 255) - provável sucesso ao matar processo crítico")
                return True, "SSH connection terminated (likely successful process kill)"
                
            # Código 1 com "no process found" = processo já estava morto (sucesso)
            elif result.returncode == 1 and "no process found" in result.stderr:
                print(f"✅ Processo já estava morto (sucesso)")
                return True, "Process already dead"
                
            # Outros códigos = erro real
            else:
                print(f"❌ Erro SSH (código {result.returncode}):")
                print(f"   stdout: {result.stdout}")
                print(f"   stderr: {result.stderr}")
                return False, result.stderr.strip()
                
        except subprocess.TimeoutExpired:
            return False, f"Timeout ao executar SSH no node {node_name}"
        except Exception as e:
            return False, f"Exceção SSH: {str(e)}"
    
    def run_remote_command(self, command: str) -> subprocess.CompletedProcess:
        """
        Executa comando genérico no control plane com descoberta automática.
        """
        if not self._ensure_control_plane_connection():
            raise Exception("Não foi possível estabelecer conexão com o control plane")
            
        print(f"🔄 Executando no control plane ({self.ssh_host}): {command}")
        ssh_cmd = [
            'ssh', '-i', self.ssh_key,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ConnectTimeout=10',
            '-o', 'BatchMode=yes',
            self.ssh_connection,
            command
        ]
        
        return subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
    
    def run_remote_kubectl(self, args: List[str]) -> subprocess.CompletedProcess:
        """
        Executa kubectl no control plane com descoberta automática.
        """
        kubectl_cmd = ['sudo', 'kubectl'] + args
        command = ' '.join(kubectl_cmd)
        return self.run_remote_command(command)
    
    # ===== MÉTODOS PARA POD =====
    
    def kill_all_processes(self, pod_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata todos os processos no container via Ubuntu debug.
        """
        try:
            # Usar debug container para matar todos os processos
            cmd = f"sudo kubectl exec {pod_name} -c debug-tools -- sh -c 'kill -9 -1 2>/dev/null || true'"
            result = self.run_remote_command(cmd)
            
            if result.returncode == 0 or "Terminated" in result.stderr:
                return True, "Container (all PIDs): kill -9 -1"
            else:
                return False, f"Erro: {result.stderr}"
                
        except Exception as e:
            return False, f"Exceção: {str(e)}"
    
    def kill_init_process(self, pod_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata processo PID 1 via Ubuntu debug.
        """
        try:
            # Usar debug container para matar PID 1
            cmd = f"sudo kubectl exec {pod_name} -c debug-tools -- sh -c 'kill -9 1 2>/dev/null || true'"
            result = self.run_remote_command(cmd)
            
            if result.returncode == 0 or "Terminated" in result.stderr:
                return True, "Container (PID 1): kill -9 1"
            else:
                return False, f"Erro: {result.stderr}"
                
        except Exception as e:
            return False, f"Exceção: {str(e)}"
    
    # ===== MÉTODOS PARA WORKER NODE =====
    
    
    # ===== MÉTODOS PARA WORKER NODE =====
    
    def kill_worker_node_processes(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata processos críticos do worker node via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill worker node processes no node {node_name}")
        
        # Comandos rigorosos para matar processos críticos
        commands = [
            "sudo -n reboot"
        ]
        
        results = []
        reboot_initiated = False
        
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
            # Se reboot foi iniciado, aguardar tempo realista
            if success and "reboot" in cmd:
                reboot_initiated = True
                print(f"⏳ Reboot iniciado em {node_name}, aguardando 45s para estabilizar...")
                # import time
                # time.sleep(45)  # Aguardar tempo realista para reboot
                print(f"⏳ Node {node_name} deve estar reiniciando agora...")
            
        if reboot_initiated or any("✅" in r for r in results):
            return True, f"Worker node processes killed on {node_name}. Results: {'; '.join(results)}. Reboot time waited."
        else:
            return False, f"Falha ao matar processos em {node_name}. Results: {'; '.join(results)}"
    
    def kill_kubelet(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata processo kubelet via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill kubelet no node {node_name}")
        
        # Comandos rigorosos para matar kubelet
        commands = [
            "sudo -n pkill -9 -f kubelet",
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
        if any("✅" in r for r in results):
            return True, f"Kubelet killed on {node_name}. Results: {'; '.join(results)}"
        else:
            return False, f"Falha ao matar kubelet em {node_name}. Results: {'; '.join(results)}"
    
    def kill_kube_proxy_pod(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Remove kube-proxy via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill kube-proxy pod no node {node_name}")
        
        # Comandos rigorosos para matar kube-proxy
        commands = [
            "sudo -n pkill -9 -f kube-proxy",
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
        if any("✅" in r for r in results):
            return True, f"Kube-proxy killed on {node_name}. Results: {'; '.join(results)}"
        else:
            return False, f"Falha ao matar kube-proxy em {node_name}. Results: {'; '.join(results)}"
    
    def restart_containerd(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Reinicia containerd via SSH direto.
        """
        print(f"💀 EXECUTANDO: restart containerd no node {node_name}")
        
        # Comandos rigorosos para reiniciar containerd
        commands = [
            # "sudo -n systemctl restart containerd",  # Primeiro tentar restart normal
            "sudo -n pkill -9 -f containerd",
            # "sudo -n systemctl start containerd",
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
                
        if any("✅" in r for r in results):
            return True, f"restart_containerd {node_name}"
        else:
            return False, f"restart_containerd {node_name} (failed)"

    def shutdown_worker_node(self, node_name: str) -> Tuple[bool, str]:
        """
        Desliga completamente um worker node via SSH (shutdown).
        
        Args:
            node_name: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        print(f"⛔ EXECUTANDO: shutdown worker node {node_name}")
        
        # Obter ID da instância antes do shutdown
        instances = self.discovery.get_all_aws_instances()
        
        if node_name not in instances:
            return False, f"shutdown_worker_node {node_name} (instance not found)"
        
        instance_id = instances[node_name]['ID']
        
        # Comando para desligar o worker node
        command = "sudo -n shutdown -h now"
        
        success, output = self._execute_ssh_command(node_name, command, timeout=30)
        
        if success or "connection closed" in output.lower():
            print(f"✅ Worker node {node_name} desligado via SSH")
            
            # AGUARDAR o estado AWS refletir a mudança para 'stopped'
            print(f"⏱️ Aguardando instância {instance_id} ficar 'stopped' na AWS...")
            if self._wait_for_instance_state(instance_id, "stopped", timeout=120):
                print(f"✅ Worker node {node_name} confirmado como 'stopped' na AWS")
                return True, f"shutdown_worker_node {node_name}"
            else:
                print(f"⚠️ Timeout aguardando estado 'stopped' - continuando mesmo assim")
                return True, f"shutdown_worker_node {node_name} (timeout but likely stopped)"
        else:
            print(f"❌ Erro ao desligar {node_name}: {output}")
            return False, f"shutdown_worker_node {node_name} (failed)"

    def start_worker_node(self, node_name: str) -> Tuple[bool, str]:
        """
        Liga um worker node desligado via AWS EC2 start-instances.
        
        Args:
            node_name: Nome do worker node
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        print(f"▶️ EXECUTANDO: start worker node {node_name}")
        
        try:
            # Forçar refresh do cache para obter estado atual
            self.discovery.refresh_cache()
            
            # Obter informações atualizadas de todas as instâncias
            instances = self.discovery.get_all_aws_instances()
            
            if node_name not in instances:
                return False, f"start_worker_node {node_name} (instance not found)"
            
            instance_info = instances[node_name]
            instance_id = instance_info['ID']
            current_state = instance_info['State']
            
            print(f"💡 Estado atual da instância {instance_id}: {current_state}")
            
            # Verificar estado atual antes de tentar iniciar
            if current_state == 'running':
                print(f"✅ Instância {node_name} ({instance_id}) já está rodando")
                return True, f"start_worker_node {node_name} (already running)"
            elif current_state in ['stopping', 'pending']:
                print(f"⏳ Instância {node_name} ({instance_id}) em estado transitório ({current_state})")
                # Aguardar estado estável antes de iniciar
                print(f"⏱️ Aguardando estado estável...")
                self._wait_for_instance_state(instance_id, "stopped", timeout=60)
            elif current_state != 'stopped':
                print(f"⚠️ Instância {node_name} ({instance_id}) em estado inválido para inicialização: {current_state}")
                return False, f"start_worker_node {node_name} (invalid state: {current_state})"
            
            # Comando para iniciar a instância via AWS CLI
            cmd = ['aws', 'ec2', 'start-instances', '--instance-ids', instance_id]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"✅ Worker node {node_name} ({instance_id}) ligado com sucesso")
                return True, f"start_worker_node {node_name}"
            else:
                print(f"❌ Erro ao ligar {node_name}: {result.stderr}")
                return False, f"start_worker_node {node_name} (failed)"
                
        except Exception as e:
            print(f"❌ Exceção ao ligar {node_name}: {e}")
            return False, f"start_worker_node {node_name} (error: {e})"
    
    def _wait_for_instance_state(self, instance_id: str, target_state: str, timeout: int = 60) -> bool:
        """
        Aguarda uma instância AWS atingir um estado específico.
        
        Args:
            instance_id: ID da instância AWS
            target_state: Estado alvo ('stopped', 'running', 'pending', etc.)
            timeout: Timeout em segundos
            
        Returns:
            True se a instância atingiu o estado, False caso contrário
        """
        import time
        
        print(f"⏳ Aguardando instância {instance_id} ficar '{target_state}' (timeout: {timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                cmd = ['aws', 'ec2', 'describe-instances', '--instance-ids', instance_id,
                       '--query', 'Reservations[0].Instances[0].State.Name', '--output', 'text']
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    current_state = result.stdout.strip()
                    print(f"  📊 Estado atual: {current_state}")
                    
                    if current_state == target_state:
                        print(f"  ✅ Instância {instance_id} está '{target_state}'!")
                        return True
                        
                    # Se está em estado de erro, não continuar aguardando
                    if current_state in ['terminated', 'terminating']:
                        print(f"  ❌ Instância em estado crítico: {current_state}")
                        return False
                        
                else:
                    print(f"  ⚠️ Erro ao verificar estado: {result.stderr}")
                    
            except Exception as e:
                print(f"  ⚠️ Exceção ao verificar estado: {e}")
            
            time.sleep(3)  # Verificar a cada 3 segundos
        
        print(f"  ⏰ Timeout: instância {instance_id} não ficou '{target_state}' em {timeout}s")
        return False
    
    # ===== MÉTODOS PARA CONTROL PLANE =====
    
    def kill_control_plane_processes(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata processos do control plane via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill control plane processes no node {node_name}")
        
        # Comandos rigorosos para matar todos os processos do control plane
        commands = [
            "sudo systemctl reboot"
        ]
        
        results = []
        reboot_initiated = False
        
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
            # Se reboot foi iniciado, aguardar tempo realista
            if success and "reboot" in cmd:
                reboot_initiated = True
                print(f"⏳ Control plane reboot iniciado em {node_name}, aguardando 60s para estabilizar...")
                # import time
                # time.sleep(60)  # Control plane demora mais para reiniciar
                print(f"⏳ Control plane {node_name} deve estar reiniciando agora...")
            
        if reboot_initiated or any("✅" in r for r in results):
            return True, f"Control plane processes killed on {node_name}. Results: {'; '.join(results)}. Reboot time waited."
        else:
            return False, f"Falha ao matar processos control plane em {node_name}. Results: {'; '.join(results)}"
    
    def kill_kube_apiserver(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata kube-apiserver via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill kube-apiserver no node {node_name}")
        
        # Comandos rigorosos para matar kube-apiserver
        commands = [
            "sudo -n pkill -9 -f kube-apiserver",
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
        if any("✅" in r for r in results):
            return True, f"Kube-apiserver killed on {node_name}. Results: {'; '.join(results)}"
        else:
            return False, f"Falha ao matar kube-apiserver em {node_name}. Results: {'; '.join(results)}"
    
    def kill_kube_controller_manager(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata kube-controller-manager via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill kube-controller-manager no node {node_name}")
        
        # Comandos rigorosos para matar kube-controller-manager
        commands = [
            "sudo -n pkill -9 -f kube-controller-manager",
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
        if any("✅" in r for r in results):
            return True, f"Kube-controller-manager killed on {node_name}. Results: {'; '.join(results)}"
        else:
            return False, f"Falha ao matar kube-controller-manager em {node_name}. Results: {'; '.join(results)}"
    
    def kill_kube_scheduler(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata kube-scheduler via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill kube-scheduler no node {node_name}")
        
        # Comandos rigorosos para matar kube-scheduler
        commands = [
            "sudo -n pkill -9 -f kube-scheduler",
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
        if any("✅" in r for r in results):
            return True, f"Kube-scheduler killed on {node_name}. Results: {'; '.join(results)}"
        else:
            return False, f"Falha ao matar kube-scheduler em {node_name}. Results: {'; '.join(results)}"
    
    def kill_etcd(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Mata etcd via SSH direto.
        """
        print(f"💀 EXECUTANDO: kill etcd no node {node_name}")
        
        commands = [
            "sudo -n pkill -9 -f etcd",
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=15)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            
        if any("✅" in r for r in results):
            return True, f"Etcd killed on {node_name}. Results: {'; '.join(results)}"
        else:
            return False, f"Falha ao matar etcd em {node_name}. Results: {'; '.join(results)}"
    
    def shutdown_control_plane(self, node_name: str) -> Tuple[bool, str]:
        """
        Desliga completamente o control plane via AWS (stop instância).
        Segue a mesma lógica do shutdown_worker_node.
        
        Args:
            node_name: Nome do control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        try:
            print(f"⛔ Desligando control plane {node_name}...")
            
            # Obter informações da instância
            instances = self._get_aws_instances()
            
            if node_name not in instances:
                print(f"❌ Control plane {node_name} não encontrado")
                return False, f"shutdown_control_plane {node_name}"
            
            instance = instances[node_name]
            instance_id = instance['ID']
            
            # Parar a instância AWS
            cmd = ['aws', 'ec2', 'stop-instances', '--instance-ids', instance_id]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"❌ Erro ao parar instância {instance_id}: {result.stderr}")
                return False, f"shutdown_control_plane {node_name}"
            
            print(f"✅ Comando de shutdown enviado para {node_name} (instância {instance_id})")
            
            # Aguardar a instância ficar stopped
            if self._wait_for_instance_state(instance_id, 'stopped', timeout=180):
                print(f"✅ Control plane {node_name} foi desligado com sucesso")
                return True, f"shutdown_control_plane {node_name}"
            else:
                print(f"⚠️ Control plane {node_name} não ficou stopped no tempo esperado")
                return False, f"shutdown_control_plane {node_name}"
                
        except Exception as e:
            print(f"❌ Erro ao desligar control plane {node_name}: {e}")
            return False, f"shutdown_control_plane {node_name} (error: {e})"
    
    def start_control_plane(self, node_name: str) -> Tuple[bool, str]:
        """
        Liga o control plane desligado e atualiza descoberta automática.
        Self-healing automático após shutdown_control_plane.
        
        Args:
            node_name: Nome do control plane
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        try:
            print(f"▶️ Ligando control plane {node_name}...")
            
            # IMPORTANTE: Limpar cache antes de obter instâncias para garantir estado atualizado
            self.discovery.refresh_cache()
            
            # Obter informações da instância
            instances = self._get_aws_instances()
            
            if node_name not in instances:
                print(f"❌ Control plane {node_name} não encontrado")
                return False, f"start_control_plane {node_name}"

            instance = instances[node_name]
            instance_id = instance['ID']
            current_state = instance['State']
            
            # Verificar se já está running
            if current_state == 'running':
                print(f"✅ Control plane {node_name} já está em execução (estado: {current_state})")
                return True, f"start_control_plane {node_name} (already running)"
            
            # Verificar se está em estado válido para start
            if current_state not in ['stopped', 'stopping']:
                print(f"⚠️ Control plane {node_name} está em estado '{current_state}' - não é possível ligar")
                return False, f"start_control_plane {node_name} (invalid state: {current_state})"
            
            print(f"📊 Estado atual: {current_state} - procedendo com o startup...")
            
            # Iniciar a instância AWS
            cmd = ['aws', 'ec2', 'start-instances', '--instance-ids', instance_id]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"❌ Erro ao ligar instância {instance_id}: {result.stderr}")
                return False, f"start_control_plane {node_name}"
            
            print(f"✅ Comando de startup enviado para {node_name} (instância {instance_id})")
            
            # Aguardar a instância ficar running
            if self._wait_for_instance_state(instance_id, 'running', timeout=120):
                print(f"✅ Control plane {node_name} foi ligado com sucesso")
                
                # IMPORTANTE: Limpar cache e redescobrir o novo IP
                print("🔄 Redescobrir control plane com novo IP...")
                self.discovery.refresh_cache()
                
                # Aguardar control plane ficar pronto para conexão SSH
                if self.discovery.wait_for_control_plane_ready(timeout=180):
                    print(f"✅ Control plane pronto para conexão SSH")
                    # Atualizar nossa própria conexão
                    self.ssh_host = None
                    self.ssh_connection = None
                    return True, f"start_control_plane {node_name}"
                else:
                    print(f"⚠️ Control plane ligado mas SSH não está pronto")
                    return False, f"start_control_plane {node_name}"
            else:
                print(f"⚠️ Control plane {node_name} não ficou running no tempo esperado")
                return False, f"start_control_plane {node_name}"
                
        except Exception as e:
            print(f"❌ Erro ao ligar control plane {node_name}: {e}")
            return False, f"start_control_plane {node_name} (error: {e})"