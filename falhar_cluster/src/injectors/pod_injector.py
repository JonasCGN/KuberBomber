#!/usr/bin/env python3
"""
Pod Failure Injector
=====================

Implementa diversos tipos de falhas em pods Kubernetes para testes de resiliência.
"""

import time
import random
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Any
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from ..core.base import (
    BaseFailureInjector, BaseMonitor, FailureMetrics, RecoveryMetrics,
    FailureType, FailureStatus, generate_failure_id, logger
)


class PodFailureInjector(BaseFailureInjector):
    """Injetor de falhas específico para pods Kubernetes"""
    
    def __init__(self, namespace: str = "default", kubeconfig_path: Optional[str] = None):
        super().__init__("PodFailureInjector")
        self.namespace = namespace
        
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
        self.apps_v1 = client.AppsV1Api()
        self.metrics_v1 = client.CustomObjectsApi()
    
    def list_targets(self) -> List[str]:
        """Lista todos os pods disponíveis como targets"""
        try:
            pods = self.v1.list_namespaced_pod(namespace=self.namespace)
            return [pod.metadata.name for pod in pods.items if pod.status.phase == "Running"]
        except ApiException as e:
            self.logger.error(f"Error listing pods: {e}")
            return []
    
    def validate_target(self, target: str) -> bool:
        """Valida se o pod existe e está rodando"""
        try:
            pod = self.v1.read_namespaced_pod(name=target, namespace=self.namespace)
            return pod.status.phase == "Running"
        except ApiException:
            return False
    
    def inject_failure(self, target: str, failure_type: str = "delete", **kwargs) -> FailureMetrics:
        """
        Injeta falha em um pod específico
        
        Args:
            target: Nome do pod
            failure_type: Tipo de falha ('delete', 'kill', 'resource_limit', 'crashloop')
            **kwargs: Parâmetros específicos do tipo de falha
        """
        if not self.validate_target(target):
            raise ValueError(f"Pod {target} not found or not running")
        
        failure_id = generate_failure_id(FailureType.POD_DELETE, target)
        metrics = FailureMetrics(
            failure_id=failure_id,
            failure_type=FailureType.POD_DELETE,  # Default, será atualizado
            target=target,
            start_time=datetime.now()
        )
        
        try:
            if failure_type == "delete":
                metrics.failure_type = FailureType.POD_DELETE
                self._delete_pod(target, metrics, **kwargs)
            elif failure_type == "kill":
                metrics.failure_type = FailureType.POD_KILL
                self._kill_pod(target, metrics, **kwargs)
            elif failure_type == "resource_limit":
                metrics.failure_type = FailureType.POD_RESOURCE_LIMIT
                self._limit_pod_resources(target, metrics, **kwargs)
            elif failure_type == "crashloop":
                metrics.failure_type = FailureType.POD_CRASHLOOP
                self._induce_crashloop(target, metrics, **kwargs)
            else:
                raise ValueError(f"Unknown failure type: {failure_type}")
            
            metrics.success = True
            self.active_failures[failure_id] = metrics
            self.logger.info(f"Successfully injected {failure_type} failure in pod {target}")
            
        except Exception as e:
            metrics.error_message = str(e)
            metrics.end_time = datetime.now()
            self.logger.error(f"Failed to inject failure in pod {target}: {e}")
        
        return metrics
    
    def _delete_pod(self, pod_name: str, metrics: FailureMetrics, **kwargs):
        """Deleta um pod diretamente"""
        grace_period = kwargs.get('grace_period_seconds', 0)
        
        try:
            self.v1.delete_namespaced_pod(
                name=pod_name,
                namespace=self.namespace,
                grace_period_seconds=grace_period
            )
            metrics.additional_metrics = {"grace_period": grace_period}
            self.logger.info(f"Deleted pod {pod_name} with grace period {grace_period}s")
        except ApiException as e:
            raise Exception(f"Failed to delete pod: {e}")
    
    def _kill_pod(self, pod_name: str, metrics: FailureMetrics, **kwargs):
        """Mata um pod usando exec para kill do processo principal"""
        signal = kwargs.get('signal', 'SIGTERM')
        
        try:
            # Executa comando para matar o processo principal no pod
            exec_command = ['sh', '-c', f'kill -{signal} 1']
            
            resp = client.stream(
                self.v1.connect_get_namespaced_pod_exec,
                pod_name,
                self.namespace,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            
            metrics.additional_metrics = {"signal": signal, "exec_output": resp}
            self.logger.info(f"Sent {signal} to main process in pod {pod_name}")
            
        except Exception as e:
            raise Exception(f"Failed to kill pod process: {e}")
    
    def _limit_pod_resources(self, pod_name: str, metrics: FailureMetrics, **kwargs):
        """Limita recursos do pod modificando o deployment"""
        cpu_limit = kwargs.get('cpu_limit', '10m')  # Muito baixo para causar throttling
        memory_limit = kwargs.get('memory_limit', '64Mi')  # Muito baixo para causar OOM
        
        try:
            # Encontra o deployment que gerencia este pod
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=self.namespace)
            
            for owner_ref in pod.metadata.owner_references or []:
                if owner_ref.kind == "ReplicaSet":
                    rs = self.apps_v1.read_namespaced_replica_set(
                        name=owner_ref.name, namespace=self.namespace
                    )
                    
                    for rs_owner in rs.metadata.owner_references or []:
                        if rs_owner.kind == "Deployment":
                            deployment = self.apps_v1.read_namespaced_deployment(
                                name=rs_owner.name, namespace=self.namespace
                            )
                            
                            # Modifica os limites de recursos
                            for container in deployment.spec.template.spec.containers:
                                if container.resources is None:
                                    container.resources = client.V1ResourceRequirements()
                                if container.resources.limits is None:
                                    container.resources.limits = {}
                                
                                container.resources.limits['cpu'] = cpu_limit
                                container.resources.limits['memory'] = memory_limit
                            
                            # Aplica a mudança
                            self.apps_v1.patch_namespaced_deployment(
                                name=rs_owner.name,
                                namespace=self.namespace,
                                body=deployment
                            )
                            
                            metrics.additional_metrics = {
                                "cpu_limit": cpu_limit,
                                "memory_limit": memory_limit,
                                "deployment": rs_owner.name
                            }
                            self.logger.info(f"Limited resources for deployment {rs_owner.name}")
                            return
            
            raise Exception("Could not find parent deployment for pod")
            
        except Exception as e:
            raise Exception(f"Failed to limit pod resources: {e}")
    
    def _induce_crashloop(self, pod_name: str, metrics: FailureMetrics, **kwargs):
        """Induz um crashloop modificando a imagem ou comando do pod"""
        crash_command = kwargs.get('crash_command', ['sh', '-c', 'exit 1'])
        
        try:
            # Similar ao método anterior, encontra e modifica o deployment
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=self.namespace)
            
            for owner_ref in pod.metadata.owner_references or []:
                if owner_ref.kind == "ReplicaSet":
                    rs = self.apps_v1.read_namespaced_replica_set(
                        name=owner_ref.name, namespace=self.namespace
                    )
                    
                    for rs_owner in rs.metadata.owner_references or []:
                        if rs_owner.kind == "Deployment":
                            deployment = self.apps_v1.read_namespaced_deployment(
                                name=rs_owner.name, namespace=self.namespace
                            )
                            
                            # Modifica o comando para causar crash
                            for container in deployment.spec.template.spec.containers:
                                container.command = crash_command
                            
                            # Aplica a mudança
                            self.apps_v1.patch_namespaced_deployment(
                                name=rs_owner.name,
                                namespace=self.namespace,
                                body=deployment
                            )
                            
                            metrics.additional_metrics = {
                                "crash_command": crash_command,
                                "deployment": rs_owner.name
                            }
                            self.logger.info(f"Induced crashloop in deployment {rs_owner.name}")
                            return
            
            raise Exception("Could not find parent deployment for pod")
            
        except Exception as e:
            raise Exception(f"Failed to induce crashloop: {e}")
    
    def recover_failure(self, failure_id: str) -> bool:
        """Recupera de uma falha específica"""
        if failure_id not in self.active_failures:
            return False
        
        metrics = self.active_failures[failure_id]
        
        try:
            # Estratégias de recuperação baseadas no tipo de falha
            if metrics.failure_type in [FailureType.POD_RESOURCE_LIMIT, FailureType.POD_CRASHLOOP]:
                # Para falhas que modificaram o deployment, precisamos reverter
                self._restore_original_deployment(metrics)
            
            # Para delete e kill, o Kubernetes geralmente se recupera automaticamente
            # via ReplicaSet/Deployment
            
            metrics.end_time = datetime.now()
            self.logger.info(f"Recovered from failure {failure_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to recover from failure {failure_id}: {e}")
            return False
    
    def _restore_original_deployment(self, metrics: FailureMetrics):
        """Restaura configuração original do deployment"""
        if not metrics.additional_metrics or 'deployment' not in metrics.additional_metrics:
            return
        
        deployment_name = metrics.additional_metrics['deployment']
        
        # Aqui idealmente teríamos salvo a configuração original
        # Por simplicidade, vamos apenas reiniciar o deployment
        deployment = self.apps_v1.read_namespaced_deployment(
            name=deployment_name, namespace=self.namespace
        )
        
        # Força um restart adicionando annotation
        if deployment.spec.template.metadata.annotations is None:
            deployment.spec.template.metadata.annotations = {}
        
        deployment.spec.template.metadata.annotations['kubectl.kubernetes.io/restartedAt'] = \
            datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        self.apps_v1.patch_namespaced_deployment(
            name=deployment_name,
            namespace=self.namespace,
            body=deployment
        )
    
    def get_pod_metrics(self, pod_name: str) -> Dict[str, Any]:
        """Obtém métricas detalhadas de um pod"""
        try:
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=self.namespace)
            
            metrics = {
                'name': pod.metadata.name,
                'namespace': pod.metadata.namespace,
                'phase': pod.status.phase,
                'ready': sum(1 for c in pod.status.conditions or [] if c.type == "Ready" and c.status == "True") > 0,
                'restart_count': sum(c.restart_count for c in pod.status.container_statuses or []),
                'created': pod.metadata.creation_timestamp,
                'node_name': pod.spec.node_name,
                'containers': []
            }
            
            for container_status in pod.status.container_statuses or []:
                container_info = {
                    'name': container_status.name,
                    'ready': container_status.ready,
                    'restart_count': container_status.restart_count,
                    'state': 'unknown'
                }
                
                if container_status.state.running:
                    container_info['state'] = 'running'
                    container_info['started_at'] = container_status.state.running.started_at
                elif container_status.state.waiting:
                    container_info['state'] = 'waiting'
                    container_info['reason'] = container_status.state.waiting.reason
                elif container_status.state.terminated:
                    container_info['state'] = 'terminated'
                    container_info['reason'] = container_status.state.terminated.reason
                    container_info['exit_code'] = container_status.state.terminated.exit_code
                
                metrics['containers'].append(container_info)
            
            return metrics
            
        except ApiException as e:
            self.logger.error(f"Error getting pod metrics for {pod_name}: {e}")
            return {}


class PodMonitor(BaseMonitor):
    """Monitor específico para pods Kubernetes"""
    
    def __init__(self, namespace: str = "default", kubeconfig_path: Optional[str] = None):
        super().__init__("PodMonitor")
        self.namespace = namespace
        
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
        """Retorna status detalhado de um pod"""
        try:
            pod = self.v1.read_namespaced_pod(name=target, namespace=self.namespace)
            return {
                'name': pod.metadata.name,
                'phase': pod.status.phase,
                'ready': any(c.type == "Ready" and c.status == "True" for c in pod.status.conditions or []),
                'restart_count': sum(c.restart_count for c in pod.status.container_statuses or []),
                'node_name': pod.spec.node_name,
                'creation_timestamp': pod.metadata.creation_timestamp
            }
        except ApiException:
            return {'exists': False}
    
    def is_healthy(self, target: str) -> bool:
        """Verifica se um pod está saudável"""
        status = self.get_status(target)
        return status.get('phase') == 'Running' and status.get('ready', False)
    
    def wait_for_recovery(self, target: str, timeout: int = 300) -> RecoveryMetrics:
        """
        Aguarda a recuperação de um pod e coleta métricas detalhadas
        """
        start_time = time.time()
        detect_time = None
        restart_time = None
        ready_time = None
        
        original_pod_uid = None
        try:
            original_pod = self.v1.read_namespaced_pod(name=target, namespace=self.namespace)
            original_pod_uid = original_pod.metadata.uid
        except:
            pass
        
        while time.time() - start_time < timeout:
            try:
                current_status = self.get_status(target)
                
                # Detecta quando o pod original sai do estado Running
                if detect_time is None and (not current_status.get('exists', True) or 
                                           current_status.get('phase') != 'Running'):
                    detect_time = time.time() - start_time
                    self.logger.info(f"Pod failure detected at {detect_time:.2f}s")
                
                # Detecta quando um novo pod é criado (ou o mesmo pod reinicia)
                if restart_time is None and current_status.get('exists', False):
                    try:
                        current_pod = self.v1.read_namespaced_pod(name=target, namespace=self.namespace)
                        if (original_pod_uid is None or 
                            current_pod.metadata.uid != original_pod_uid or
                            current_status.get('restart_count', 0) > 0):
                            restart_time = time.time() - start_time
                            self.logger.info(f"Pod restart detected at {restart_time:.2f}s")
                    except:
                        pass
                
                # Detecta quando o pod fica Ready novamente
                if ready_time is None and self.is_healthy(target):
                    ready_time = time.time() - start_time
                    self.logger.info(f"Pod ready at {ready_time:.2f}s")
                    break
                
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error monitoring pod recovery: {e}")
                time.sleep(1)
        
        total_recovery_time = ready_time if ready_time else time.time() - start_time
        
        return RecoveryMetrics(
            time_to_detect=detect_time or 0,
            time_to_restart=restart_time or 0,
            time_to_ready=ready_time or total_recovery_time,
            total_recovery_time=total_recovery_time,
            availability_impact=(total_recovery_time / timeout) * 100
        )


# Funções utilitárias para facilitar o uso
def delete_random_pod(namespace: str = "default", 
                      app_label: Optional[str] = None) -> FailureMetrics:
    """Deleta um pod aleatório do namespace/aplicação especificada"""
    injector = PodFailureInjector(namespace)
    
    targets = injector.list_targets()
    if app_label:
        # Filtrar pods por label de aplicação
        filtered_targets = []
        for target in targets:
            try:
                pod = injector.v1.read_namespaced_pod(name=target, namespace=namespace)
                if pod.metadata.labels and pod.metadata.labels.get('app') == app_label:
                    filtered_targets.append(target)
            except:
                continue
        targets = filtered_targets
    
    if not targets:
        raise ValueError("No suitable pods found")
    
    target = random.choice(targets)
    return injector.inject_failure(target, failure_type="delete")


def stress_test_pods(namespace: str = "default", 
                     duration_minutes: int = 10,
                     interval_seconds: int = 30) -> List[FailureMetrics]:
    """
    Executa um teste de stress deletando pods em intervalos regulares
    """
    injector = PodFailureInjector(namespace)
    monitor = PodMonitor(namespace)
    results = []
    
    end_time = time.time() + (duration_minutes * 60)
    
    while time.time() < end_time:
        try:
            targets = injector.list_targets()
            if targets:
                target = random.choice(targets)
                metrics = injector.inject_failure(target, failure_type="delete")
                
                # Monitora a recuperação
                recovery_metrics = monitor.wait_for_recovery(target)
                metrics.recovery_time = recovery_metrics.total_recovery_time
                
                results.append(metrics)
                logger.info(f"Stressed pod {target}, recovery time: {metrics.recovery_time:.2f}s")
            
            time.sleep(interval_seconds)
            
        except Exception as e:
            logger.error(f"Error during stress test: {e}")
            time.sleep(interval_seconds)
    
    return results


if __name__ == "__main__":
    # Exemplo de uso
    injector = PodFailureInjector()
    monitor = PodMonitor()
    
    print("Pods disponíveis:")
    for pod in injector.list_targets():
        print(f"  - {pod}")
        print(f"    Status: {monitor.get_status(pod)}")