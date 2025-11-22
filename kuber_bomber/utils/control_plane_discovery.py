#!/usr/bin/env python3
"""
Control Plane Discovery
======================

Módulo para descoberta automática do IP do control plane usando AWS CLI.
Remove a dependência do ssh_host fixo no aws_config.json.
"""

import subprocess
import json
import time
from typing import Optional, Dict, List, Tuple


class ControlPlaneDiscovery:
    """
    Descobre automaticamente o IP do control plane AWS usando AWS CLI.
    """
    # Cache estático compartilhado entre instâncias
    _instances_cache = {}
    _instances_cache_time = None
    _control_plane_cache = None
    _control_plane_cache_time = None
    _cache_duration = 60  # Cache por 60 segundos
    _discovery_logged = False
    
    def __init__(self, aws_config: Dict):
        """
        Inicializa o discovery com configurações AWS básicas.
        
        Args:
            aws_config: Config com ssh_key, ssh_user (ssh_host será descoberto)
        """
        self.ssh_key = aws_config.get('ssh_key', '~/.ssh/vockey.pem')
        self.ssh_user = aws_config.get('ssh_user', 'ubuntu')
        
    def discover_control_plane_ip(self, force_refresh: bool = False) -> Optional[str]:
        """
        Descobre o IP público do control plane automaticamente com cache.
        
        Args:
            force_refresh: Se deve forçar nova descoberta (ignorar cache)
            
        Returns:
            IP público do control plane ou None se não encontrado
        """
        import time
        
        # Verificar cache se não for refresh forçado
        if not force_refresh:
            current_time = time.time()
            if (self._control_plane_cache is not None and 
                self._control_plane_cache_time is not None and
                current_time - self._control_plane_cache_time < self._cache_duration):
                return self._control_plane_cache
        
        # Cache expirou ou refresh forçado, fazer nova descoberta
        try:
            # Obter todas as instâncias AWS
            cmd = [
                'aws', 'ec2', 'describe-instances',
                '--query', 
                'Reservations[].Instances[].{ID:InstanceId,Name:Tags[?Key==`Name`]|[0].Value,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress,State:State.Name}',
                '--output', 'json'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"❌ Erro ao executar AWS CLI: {result.stderr}")
                return None
                
            instances_data = json.loads(result.stdout)
            
            # Procurar pelo control plane
            for instance in instances_data:
                name = instance.get('Name', '')
                state = instance.get('State')
                
                # Buscar instâncias que contenham 'control' ou 'master' no nome (case insensitive)
                if state == 'running' and name:
                    name_lower = name.lower()
                    if ('control' in name_lower or 'master' in name_lower or 
                        name_lower == 'controlplane' or name == 'ControlPlane'):
                        public_ip = instance.get('PublicIP')
                        if public_ip:
                            # Atualizar cache
                            self._control_plane_cache = public_ip
                            self._control_plane_cache_time = time.time()
                            
                            # Log apenas na primeira descoberta ou refresh forçado
                            if force_refresh or not self._discovery_logged:
                                print(f"✅ Control plane descoberto: {name} ({public_ip})")
                            
                            return public_ip
                        
            print("❌ Control plane não encontrado ou não está rodando")
            return None
            
        except Exception as e:
            print(f"❌ Erro na descoberta do control plane: {e}")
            return None
    
    def get_all_aws_instances(self) -> Dict[str, Dict]:
        """
        Obtém informações de todas as instâncias AWS com cache.
        
        Returns:
            Dict mapeando node_name -> instance_info
        """
        import time
        
        # Verificar se o cache ainda é válido
        current_time = time.time()
        if (self._instances_cache and 
            self._instances_cache_time is not None and
            current_time - self._instances_cache_time < self._cache_duration):
            return self._instances_cache
            
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
                        private_ip = instance['PrivateIP']
                        
                        # Mapear nomes para formato de node do Kubernetes
                        if 'WN' in name or 'worker' in name.lower():
                            node_name = f"ip-{private_ip.replace('.', '-')}"
                            instances[node_name] = instance
                        elif 'control' in name.lower() or 'master' in name.lower():
                            node_name = f"ip-{private_ip.replace('.', '-')}"
                            instances[node_name] = instance
                            
                # Atualizar cache
                self._instances_cache = instances
                self._instances_cache_time = current_time
                
                # Log apenas na primeira descoberta
                if not self._discovery_logged:
                    print(f"🔍 Descobertas {len(instances)} instâncias AWS:")
                    for node_name, info in instances.items():
                        print(f"  • {node_name}: {info['Name']} ({info['PublicIP']})")
                    self._discovery_logged = True
                    
                return instances
            else:
                print(f"❌ Erro ao obter instâncias: {result.stderr}")
                return {}
                
        except Exception as e:
            print(f"❌ Erro ao obter instâncias AWS: {e}")
            return {}
    
    def wait_for_control_plane_ready(self, timeout: int = 300) -> bool:
        """
        Aguarda o control plane ficar pronto após restart/shutdown.
        
        Args:
            timeout: Timeout em segundos
            
        Returns:
            True se control plane ficou pronto
        """
        print(f"⏳ Aguardando control plane ficar pronto (timeout: {timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Descobrir novo IP do control plane
            current_ip = self.discover_control_plane_ip(force_refresh=True)
            
            if current_ip:
                # Testar conectividade SSH
                if self._test_ssh_connectivity(current_ip):
                    print(f"✅ Control plane pronto em {current_ip}")
                    return True
            
            print(f"⏸️ Aguardando 10s antes da próxima verificação...")
            time.sleep(10)
        
        print(f"❌ Control plane não ficou pronto em {timeout}s")
        return False
    
    def _test_ssh_connectivity(self, ip: str) -> bool:
        """
        Testa conectividade SSH com o IP fornecido.
        
        Args:
            ip: IP para testar
            
        Returns:
            True se SSH funcionou
        """
        try:
            cmd = [
                'ssh', '-i', self.ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=5',
                '-o', 'BatchMode=yes',
                f"{self.ssh_user}@{ip}",
                'echo "SSH OK"'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.returncode == 0 and "SSH OK" in result.stdout
            
        except Exception:
            return False
    
    def get_node_public_ip(self, node_name: str) -> Optional[str]:
        """
        Obtém o IP público de um node específico.
        
        Args:
            node_name: Nome do node (ex: ip-10-0-0-98)
            
        Returns:
            IP público do node ou None se não encontrado
        """
        instances = self.get_all_aws_instances()
        
        if node_name in instances:
            return instances[node_name]['PublicIP']
        else:
            print(f"❌ Node {node_name} não encontrado nas instâncias AWS")
            return None
    
    def refresh_cache(self):
        """
        Limpa o cache e força nova descoberta.
        """
        print("🔄 Limpando cache de descoberta...")
        self._instances_cache = {}
        self._control_plane_ip = None