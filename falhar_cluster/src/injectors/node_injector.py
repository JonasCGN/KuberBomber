#!/usr/bin/env python3
"""
Node Failure Injector
=====================

Implementa diversos tipos de falhas em nós Kubernetes para testes de resiliência.
"""

import time
import subprocess
import boto3
from datetime import datetime
from typing import Dict, List, Optional, Any
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import paramiko

from ..core.base import (
    BaseFailureInjector, BaseMonitor, FailureMetrics, RecoveryMetrics,
    FailureType, FailureStatus, generate_failure_id, logger
)


class NodeFailureInjector(BaseFailureInjector):
    """Injetor de falhas específico para nós Kubernetes"""
    
    def __init__(self, 
                 kubeconfig_path: Optional[str] = None,
                 aws_region: str = "us-east-1",
                 ssh_key_path: Optional[str] = None,
                 ssh_user: str = "ubuntu"):
        super().__init__("NodeFailureInjector")
        
        # Configurar cliente Kubernetes
        try:
            if kubeconfig_path:
                config.load_kube_config(config_file=kubeconfig_path)
            else:
                config.load_incluster_config()
        except:
            try:
                config.load_kube_config()
            except Exception as e:
                self.logger.error(f"Failed to load kubeconfig: {e}")
                raise
        
        self.v1 = client.CoreV1Api()
        
        # Configurar cliente AWS (se disponível)
        try:
            self.ec2_client = boto3.client('ec2', region_name=aws_region)
            self.aws_available = True
        except Exception as e:
            self.logger.warning(f"AWS client not available: {e}")
            self.ec2_client = None
            self.aws_available = False
        
        self.ssh_key_path = ssh_key_path
        self.ssh_user = ssh_user
    
    def list_targets(self) -> List[str]:
        """Lista todos os nós disponíveis como targets"""
        try:
            nodes = self.v1.list_node()
            return [node.metadata.name for node in nodes.items]
        except ApiException as e:
            self.logger.error(f"Error listing nodes: {e}")
            return []
    
    def validate_target(self, target: str) -> bool:
        """Valida se o nó existe"""
        try:
            self.v1.read_node(name=target)
            return True
        except ApiException:
            return False
    
    def inject_failure(self, target: str, failure_type: str = "drain", **kwargs) -> FailureMetrics:
        """
        Injeta falha em um nó específico
        
        Args:
            target: Nome do nó
            failure_type: Tipo de falha ('drain', 'cordon', 'reboot', 'shutdown', 'network_partition', 'disk_fill')
            **kwargs: Parâmetros específicos do tipo de falha
        """
        if not self.validate_target(target):
            raise ValueError(f"Node {target} not found")
        
        failure_id = generate_failure_id(FailureType.NODE_DRAIN, target)
        metrics = FailureMetrics(
            failure_id=failure_id,
            failure_type=FailureType.NODE_DRAIN,  # Default, será atualizado
            target=target,
            start_time=datetime.now()
        )
        
        try:
            if failure_type == "drain":
                metrics.failure_type = FailureType.NODE_DRAIN
                self._drain_node(target, metrics, **kwargs)
            elif failure_type == "cordon":
                metrics.failure_type = FailureType.NODE_CORDON
                self._cordon_node(target, metrics, **kwargs)
            elif failure_type == "reboot":
                metrics.failure_type = FailureType.NODE_REBOOT
                self._reboot_node(target, metrics, **kwargs)
            elif failure_type == "shutdown":
                metrics.failure_type = FailureType.NODE_SHUTDOWN
                self._shutdown_node(target, metrics, **kwargs)
            elif failure_type == "network_partition":
                metrics.failure_type = FailureType.NODE_NETWORK_PARTITION
                self._network_partition_node(target, metrics, **kwargs)
            elif failure_type == "disk_fill":
                metrics.failure_type = FailureType.NODE_DISK_FILL
                self._disk_fill_node(target, metrics, **kwargs)
            else:
                raise ValueError(f"Unknown failure type: {failure_type}")
            
            metrics.success = True
            self.active_failures[failure_id] = metrics
            self.logger.info(f"Successfully injected {failure_type} failure in node {target}")
            
        except Exception as e:
            metrics.error_message = str(e)
            metrics.end_time = datetime.now()
            self.logger.error(f"Failed to inject failure in node {target}: {e}")
        
        return metrics
    
    def _drain_node(self, node_name: str, metrics: FailureMetrics, **kwargs):
        """Draina um nó movendo todos os pods para outros nós"""
        ignore_daemonsets = kwargs.get('ignore_daemonsets', True)
        force = kwargs.get('force', False)
        grace_period = kwargs.get('grace_period', -1)
        timeout = kwargs.get('timeout', 300)
        
        try:
            # Primeiro, marca o nó como unschedulable
            node = self.v1.read_node(name=node_name)
            node.spec.unschedulable = True
            self.v1.patch_node(name=node_name, body=node)
            
            # Lista pods no nó
            pods = self.v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
            
            pods_to_delete = []
            for pod in pods.items:
                # Pula DaemonSets se configurado
                if ignore_daemonsets:
                    for owner_ref in pod.metadata.owner_references or []:
                        if owner_ref.kind == "DaemonSet":
                            continue
                
                # Pula pods do sistema se não forçado
                if not force and pod.metadata.namespace in ['kube-system', 'kube-public']:
                    continue
                
                pods_to_delete.append((pod.metadata.name, pod.metadata.namespace))
            
            # Deleta pods
            for pod_name, namespace in pods_to_delete:
                try:
                    self.v1.delete_namespaced_pod(
                        name=pod_name,
                        namespace=namespace,
                        grace_period_seconds=grace_period if grace_period >= 0 else None
                    )
                except ApiException as e:
                    self.logger.warning(f"Failed to delete pod {pod_name}: {e}")
            
            metrics.additional_metrics = {
                "ignore_daemonsets": ignore_daemonsets,
                "force": force,
                "grace_period": grace_period,
                "pods_deleted": len(pods_to_delete)
            }
            self.logger.info(f"Drained node {node_name}, deleted {len(pods_to_delete)} pods")
            
        except Exception as e:
            raise Exception(f"Failed to drain node: {e}")
    
    def _cordon_node(self, node_name: str, metrics: FailureMetrics, **kwargs):
        """Marca um nó como unschedulable (cordon)"""
        try:
            node = self.v1.read_node(name=node_name)
            node.spec.unschedulable = True
            self.v1.patch_node(name=node_name, body=node)
            
            metrics.additional_metrics = {
                "original_schedulable": not getattr(node.spec, 'unschedulable', False)
            }
            self.logger.info(f"Cordoned node {node_name}")
            
        except Exception as e:
            raise Exception(f"Failed to cordon node: {e}")
    
    def _reboot_node(self, node_name: str, metrics: FailureMetrics, **kwargs):
        """Reinicializa um nó"""
        delay = kwargs.get('delay', 0)  # segundos antes do reboot
        
        try:
            # Primeira tentativa: reboot via AWS se disponível
            if self.aws_available and self._is_aws_node(node_name):
                instance_id = self._get_aws_instance_id(node_name)
                if instance_id:
                    if delay > 0:
                        time.sleep(delay)
                    
                    if self.ec2_client:
                        self.ec2_client.reboot_instances(InstanceIds=[instance_id])
                    metrics.additional_metrics = {
                        "method": "aws_ec2",
                        "instance_id": instance_id,
                        "delay": delay
                    }
                    self.logger.info(f"Rebooted AWS instance {instance_id} for node {node_name}")
                    return
            
            # Segunda tentativa: reboot via SSH
            if self.ssh_key_path:
                node_ip = self._get_node_ip(node_name)
                if node_ip:
                    ssh_client = paramiko.SSHClient()
                    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    ssh_client.connect(
                        hostname=node_ip,
                        username=self.ssh_user,
                        key_filename=self.ssh_key_path,
                        timeout=30
                    )
                    
                    reboot_command = f"sleep {delay} && sudo reboot"
                    ssh_client.exec_command(reboot_command)
                    ssh_client.close()
                    
                    metrics.additional_metrics = {
                        "method": "ssh",
                        "node_ip": node_ip,
                        "delay": delay
                    }
                    self.logger.info(f"Rebooted node {node_name} via SSH")
                    return
            
            raise Exception("No available method to reboot node (tried AWS and SSH)")
            
        except Exception as e:
            raise Exception(f"Failed to reboot node: {e}")
    
    def _shutdown_node(self, node_name: str, metrics: FailureMetrics, **kwargs):
        """Desliga um nó"""
        try:
            # Primeira tentativa: shutdown via AWS
            if self.aws_available and self._is_aws_node(node_name):
                instance_id = self._get_aws_instance_id(node_name)
                if instance_id and self.ec2_client:
                    self.ec2_client.stop_instances(InstanceIds=[instance_id])
                    metrics.additional_metrics = {
                        "method": "aws_ec2",
                        "instance_id": instance_id
                    }
                    self.logger.info(f"Stopped AWS instance {instance_id} for node {node_name}")
                    return
            
            # Segunda tentativa: shutdown via SSH
            if self.ssh_key_path:
                node_ip = self._get_node_ip(node_name)
                if node_ip:
                    ssh_client = paramiko.SSHClient()
                    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    ssh_client.connect(
                        hostname=node_ip,
                        username=self.ssh_user,
                        key_filename=self.ssh_key_path,
                        timeout=30
                    )
                    
                    ssh_client.exec_command("sudo shutdown -h now")
                    ssh_client.close()
                    
                    metrics.additional_metrics = {
                        "method": "ssh",
                        "node_ip": node_ip
                    }
                    self.logger.info(f"Shutdown node {node_name} via SSH")
                    return
            
            raise Exception("No available method to shutdown node (tried AWS and SSH)")
            
        except Exception as e:
            raise Exception(f"Failed to shutdown node: {e}")
    
    def _network_partition_node(self, node_name: str, metrics: FailureMetrics, **kwargs):
        """Simula partição de rede bloqueando tráfego"""
        duration = kwargs.get('duration', 60)  # segundos
        block_ports = kwargs.get('block_ports', [6443, 2379, 2380])  # API server, etcd
        
        try:
            node_ip = self._get_node_ip(node_name)
            if not node_ip or not self.ssh_key_path:
                raise Exception("SSH access required for network partition")
            
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh_client.connect(
                hostname=node_ip,
                username=self.ssh_user,
                key_filename=self.ssh_key_path,
                timeout=30
            )
            
            # Bloqueia portas específicas usando iptables
            block_commands = []
            for port in block_ports:
                block_commands.extend([
                    f"sudo iptables -A INPUT -p tcp --dport {port} -j DROP",
                    f"sudo iptables -A OUTPUT -p tcp --sport {port} -j DROP"
                ])
            
            for cmd in block_commands:
                ssh_client.exec_command(cmd)
            
            # Agenda remoção das regras
            cleanup_command = (
                f"sleep {duration} && "
                + " && ".join([f"sudo iptables -D INPUT -p tcp --dport {port} -j DROP" for port in block_ports])
                + " && "
                + " && ".join([f"sudo iptables -D OUTPUT -p tcp --sport {port} -j DROP" for port in block_ports])
            )
            
            # Executa cleanup em background
            ssh_client.exec_command(f"nohup bash -c '{cleanup_command}' &")
            ssh_client.close()
            
            metrics.additional_metrics = {
                "method": "iptables",
                "node_ip": node_ip,
                "duration": duration,
                "blocked_ports": block_ports
            }
            self.logger.info(f"Applied network partition to node {node_name} for {duration}s")
            
        except Exception as e:
            raise Exception(f"Failed to apply network partition: {e}")
    
    def _disk_fill_node(self, node_name: str, metrics: FailureMetrics, **kwargs):
        """Preenche o disco do nó para simular falta de espaço"""
        size_gb = kwargs.get('size_gb', 5)  # GB para preencher
        duration = kwargs.get('duration', 300)  # segundos para manter
        path = kwargs.get('path', '/tmp')  # caminho para criar arquivo
        
        try:
            node_ip = self._get_node_ip(node_name)
            if not node_ip or not self.ssh_key_path:
                raise Exception("SSH access required for disk fill")
            
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh_client.connect(
                hostname=node_ip,
                username=self.ssh_user,
                key_filename=self.ssh_key_path,
                timeout=30
            )
            
            # Cria arquivo grande para consumir espaço
            fill_file = f"{path}/chaos_disk_fill_{int(time.time())}.tmp"
            fill_command = f"dd if=/dev/zero of={fill_file} bs=1G count={size_gb}"
            
            ssh_client.exec_command(fill_command)
            
            # Agenda remoção do arquivo
            cleanup_command = f"sleep {duration} && rm -f {fill_file}"
            ssh_client.exec_command(f"nohup bash -c '{cleanup_command}' &")
            ssh_client.close()
            
            metrics.additional_metrics = {
                "method": "dd",
                "node_ip": node_ip,
                "size_gb": size_gb,
                "duration": duration,
                "fill_file": fill_file
            }
            self.logger.info(f"Filled {size_gb}GB disk space on node {node_name} for {duration}s")
            
        except Exception as e:
            raise Exception(f"Failed to fill disk: {e}")
    
    def _is_aws_node(self, node_name: str) -> bool:
        """Verifica se o nó é uma instância AWS"""
        try:
            node = self.v1.read_node(name=node_name)
            provider_id = getattr(node.spec, 'provider_id', '')
            return provider_id.startswith('aws://')
        except:
            return False
    
    def _get_aws_instance_id(self, node_name: str) -> Optional[str]:
        """Obtém o instance ID da AWS para um nó"""
        try:
            node = self.v1.read_node(name=node_name)
            provider_id = getattr(node.spec, 'provider_id', '')
            if provider_id.startswith('aws://'):
                # Format: aws:///zone/instance-id
                return provider_id.split('/')[-1]
            
            # Fallback: buscar por nome de host
            if self.ec2_client:
                response = self.ec2_client.describe_instances(
                    Filters=[
                        {'Name': 'private-dns-name', 'Values': [node_name]},
                        {'Name': 'state-name', 'Values': ['running']}
                    ]
                )
                
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        return instance['InstanceId']
            
            return None
        except Exception:
            return None
    
    def _get_node_ip(self, node_name: str) -> Optional[str]:
        """Obtém o IP externo ou interno de um nó"""
        try:
            node = self.v1.read_node(name=node_name)
            
            # Prioriza IP externo
            for address in node.status.addresses or []:
                if address.type == 'ExternalIP':
                    return address.address
            
            # Fallback para IP interno
            for address in node.status.addresses or []:
                if address.type == 'InternalIP':
                    return address.address
            
            return None
        except Exception:
            return None
    
    def recover_failure(self, failure_id: str) -> bool:
        """Recupera de uma falha específica"""
        if failure_id not in self.active_failures:
            return False
        
        metrics = self.active_failures[failure_id]
        
        try:
            if metrics.failure_type == FailureType.NODE_CORDON:
                # Uncordon do nó
                node = self.v1.read_node(name=metrics.target)
                node.spec.unschedulable = False
                self.v1.patch_node(name=metrics.target, body=node)
                self.logger.info(f"Uncordoned node {metrics.target}")
            
            elif metrics.failure_type == FailureType.NODE_DRAIN:
                # Uncordon do nó (drain também faz cordon)
                node = self.v1.read_node(name=metrics.target)
                node.spec.unschedulable = False
                self.v1.patch_node(name=metrics.target, body=node)
                self.logger.info(f"Uncordoned drained node {metrics.target}")
            
            elif metrics.failure_type == FailureType.NODE_SHUTDOWN:
                # Reinicia instância AWS se disponível
                if self.aws_available and self._is_aws_node(metrics.target):
                    instance_id = self._get_aws_instance_id(metrics.target)
                    if instance_id and self.ec2_client:
                        self.ec2_client.start_instances(InstanceIds=[instance_id])
                        self.logger.info(f"Started AWS instance {instance_id}")
            
            # Para outros tipos de falha (reboot, network, disk), a recuperação é automática
            
            metrics.end_time = datetime.now()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to recover from failure {failure_id}: {e}")
            return False
    
    def get_node_metrics(self, node_name: str) -> Dict[str, Any]:
        """Obtém métricas detalhadas de um nó"""
        try:
            node = self.v1.read_node(name=node_name)
            
            # Status básico
            metrics = {
                'name': node.metadata.name,
                'ready': False,
                'schedulable': not getattr(node.spec, 'unschedulable', False),
                'creation_timestamp': node.metadata.creation_timestamp,
                'addresses': {},
                'conditions': {},
                'capacity': node.status.capacity if node.status.capacity else {},
                'allocatable': node.status.allocatable if node.status.allocatable else {},
                'pods_count': 0
            }
            
            # Endereços
            for addr in node.status.addresses or []:
                metrics['addresses'][addr.type] = addr.address
            
            # Condições
            for condition in node.status.conditions or []:
                metrics['conditions'][condition.type] = {
                    'status': condition.status,
                    'reason': condition.reason,
                    'message': condition.message,
                    'last_transition_time': condition.last_transition_time
                }
                
                if condition.type == 'Ready' and condition.status == 'True':
                    metrics['ready'] = True
            
            # Contagem de pods no nó
            pods = self.v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
            metrics['pods_count'] = len(pods.items)
            
            return metrics
            
        except ApiException as e:
            self.logger.error(f"Error getting node metrics for {node_name}: {e}")
            return {}


class NodeMonitor(BaseMonitor):
    """Monitor específico para nós Kubernetes"""
    
    def __init__(self, kubeconfig_path: Optional[str] = None):
        super().__init__("NodeMonitor")
        
        # Usar a mesma configuração do injector
        try:
            if kubeconfig_path:
                config.load_kube_config(config_file=kubeconfig_path)
            else:
                config.load_incluster_config()
        except:
            config.load_kube_config()
        
        self.v1 = client.CoreV1Api()
    
    def get_status(self, target: str) -> Dict[str, Any]:
        """Retorna status detalhado de um nó"""
        try:
            node = self.v1.read_node(name=target)
            
            ready = False
            for condition in node.status.conditions or []:
                if condition.type == 'Ready' and condition.status == 'True':
                    ready = True
                    break
            
            return {
                'name': node.metadata.name,
                'ready': ready,
                'schedulable': not getattr(node.spec, 'unschedulable', False),
                'creation_timestamp': node.metadata.creation_timestamp,
                'exists': True
            }
        except ApiException:
            return {'exists': False}
    
    def is_healthy(self, target: str) -> bool:
        """Verifica se um nó está saudável e pronto"""
        status = self.get_status(target)
        return status.get('ready', False) and status.get('schedulable', False)
    
    def wait_for_recovery(self, target: str, timeout: int = 600) -> RecoveryMetrics:
        """
        Aguarda a recuperação de um nó e coleta métricas detalhadas
        """
        start_time = time.time()
        detect_time = None
        ready_time = None
        
        # Estado inicial
        initial_status = self.get_status(target)
        was_healthy = self.is_healthy(target)
        
        while time.time() - start_time < timeout:
            current_status = self.get_status(target)
            is_currently_healthy = self.is_healthy(target)
            
            # Detecta quando o nó fica não-saudável
            if detect_time is None and was_healthy and not is_currently_healthy:
                detect_time = time.time() - start_time
                self.logger.info(f"Node failure detected at {detect_time:.2f}s")
            
            # Detecta quando o nó volta a ficar saudável
            if ready_time is None and is_currently_healthy:
                ready_time = time.time() - start_time
                self.logger.info(f"Node recovery detected at {ready_time:.2f}s")
                break
            
            time.sleep(5)  # Check a cada 5 segundos para nós
        
        total_recovery_time = ready_time if ready_time else time.time() - start_time
        
        return RecoveryMetrics(
            time_to_detect=detect_time or 0,
            time_to_restart=ready_time or total_recovery_time,  # Para nós, restart = ready
            time_to_ready=ready_time or total_recovery_time,
            total_recovery_time=total_recovery_time,
            availability_impact=(total_recovery_time / timeout) * 100
        )


# Funções utilitárias
def drain_random_node(exclude_master: bool = True) -> FailureMetrics:
    """Draina um nó aleatório (excluindo master por padrão)"""
    injector = NodeFailureInjector()
    
    nodes = injector.list_targets()
    if exclude_master:
        # Remove nós master/control-plane
        filtered_nodes = []
        for node_name in nodes:
            try:
                node = injector.v1.read_node(name=node_name)
                labels = node.metadata.labels or {}
                
                # Pula nós master/control-plane
                if any(key in labels for key in [
                    'node-role.kubernetes.io/master',
                    'node-role.kubernetes.io/control-plane'
                ]):
                    continue
                
                filtered_nodes.append(node_name)
            except:
                continue
        
        nodes = filtered_nodes
    
    if not nodes:
        raise ValueError("No suitable nodes found")
    
    import random
    target = random.choice(nodes)
    return injector.inject_failure(target, failure_type="drain")


def chaos_test_nodes(duration_minutes: int = 30, 
                     failure_types: Optional[List[str]] = None) -> List[FailureMetrics]:
    """
    Executa teste de chaos em nós por período determinado
    """
    if failure_types is None:
        failure_types = ["drain", "cordon", "network_partition"]
    
    injector = NodeFailureInjector()
    monitor = NodeMonitor()
    results = []
    
    import random
    end_time = time.time() + (duration_minutes * 60)
    
    while time.time() < end_time:
        try:
            nodes = injector.list_targets()
            if nodes:
                target = random.choice(nodes)
                failure_type = random.choice(failure_types)
                
                # Pula nós master para alguns tipos de falha
                if failure_type in ["reboot", "shutdown"]:
                    node = injector.v1.read_node(name=target)
                    labels = node.metadata.labels or {}
                    if any(key in labels for key in [
                        'node-role.kubernetes.io/master',
                        'node-role.kubernetes.io/control-plane'
                    ]):
                        continue
                
                metrics = injector.inject_failure(target, failure_type=failure_type)
                
                # Monitora recuperação para alguns tipos
                if failure_type in ["drain", "cordon"]:
                    recovery_metrics = monitor.wait_for_recovery(target, timeout=300)
                    metrics.recovery_time = recovery_metrics.total_recovery_time
                
                results.append(metrics)
                logger.info(f"Chaos test: {failure_type} on {target}")
            
            # Intervalo entre falhas
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"Error during chaos test: {e}")
            time.sleep(60)
    
    return results


if __name__ == "__main__":
    # Exemplo de uso
    injector = NodeFailureInjector()
    monitor = NodeMonitor()
    
    print("Nós disponíveis:")
    for node in injector.list_targets():
        print(f"  - {node}")
        print(f"    Status: {monitor.get_status(node)}")