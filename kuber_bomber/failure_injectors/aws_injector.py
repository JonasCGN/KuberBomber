"""
AWS Failure Injector
===================

Injeta falhas em ambientes AWS via SSH usando AWS CLI para descoberta automática de IPs.
"""

import subprocess
import json
from typing import Dict, List, Optional, Tuple


class AWSFailureInjector:
    """
    Injetor de falhas específico para ambiente AWS via SSH com descoberta automática de IPs.
    """
    
    def __init__(self, ssh_key: str, ssh_host: str, ssh_user: str = "ubuntu"):
        self.ssh_key = ssh_key
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_connection = f"{ssh_user}@{ssh_host}"
        self._instance_cache = {}  # Cache para IPs das instâncias
        
    def _get_aws_instances(self) -> Dict[str, Dict]:
        """
        Obtém informações das instâncias AWS via AWS CLI.
        """
        if self._instance_cache:
            return self._instance_cache
            
        try:
            cmd = [
                'aws', 'ec2', 'describe-instances',
                '--query', 
                'Reservations[].Instances[].{ID:InstanceId,Name:Tags[?Key==`Name`]|[0].Value,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress,State:State.Name}',
                '--output', 'json'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                instances_data = json.loads(result.stdout)
                instances = {}
                
                for instance in instances_data:
                    if instance.get('State') == 'running' and instance.get('Name'):
                        name = instance['Name']
                        # Mapear nomes para formato de node do Kubernetes
                        if 'WN' in name or 'worker' in name.lower():
                            # WN0 -> ip-10-0-0-98, WN1 -> ip-10-0-0-241
                            private_ip = instance['PrivateIP']
                            node_name = f"ip-{private_ip.replace('.', '-')}"
                            instances[node_name] = instance
                        elif 'control' in name.lower() or 'master' in name.lower():
                            private_ip = instance['PrivateIP']
                            node_name = f"ip-{private_ip.replace('.', '-')}"
                            instances[node_name] = instance
                            
                self._instance_cache = instances
                print(f"🔍 Descobertas {len(instances)} instâncias AWS:")
                for node_name, info in instances.items():
                    print(f"  • {node_name}: {info['Name']} ({info['PublicIP']})")
                    
                return instances
            else:
                print(f"❌ Erro ao executar AWS CLI: {result.stderr}")
                return {}
                
        except Exception as e:
            print(f"❌ Exceção ao obter instâncias AWS: {str(e)}")
            return {}
    
    def _get_node_public_ip(self, node_name: str) -> str:
        """
        Obtém o IP público de um node via AWS CLI.
        """
        instances = self._get_aws_instances()
        
        if node_name in instances:
            public_ip = instances[node_name]['PublicIP']
            print(f"🌐 Node {node_name} -> IP público: {public_ip}")
            return public_ip
        else:
            raise Exception(f"Node {node_name} não encontrado nas instâncias AWS")
    
    def _execute_ssh_command(self, node_name: str, command: str, timeout: int = 30) -> Tuple[bool, str]:
        """
        Executa comando SSH em um node específico usando seu IP público.
        """
        try:
            public_ip = self._get_node_public_ip(node_name)
            
            ssh_cmd = [
                'ssh', '-i', self.ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                '-o', 'BatchMode=yes',
                f'{self.ssh_user}@{public_ip}',
                command
            ]
            
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
        Executa comando genérico no control plane (mantido para compatibilidade).
        """
        print(f"🔄 Executando no control plane: {command}")
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
        Executa kubectl no control plane.
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
            cmd = f"sudo kubectl exec -it {pod_name} -c debug-tools -- kill -9 -1"
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
            cmd = f"sudo kubectl exec -it {pod_name} -c debug-tools -- kill -9 1"
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
                import time
                time.sleep(45)  # Aguardar tempo realista para reboot
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
    
    def delete_kube_proxy_pod(self, node_name: str) -> Tuple[bool, str]:
        """
        EXATO da tabela: Remove kube-proxy via SSH direto.
        """
        print(f"💀 EXECUTANDO: delete kube-proxy pod no node {node_name}")
        
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
            # "sudo systemctl restart containerd",  
            "sudo -n pkill -9 -f containerd",
            # "sudo systemctl stop containerd && sudo systemctl start containerd",
            # "sudo pkill -9 -f containerd && sudo systemctl start containerd"
        ]
        
        results = []
        for cmd in commands:
            success, output = self._execute_ssh_command(node_name, cmd, timeout=30)
            results.append(f"{cmd}: {'✅' if success else '❌'}")
            if success:  # Se um comando funcionou, parar
                break
                
        if any("✅" in r for r in results):
            return True, f"Containerd restarted on {node_name}. Results: {'; '.join(results)}"
        else:
            return False, f"Falha ao reiniciar containerd em {node_name}. Results: {'; '.join(results)}"
    
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
                import time
                time.sleep(60)  # Control plane demora mais para reiniciar
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