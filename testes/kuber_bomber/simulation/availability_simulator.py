"""
Simulador de Disponibilidade
============================

Simulador que modela falhas de toda a infraestrutura Kubernetes usando
distribuição exponencial e mede disponibilidade do sistema.
"""

import time
import heapq
import random
import numpy as np
import subprocess
import json
import requests
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..failure_injectors.pod_injector import PodFailureInjector
from ..failure_injectors.node_injector import NodeFailureInjector
from ..failure_injectors.control_plane_injector import ControlPlaneInjector
from ..monitoring.health_checker import HealthChecker
from ..reports.csv_reporter import CSVReporter


@dataclass
class Component:
    """Representa um componente do sistema."""
    name: str
    component_type: str  # 'pod', 'node', 'control_plane'
    mttf_hours: float
    current_status: str = 'healthy'  # 'healthy', 'failed', 'recovering'
    failure_count: int = 0
    total_downtime: float = 0.0
    available_failure_methods: Optional[List[str]] = None
    
    def __post_init__(self):
        """Define métodos de falha disponíveis baseado no tipo do componente."""
        if self.available_failure_methods is None:
            if self.component_type == "pod":
                # Removido delete_pod conforme solicitado
                self.available_failure_methods = [
                    "kill_all_processes",
                    "kill_init_process"
                ]
            elif self.component_type == "node":
                self.available_failure_methods = [
                    "kill_worker_node_processes",
                    "kill_kubelet",
                    "delete_kube_proxy",
                    "restart_containerd"
                ]
            elif self.component_type == "control_plane":
                self.available_failure_methods = [
                    "kill_control_plane_processes",
                    "kill_kube_apiserver", 
                    "kill_kube_controller_manager",
                    "kill_kube_scheduler",
                    "kill_etcd",
                    "restart_containerd"
                ]
            else:
                self.available_failure_methods = []
    
    def get_random_failure_method(self) -> str:
        """Retorna um método de falha aleatório para este componente."""
        import random
        if self.available_failure_methods:
            return random.choice(self.available_failure_methods)
        return "kill_all_processes"  # fallback


@dataclass
class FailureEvent:
    """Evento de falha agendado."""
    time_hours: float
    component: Component
    event_type: str = 'failure'
    
    def __lt__(self, other):
        return self.time_hours < other.time_hours


class AvailabilitySimulator:
    """
    Simulador principal de disponibilidade.
    
    Características:
    - Falhas baseadas em MTTF exponencial
    - Tempo entre falhas: 1min real fixo
    - Recuperação: tempo real do Kubernetes
    - Monitoramento contínuo de disponibilidade
    - Descoberta automática de componentes
    """
    
    def __init__(self, components: Optional[List[Component]] = None, min_pods_required: int = 2):
        """
        Inicializa o simulador.
        
        Args:
            components: Lista de componentes personalizados (opcional)
            min_pods_required: Número mínimo de pods necessários para disponibilidade
        """
        self.min_pods_required = min_pods_required
        
        # Monitor de saúde (inicializar primeiro para descoberta)
        self.health_checker = HealthChecker()
        
        # Descobrir URLs dos serviços automaticamente
        discovered_urls = self._discover_services_urls()
        
        # Atualizar configuração de serviços com URLs descobertas
        if discovered_urls:
            self.health_checker.config.services = self.health_checker.config.services or {}
            for service_name, urls in discovered_urls.items():
                # Mapear nome do serviço para nome da app (remover sufixos comuns)
                app_name = service_name.replace('-service', '').replace('-svc', '')
                
                self.health_checker.config.services[app_name] = {
                    'loadbalancer_url': urls.get('loadbalancer_url', ''),
                    'nodeport_url': urls.get('nodeport_url', ''),
                    'ingress_url': urls.get('ingress_url', ''),
                    'port': urls.get('port', 80),
                    'endpoint': urls.get('endpoint', f'/{app_name}')
                }
        
        # Critérios de disponibilidade por aplicação (será configurado dinamicamente)
        self.availability_criteria = {}
        
        # ========== CONFIGURAÇÃO DE COMPONENTES ==========
        if components:
            self.components = components
        else:
            # Descoberta automática de componentes
            self.components = self._discover_components()
        
        # Configurar critérios de disponibilidade baseado nos componentes descobertos
        self._setup_default_availability_criteria()
        
        # Injetores de falha
        self.pod_injector = PodFailureInjector()
        self.node_injector = NodeFailureInjector()
        self.control_plane_injector = ControlPlaneInjector()
        
        # Reporter CSV
        self.csv_reporter = CSVReporter()
        
        # Estado da simulação
        self.current_simulated_time = 0.0  # horas simuladas
        self.event_queue = []  # heap de eventos
        self.availability_history = []  # histórico de disponibilidade
        self.simulation_logs = []  # logs detalhados
        
        # Configurações
        self.real_delay_between_failures = 60  # 1 minuto em segundos
    
    def _discover_components(self) -> List[Component]:
        """
        Descobre automaticamente componentes do cluster Kubernetes.
        
        Returns:
            Lista de componentes descobertos
        """
        discovered_components = []
        
        print("🔍 === DESCOBRINDO COMPONENTES DO CLUSTER ===")
        
        # Descobrir aplicações (pods)
        try:
            # Obter todos os deployments
            result = subprocess.run([
                'kubectl', 'get', 'deployments', '-o', 'json',
                '--context', self.health_checker.config.context
            ], capture_output=True, text=True, check=True)
            
            deployments_data = json.loads(result.stdout)
            
            for deployment in deployments_data.get('items', []):
                name = deployment['metadata']['name']
                app_label = deployment['spec']['selector']['matchLabels'].get('app', name)
                
                # MTTF padrão baseado no tipo de aplicação
                default_mttf = 100.0  # horas
                
                component = Component(f"{app_label}-app", "pod", mttf_hours=default_mttf)
                discovered_components.append(component)
                print(f"  📦 Pod descoberto: {app_label}-app (MTTF: {default_mttf}h)")
                
        except Exception as e:
            print(f"⚠️ Erro ao descobrir pods: {e}")
            print("  ℹ️ Nenhuma aplicação foi descoberta automaticamente")
        
        # Descobrir nodes
        try:
            result = subprocess.run([
                'kubectl', 'get', 'nodes', '-o', 'json',
                '--context', self.health_checker.config.context
            ], capture_output=True, text=True, check=True)
            
            nodes_data = json.loads(result.stdout)
            
            for node in nodes_data.get('items', []):
                node_name = node['metadata']['name']
                
                # Determinar tipo do node baseado nos labels
                labels = node['metadata'].get('labels', {})
                taints = node['spec'].get('taints', [])
                
                # Verificar se é control plane (múltiplos critérios)
                is_control_plane = False
                
                # Labels para control plane
                control_plane_labels = [
                    'node-role.kubernetes.io/control-plane',
                    'node-role.kubernetes.io/master',
                    'kubernetes.io/role=master'
                ]
                
                for label in control_plane_labels:
                    if label in labels:
                        is_control_plane = True
                        break
                
                # Verificar por taints típicos de control plane
                if not is_control_plane:
                    for taint in taints:
                        taint_key = taint.get('key', '')
                        if 'master' in taint_key or 'control-plane' in taint_key:
                            is_control_plane = True
                            break
                
                # Verificar por hostname/nome (fallback)
                if not is_control_plane:
                    control_plane_names = ['master', 'control-plane', 'controlplane']
                    for cp_name in control_plane_names:
                        if cp_name in node_name.lower():
                            is_control_plane = True
                            break
                
                if is_control_plane:
                    component_type = "control_plane"
                    default_mttf = 800.0  # Control plane mais confiável (33+ dias)
                    print(f"  🎛️ Control Plane descoberto: {node_name} (MTTF: {default_mttf}h)")
                else:
                    component_type = "node"
                    default_mttf = 500.0  # Worker nodes (20+ dias)
                    print(f"  🖥️ Worker Node descoberto: {node_name} (MTTF: {default_mttf}h)")
                
                component = Component(node_name, component_type, mttf_hours=default_mttf)
                discovered_components.append(component)
                
        except Exception as e:
            print(f"⚠️ Erro ao descobrir nodes: {e}")
            # Fallback para nodes conhecidos se houver erro
            print("  ℹ️ Tentando fallback para nodes conhecidos...")
            
            # Exemplo de fallback mínimo (sem hardcode específico):
            fallback_components = [
                # Se nenhum componente for descoberto, este fallback deve ser vazio
                # para forçar o usuário a verificar seu cluster
            ]
            
            # Se não conseguiu descobrir nada, alertar o usuário
            print("❌ Nenhum componente descoberto no cluster!")
            print("   Verifique se o cluster está rodando e acessível:")
            print("   kubectl get nodes")
            print("   kubectl get deployments")
            return []
        
        print(f"✅ Total de {len(discovered_components)} componentes descobertos")
        print()
        
        # Mostrar resumo por tipo
        pods = [c for c in discovered_components if c.component_type == "pod"]
        workers = [c for c in discovered_components if c.component_type == "node"]  
        control_planes = [c for c in discovered_components if c.component_type == "control_plane"]
        
        print("📊 === RESUMO DA DESCOBERTA ===")
        print(f"  📦 Aplicações (Pods): {len(pods)} componentes")
        for pod in pods:
            print(f"    • {pod.name}: MTTF {pod.mttf_hours}h (~{pod.mttf_hours/24:.1f} dias)")
        
        print(f"  🖥️ Worker Nodes: {len(workers)} componentes")
        for worker in workers:
            print(f"    • {worker.name}: MTTF {worker.mttf_hours}h (~{worker.mttf_hours/24:.1f} dias)")
        
        print(f"  🎛️ Control Planes: {len(control_planes)} componentes")
        for cp in control_planes:
            print(f"    • {cp.name}: MTTF {cp.mttf_hours}h (~{cp.mttf_hours/24:.1f} dias)")
        
        print()
        
        return discovered_components
    
    def _discover_services_urls(self) -> Dict[str, Dict[str, str]]:
        """
        Descobre automaticamente URLs dos serviços (LoadBalancer, NodePort, Ingress).
        
        Returns:
            Dicionário com URLs descobertas para cada serviço
        """
        discovered_urls = {}
        
        print("🌐 === DESCOBRINDO URLs DOS SERVIÇOS ===")
        
        try:
            # Descobrir serviços LoadBalancer
            result = subprocess.run([
                'kubectl', 'get', 'services', '-o', 'json',
                '--context', self.health_checker.config.context
            ], capture_output=True, text=True, check=True)
            
            services_data = json.loads(result.stdout)
            
            for service in services_data.get('items', []):
                service_name = service['metadata']['name']
                service_type = service['spec'].get('type', 'ClusterIP')
                
                # Pular serviços do sistema
                if service_name in ['kubernetes', 'kube-dns']:
                    continue
                
                service_urls = {}
                
                if service_type == 'LoadBalancer':
                    # LoadBalancer com IP externo
                    ingress = service['status'].get('loadBalancer', {}).get('ingress', [])
                    if ingress:
                        external_ip = ingress[0].get('ip')
                        if external_ip:
                            ports = service['spec'].get('ports', [])
                            for port in ports:
                                port_num = port.get('port', 80)
                                target_port = port.get('targetPort', port_num)
                                
                                # Detectar endpoint baseado no nome do serviço
                                # Remover sufixos comuns para descobrir o endpoint real
                                base_name = service_name.replace('-loadbalancer', '').replace('-service', '').replace('-svc', '')
                                endpoint = f"/{base_name}"
                                
                                if port_num == 80:
                                    url = f"http://{external_ip}{endpoint}"
                                else:
                                    url = f"http://{external_ip}:{port_num}{endpoint}"
                                
                                service_urls['loadbalancer_url'] = url
                                service_urls['port'] = target_port
                                service_urls['endpoint'] = endpoint
                                break
                
                elif service_type == 'NodePort':
                    # NodePort - pegar IP de qualquer node
                    node_result = subprocess.run([
                        'kubectl', 'get', 'nodes', '-o', 'json',
                        '--context', self.health_checker.config.context
                    ], capture_output=True, text=True, check=True)
                    
                    nodes_data = json.loads(node_result.stdout)
                    
                    # Pegar IP do primeiro node disponível
                    node_ip = None
                    for node in nodes_data.get('items', []):
                        addresses = node['status'].get('addresses', [])
                        for addr in addresses:
                            if addr['type'] in ['InternalIP', 'ExternalIP']:
                                node_ip = addr['address']
                                break
                        if node_ip:
                            break
                    
                    if node_ip:
                        ports = service['spec'].get('ports', [])
                        for port in ports:
                            node_port = port.get('nodePort')
                            target_port = port.get('targetPort', port.get('port', 80))
                            
                            if node_port:
                                base_name = service_name.replace('-loadbalancer', '').replace('-service', '').replace('-svc', '')
                                endpoint = f"/{base_name}"
                                url = f"http://{node_ip}:{node_port}{endpoint}"
                                
                                service_urls['nodeport_url'] = url
                                service_urls['port'] = target_port
                                service_urls['endpoint'] = endpoint
                                break
                
                if service_urls:
                    discovered_urls[service_name] = service_urls
                    url_type = 'LoadBalancer' if 'loadbalancer_url' in service_urls else 'NodePort'
                    main_url = service_urls.get('loadbalancer_url') or service_urls.get('nodeport_url')
                    print(f"  🌐 {service_name} ({url_type}): {main_url}")
            
            # Tentar descobrir Ingress também
            try:
                ingress_result = subprocess.run([
                    'kubectl', 'get', 'ingress', '-o', 'json',
                    '--context', self.health_checker.config.context
                ], capture_output=True, text=True, check=True)
                
                ingress_data = json.loads(ingress_result.stdout)
                
                for ingress in ingress_data.get('items', []):
                    ingress_name = ingress['metadata']['name']
                    
                    # Pegar IP do ingress
                    ingress_ip = None
                    status = ingress.get('status', {})
                    load_balancer = status.get('loadBalancer', {})
                    ingress_list = load_balancer.get('ingress', [])
                    
                    if ingress_list:
                        ingress_ip = ingress_list[0].get('ip')
                    
                    if ingress_ip:
                        rules = ingress['spec'].get('rules', [])
                        for rule in rules:
                            paths = rule.get('http', {}).get('paths', [])
                            for path in paths:
                                path_str = path.get('path', '/')
                                backend = path.get('backend', {})
                                service_name = backend.get('service', {}).get('name') or backend.get('serviceName')
                                
                                if service_name and service_name in discovered_urls:
                                    ingress_url = f"http://{ingress_ip}{path_str}"
                                    discovered_urls[service_name]['ingress_url'] = ingress_url
                                    print(f"  🔗 {service_name} (Ingress): {ingress_url}")
                                    
            except subprocess.CalledProcessError:
                print("  ℹ️ Nenhum Ingress encontrado ou erro ao consultar")
        
        except Exception as e:
            print(f"⚠️ Erro ao descobrir URLs dos serviços: {e}")
        
        print(f"✅ URLs descobertas para {len(discovered_urls)} serviços")
        print()
        
        return discovered_urls
    
    def _setup_default_availability_criteria(self):
        """
        Configura critérios de disponibilidade padrão baseado nos componentes descobertos.
        """
        # Para cada aplicação (pod), exigir pelo menos 1 instância
        for component in self.components:
            if component.component_type == "pod":
                app_name = component.name  # já está no formato "app-name"
                self.availability_criteria[app_name] = 1
                print(f"📋 Critério padrão: {app_name} ≥ 1 pod(s)")
        
        if self.availability_criteria:
            print(f"✅ {len(self.availability_criteria)} critérios de disponibilidade configurados")
        else:
            print("⚠️ Nenhum critério de disponibilidade configurado")
        print()
    
    def configure_component_mttfs(self, custom_mttfs: Optional[Dict[str, float]] = None):
        """
        Configura MTTFs personalizados para componentes específicos.
        
        Args:
            custom_mttfs: Dicionário com {nome_componente: mttf_horas}
        """
        if not custom_mttfs:
            return
        
        print("🔧 === CONFIGURANDO MTTFs PERSONALIZADOS ===")
        
        for component in self.components:
            if component.name in custom_mttfs:
                old_mttf = component.mttf_hours
                component.mttf_hours = custom_mttfs[component.name]
                print(f"  📊 {component.name}: {old_mttf}h ➜ {component.mttf_hours}h")
        
        print("✅ MTTFs personalizados aplicados")
        print()
    
    def get_discovered_components_info(self) -> Dict:
        """
        Retorna informações sobre os componentes descobertos.
        
        Returns:
            Dicionário com informações dos componentes
        """
        return {
            'total_components': len(self.components),
            'pods': [c for c in self.components if c.component_type == "pod"],
            'nodes': [c for c in self.components if c.component_type == "node"], 
            'control_planes': [c for c in self.components if c.component_type == "control_plane"],
            'availability_criteria': self.availability_criteria,
            'discovered_services': getattr(self.health_checker.config, 'services', {})
        }
    
    def get_mttf_standards(self) -> Dict[str, Dict]:
        """
        Retorna os padrões de MTTF usados na descoberta automática.
        
        Returns:
            Dicionário com padrões de MTTF por tipo de componente
        """
        return {
            'pod': {
                'mttf_hours': 100.0,
                'mttf_days': 4.2,
                'description': 'Aplicações em pods - reinicialização automática'
            },
            'node': {
                'mttf_hours': 500.0,
                'mttf_days': 20.8,
                'description': 'Worker nodes - falhas de hardware/SO'
            },
            'control_plane': {
                'mttf_hours': 800.0,
                'mttf_days': 33.3,
                'description': 'Control plane - componentes críticos'
            }
        }
    
    def print_mttf_info(self):
        """Imprime informações detalhadas sobre os MTTFs configurados."""
        standards = self.get_mttf_standards()
        
        print("📈 === PADRÕES DE MTTF (MEAN TIME TO FAILURE) ===")
        print()
        
        for comp_type, info in standards.items():
            type_display = {
                'pod': '📦 Aplicações (Pods)',
                'node': '🖥️ Worker Nodes', 
                'control_plane': '🎛️ Control Planes'
            }[comp_type]
            
            print(f"{type_display}:")
            print(f"  • MTTF: {info['mttf_hours']}h (~{info['mttf_days']:.1f} dias)")
            print(f"  • Descrição: {info['description']}")
            print()
        
        print("💡 Estes valores podem ser personalizados usando configure_component_mttfs()")
        print("📊 MTTFs baseados em padrões industriais para infraestrutura cloud")
        print()
        
    def setup_availability_criteria(self):
        """Pergunta ao usuário quantos pods precisam estar disponíveis."""
        print("\n🎯 === CONFIGURAÇÃO DE DISPONIBILIDADE ===")
        
        # Mostrar pods disponíveis
        pod_components = [c for c in self.components if c.component_type == "pod"]
        print(f"📦 Pods na infraestrutura:")
        for i, pod in enumerate(pod_components, 1):
            print(f"  {i}. {pod.name} (MTTF: {pod.mttf_hours}h)")
        
        total_pods = len(pod_components)
        print(f"\n📊 Total de pods: {total_pods}")
        
        while True:
            try:
                required = int(input(f"🔢 Quantos pods precisam estar disponíveis para o sistema funcionar? (1-{total_pods}): "))
                if 1 <= required <= total_pods:
                    self.required_pods_available = required
                    print(f"✅ Configurado: Sistema disponível quando >= {required} pods estão funcionando")
                    break
                else:
                    print(f"❌ Digite um número entre 1 e {total_pods}")
            except ValueError:
                print("❌ Digite um número válido")
        
        print()
    
    def generate_next_failure_time(self, component: Component) -> float:
        """
        Gera próximo tempo de falha usando distribuição exponencial.
        
        Args:
            component: Componente para gerar falha
            
        Returns:
            Tempo em horas quando a falha deve ocorrer
        """
        # Taxa de falha (lambda) = 1 / MTTF
        failure_rate = 1.0 / component.mttf_hours
        
        # Distribuição exponencial
        time_until_failure = np.random.exponential(1.0 / failure_rate)
        
        return self.current_simulated_time + time_until_failure
    
    def initialize_events(self):
        """Gera eventos iniciais para todos os componentes."""
        print("🎲 Gerando eventos iniciais de falha...")
        
        for component in self.components:
            failure_time = self.generate_next_failure_time(component)
            event = FailureEvent(failure_time, component)
            heapq.heappush(self.event_queue, event)
            
            print(f"  📅 {component.name}: próxima falha em {failure_time:.1f}h simuladas")
        
        print(f"✅ {len(self.event_queue)} eventos iniciais criados\n")
    
    def inject_failure(self, component: Component) -> bool:
        """
        Injeta falha no componente especificado.
        
        Args:
            component: Componente para falhar
            
        Returns:
            True se falha foi injetada com sucesso
        """
        print(f"💥 INJETANDO FALHA: {component.name} ({component.component_type})")
        
        try:
            # Escolher método de falha aleatório
            failure_method = component.get_random_failure_method()
            print(f"  🎲 Método escolhido: {failure_method}")
            
            if component.component_type == "pod":
                # Encontrar pod específico primeiro
                pods = self.health_checker.get_pods_by_app_label(component.name.replace("-app", ""))
                if pods:
                    pod_name = pods[0]['name']
                    
                    # Executar método escolhido aleatoriamente
                    if failure_method == "kill_all_processes":
                        success = self.pod_injector.kill_all_processes(pod_name)
                        print(f"  🎯 Comando: kubectl exec {pod_name} -- kill -9 -1")
                    elif failure_method == "kill_init_process":
                        success = self.pod_injector.kill_init_process(pod_name)
                        print(f"  🎯 Comando: kubectl exec {pod_name} -- kill -9 1")
                    else:
                        # Fallback para kill_all_processes
                        success = self.pod_injector.kill_all_processes(pod_name)
                        print(f"  🎯 Comando (fallback): kubectl exec {pod_name} -- kill -9 -1")
                else:
                    print(f"  ❌ Pod {component.name} não encontrado")
                    return False
                    
            elif component.component_type == "node":
                # Executar método escolhido aleatoriamente para nodes
                if failure_method == "kill_worker_node_processes":
                    success, _ = self.node_injector.kill_worker_node_processes(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (kill worker processes)")
                elif failure_method == "kill_kubelet":
                    success, _ = self.control_plane_injector.kill_kubelet(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (kill kubelet)")
                elif failure_method == "delete_kube_proxy":
                    success, _ = self.control_plane_injector.delete_kube_proxy_pod(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (delete kube-proxy)")
                elif failure_method == "restart_containerd":
                    success, _ = self.control_plane_injector.restart_containerd(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (restart containerd)")
                else:
                    # Fallback
                    success, _ = self.node_injector.kill_worker_node_processes(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (fallback)")
                
            elif component.component_type == "control_plane":
                # Executar método escolhido aleatoriamente para control plane
                if failure_method == "kill_control_plane_processes":
                    success = self.node_injector.kill_control_plane_processes(component.name)
                    print(f"  🎯 Falha no control plane: {component.name} (kill all processes)")
                elif failure_method == "kill_kube_apiserver":
                    success = self.control_plane_injector.kill_kube_apiserver(component.name)
                    print(f"  🎯 Falha no control plane: {component.name} (kill apiserver)")
                elif failure_method == "kill_kube_controller_manager":
                    success = self.control_plane_injector.kill_kube_controller_manager(component.name)
                    print(f"  🎯 Falha no control plane: {component.name} (kill controller-manager)")
                elif failure_method == "kill_kube_scheduler":
                    success = self.control_plane_injector.kill_kube_scheduler(component.name)
                    print(f"  🎯 Falha no control plane: {component.name} (kill scheduler)")
                elif failure_method == "kill_etcd":
                    success = self.control_plane_injector.kill_etcd(component.name)
                    print(f"  🎯 Falha no control plane: {component.name} (kill etcd)")
                elif failure_method == "restart_containerd":
                    success = self.control_plane_injector.restart_containerd(component.name)
                    print(f"  🎯 Falha no control plane: {component.name} (restart containerd)")
                else:
                    # Fallback
                    success = self.node_injector.kill_control_plane_processes(component.name)
                    print(f"  🎯 Falha no control plane: {component.name} (fallback)")
                
            else:
                print(f"  ❌ Tipo de componente desconhecido: {component.component_type}")
                return False
            
            if success:
                component.current_status = 'failed'
                component.failure_count += 1
                print(f"  ✅ Falha injetada com sucesso")
                return True
            else:
                print(f"  ❌ Falha na injeção")
                return False
                
        except Exception as e:
            print(f"  ❌ Erro ao injetar falha: {e}")
            return False
    
    def is_system_available(self) -> Tuple[bool, Dict]:
        """
        Verifica se o sistema está disponível baseado nos critérios configurados.
        
        Returns:
            Tuple com (sistema_disponível, detalhes_por_app)
        """
        availability_details = {}
        system_available = True
        
        # Verificar cada aplicação
        for app_name, min_required in self.availability_criteria.items():
            try:
                pods = self.health_checker.get_pods_by_app_label(app_name.replace("-app", ""))
                ready_pods = sum(1 for pod in pods if pod.get('ready', False))
                
                app_available = ready_pods >= min_required
                availability_details[app_name] = {
                    'ready_pods': ready_pods,
                    'required_pods': min_required,
                    'available': app_available
                }
                
                if not app_available:
                    system_available = False
                    
            except Exception as e:
                print(f"⚠️ Erro ao verificar {app_name}: {e}")
                availability_details[app_name] = {
                    'ready_pods': 0,
                    'required_pods': min_required,
                    'available': False
                }
                system_available = False
        
        return system_available, availability_details
    
    def wait_for_recovery(self, component: Component) -> float:
        """
        Aguarda recuperação real do componente verificando requisições HTTP.
        
        Args:
            component: Componente a aguardar recuperação
            
        Returns:
            Tempo real de recuperação em segundos
        """
        print(f"⏳ Aguardando recuperação de {component.name}...")
        
        start_time = time.time()
        check_interval = 2  # verificar a cada 2 segundos
        
        while True:  # Aguarda indefinidamente até recuperar
            try:
                if component.component_type == "pod":
                    # CORREÇÃO: Usar descoberta dinâmica diretamente
                    app_name = component.name  # Manter nome completo (ex: bar-app)
                    
                    # Usar health_checker com descoberta dinâmica
                    health_result = self.health_checker.check_application_health(app_name, verbose=False)
                    
                    if health_result.get('healthy', False):
                        recovery_time = time.time() - start_time
                        url_info = health_result.get('url_type', 'health check')
                        print(f"  ✅ {component.name} recuperado em {recovery_time:.1f}s ({url_info})")
                        component.current_status = 'healthy'
                        return recovery_time
                    
                    # NÃO usar fallback de pod Ready - esperar recuperação HTTP real
                        
                elif component.component_type in ["node", "control_plane"]:
                    # Para nodes, PRIMEIRO verificar se todas as aplicações estão funcionando (curl/HTTP)
                    # Verificar se todas as aplicações definidas nos critérios estão funcionando
                    all_apps_healthy = True
                    apps_status = []
                    
                    for app_name in self.availability_criteria.keys():
                        health_result = self.health_checker.check_application_health(app_name, verbose=False)
                        is_healthy = health_result.get('healthy', False)
                        url_info = health_result.get('url_type', 'unknown')
                        apps_status.append(f"{app_name}: {'✅' if is_healthy else '❌'} ({url_info})")
                        
                        if not is_healthy:
                            all_apps_healthy = False
                    
                    if all_apps_healthy:
                        # Todas as apps estão funcionando via HTTP - recuperação confirmada!
                        recovery_time = time.time() - start_time
                        print(f"  ✅ {component.name} recuperado em {recovery_time:.1f}s (todas apps funcionando via HTTP)")
                        component.current_status = 'healthy'
                        return recovery_time
                    else:
                        # Apps ainda não funcionando, verificar node status como informação adicional
                        node_ready = self.health_checker.is_node_ready(component.name)
                        node_status = "Ready" if node_ready else "NotReady"
                        
                        print(f"  ⏳ Apps ainda recuperando (node: {node_status}): {', '.join(apps_status)}")
                        
                        # FALLBACK: Se todas as apps falharam no HTTP mas node está Ready e tempo > 2min, aceitar
                        if node_ready and (time.time() - start_time) > 120:  # 2 minutos
                            print(f"  ⚠️ FALLBACK: Node Ready há >2min mas apps não respondem HTTP")
                            recovery_time = time.time() - start_time
                            print(f"  ✅ {component.name} recuperado em {recovery_time:.1f}s (fallback: node Ready)")
                            component.current_status = 'healthy'
                            return recovery_time
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"  ⚠️ Erro verificando recuperação: {e}")
                time.sleep(check_interval)
    
    def check_system_availability(self) -> bool:
        """
        Verifica se o sistema está disponível baseado nos critérios configurados.
        
        Returns:
            True se sistema está disponível
        """
        try:
            # Usar o método is_system_available que já implementa a lógica correta
            system_available, details = self.is_system_available()
            
            # Log detalhado para debug
            if not system_available:
                failed_apps = [app for app, info in details.items() if not info['available']]
                print(f"  ⚠️ Sistema INDISPONÍVEL - Apps com problema: {failed_apps}")
                for app, info in details.items():
                    if not info['available']:
                        print(f"    • {app}: {info['ready_pods']}/{info['required_pods']} pods Ready")
            
            return system_available
            
        except Exception as e:
            print(f"⚠️ Erro ao verificar disponibilidade: {e}")
            return False
    
    def run_simulation(self, duration_hours: float = 24.0, iterations: int = 1):
        """
        Executa simulação principal.
        
        Args:
            duration_hours: Duração da simulação em horas simuladas
            iterations: Número de iterações da simulação
        """
        print(f"🚀 === INICIANDO SIMULAÇÃO ===")
        print(f"📊 Parâmetros:")
        print(f"  • Duração: {duration_hours}h simuladas")
        print(f"  • Iterações: {iterations}")
        print(f"  • Delay entre falhas: {self.real_delay_between_failures}s reais")
        
        print(f"📋 Critérios de disponibilidade:")
        for app, min_pods in self.availability_criteria.items():
            print(f"  • {app}: ≥{min_pods} pod(s)")
        print()
        
        all_results = []
        
        for iteration in range(1, iterations + 1):
            print(f"🔄 === ITERAÇÃO {iteration}/{iterations} ===")
            
            # Resetar estado
            self.current_simulated_time = 0.0
            self.event_queue = []
            self.availability_history = []
            self.simulation_logs = []
            
            # Resetar componentes
            for component in self.components:
                component.current_status = 'healthy'
                component.failure_count = 0
                component.total_downtime = 0.0
            
            # Gerar eventos iniciais
            self.initialize_events()
            
            # Executar simulação
            iteration_results = self._run_single_iteration(duration_hours)
            all_results.append(iteration_results)
            
            print(f"✅ Iteração {iteration} concluída")
            print(f"📈 Disponibilidade: {iteration_results['availability_percentage']:.2f}%")
            print()
        
        # Gerar relatório final
        self._generate_final_report(all_results)
    
    def _run_single_iteration(self, duration_hours: float) -> Dict:
        """
        Executa uma iteração da simulação.
        
        Args:
            duration_hours: Duração em horas simuladas
            
        Returns:
            Resultados da iteração
        """
        start_real_time = time.time()
        total_available_time = 0.0
        last_check_time = 0.0
        event_records = []  # Lista para registrar eventos para o CSV
        
        while self.current_simulated_time < duration_hours and self.event_queue:
            # Pegar próximo evento
            next_event = heapq.heappop(self.event_queue)
            
            # Verificar disponibilidade no período anterior
            time_delta = next_event.time_hours - last_check_time
            system_was_available = self.check_system_availability()
            if system_was_available:
                total_available_time += time_delta
            
            # Avançar tempo simulado
            self.current_simulated_time = next_event.time_hours
            last_check_time = self.current_simulated_time
            
            print(f"⏰ Tempo simulado: {self.current_simulated_time:.1f}h")
            
            # Injetar falha
            failure_method = next_event.component.get_random_failure_method()
            if self.inject_failure(next_event.component):
                # Aguardar recuperação (tempo real) primeiro
                recovery_start_time = time.time()
                recovery_time = self.wait_for_recovery(next_event.component)
                next_event.component.total_downtime += recovery_time
                
                # Aguardar 1 minuto real (delay fixo) - DEPOIS da recuperação
                print(f"⏸️ Aguardando {self.real_delay_between_failures}s (delay entre falhas)...")
                time.sleep(self.real_delay_between_failures)
                
                # Para nodes, aguardar um tempo adicional para pods se estabilizarem
                if next_event.component.component_type in ["node", "control_plane"]:
                    stabilization_time = 30  # 30 segundos extras para estabilização
                    print(f"⏳ Aguardando {stabilization_time}s extras para estabilização do sistema...")
                    time.sleep(stabilization_time)
                
                # Verificar disponibilidade do sistema após falha
                system_available_after, availability_details = self.is_system_available()
                
                # Contar pods disponíveis total
                total_available_pods = sum(info['ready_pods'] for info in availability_details.values())
                total_required_pods = sum(info['required_pods'] for info in availability_details.values())
                
                # Calcular % de disponibilidade até agora
                current_availability_pct = (total_available_time / self.current_simulated_time * 100) if self.current_simulated_time > 0 else 100
                
                # Registrar evento para CSV
                event_record = {
                    'event_time_hours': self.current_simulated_time,
                    'real_time_seconds': time.time() - start_real_time,
                    'component_type': next_event.component.component_type,
                    'component_name': next_event.component.name,
                    'failure_type': failure_method,
                    'recovery_time_seconds': recovery_time,
                    'system_available': system_available_after,
                    'available_pods': total_available_pods,
                    'required_pods': total_required_pods,
                    'availability_percentage': current_availability_pct,
                    'downtime_duration': recovery_time / 3600,  # converter para horas
                    'cumulative_downtime': next_event.component.total_downtime / 3600  # converter para horas
                }
                event_records.append(event_record)
                
                print(f"📝 Evento registrado: {failure_method} em {next_event.component.name}")
                
                # Gerar próxima falha para este componente
                next_failure_time = self.generate_next_failure_time(next_event.component)
                new_event = FailureEvent(next_failure_time, next_event.component)
                heapq.heappush(self.event_queue, new_event)
                
                print(f"📅 Próxima falha de {next_event.component.name}: {next_failure_time:.1f}h")
            
            print()
        
        # Calcular disponibilidade final
        availability_percentage = (total_available_time / duration_hours) * 100 if duration_hours > 0 else 0
        
        return {
            'duration_hours': duration_hours,
            'total_available_time': total_available_time,
            'availability_percentage': availability_percentage,
            'total_failures': sum(c.failure_count for c in self.components),
            'event_records': event_records,  # Adicionar os eventos registrados
            'components': [
                {
                    'name': c.name,
                    'type': c.component_type,
                    'failures': c.failure_count,
                    'total_downtime': c.total_downtime
                }
                for c in self.components
            ]
        }
    
    def _generate_final_report(self, all_results: List[Dict]):
        """
        Gera relatório final com todas as iterações.
        
        Args:
            all_results: Lista com resultados de todas as iterações
        """
        print("📋 === RELATÓRIO FINAL ===")
        
        if not all_results:
            print("❌ Nenhum resultado para reportar")
            return
        
        # Estatísticas agregadas
        total_iterations = len(all_results)
        avg_availability = sum(r['availability_percentage'] for r in all_results) / total_iterations
        min_availability = min(r['availability_percentage'] for r in all_results)
        max_availability = max(r['availability_percentage'] for r in all_results)
        total_failures = sum(r['total_failures'] for r in all_results)
        
        print(f"🎯 Simulação de {total_iterations} iterações concluída")
        print(f"📊 Disponibilidade Média: {avg_availability:.2f}%")
        print(f"📉 Disponibilidade Mínima: {min_availability:.2f}%")
        print(f"📈 Disponibilidade Máxima: {max_availability:.2f}%")
        print(f"💥 Total de Falhas: {total_failures}")
        print()
        
        # Relatório por componente
        print("🔧 === ESTATÍSTICAS POR COMPONENTE ===")
        for component in self.components:
            total_failures_comp = sum(
                sum(1 for c in r['components'] if c['name'] == component.name and c['failures'] > 0)
                for r in all_results
            )
            avg_failures = total_failures_comp / total_iterations if total_iterations > 0 else 0
            
            print(f"  📦 {component.name}:")
            print(f"    • MTTF configurado: {component.mttf_hours}h")
            print(f"    • Falhas médias por iteração: {avg_failures:.1f}")
        
        # Salvar CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"availability_simulation_{timestamp}.csv"
        
        try:
            # Coletar todos os eventos de todas as iterações
            all_events = []
            for result in all_results:
                if 'event_records' in result:
                    all_events.extend(result['event_records'])
            
            print(f"📊 Total de eventos registrados: {len(all_events)}")
            
            # Preparar estatísticas para salvar
            simulation_stats = {
                'total_simulation_time': all_results[0].get('duration_hours', 0) if all_results else 0,
                'total_failures': len(all_events),
                'system_availability': avg_availability,
                'mean_recovery_time': sum(event.get('recovery_time_seconds', 0) for event in all_events) / len(all_events) if all_events else 0,
                'total_downtime': sum(event.get('downtime_duration', 0) for event in all_events),
                'iterations': total_iterations
            }
            
            # Salvar eventos no CSV
            if all_events:
                self.csv_reporter.save_availability_results(all_events, simulation_stats)
                print(f"💾 Relatório salvo com {len(all_events)} eventos")
            else:
                print("⚠️ Nenhum evento foi registrado durante a simulação")
        except Exception as e:
            print(f"⚠️ Erro ao salvar CSV: {e}")
            import traceback
            traceback.print_exc()