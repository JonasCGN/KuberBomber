#!/usr/bin/env python3
"""
System Monitor and Listing Module
=================================

Centraliza funcionalidades de listagem e monitoramento de recursos do cluster.
"""

import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from ..core.base import BaseMonitor, logger


class ResourceType(Enum):
    """Tipos de recursos monitoráveis"""
    POD = "pod"
    NODE = "node" 
    PROCESS = "process"
    SERVICE = "service"
    DEPLOYMENT = "deployment"
    NAMESPACE = "namespace"


class HealthStatus(Enum):
    """Estados de saúde dos recursos"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class ResourceInfo:
    """Informações básicas de um recurso"""
    name: str
    type: ResourceType
    namespace: Optional[str] = None
    status: str = "unknown"
    health: HealthStatus = HealthStatus.UNKNOWN
    created: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ClusterHealth:
    """Estado geral de saúde do cluster"""
    total_nodes: int
    healthy_nodes: int
    total_pods: int
    running_pods: int
    total_services: int
    healthy_services: int
    cluster_score: float  # 0-100
    issues: List[str]
    timestamp: datetime


class SystemMonitor:
    """Monitor centralizado do sistema"""
    
    def __init__(self, kubeconfig_path: Optional[str] = None):
        self.logger = logger.getChild("SystemMonitor")
        
        # Configurar Kubernetes se disponível
        self.k8s_available = False
        if KUBERNETES_AVAILABLE:
            try:
                if kubeconfig_path:
                    config.load_kube_config(config_file=kubeconfig_path)
                else:
                    config.load_incluster_config()
            except:
                try:
                    config.load_kube_config()
                except Exception as e:
                    self.logger.warning(f"Kubernetes not available: {e}")
            
            if self.k8s_available or True:  # Assumir disponível se chegou até aqui
                try:
                    self.v1 = client.CoreV1Api()
                    self.apps_v1 = client.AppsV1Api()
                    self.k8s_available = True
                except Exception as e:
                    self.logger.warning(f"Failed to create Kubernetes clients: {e}")
    
    def list_all_resources(self) -> Dict[ResourceType, List[ResourceInfo]]:
        """Lista todos os recursos disponíveis"""
        resources = {}
        
        if self.k8s_available:
            resources[ResourceType.NODE] = self.list_nodes()
            resources[ResourceType.POD] = self.list_pods()
            resources[ResourceType.SERVICE] = self.list_services()
            resources[ResourceType.DEPLOYMENT] = self.list_deployments()
            resources[ResourceType.NAMESPACE] = self.list_namespaces()
        
        if PSUTIL_AVAILABLE:
            resources[ResourceType.PROCESS] = self.list_processes()
        
        return resources
    
    def list_nodes(self) -> List[ResourceInfo]:
        """Lista todos os nós do cluster"""
        if not self.k8s_available:
            return []
        
        nodes = []
        try:
            node_list = self.v1.list_node()
            
            for node in node_list.items:
                # Determina status e saúde
                ready = False
                schedulable = not getattr(node.spec, 'unschedulable', False)
                
                for condition in node.status.conditions or []:
                    if condition.type == 'Ready' and condition.status == 'True':
                        ready = True
                        break
                
                if ready and schedulable:
                    health = HealthStatus.HEALTHY
                elif ready and not schedulable:
                    health = HealthStatus.DEGRADED
                else:
                    health = HealthStatus.UNHEALTHY
                
                # Coleta metadados
                metadata = {
                    'ready': ready,
                    'schedulable': schedulable,
                    'addresses': {},
                    'capacity': node.status.capacity or {},
                    'labels': node.metadata.labels or {},
                    'annotations': node.metadata.annotations or {}
                }
                
                for addr in node.status.addresses or []:
                    metadata['addresses'][addr.type] = addr.address
                
                nodes.append(ResourceInfo(
                    name=node.metadata.name,
                    type=ResourceType.NODE,
                    status=f"Ready={ready}, Schedulable={schedulable}",
                    health=health,
                    created=node.metadata.creation_timestamp,
                    metadata=metadata
                ))
                
        except ApiException as e:
            self.logger.error(f"Error listing nodes: {e}")
        
        return nodes
    
    def list_pods(self, namespace: Optional[str] = None) -> List[ResourceInfo]:
        """Lista todos os pods (ou de um namespace específico)"""
        if not self.k8s_available:
            return []
        
        pods = []
        try:
            if namespace:
                pod_list = self.v1.list_namespaced_pod(namespace=namespace)
            else:
                pod_list = self.v1.list_pod_for_all_namespaces()
            
            for pod in pod_list.items:
                # Determina saúde baseada no status
                phase = pod.status.phase
                ready_containers = 0
                total_containers = len(pod.spec.containers or [])
                
                for status in pod.status.container_statuses or []:
                    if status.ready:
                        ready_containers += 1
                
                if phase == 'Running' and ready_containers == total_containers:
                    health = HealthStatus.HEALTHY
                elif phase in ['Pending', 'ContainerCreating']:
                    health = HealthStatus.DEGRADED
                elif phase in ['Failed', 'CrashLoopBackOff']:
                    health = HealthStatus.UNHEALTHY
                else:
                    health = HealthStatus.UNKNOWN
                
                # Metadados
                metadata = {
                    'phase': phase,
                    'ready_containers': f"{ready_containers}/{total_containers}",
                    'node_name': pod.spec.node_name,
                    'restart_count': sum(c.restart_count for c in pod.status.container_statuses or []),
                    'labels': pod.metadata.labels or {},
                    'owner_references': []
                }
                
                for owner in pod.metadata.owner_references or []:
                    metadata['owner_references'].append({
                        'kind': owner.kind,
                        'name': owner.name
                    })
                
                pods.append(ResourceInfo(
                    name=pod.metadata.name,
                    type=ResourceType.POD,
                    namespace=pod.metadata.namespace,
                    status=f"{phase} ({ready_containers}/{total_containers})",
                    health=health,
                    created=pod.metadata.creation_timestamp,
                    metadata=metadata
                ))
                
        except ApiException as e:
            self.logger.error(f"Error listing pods: {e}")
        
        return pods
    
    def list_services(self, namespace: Optional[str] = None) -> List[ResourceInfo]:
        """Lista todos os services"""
        if not self.k8s_available:
            return []
        
        services = []
        try:
            if namespace:
                service_list = self.v1.list_namespaced_service(namespace=namespace)
            else:
                service_list = self.v1.list_service_for_all_namespaces()
            
            for service in service_list.items:
                # Services são geralmente considerados saudáveis se existem
                # Poderia verificar endpoints para determinar saúde real
                health = HealthStatus.HEALTHY
                
                metadata = {
                    'type': service.spec.type,
                    'cluster_ip': service.spec.cluster_ip,
                    'ports': [],
                    'selector': service.spec.selector or {},
                    'labels': service.metadata.labels or {}
                }
                
                for port in service.spec.ports or []:
                    port_info = {
                        'port': port.port,
                        'target_port': port.target_port,
                        'protocol': port.protocol
                    }
                    if hasattr(port, 'node_port') and port.node_port:
                        port_info['node_port'] = port.node_port
                    metadata['ports'].append(port_info)
                
                services.append(ResourceInfo(
                    name=service.metadata.name,
                    type=ResourceType.SERVICE,
                    namespace=service.metadata.namespace,
                    status=f"{service.spec.type}",
                    health=health,
                    created=service.metadata.creation_timestamp,
                    metadata=metadata
                ))
                
        except ApiException as e:
            self.logger.error(f"Error listing services: {e}")
        
        return services
    
    def list_deployments(self, namespace: Optional[str] = None) -> List[ResourceInfo]:
        """Lista todos os deployments"""
        if not self.k8s_available:
            return []
        
        deployments = []
        try:
            if namespace:
                deployment_list = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            else:
                deployment_list = self.apps_v1.list_deployment_for_all_namespaces()
            
            for deployment in deployment_list.items:
                # Saúde baseada em réplicas
                desired = deployment.spec.replicas or 0
                ready = deployment.status.ready_replicas or 0
                available = deployment.status.available_replicas or 0
                
                if ready == desired and available == desired:
                    health = HealthStatus.HEALTHY
                elif ready > 0:
                    health = HealthStatus.DEGRADED
                else:
                    health = HealthStatus.UNHEALTHY
                
                metadata = {
                    'replicas_desired': desired,
                    'replicas_ready': ready,
                    'replicas_available': available,
                    'replicas_updated': deployment.status.updated_replicas or 0,
                    'strategy': deployment.spec.strategy.type if deployment.spec.strategy else 'Unknown',
                    'labels': deployment.metadata.labels or {},
                    'selector': deployment.spec.selector.match_labels if deployment.spec.selector else {}
                }
                
                deployments.append(ResourceInfo(
                    name=deployment.metadata.name,
                    type=ResourceType.DEPLOYMENT,
                    namespace=deployment.metadata.namespace,
                    status=f"{ready}/{desired} ready",
                    health=health,
                    created=deployment.metadata.creation_timestamp,
                    metadata=metadata
                ))
                
        except ApiException as e:
            self.logger.error(f"Error listing deployments: {e}")
        
        return deployments
    
    def list_namespaces(self) -> List[ResourceInfo]:
        """Lista todos os namespaces"""
        if not self.k8s_available:
            return []
        
        namespaces = []
        try:
            namespace_list = self.v1.list_namespace()
            
            for ns in namespace_list.items:
                # Namespaces são saudáveis se estão ativos
                phase = ns.status.phase
                health = HealthStatus.HEALTHY if phase == 'Active' else HealthStatus.UNHEALTHY
                
                metadata = {
                    'phase': phase,
                    'labels': ns.metadata.labels or {},
                    'annotations': ns.metadata.annotations or {}
                }
                
                namespaces.append(ResourceInfo(
                    name=ns.metadata.name,
                    type=ResourceType.NAMESPACE,
                    status=phase,
                    health=health,
                    created=ns.metadata.creation_timestamp,
                    metadata=metadata
                ))
                
        except ApiException as e:
            self.logger.error(f"Error listing namespaces: {e}")
        
        return namespaces
    
    def list_processes(self, filter_by: Optional[str] = None) -> List[ResourceInfo]:
        """Lista processos do sistema"""
        if not PSUTIL_AVAILABLE:
            return []
        
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent', 'create_time']):
                try:
                    proc_info = proc.info
                    
                    # Filtro opcional por nome
                    if filter_by and filter_by.lower() not in proc_info['name'].lower():
                        continue
                    
                    # Determina saúde baseada no status
                    status = proc_info['status']
                    if status in [psutil.STATUS_RUNNING, psutil.STATUS_SLEEPING]:
                        health = HealthStatus.HEALTHY
                    elif status in [psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE]:
                        health = HealthStatus.UNHEALTHY
                    else:
                        health = HealthStatus.DEGRADED
                    
                    metadata = {
                        'pid': proc_info['pid'],
                        'status': status,
                        'cpu_percent': proc_info['cpu_percent'],
                        'memory_percent': proc_info['memory_percent'],
                        'create_time': proc_info['create_time']
                    }
                    
                    # Informações adicionais se disponíveis
                    try:
                        metadata.update({
                            'ppid': proc.ppid(),
                            'cmdline': ' '.join(proc.cmdline()[:3])  # Primeiros 3 argumentos
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    
                    processes.append(ResourceInfo(
                        name=f"{proc_info['name']} ({proc_info['pid']})",
                        type=ResourceType.PROCESS,
                        status=status,
                        health=health,
                        created=datetime.fromtimestamp(proc_info['create_time']) if proc_info['create_time'] else None,
                        metadata=metadata
                    ))
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error listing processes: {e}")
        
        return processes
    
    def get_cluster_health(self) -> ClusterHealth:
        """Calcula o estado geral de saúde do cluster"""
        issues = []
        
        # Coleta métricas de nós
        nodes = self.list_nodes()
        total_nodes = len(nodes)
        healthy_nodes = sum(1 for n in nodes if n.health == HealthStatus.HEALTHY)
        
        if healthy_nodes < total_nodes:
            issues.append(f"{total_nodes - healthy_nodes} node(s) unhealthy")
        
        # Coleta métricas de pods
        pods = self.list_pods()
        total_pods = len(pods)
        running_pods = sum(1 for p in pods if p.health == HealthStatus.HEALTHY)
        
        if running_pods < total_pods * 0.9:  # Menos de 90% rodando
            issues.append(f"Only {running_pods}/{total_pods} pods healthy")
        
        # Coleta métricas de services
        services = self.list_services()
        total_services = len(services)
        healthy_services = sum(1 for s in services if s.health == HealthStatus.HEALTHY)
        
        # Calcula score geral (0-100)
        node_score = (healthy_nodes / total_nodes * 100) if total_nodes > 0 else 100
        pod_score = (running_pods / total_pods * 100) if total_pods > 0 else 100
        service_score = (healthy_services / total_services * 100) if total_services > 0 else 100
        
        # Peso maior para pods e nós
        cluster_score = (node_score * 0.4 + pod_score * 0.5 + service_score * 0.1)
        
        return ClusterHealth(
            total_nodes=total_nodes,
            healthy_nodes=healthy_nodes,
            total_pods=total_pods,
            running_pods=running_pods,
            total_services=total_services,
            healthy_services=healthy_services,
            cluster_score=round(cluster_score, 2),
            issues=issues,
            timestamp=datetime.now()
        )
    
    def get_resource_details(self, resource_type: ResourceType, name: str, 
                           namespace: Optional[str] = None) -> Optional[ResourceInfo]:
        """Obtém detalhes específicos de um recurso"""
        resources = []
        
        if resource_type == ResourceType.NODE:
            resources = self.list_nodes()
        elif resource_type == ResourceType.POD:
            resources = self.list_pods(namespace)
        elif resource_type == ResourceType.SERVICE:
            resources = self.list_services(namespace)
        elif resource_type == ResourceType.DEPLOYMENT:
            resources = self.list_deployments(namespace)
        elif resource_type == ResourceType.NAMESPACE:
            resources = self.list_namespaces()
        elif resource_type == ResourceType.PROCESS:
            resources = self.list_processes()
        
        for resource in resources:
            if resource.name == name:
                return resource
        
        return None
    
    def watch_resource_health(self, resource_type: ResourceType, name: str,
                             duration_seconds: int = 300,
                             check_interval: int = 10) -> List[Tuple[datetime, HealthStatus]]:
        """
        Monitora a saúde de um recurso ao longo do tempo
        """
        health_history = []
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            resource = self.get_resource_details(resource_type, name)
            timestamp = datetime.now()
            
            if resource:
                health_history.append((timestamp, resource.health))
            else:
                health_history.append((timestamp, HealthStatus.UNKNOWN))
            
            time.sleep(check_interval)
        
        return health_history
    
    def export_system_state(self, filename: Optional[str] = None) -> str:
        """Exporta o estado atual do sistema para JSON"""
        if filename is None:
            filename = f"system_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        resources = self.list_all_resources()
        cluster_health = self.get_cluster_health()
        
        # Converte para dicionários serializáveis
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'cluster_health': asdict(cluster_health),
            'resources': {}
        }
        
        for resource_type, resource_list in resources.items():
            export_data['resources'][resource_type.value] = [
                asdict(resource) for resource in resource_list
            ]
        
        # Converte datetime objects para strings
        def datetime_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=datetime_serializer)
        
        self.logger.info(f"System state exported to {filename}")
        return filename


# Funções utilitárias
def print_cluster_summary():
    """Imprime um resumo do estado do cluster"""
    monitor = SystemMonitor()
    health = monitor.get_cluster_health()
    
    print("\n=== CLUSTER HEALTH SUMMARY ===")
    print(f"Overall Score: {health.cluster_score}/100")
    print(f"Timestamp: {health.timestamp}")
    print()
    print(f"Nodes: {health.healthy_nodes}/{health.total_nodes} healthy")
    print(f"Pods: {health.running_pods}/{health.total_pods} running")
    print(f"Services: {health.healthy_services}/{health.total_services} healthy")
    
    if health.issues:
        print("\nIssues detected:")
        for issue in health.issues:
            print(f"  - {issue}")
    else:
        print("\nNo issues detected!")


def print_resource_list(resource_type: ResourceType, namespace: Optional[str] = None):
    """Imprime lista formatada de recursos"""
    monitor = SystemMonitor()
    
    if resource_type == ResourceType.NODE:
        resources = monitor.list_nodes()
    elif resource_type == ResourceType.POD:
        resources = monitor.list_pods(namespace)
    elif resource_type == ResourceType.SERVICE:
        resources = monitor.list_services(namespace)
    elif resource_type == ResourceType.DEPLOYMENT:
        resources = monitor.list_deployments(namespace)
    elif resource_type == ResourceType.NAMESPACE:
        resources = monitor.list_namespaces()
    elif resource_type == ResourceType.PROCESS:
        resources = monitor.list_processes()
    else:
        print(f"Unsupported resource type: {resource_type}")
        return
    
    print(f"\n=== {resource_type.value.upper()}S ===")
    print(f"Total: {len(resources)}")
    print()
    
    for resource in resources:
        health_icon = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.UNHEALTHY: "❌", 
            HealthStatus.UNKNOWN: "❓"
        }.get(resource.health, "❓")
        
        namespace_info = f" (ns: {resource.namespace})" if resource.namespace else ""
        print(f"{health_icon} {resource.name}{namespace_info} - {resource.status}")


if __name__ == "__main__":
    # Exemplo de uso
    print("System Monitor - Example Usage")
    
    monitor = SystemMonitor()
    
    # Mostra resumo do cluster
    print_cluster_summary()
    
    # Lista recursos
    print_resource_list(ResourceType.NODE)
    print_resource_list(ResourceType.POD, namespace="default")
    
    # Exporta estado
    filename = monitor.export_system_state()
    print(f"\nSystem state exported to: {filename}")