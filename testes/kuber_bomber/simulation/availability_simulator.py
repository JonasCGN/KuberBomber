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
import signal
import sys
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..failure_injectors.pod_injector import PodFailureInjector
from ..failure_injectors.node_injector import NodeFailureInjector
from ..failure_injectors.control_plane_injector import ControlPlaneInjector
from ..failure_injectors.aws_injector import AWSFailureInjector
from ..monitoring.health_checker import HealthChecker
from ..reports.csv_reporter import CSVReporter
from ..utils.pod_limiter import PodLimiter
from ..utils.kubectl_executor import get_kubectl_executor


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
                    "restart_containerd",
                    # "shutdown_worker_node" 
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
    # Cache estático para evitar descoberta duplicada durante testes
    _service_urls_cache = None
    _cache_timestamp = None
    _cache_ttl = 300  # 5 minutos
    _components_cache = None
    _components_cache_timestamp = None
    _criteria_setup_done = False
    
    def __init__(self, components: Optional[List[Component]] = None, min_pods_required: int = 2, aws_config: Optional[dict] = None):
        """
        Inicializa o simulador.
        
        Args:
            components: Lista de componentes personalizados (opcional)
            min_pods_required: Número mínimo de pods necessários para disponibilidade
            aws_config: Configuração AWS para conexão remota
        """
        self.min_pods_required = min_pods_required
        self.aws_config = aws_config
        self.is_aws_mode = aws_config is not None
        
        # Monitor de saúde (inicializar primeiro para descoberta)
        self.health_checker = HealthChecker(aws_config=aws_config)
        
        # Executor de kubectl centralizado
        self.kubectl = get_kubectl_executor(aws_config)
        
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
        
        # Injetores de falha - usar AWS quando estiver em modo AWS
        if self.is_aws_mode and aws_config:
            print("🔧 Inicializando injetores AWS...")
            ssh_host = aws_config.get('ssh_host', '')
            if not ssh_host:
                raise ValueError("ssh_host é obrigatório para modo AWS")
            
            self.aws_injector = AWSFailureInjector(
                ssh_key=aws_config.get('ssh_key', '~/.ssh/vockey.pem'),
                ssh_host=ssh_host,
                ssh_user=aws_config.get('ssh_user', 'ubuntu')
            )
            print(f"✅ AWS injector configurado para {ssh_host}")
        else:
            print("🔧 Inicializando injetores locais...")
            self.aws_injector = None
            
        # Sempre inicializar injetores locais (como fallback)
        self.pod_injector = PodFailureInjector()
        self.node_injector = NodeFailureInjector()
        self.control_plane_injector = ControlPlaneInjector()
        
        # Reporter CSV
        self.csv_reporter = CSVReporter()
        
        # Limitador de pods (será configurado se usar ConfigSimples)
        self.pod_limiter = None
        
        # Estado da simulação
        self.current_simulated_time = 0.0  # horas simuladas
        self.event_queue = []  # heap de eventos
        self.availability_history = []  # histórico de disponibilidade
    

        self.simulation_logs = []  # logs detalhados
        
        # Configurações
        self.real_delay_between_failures = 60  # 1 minuto em segundos
        
        # Controle de salvamento incremental
        self.all_results = []  # Resultados de todas as iterações
        self.current_iteration = 0
        self.simulation_interrupted = False
        
        # Configurar handler para Ctrl+C
        signal.signal(signal.SIGINT, self._handle_interrupt)
    
    def _discover_components(self) -> List[Component]:
        """
        Descobre automaticamente componentes do cluster Kubernetes.
        Usa cache para evitar descoberta duplicada durante testes consecutivos.
        
        Returns:
            Lista de componentes descobertos
        """
        import time
        
        # Verificar cache
        current_time = time.time()
        if (AvailabilitySimulator._components_cache is not None and 
            AvailabilitySimulator._components_cache_timestamp is not None and 
            current_time - AvailabilitySimulator._components_cache_timestamp < AvailabilitySimulator._cache_ttl):
            return AvailabilitySimulator._components_cache
        
        discovered_components = []
        
        print("🔍 === DESCOBRINDO COMPONENTES DO CLUSTER ===")
        
        # Descobrir aplicações (pods)
        try:
            # Obter todos os deployments
            result = self.kubectl.execute_kubectl(['get', 'deployments', '-o', 'json'])
            
            if not result['success']:
                print(f"❌ Erro ao obter deployments: {result['error']}")
                return discovered_components
            
            deployments_data = json.loads(result['output'])
            
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
            result = self.kubectl.execute_kubectl(['get', 'nodes', '-o', 'json'])
            
            if not result['success']:
                print(f"❌ Erro ao obter nodes: {result['error']}")
                return discovered_components
            
            nodes_data = json.loads(result['output'])
            
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
        
        # Atualizar cache
        AvailabilitySimulator._components_cache = discovered_components
        AvailabilitySimulator._components_cache_timestamp = current_time
        
        return discovered_components
    
    def _discover_services_urls(self) -> Dict[str, Dict[str, str]]:
        """
        Descobre automaticamente URLs dos serviços (LoadBalancer, NodePort, Ingress).
        Usa cache para evitar descoberta duplicada durante testes consecutivos.
        
        Returns:
            Dicionário com URLs descobertas para cada serviço
        """
        import time
        
        # Verificar cache
        current_time = time.time()
        if (AvailabilitySimulator._service_urls_cache is not None and 
            AvailabilitySimulator._cache_timestamp is not None and 
            current_time - AvailabilitySimulator._cache_timestamp < AvailabilitySimulator._cache_ttl):
            return AvailabilitySimulator._service_urls_cache
        
        discovered_urls = {}
        
        print("🌐 === DESCOBRINDO URLs DOS SERVIÇOS ===")
        
        try:
            # Descobrir serviços LoadBalancer
            result = self.kubectl.execute_kubectl(['get', 'services', '-o', 'json'])
            
            if not result['success']:
                print(f"❌ Erro ao obter services: {result['error']}")
                return discovered_urls
            
            services_data = json.loads(result['output'])
            
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
                    node_result = self.kubectl.execute_kubectl([
                        'get', 'nodes', '-o', 'json'
                    ])
                    
                    if node_result['success']:
                        nodes_data = json.loads(node_result['output'])
                        
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
                ingress_result = self.kubectl.execute_kubectl([
                    'get', 'ingress', '-o', 'json'
                ])
                
                if ingress_result['success']:
                    ingress_data = json.loads(ingress_result['output'])
                    
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
                                        
            except Exception:
                print("  ℹ️ Nenhum Ingress encontrado ou erro ao consultar")
        
        except Exception as e:
            print(f"⚠️ Erro ao descobrir URLs dos serviços: {e}")
        
        print(f"✅ URLs descobertas para {len(discovered_urls)} serviços")
        print()
        
        # Atualizar cache
        AvailabilitySimulator._service_urls_cache = discovered_urls
        AvailabilitySimulator._cache_timestamp = current_time
        
        return discovered_urls
    
    def _setup_default_availability_criteria(self):
        """
        Configura critérios de disponibilidade padrão baseado nos componentes descobertos.
        Usa cache para evitar configuração duplicada.
        """
        # Verificar se já foi configurado
        if AvailabilitySimulator._criteria_setup_done:
            return
            
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
            
        # Marcar como configurado
        AvailabilitySimulator._criteria_setup_done = True
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
        
        # Debug: mostrar cálculo apenas para primeiros componentes
        if len(self.components) <= 7:  # Evitar spam de debug
            print(f"  🎲 {component.name}: MTTF={component.mttf_hours}h → λ={failure_rate:.6f} → próxima={time_until_failure:.1f}h")
        
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
    
    def _handle_interrupt(self, signum, frame):
        """
        Handler para Ctrl+C - salva todos os arquivos necessários com dados parciais.
        Gera os mesmos arquivos que uma simulação completa.
        """
        print(f"\n⏹️ Simulação interrompida pelo usuário")
        print(f"💾 Salvando dados parciais nos arquivos padrão...")
        
        self.simulation_interrupted = True
        
        try:
            # Garantir que temos um diretório de simulação com estrutura hierárquica
            if not hasattr(self.csv_reporter, '_simulation_base_dir'):
                from datetime import datetime
                now = datetime.now()
                year = now.strftime('%Y')
                month = now.strftime('%m')
                day = now.strftime('%d')
                timestamp = now.strftime('%H%M%S')
                
                # Criar estrutura: simulation/YYYY/MM/DD/HHMMSS/
                base_dir = os.path.join('./simulation', year, month, day, timestamp)
                os.makedirs(base_dir, exist_ok=True)
                self.csv_reporter._simulation_base_dir = base_dir
            
            simulation_dir = self.csv_reporter._simulation_base_dir
            
            # 1. config_simples_used.json
            print("📄 Salvando config_simples_used.json...")
            if hasattr(self, '_config_simples') and self._config_simples:
                config_file = os.path.join(simulation_dir, 'config_simples_used.json')
                try:
                    self._config_simples.save_config(config_file)
                    print(f"  ✅ {config_file}")
                except Exception as e:
                    print(f"  ⚠️ Erro ao salvar config_simples: {e}")
            else:
                print(f"  ⚠️ ConfigSimples não disponível")
            
            # 2. experiment_config.json  
            print("� Salvando experiment_config.json...")
            config_data = self._save_experiment_configuration_interrupt(self.all_results)
            print(f"  ✅ {os.path.join(simulation_dir, 'experiment_config.json')}")
            
            # 3. experiment_iterations.csv
            print("📄 Salvando experiment_iterations.csv...")
            self._save_iterations_csv_interrupt(self.all_results)
            print(f"  ✅ {os.path.join(simulation_dir, 'experiment_iterations.csv')}")
            
            # 4. experiment_components.csv  
            print("📄 Salvando experiment_components.csv...")
            component_stats = self._calculate_component_statistics(self.all_results)
            self._save_components_csv_interrupt(component_stats)
            print(f"  ✅ {os.path.join(simulation_dir, 'experiment_components.csv')}")
            
            # 5. experiment_all_events.csv
            print("📄 Salvando experiment_all_events.csv...")
            self._save_all_events_csv_interrupt(self.all_results)
            print(f"  ✅ {os.path.join(simulation_dir, 'experiment_all_events.csv')}")
            
            # Verificar e informar sobre arquivos de tempo real já existentes
            print(f"\n📋 Arquivos de tempo real (padrão ITERACAO{self.current_iteration}/):")
            
            iteration_dir = os.path.join(simulation_dir, f'ITERACAO{self.current_iteration}')
            if os.path.exists(iteration_dir):
                realtime_files = ['events.csv', 'statistics.csv']
                
                for filename in realtime_files:
                    filepath = os.path.join(iteration_dir, filename)
                    if os.path.exists(filepath):
                        size = os.path.getsize(filepath)
                        print(f"  ✅ ITERACAO{self.current_iteration}/{filename} ({size} bytes)")
                    else:
                        print(f"  ⚠️ ITERACAO{self.current_iteration}/{filename} (não encontrado)")
            else:
                print(f"  ⚠️ Diretório ITERACAO{self.current_iteration}/ não encontrado")
            
            print(f"\n✅ Todos os arquivos salvos com sucesso!")
            print(f"📁 Diretório: {simulation_dir}")
            print(f"📊 Iterações salvas: {len(self.all_results)}")
            
            # Mostrar estatísticas básicas
            if self.all_results:
                availabilities = [r['availability_percentage'] for r in self.all_results]
                avg_availability = sum(availabilities) / len(availabilities)
                total_failures = sum(r['total_failures'] for r in self.all_results)
                print(f"📈 Disponibilidade média: {avg_availability:.2f}%")
                print(f"💥 Total de falhas: {total_failures}")
            
            print(f"\n💡 Arquivos de tempo real salvam dados imediatamente após cada evento!")
            print(f"📊 Use 'ITERACAO{self.current_iteration}/events.csv' para análise detalhada em tempo real")
            print(f"📈 Use 'ITERACAO{self.current_iteration}/statistics.csv' para estatísticas atualizadas")
            
        except Exception as e:
            print(f"❌ Erro ao salvar dados: {e}")
            import traceback
            traceback.print_exc()
        
        sys.exit(0)
    
    def _save_event_incremental(self, event_record: Dict):
        """
        Salva evento individual no arquivo CSV incrementalmente.
        
        Args:
            event_record: Dados do evento para salvar
        """
        try:
            # Salvar no CSV de eventos individuais usando padrão ITERACAO{N}/events.csv
            if hasattr(self.csv_reporter, '_simulation_base_dir'):
                iteration_dir = os.path.join(self.csv_reporter._simulation_base_dir, f'ITERACAO{self.current_iteration}')
                
                # Criar diretório da iteração se não existir
                os.makedirs(iteration_dir, exist_ok=True)
                
                events_file = os.path.join(iteration_dir, 'events.csv')
                
                # Verificar se arquivo existe para decidir se escrever header
                file_exists = os.path.exists(events_file)
                
                with open(events_file, 'a', newline='', encoding='utf-8') as csvfile:
                    import csv
                    fieldnames = [
                        'event_time_hours', 'real_time_seconds', 
                        'component_type', 'component_name', 'failure_type',
                        'recovery_time_seconds', 'system_available', 'available_pods',
                        'required_pods', 'availability_percentage', 'downtime_duration', 'cumulative_downtime'
                    ]
                    
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    # Escrever header apenas se arquivo é novo
                    if not file_exists:
                        writer.writeheader()
                    
                    writer.writerow(event_record)
                    
                print(f"💾 Evento salvo: {event_record['failure_type']} em {event_record['component_name']}")
                    
        except Exception as e:
            print(f"⚠️ Erro ao salvar evento incremental: {e}")
    
    def _save_iteration_progress_realtime(self, current_time: float, total_available_time: float, duration_hours: float, events_count: int):
        """
        Salva progresso da iteração atual em tempo real no arquivo statistics.csv.
        
        Args:
            current_time: Tempo simulado atual em horas
            total_available_time: Tempo total disponível até agora
            duration_hours: Duração total da iteração
            events_count: Número de eventos processados até agora
        """
        try:
            if hasattr(self.csv_reporter, '_simulation_base_dir'):
                iteration_dir = os.path.join(self.csv_reporter._simulation_base_dir, f'ITERACAO{self.current_iteration}')
                
                # Criar diretório da iteração se não existir
                os.makedirs(iteration_dir, exist_ok=True)
                
                statistics_file = os.path.join(iteration_dir, 'statistics.csv')
                
                # Calcular disponibilidade atual
                current_availability = (total_available_time / current_time * 100) if current_time > 0 else 100.0
                
                # Calcular tempo médio de recuperação (se houver eventos)
                mean_recovery_time = 0.0
                total_downtime = current_time - total_available_time
                
                # Dados das estatísticas seguindo o padrão existente
                statistics_data = [
                    ('iteration', self.current_iteration),
                    ('duration_hours', duration_hours),
                    ('current_time_hours', current_time),
                    ('total_failures', events_count),
                    ('availability_percentage', current_availability),
                    ('total_downtime', total_downtime),
                    ('mean_recovery_time', mean_recovery_time)
                ]
                
                # Reescrever arquivo completamente com dados atualizados
                with open(statistics_file, 'w', newline='', encoding='utf-8') as csvfile:
                    import csv
                    writer = csv.writer(csvfile)
                    writer.writerow(['metric', 'value'])  # Header
                    writer.writerows(statistics_data)
                    
                print(f"📊 Estatísticas atualizadas: {events_count} eventos, {current_availability:.1f}% disponibilidade")
                    
        except Exception as e:
            print(f"⚠️ Erro ao salvar progresso da iteração: {e}")
    
    def _save_iteration_incremental(self, iteration: int, iteration_results: Dict):
        """
        Salva resultados da iteração incrementalmente.
        
        Args:
            iteration: Número da iteração
            iteration_results: Dados da iteração
        """
        try:
            # Salvar no CSV de iterações
            if hasattr(self.csv_reporter, '_simulation_base_dir'):
                iterations_file = os.path.join(self.csv_reporter._simulation_base_dir, 'iterations_incremental.csv')
                
                # Verificar se arquivo existe
                file_exists = os.path.exists(iterations_file)
                
                with open(iterations_file, 'a', newline='', encoding='utf-8') as csvfile:
                    import csv
                    fieldnames = [
                        'iteration', 'duration_hours', 'total_available_time',
                        'availability_percentage', 'total_failures', 'timestamp'
                    ]
                    
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    # Escrever header apenas se arquivo é novo
                    if not file_exists:
                        writer.writeheader()
                    
                    # Dados da iteração
                    row_data = {
                        'iteration': iteration,
                        'duration_hours': iteration_results['duration_hours'],
                        'total_available_time': iteration_results['total_available_time'],
                        'availability_percentage': iteration_results['availability_percentage'],
                        'total_failures': iteration_results['total_failures'],
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    writer.writerow(row_data)
                    
            print(f"💾 Iteração {iteration} salva incrementalmente")
                    
        except Exception as e:
            print(f"⚠️ Erro ao salvar iteração incremental: {e}")
    
    def _save_experiment_configuration_interrupt(self, all_results: List[Dict]) -> Dict:
        """
        Salva configuração do experimento durante interrupção.
        """
        return self._save_experiment_configuration(all_results)
    
    def _save_iterations_csv_interrupt(self, all_results: List[Dict]):
        """
        Salva CSV de iterações durante interrupção.
        """
        try:
            simulation_dir = self.csv_reporter._simulation_base_dir
            iterations_filename = os.path.join(simulation_dir, 'experiment_iterations.csv')
            
            import csv
            with open(iterations_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'iteration', 'duration_hours', 'total_available_time',
                    'availability_percentage', 'total_failures', 'timestamp'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, result in enumerate(all_results, 1):
                    writer.writerow({
                        'iteration': i,
                        'duration_hours': result['duration_hours'],
                        'total_available_time': result['total_available_time'],
                        'availability_percentage': result['availability_percentage'],
                        'total_failures': result['total_failures'],
                        'timestamp': datetime.now().isoformat()
                    })
                    
        except Exception as e:
            print(f"⚠️ Erro ao salvar iterations CSV: {e}")
    
    def _save_components_csv_interrupt(self, component_stats: Dict):
        """
        Salva CSV de componentes durante interrupção.
        """
        try:
            simulation_dir = self.csv_reporter._simulation_base_dir
            components_filename = os.path.join(simulation_dir, 'experiment_components.csv')
            
            import csv
            with open(components_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'component_name', 'component_type', 'mttf_configured',
                    'failures_mean', 'failures_std', 'mttr_mean', 'mttr_std',
                    'downtime_mean', 'downtime_std', 'observed_failure_rate',
                    'total_failures'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for comp_name, stats in component_stats.items():
                    writer.writerow({
                        'component_name': comp_name,
                        'component_type': next((c.component_type for c in self.components if c.name == comp_name), 'unknown'),
                        'mttf_configured': stats['mttf_configured'],
                        'failures_mean': stats['failures_mean'],
                        'failures_std': stats['failures_std'],
                        'mttr_mean': stats['mttr_mean'],
                        'mttr_std': stats['mttr_std'],
                        'downtime_mean': stats['downtime_mean'],
                        'downtime_std': stats['downtime_std'],
                        'observed_failure_rate': stats['observed_failure_rate'],
                        'total_failures': stats['total_failures']
                    })
                    
        except Exception as e:
            print(f"⚠️ Erro ao salvar components CSV: {e}")
    
    def _save_all_events_csv_interrupt(self, all_results: List[Dict]):
        """
        Salva CSV de todos os eventos durante interrupção.
        """
        try:
            simulation_dir = self.csv_reporter._simulation_base_dir
            events_filename = os.path.join(simulation_dir, 'experiment_all_events.csv')
            
            import csv
            with open(events_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'iteration', 'event_time_hours', 'real_time_seconds',
                    'component_type', 'component_name', 'failure_type',
                    'recovery_time_seconds', 'system_available', 'available_pods',
                    'required_pods', 'availability_percentage', 'downtime_duration',
                    'cumulative_downtime'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, result in enumerate(all_results, 1):
                    for event in result.get('event_records', []):
                        event_row = dict(event)
                        event_row['iteration'] = i
                        writer.writerow(event_row)
                        
        except Exception as e:
            print(f"⚠️ Erro ao salvar events CSV: {e}")
    
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
                        if self.is_aws_mode and self.aws_injector:
                            success, _ = self.aws_injector.kill_all_processes(pod_name)
                            print(f"  🎯 Comando AWS: kill all processes via SSH")
                        else:
                            success = self.pod_injector.kill_all_processes(pod_name)
                            print(f"  🎯 Comando: kubectl exec {pod_name} -- kill -9 -1")
                    elif failure_method == "kill_init_process":
                        if self.is_aws_mode and self.aws_injector:
                            success, _ = self.aws_injector.kill_init_process(pod_name)
                            print(f"  🎯 Comando AWS: kill init process via SSH")
                        else:
                            success = self.pod_injector.kill_init_process(pod_name)
                            print(f"  🎯 Comando: kubectl exec {pod_name} -- kill -9 1")
                    else:
                        # Fallback para kill_all_processes
                        if self.is_aws_mode and self.aws_injector:
                            success, _ = self.aws_injector.kill_all_processes(pod_name)
                            print(f"  🎯 Comando AWS (fallback): kill all processes via SSH")
                        else:
                            success = self.pod_injector.kill_all_processes(pod_name)
                            print(f"  🎯 Comando (fallback): kubectl exec {pod_name} -- kill -9 -1")
                else:
                    print(f"  ❌ Pod {component.name} não encontrado")
                    return False
                    
            elif component.component_type == "node":
                # Executar método escolhido aleatoriamente para nodes
                if failure_method == "kill_worker_node_processes":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_worker_node_processes(component.name)
                        print(f"  🎯 Comando AWS: kill worker processes via SSH")
                    else:
                        success, _ = self.node_injector.kill_worker_node_processes(component.name)
                        print(f"  🎯 Falha injetada no node: {component.name} (kill worker processes)")
                elif failure_method == "kill_kubelet":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_kubelet(component.name)
                        print(f"  🎯 Comando AWS: kill kubelet via SSH")
                    else:
                        success, _ = self.control_plane_injector.kill_kubelet(component.name)
                        print(f"  🎯 Falha injetada no node: {component.name} (kill kubelet)")
                elif failure_method == "delete_kube_proxy":
                    print(f"  🔄 Iniciando delete_kube_proxy para {component.name}...")
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.delete_kube_proxy_pod(component.name)
                        print(f"  🎯 Comando AWS: delete kube-proxy via SSH")
                    else:
                        success, command = self.control_plane_injector.delete_kube_proxy_pod(component.name)
                        if success:
                            print(f"  ✅ Falha injetada no node: {component.name} (delete kube-proxy)")
                        else:
                            print(f"  ⚠️ Falha parcial no node: {component.name} (delete kube-proxy) - continuando...")
                            success = True  # Não parar simulação por falha no kube-proxy
                    print(f"  🔄 Finalizou delete_kube_proxy para {component.name}")
                elif failure_method == "restart_containerd":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.restart_containerd(component.name)
                        print(f"  🎯 Comando AWS: restart containerd via SSH")
                    else:
                        success, _ = self.control_plane_injector.restart_containerd(component.name)
                        print(f"  🎯 Falha injetada no node: {component.name} (restart containerd)")
                elif failure_method == "shutdown_worker_node":
                    if self.is_aws_mode and self.aws_injector:
                        # Para AWS, usar restart em vez de shutdown específico
                        success, _ = self.aws_injector.kill_worker_node_processes(component.name)
                        print(f"  🎯 Comando AWS: shutdown worker node via SSH (usando kill_worker_node_processes)")
                    else:
                        # Lógica especial para shutdown de VM
                        success = self._handle_shutdown_worker_node(component.name)
                        print(f"  🎯 Falha injetada no node: {component.name} (shutdown VM)")
                else:
                    # Fallback
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_worker_node_processes(component.name)
                        print(f"  🎯 Comando AWS (fallback): kill worker processes via SSH")
                    else:
                        success, _ = self.node_injector.kill_worker_node_processes(component.name)
                        print(f"  🎯 Falha injetada no node: {component.name} (fallback)")
                
            elif component.component_type == "control_plane":
                # Executar método escolhido aleatoriamente para control plane
                if failure_method == "kill_control_plane_processes":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_control_plane_processes(component.name)
                        print(f"  🎯 Comando AWS: kill control plane processes via SSH")
                    else:
                        success = self.node_injector.kill_control_plane_processes(component.name)
                        print(f"  🎯 Falha no control plane: {component.name} (kill all processes)")
                elif failure_method == "kill_kube_apiserver":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_kube_apiserver(component.name)
                        print(f"  🎯 Comando AWS: kill apiserver via SSH")
                    else:
                        success = self.control_plane_injector.kill_kube_apiserver(component.name)
                        print(f"  🎯 Falha no control plane: {component.name} (kill apiserver)")
                elif failure_method == "kill_kube_controller_manager":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_kube_controller_manager(component.name)
                        print(f"  🎯 Comando AWS: kill controller-manager via SSH")
                    else:
                        success = self.control_plane_injector.kill_kube_controller_manager(component.name)
                        print(f"  🎯 Falha no control plane: {component.name} (kill controller-manager)")
                elif failure_method == "kill_kube_scheduler":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_kube_scheduler(component.name)
                        print(f"  🎯 Comando AWS: kill scheduler via SSH")
                    else:
                        success = self.control_plane_injector.kill_kube_scheduler(component.name)
                        print(f"  🎯 Falha no control plane: {component.name} (kill scheduler)")
                elif failure_method == "kill_etcd":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_etcd(component.name)
                        print(f"  🎯 Comando AWS: kill etcd via SSH")
                    else:
                        success = self.control_plane_injector.kill_etcd(component.name)
                        print(f"  🎯 Falha no control plane: {component.name} (kill etcd)")
                elif failure_method == "restart_containerd":
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.restart_containerd(component.name)
                        print(f"  🎯 Comando AWS: restart containerd via SSH")
                    else:
                        success = self.control_plane_injector.restart_containerd(component.name)
                        print(f"  🎯 Falha no control plane: {component.name} (restart containerd)")
                else:
                    # Fallback
                    if self.is_aws_mode and self.aws_injector:
                        success, _ = self.aws_injector.kill_control_plane_processes(component.name)
                        print(f"  🎯 Comando AWS (fallback): kill control plane processes via SSH")
                    else:
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
                        
                        # Aplicar limites de pods após recuperação de componente
                        print(f"  🔍 Verificando limites de pods após recuperação de {component.name}...")
                        self._monitor_and_enforce_pod_limits(verbose=False)
                        
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
                        
                        # Aplicar limites de pods após recuperação de node/control plane
                        print(f"  🔍 Verificando limites de pods após recuperação de {component.name}...")
                        self._monitor_and_enforce_pod_limits(verbose=False)
                        
                        return recovery_time
                    else:
                        # Apps ainda não funcionando, verificar node status como informação adicional
                        node_ready = self.health_checker.is_node_ready(component.name)
                        node_status = "Ready" if node_ready else "NotReady"
                        
                        print(f"  ⏳ Apps ainda recuperando (node: {node_status}): {', '.join(apps_status)}")
                        
                        # FALLBACK: Se todas as apps falharam no HTTP mas node está Ready e tempo > 10min, aceitar
                        if node_ready and (time.time() - start_time) > 600:  # 10 minutos
                            print(f"  ⚠️ FALLBACK: Node Ready há >10min mas apps não respondem HTTP")
                            recovery_time = time.time() - start_time
                            print(f"  ✅ {component.name} recuperado em {recovery_time:.1f}s (fallback: node Ready)")
                            component.current_status = 'healthy'
                            
                            # Aplicar limites de pods após fallback de recuperação
                            print(f"  🔍 Verificando limites de pods após fallback de {component.name}...")
                            self._monitor_and_enforce_pod_limits(verbose=False)
                            
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
        Executa simulação principal com salvamento incremental e suporte a Ctrl+C.
        
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
        
        # Inicializar estrutura para salvamento incremental
        self.all_results = []
        
        # Garantir que o diretório de simulação seja criado com estrutura hierárquica
        if not hasattr(self.csv_reporter, '_simulation_base_dir'):
            from datetime import datetime
            now = datetime.now()
            year = now.strftime('%Y')
            month = now.strftime('%m')
            day = now.strftime('%d')
            timestamp = now.strftime('%H%M%S')
            
            # Criar estrutura: simulation/YYYY/MM/DD/HHMMSS/
            base_dir = os.path.join('./simulation', year, month, day, timestamp)
            os.makedirs(base_dir, exist_ok=True)
            self.csv_reporter._simulation_base_dir = base_dir
            print(f"📁 Diretório de simulação: {base_dir}")
        
        try:
            for iteration in range(1, iterations + 1):
                # Verificar se foi interrompido
                if self.simulation_interrupted:
                    break
                    
                print(f"🔄 === ITERAÇÃO {iteration}/{iterations} ===")
                self.current_iteration = iteration
                
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
                iteration_results = self._run_single_iteration(duration_hours, save_incremental=True)
                self.all_results.append(iteration_results)
                
                # Salvar iteração incrementalmente
                self._save_iteration_incremental(iteration, iteration_results)
                
                # Salvar CSV da iteração individual (método existente)
                self._save_iteration_results(iteration, iteration_results)
                
                print(f"✅ Iteração {iteration} concluída")
                print(f"📈 Disponibilidade: {iteration_results['availability_percentage']:.2f}%")
                print()
        
        except KeyboardInterrupt:
            # Já tratado pelo signal handler
            return
        
        # Gerar relatório final apenas se não foi interrompido
        if not self.simulation_interrupted:
            self._generate_final_report(self.all_results)
    
    def _run_single_iteration(self, duration_hours: float, save_incremental: bool = False) -> Dict:
        """
        Executa uma iteração da simulação com opção de salvamento incremental.
        
        Args:
            duration_hours: Duração em horas simuladas
            save_incremental: Se True, salva eventos incrementalmente
            
        Returns:
            Resultados da iteração
        """
        # Aplicar limites de pods no início da iteração
        print(f"🔍 Verificando limites de pods no início da iteração {self.current_iteration}...")
        self._monitor_and_enforce_pod_limits(verbose=True)
        
        start_real_time = time.time()
        total_available_time = 0.0
        last_check_time = 0.0
        event_records = []  # Lista para registrar eventos para o CSV
        
        while self.current_simulated_time < duration_hours and self.event_queue:
            # Pegar próximo evento
            next_event = heapq.heappop(self.event_queue)
            
            # Se o próximo evento excede a duração, parar e contabilizar apenas até a duração
            if next_event.time_hours > duration_hours:
                # Contabilizar tempo disponível do último check até o fim da simulação
                time_delta = duration_hours - last_check_time
                system_was_available = self.check_system_availability()
                if system_was_available:
                    total_available_time += time_delta
                
                # Retornar o evento para a fila (não processado)
                heapq.heappush(self.event_queue, next_event)
                break
            
            # Verificar disponibilidade no período anterior ao evento
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
                
                # Salvar evento incrementalmente se solicitado
                if save_incremental:
                    self._save_event_incremental(event_record)
                    
                    # Salvar progresso da iteração em tempo real
                    self._save_iteration_progress_realtime(
                        current_time=self.current_simulated_time,
                        total_available_time=total_available_time,
                        duration_hours=duration_hours,
                        events_count=len(event_records)
                    )
                
                print(f"📝 Evento registrado: {failure_method} em {next_event.component.name}")
                
                # Gerar próxima falha para este componente
                next_failure_time = self.generate_next_failure_time(next_event.component)
                new_event = FailureEvent(next_failure_time, next_event.component)
                heapq.heappush(self.event_queue, new_event)
                
                print(f"📅 Próxima falha de {next_event.component.name}: {next_failure_time:.1f}h")
            
            print()
        
        # Contabilizar o período final APENAS se nenhum evento foi processado 
        # (todos os eventos estavam além da duração)
        if last_check_time == 0.0:
            # Nenhum evento foi processado - sistema ficou disponível toda a duração
            system_available_full = self.check_system_availability()
            if system_available_full:
                total_available_time = duration_hours
            print(f"📊 Nenhum evento processado - período completo: {duration_hours}h (disponível: {system_available_full})")
        
        print(f"📊 Resumo da iteração:")
        print(f"  • Duração total: {duration_hours}h")
        print(f"  • Tempo disponível: {total_available_time:.3f}h")
        print(f"  • Tempo indisponível: {duration_hours - total_available_time:.3f}h")
        
        # Calcular disponibilidade final
        availability_percentage = (total_available_time / duration_hours) * 100 if duration_hours > 0 else 0.0
        
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
        Gera relatório final com todas as iterações incluindo estatísticas detalhadas.
        
        Args:
            all_results: Lista com resultados de todas as iterações
        """
        print("📋 === RELATÓRIO FINAL ===")
        
        if not all_results:
            print("❌ Nenhum resultado para reportar")
            return
        
        # Estatísticas agregadas básicas
        total_iterations = len(all_results)
        availabilities = [r['availability_percentage'] for r in all_results]
        avg_availability = sum(availabilities) / total_iterations
        min_availability = min(availabilities)
        max_availability = max(availabilities)
        total_failures = sum(r['total_failures'] for r in all_results)
        
        # Calcular desvio padrão da disponibilidade
        import statistics
        std_availability = statistics.stdev(availabilities) if len(availabilities) > 1 else 0.0
        
        print(f"🎯 Simulação de {total_iterations} iterações concluída")
        print(f"📊 Disponibilidade Média: {avg_availability:.2f}% (±{std_availability:.2f}%)")
        print(f"📉 Disponibilidade Mínima: {min_availability:.2f}%")
        print(f"📈 Disponibilidade Máxima: {max_availability:.2f}%")
        print(f"💥 Total de Falhas: {total_failures}")
        print()
        
        # Salvar configuração MTTF/MTTR usada no experimento
        config_data = self._save_experiment_configuration(all_results)
        
        # Calcular estatísticas detalhadas por componente
        component_stats = self._calculate_component_statistics(all_results)
        
        # Relatório por componente com estatísticas
        print("🔧 === ESTATÍSTICAS DETALHADAS POR COMPONENTE ===")
        for component_name, stats in component_stats.items():
            print(f"  📦 {component_name}:")
            print(f"    • MTTF configurado: {stats['mttf_configured']}h")
            print(f"    • Falhas por iteração: {stats['failures_mean']:.2f} (±{stats['failures_std']:.2f})")
            print(f"    • MTTR médio: {stats['mttr_mean']:.2f}s (±{stats['mttr_std']:.2f}s)")
            print(f"    • Downtime total médio: {stats['downtime_mean']:.4f}h (±{stats['downtime_std']:.4f}h)")
            print(f"    • Taxa de falha observada: {stats['observed_failure_rate']:.4f} falhas/h")
        
        # Salvar CSVs detalhados
        self._save_detailed_statistics(all_results, component_stats, config_data)
        
        print()
        print("📊 === VERIFICAÇÃO DOS CÁLCULOS ===")
        self._verify_calculations(all_results, component_stats)
    
    def _save_experiment_configuration(self, all_results: List[Dict]) -> Dict:
        """
        Salva a configuração MTTF/MTTR usada no experimento no diretório da simulação.
        
        Returns:
            Dicionário com configuração salva
        """
        from datetime import datetime
        import json
        import os
        
        # Obter diretório base da simulação do csv_reporter
        simulation_base_dir = getattr(self.csv_reporter, '_simulation_base_dir', './simulation')
        
        # Criar configuração detalhada
        config_data = {
            'experiment_info': {
                'timestamp': datetime.now().isoformat(),
                'total_iterations': len(all_results),
                'duration_per_iteration': all_results[0]['duration_hours'] if all_results else 0,
                'total_simulation_time': len(all_results) * all_results[0]['duration_hours'] if all_results else 0,
                'real_delay_between_failures': self.real_delay_between_failures
            },
            'availability_criteria': dict(self.availability_criteria),
            'component_configuration': {},
            'failure_methods_available': {},
            'config_simples_used': hasattr(self, '_config_simples')
        }
        
        # Salvar configuração de cada componente
        for component in self.components:
            config_data['component_configuration'][component.name] = {
                'component_type': component.component_type,
                'mttf_hours': component.mttf_hours,
                'mttr_configured': getattr(component, 'mttr_hours', 'auto-healing'),
                'failure_methods': component.available_failure_methods
            }
            
            # Agrupar métodos por tipo
            comp_type = component.component_type
            if comp_type not in config_data['failure_methods_available']:
                config_data['failure_methods_available'][comp_type] = set()
            config_data['failure_methods_available'][comp_type].update(component.available_failure_methods)
        
        # Converter sets para listas para JSON
        for comp_type in config_data['failure_methods_available']:
            config_data['failure_methods_available'][comp_type] = list(config_data['failure_methods_available'][comp_type])
        
        # Salvar ConfigSimples se foi usado
        if hasattr(self, '_config_simples'):
            config_simples_file = self._save_config_simples_to_simulation_dir(simulation_base_dir)
            config_data['config_simples_file'] = os.path.basename(config_simples_file) if config_simples_file else None
        
        # Salvar arquivo de configuração no diretório da simulação
        config_filename = os.path.join(simulation_base_dir, 'experiment_config.json')
        
        try:
            with open(config_filename, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"💾 Configuração do experimento salva: {config_filename}")
        except Exception as e:
            print(f"⚠️ Erro ao salvar configuração: {e}")
        
        return config_data
    
    def _calculate_component_statistics(self, all_results: List[Dict]) -> Dict:
        """
        Calcula estatísticas detalhadas para cada componente.
        
        Args:
            all_results: Resultados de todas as iterações
            
        Returns:
            Dicionário com estatísticas por componente
        """
        import statistics
        from collections import defaultdict
        
        # Inicializar estrutura de dados corretamente
        def create_component_data():
            return {
                'failures_per_iteration': [],
                'mttr_times': [],
                'downtime_per_iteration': [],
                'mttf_configured': 0.0
            }
        
        component_data = defaultdict(create_component_data)
        
        # Coletar dados de cada iteração
        for result in all_results:
            # Inicializar contadores para esta iteração
            iteration_failures = defaultdict(int)
            iteration_downtime = defaultdict(float)
            
            # Processar eventos da iteração
            for event in result.get('event_records', []):
                comp_name = event['component_name']
                iteration_failures[comp_name] += 1
                iteration_downtime[comp_name] += event.get('downtime_duration', 0)
                component_data[comp_name]['mttr_times'].append(event.get('recovery_time_seconds', 0))
            
            # Processar componentes da iteração  
            for comp_info in result.get('components', []):
                comp_name = comp_info['name']
                component_data[comp_name]['failures_per_iteration'].append(iteration_failures[comp_name])
                component_data[comp_name]['downtime_per_iteration'].append(iteration_downtime[comp_name])
        
        # Buscar MTTF configurado de cada componente
        for component in self.components:
            if component.name in component_data:
                component_data[component.name]['mttf_configured'] = component.mttf_hours
        
        # Calcular estatísticas
        component_stats = {}
        for comp_name, data in component_data.items():
            failures_list = data['failures_per_iteration']
            mttr_list = data['mttr_times']
            downtime_list = data['downtime_per_iteration']
            
            # Calcular médias e desvios padrão
            failures_mean = statistics.mean(failures_list) if failures_list else 0
            failures_std = statistics.stdev(failures_list) if len(failures_list) > 1 else 0
            
            mttr_mean = statistics.mean(mttr_list) if mttr_list else 0
            mttr_std = statistics.stdev(mttr_list) if len(mttr_list) > 1 else 0
            
            downtime_mean = statistics.mean(downtime_list) if downtime_list else 0
            downtime_std = statistics.stdev(downtime_list) if len(downtime_list) > 1 else 0
            
            # Calcular taxa de falha observada (falhas por hora simulada)
            total_failures = sum(failures_list)
            total_sim_time = len(all_results) * all_results[0]['duration_hours'] if all_results else 1
            observed_failure_rate = total_failures / total_sim_time if total_sim_time > 0 else 0
            
            component_stats[comp_name] = {
                'mttf_configured': data['mttf_configured'],
                'failures_mean': failures_mean,
                'failures_std': failures_std,
                'failures_list': failures_list,
                'mttr_mean': mttr_mean,
                'mttr_std': mttr_std,
                'mttr_list': mttr_list,
                'downtime_mean': downtime_mean,
                'downtime_std': downtime_std,
                'downtime_list': downtime_list,
                'observed_failure_rate': observed_failure_rate,
                'total_failures': total_failures
            }
        
        return component_stats
    
    def _apply_config_simples(self, config_simples):
        """
        Aplica configuração do ConfigSimples aos componentes descobertos.
        Mantém os pods reais descobertos e apenas aplica MTTFs, em vez de criar pods fictícios.
        
        Args:
            config_simples: Instância do ConfigSimples
        """
        print("🔧 Aplicando ConfigSimples aos componentes descobertos...")
        
        # Armazenar referência para uso em outros métodos
        self._config_simples = config_simples
        
        # Inicializar limitador de pods
        self.pod_limiter = PodLimiter(config_simples)
        print("📊 Limitador de pods inicializado")
        
        # Aplicar limites de pods imediatamente
        self.pod_limiter.print_pod_status()
        print("🚫 Aplicando limites de pods...")
        limit_results = self.pod_limiter.enforce_pod_limits()
        
        for worker, success in limit_results.items():
            if success:
                print(f"✅ Limites aplicados em {worker}")
            else:
                print(f"❌ Falha ao aplicar limites em {worker}")
        
        # Descobrir worker nodes e pods reais disponíveis
        available_worker_nodes = []
        control_plane_nodes = []
        real_pods = []
        
        for component in self.components:
            if component.component_type == "node":
                available_worker_nodes.append(component.name)
            elif component.component_type == "control_plane":
                control_plane_nodes.append(component.name)
            elif component.component_type == "pod":
                real_pods.append(component.name)
        
        print(f"📋 Worker nodes disponíveis descobertos: {available_worker_nodes}")
        print(f"📋 Control plane nodes descobertos: {control_plane_nodes}")
        print(f"📋 Pods reais descobertos: {real_pods}")
        
        # MANTER OS PODS REAIS - não criar pods fictícios
        # Apenas aplicar MTTF do ConfigSimples aos componentes existentes
        for component in self.components:
            if component.component_type == "pod":
                component.mttf_hours = config_simples.get_mttf('pod')
            elif component.component_type == "node":
                component.mttf_hours = config_simples.get_mttf('worker_node')
            elif component.component_type == "control_plane":
                component.mttf_hours = config_simples.get_mttf('control_plane')
            
            print(f"  ✅ {component.name} ({component.component_type}): MTTF={component.mttf_hours}h")
        
        # Extrair nomes das aplicações dos pods reais para critérios de disponibilidade
        discovered_apps = set()
        for pod_name in real_pods:
            # Extrair nome da aplicação do pod (ex: "bar-app" de "bar-app-6664549c89-n7kz2")
            if '-' in pod_name:
                app_name = pod_name.split('-')[0] + '-app'  # Assumindo padrão "app-name-hash-id"
                if app_name.endswith('-app-app'):  # Evitar duplicação de "-app"
                    app_name = app_name[:-4]  # Remove o "-app" extra
                discovered_apps.add(app_name)
        
        # Usar aplicações descobertas dos pods reais em vez das fictícias do ConfigSimples
        if discovered_apps:
            self.availability_criteria = {app: 1 for app in discovered_apps}
            print(f"🎯 Critérios de disponibilidade baseados nos pods reais: {self.availability_criteria}")
        else:
            # Fallback para configuração do ConfigSimples se não conseguir descobrir
            if hasattr(config_simples, 'applications'):
                self.availability_criteria = config_simples.get_availability_criteria()
                print(f"🎯 Critérios de disponibilidade (fallback ConfigSimples): {self.availability_criteria}")
        
        # Salvar referência do config_simples para usar posteriormente
        self._config_simples = config_simples
        print("✅ ConfigSimples aplicado com sucesso (mantendo pods reais)")
        print(f"📊 Total de componentes: {len(self.components)}")
    
    def _monitor_and_enforce_pod_limits(self, verbose: bool = False):
        """
        Monitora e aplica limites de pods durante a simulação.
        
        Args:
            verbose: Se True, exibe informações detalhadas
        """
        if not hasattr(self, 'pod_limiter') or self.pod_limiter is None:
            if verbose:
                print("⚠️ PodLimiter não disponível")
            return
            
        try:
            status = self.pod_limiter.check_pod_limits()
            violations = []
            
            for worker_name, worker_status in status.items():
                if not worker_status['within_limit']:
                    violations.append(worker_name)
                    if verbose:
                        print(f"🚨 Limite violado em {worker_name}: {worker_status['app_pods']} > {worker_status['limit']}")
            
            if violations:
                print(f"🚫 Aplicando limites em {len(violations)} worker(s): {violations}")
                limit_results = self.pod_limiter.enforce_pod_limits()
                
                for worker, success in limit_results.items():
                    if success:
                        print(f"  ✅ Limites aplicados em {worker}")
                    else:
                        print(f"  ❌ Falha ao aplicar limites em {worker}")
            elif verbose:
                print(f"✅ Todos os workers respeitam os limites de pods")
                
        except Exception as e:
            print(f"⚠️ Erro ao monitorar limites de pods: {e}")
    
    def _save_config_simples_to_simulation_dir(self, simulation_base_dir: str):
        """
        Salva a configuração ConfigSimples no diretório da simulação.
        
        Args:
            simulation_base_dir: Diretório base da simulação
        """
        if hasattr(self, '_config_simples'):
            import os
            config_file = os.path.join(simulation_base_dir, 'config_simples_used.json')
            saved_file = self._config_simples.save_config(config_file)
            print(f"💾 ConfigSimples salvo em: {saved_file}")
            return saved_file
        return None
    
    def _save_detailed_statistics(self, all_results: List[Dict], component_stats: Dict, config_data: Dict):
        """
        Salva CSVs detalhados com estatísticas por iteração e componente no diretório da simulação.
        
        Args:
            all_results: Resultados de todas as iterações
            component_stats: Estatísticas por componente
            config_data: Configuração do experimento
        """
        import csv
        import os
        
        # Obter diretório base da simulação do csv_reporter
        simulation_base_dir = getattr(self.csv_reporter, '_simulation_base_dir', './simulation')
        
        # 1. CSV de estatísticas por iteração
        iterations_filename = os.path.join(simulation_base_dir, 'experiment_iterations.csv')
        try:
            with open(iterations_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'iteration', 'duration_hours', 'availability_percentage', 
                    'total_failures', 'total_available_time', 'total_downtime'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, result in enumerate(all_results, 1):
                    total_downtime = sum(
                        event.get('downtime_duration', 0) 
                        for event in result.get('event_records', [])
                    )
                    
                    writer.writerow({
                        'iteration': i,
                        'duration_hours': result['duration_hours'],
                        'availability_percentage': result['availability_percentage'],
                        'total_failures': result['total_failures'],
                        'total_available_time': result['total_available_time'],
                        'total_downtime': total_downtime
                    })
            
            print(f"💾 Estatísticas por iteração salvas: {iterations_filename}")
        except Exception as e:
            print(f"⚠️ Erro ao salvar estatísticas por iteração: {e}")
        
        # 2. CSV de estatísticas por componente
        components_filename = os.path.join(simulation_base_dir, 'experiment_components.csv')
        try:
            with open(components_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'component_name', 'component_type', 'mttf_configured', 
                    'failures_mean', 'failures_std', 'mttr_mean_seconds', 'mttr_std_seconds',
                    'downtime_mean_hours', 'downtime_std_hours', 'observed_failure_rate',
                    'total_failures', 'theoretical_failure_rate'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for comp_name, stats in component_stats.items():
                    # Taxa teórica de falha (1/MTTF)
                    theoretical_rate = 1/stats['mttf_configured'] if stats['mttf_configured'] > 0 else 0
                    
                    writer.writerow({
                        'component_name': comp_name,
                        'component_type': self._get_component_type(comp_name),
                        'mttf_configured': stats['mttf_configured'],
                        'failures_mean': stats['failures_mean'],
                        'failures_std': stats['failures_std'],
                        'mttr_mean_seconds': stats['mttr_mean'],
                        'mttr_std_seconds': stats['mttr_std'],
                        'downtime_mean_hours': stats['downtime_mean'],
                        'downtime_std_hours': stats['downtime_std'],
                        'observed_failure_rate': stats['observed_failure_rate'],
                        'total_failures': stats['total_failures'],
                        'theoretical_failure_rate': theoretical_rate
                    })
            
            print(f"💾 Estatísticas por componente salvas: {components_filename}")
        except Exception as e:
            print(f"⚠️ Erro ao salvar estatísticas por componente: {e}")
        
        # 3. CSV consolidado de todos os eventos
        events_filename = os.path.join(simulation_base_dir, 'experiment_all_events.csv')
        try:
            all_events = []
            for i, result in enumerate(all_results, 1):
                for event in result.get('event_records', []):
                    event_copy = event.copy()
                    event_copy['iteration'] = i
                    all_events.append(event_copy)
            
            if all_events:
                with open(events_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = list(all_events[0].keys())
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_events)
                
                print(f"💾 Todos os eventos salvos: {events_filename}")
            else:
                print("⚠️ Nenhum evento para salvar")
        except Exception as e:
            print(f"⚠️ Erro ao salvar todos os eventos: {e}")
    
    def _get_component_type(self, component_name: str) -> str:
        """Busca o tipo de um componente pelo nome."""
        for component in self.components:
            if component.name == component_name:
                return component.component_type
        return 'unknown'
    
    def _verify_calculations(self, all_results: List[Dict], component_stats: Dict):
        """
        Verifica se os cálculos estão corretos.
        
        Args:
            all_results: Resultados de todas as iterações
            component_stats: Estatísticas por componente
        """
        print("🔍 Verificando consistência dos cálculos...")
        
        # Verificar disponibilidade
        total_sim_time = len(all_results) * all_results[0]['duration_hours'] if all_results else 0
        total_downtime = sum(
            event.get('downtime_duration', 0)
            for result in all_results
            for event in result.get('event_records', [])
        )
        
        expected_uptime = total_sim_time - total_downtime
        expected_availability = (expected_uptime / total_sim_time * 100) if total_sim_time > 0 else 0
        
        calculated_avg = sum(r['availability_percentage'] for r in all_results) / len(all_results) if all_results else 0
        
        print(f"  ✅ Tempo simulado total: {total_sim_time:.2f}h")
        print(f"  ✅ Downtime total: {total_downtime:.4f}h ({total_downtime*3600:.1f}s)")
        print(f"  ✅ Uptime total: {expected_uptime:.4f}h")
        print(f"  ✅ Disponibilidade calculada: {expected_availability:.2f}%")
        print(f"  ✅ Disponibilidade média iterações: {calculated_avg:.2f}%")
        
        # Verificar MTTFs observados vs configurados
        print(f"  📊 Verificação MTTF vs Observado:")
        for comp_name, stats in component_stats.items():
            if stats['total_failures'] > 0:
                observed_mttf = total_sim_time / stats['total_failures']
                configured_mttf = stats['mttf_configured']
                diff_pct = abs(observed_mttf - configured_mttf) / configured_mttf * 100 if configured_mttf > 0 else 0
                
                print(f"    • {comp_name}:")
                print(f"      - MTTF configurado: {configured_mttf:.1f}h")
                print(f"      - MTTF observado: {observed_mttf:.1f}h")
                print(f"      - Diferença: {diff_pct:.1f}%")
        
        print("✅ Verificação de cálculos concluída")
    
    def _handle_shutdown_worker_node(self, node_name: str) -> bool:
        """
        Lógica especial para shutdown de worker node.
        
        1. Desliga o nó
        2. Aguarda MTTR configurado no ConfigSimples (ou 60s se não configurado)
        3. Religa o nó automaticamente (self-healing)
        4. Contabiliza MTTR configurado para estatísticas
        """
        try:
            import time
            
            print(f"  🔌 Desligando worker node: {node_name}")
            
            # 1. Desligar o nó usando node_injector
            shutdown_success, shutdown_command = self.node_injector.shutdown_worker_node(node_name)
            if not shutdown_success:
                print(f"  ❌ Falha ao desligar nó {node_name}")
                return False
            
            # 2. Obter MTTR configurado no ConfigSimples para contabilização
            mttr_hours = 1.0  # Default de 1h simulada
            mttr_seconds_real = 60  # Sempre 60s reais para testes
            
            if hasattr(self, '_config_simples') and self._config_simples:
                mttr_hours = self._config_simples.get_mttr('worker_node')
                if mttr_hours > 0:
                    print(f"  ⚙️ MTTR configurado: {mttr_hours}h simuladas (60s reais)")
                else:
                    print(f"  ⚙️ MTTR padrão: {mttr_hours}h simuladas (60s reais)")
            
            print(f"  ⏱️ Aguardando 60s reais (simulando {mttr_hours}h de downtime)...")
            time.sleep(mttr_seconds_real)
            
            # 3. Religar o nó automaticamente usando node_injector  
            print(f"  � Self-healing: Religando worker node: {node_name}")
            startup_success, startup_command = self.node_injector.start_worker_node(node_name)
            
            if startup_success:
                print(f"  ✅ Worker node {node_name} religado com sucesso")
                return True
            else:
                print(f"  ❌ Falha ao religar nó {node_name}")
                return False
                
        except Exception as e:
            print(f"  ❌ Erro durante shutdown/startup de {node_name}: {e}")
            return False
    
    def _save_iteration_results(self, iteration: int, iteration_results: Dict):
        """Salva resultados de uma iteração individual."""
        try:
            events = iteration_results.get('event_records', [])
            if events:
                # Preparar estatísticas da iteração
                iteration_stats = {
                    'iteration': iteration,
                    'duration_hours': iteration_results.get('duration_hours', 0),
                    'total_failures': len(events),
                    'availability_percentage': iteration_results.get('availability_percentage', 0),
                    'total_downtime': sum(event.get('downtime_duration', 0) for event in events),
                    'mean_recovery_time': sum(event.get('recovery_time_seconds', 0) for event in events) / len(events) if events else 0
                }
                
                # Salvar usando csv_reporter
                self.csv_reporter.save_iteration_results(events, iteration_stats, iteration)
            else:
                print(f"⚠️ Nenhum evento registrado na iteração {iteration}")
                
        except Exception as e:
            print(f"❌ Erro ao salvar iteração {iteration}: {e}")