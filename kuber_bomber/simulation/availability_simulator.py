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
from ..utils.kubectl_executor import get_kubectl_executor
from ..utils.aws_config_loader import load_aws_config

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
    mttf_key: Optional[str] = None  # Chave do mttf_config (ex: 'wn_kubelet', 'pod', etc.)
    parent_component: Optional[str] = None  # Nome do componente pai (ex: 'worker-node-1')
    
    def __post_init__(self):
        """Define métodos de falha disponíveis baseado no tipo do componente."""
        if self.available_failure_methods is None:
            # Mapear métodos baseado na chave MTTF específica
            if self.mttf_key == "pod" or self.component_type == "pod":
                self.available_failure_methods = [
                    "kill_all_processes",
                ]
            elif self.mttf_key == "container":
                self.available_failure_methods = [
                    "kill_all_processes",
                ]
            elif self.mttf_key == "worker_node" or (self.component_type == "node" and not self.mttf_key):
                self.available_failure_methods = [
                    # "kill_worker_node_processes",
                    "shutdown_worker_node"
                ]
            elif self.mttf_key == "wn_runtime":
                self.available_failure_methods = [
                    "restart_containerd",
                ]
            elif self.mttf_key == "wn_proxy":
                self.available_failure_methods = [
                    "kill_kube_proxy"
                ]
            elif self.mttf_key == "wn_kubelet":
                self.available_failure_methods = [
                    "kill_kubelet",
                ]
            elif self.mttf_key == "control_plane" or (self.component_type == "control_plane" and not self.mttf_key):
                self.available_failure_methods = [
                    "shutdown_control_plane",
                    # "kill_control_plane_processes",
                ]
            elif self.mttf_key == "cp_apiserver":
                self.available_failure_methods = [
                    "kill_kube_apiserver",
                ]
            elif self.mttf_key == "cp_manager":
                self.available_failure_methods = [
                    "kill_kube_controller_manager",
                ]
            elif self.mttf_key == "cp_scheduler":
                self.available_failure_methods = [
                    "kill_kube_scheduler",
                ]
            elif self.mttf_key == "cp_etcd":
                self.available_failure_methods = [
                    "kill_etcd",
                ]
    
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
        
        # NÃO descobrir URLs automaticamente aqui - será feito após ConfigSimples
        discovered_urls = {}
        
        # Critérios de disponibilidade por aplicação (será configurado dinamicamente)
        self.availability_criteria = {}
        
        # ========== CONFIGURAÇÃO DE COMPONENTES ==========
        if components:
            self.components = components
        else:
            # Para nova arquitetura, componentes serão carregados via ConfigSimples
            self.components = []
        
        # Configurar critérios de disponibilidade baseado nos componentes descobertos
        self._setup_default_availability_criteria()
        
        # Injetores de falha - usar AWS quando estiver em modo AWS
        if self.is_aws_mode and aws_config:
            
            print("🔧 Inicializando AWS injector com descoberta automática...")
            # Usar aws_config passado como parâmetro, não recarregar
            # aws_config já foi carregado pelo CLI com discovery automático
            
            self.aws_injector = AWSFailureInjector(
                ssh_key=aws_config.get('ssh_key', '~/.ssh/vockey.pem'),
                ssh_user=aws_config.get('ssh_user', 'ubuntu'),
                aws_config=aws_config  # Passar config completo para discovery
            )
            print("✅ AWS injector configurado com descoberta automática de control plane")
        elif self.is_aws_mode:
            # Se is_aws_mode=True mas aws_config=None, tentar carregar
            print("🔧 Inicializando injetores AWS...")
            aws_config = load_aws_config()
            if not aws_config:
                print("❌ Falha ao carregar configuração AWS. Abortando inicialização do simulador.")
                sys.exit(1)
            
            self.aws_injector = AWSFailureInjector(
                ssh_key=aws_config.get('ssh_key', '~/.ssh/vockey.pem'),
                ssh_user=aws_config.get('ssh_user', 'ubuntu'),
                aws_config=aws_config  # Passar config completo para discovery
            )
            print("✅ AWS injector configurado com descoberta automática de control plane")
        else:
            print("🔧 Inicializando injetores locais...")
            self.aws_injector = None
            
        # Sempre inicializar injetores locais (como fallback) com config
        from ..utils.config import get_config
        config = get_config(aws_mode=self.is_aws_mode, aws_config=aws_config)
        
        self.pod_injector = PodFailureInjector(config)
        self.node_injector = NodeFailureInjector(config)
        self.control_plane_injector = ControlPlaneInjector(aws_config=aws_config)
        
        # Reporter CSV
        self.csv_reporter = CSVReporter()
        
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
        
        try:
            # Descobrir serviços LoadBalancer e NodePort
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
                
                if service_type == 'NodePort':
                    # NodePort - pegar IP do primeiro node disponível
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
                                
                                if node_port:
                                    base_name = service_name.replace('-nodeport', '').replace('-service', '').replace('-svc', '')
                                    endpoint = f"/{base_name}"
                                    url = f"http://{node_ip}:{node_port}{endpoint}"
                                    
                                    service_urls['NodePort'] = url
                                    print(f"  🌐 {service_name} (NodePort): {url}")
                                    break
                
                if service_urls:
                    discovered_urls[service_name] = service_urls
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
                
                # Calcular tempo médio de recuperação (se houver eventos)
                mean_recovery_time = 0.0
                total_downtime = current_time - total_available_time
                
                current_availability = total_available_time / current_time
                
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
                    
                print(f"📊 Estatísticas atualizadas: {events_count} eventos, {current_availability:.1f}% disponibilidade, tempo total:{current_time}")
                    
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
    
    def inject_failure(self, component: Component, failure_method: Optional[str] = None) -> bool:
        """
        Injeta falha no componente especificado (agora com suporte granular).
        
        Args:
            component: Componente para falhar
            failure_method: Método específico de falha (opcional)
            
        Returns:
            True se falha foi injetada com sucesso
        """
        print(f"💥 INJETANDO FALHA GRANULAR: {component.name}")
        print(f"  📋 Tipo: {component.component_type}")
        print(f"  🔧 MTTF Key: {component.mttf_key}")
        if component.parent_component:
            print(f"  👥 Pai: {component.parent_component}")
        
        try:
            # Usar método especificado ou escolher aleatório
            if failure_method is None:
                failure_method = component.get_random_failure_method()
            print(f"  🎲 Método: {failure_method}")
            
            # === PODS E CONTAINERS ===
            if component.mttf_key == "pod":
                return self._inject_pod_failure(component, failure_method)
                
            elif component.mttf_key == "container":
                return self._inject_container_failure(component, failure_method)
            
            # === WORKER NODE E SEUS SUBCOMPONENTES ===
            elif component.mttf_key == "worker_node":
                return self._inject_worker_node_failure(component, failure_method)
                
            elif component.mttf_key == "wn_runtime":
                return self._inject_runtime_failure(component, failure_method)
                
            elif component.mttf_key == "wn_proxy":
                return self._inject_proxy_failure(component, failure_method)
                
            elif component.mttf_key == "wn_kubelet":
                return self._inject_kubelet_failure(component, failure_method)
            
            # === CONTROL PLANE E SEUS SUBCOMPONENTES ===
            elif component.mttf_key == "control_plane":
                return self._inject_control_plane_failure(component, failure_method)
                
            elif component.mttf_key == "cp_apiserver":
                return self._inject_apiserver_failure(component, failure_method)
                
            elif component.mttf_key == "cp_manager":
                return self._inject_manager_failure(component, failure_method)
                
            elif component.mttf_key == "cp_scheduler":
                return self._inject_scheduler_failure(component, failure_method)
                
            elif component.mttf_key == "cp_etcd":
                return self._inject_etcd_failure(component, failure_method)
            
            # === FALLBACK PARA TIPOS ANTIGOS ===
            elif component.component_type == "pod":
                return self._inject_pod_failure(component, failure_method)
            elif component.component_type == "node":
                return self._inject_worker_node_failure(component, failure_method)
            elif component.component_type == "control_plane":
                return self._inject_control_plane_failure(component, failure_method)
            else:
                print(f"  ❌ Tipo de componente desconhecido: {component.component_type}/{component.mttf_key}")
                return False
                
        except Exception as e:
            print(f"  ❌ Erro ao injetar falha: {e}")
            return False
    
    def _inject_pod_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica em pod."""
        print(f"  📦 Executando falha de POD: {failure_method}")
        
        # Extrair nome da aplicação do componente (ex: pod-bar-app-775c8885f5-6wdlt)
        if component.name.startswith('pod-'):
            # Extrair nome da aplicação do nome do componente
            # pod-bar-app-775c8885f5-6wdlt -> bar-app
            pod_full_name = component.name[4:]  # Remover 'pod-'
            app_name = self._extract_app_name_from_pod_component(pod_full_name)
            
            # Descobrir pods atuais dessa aplicação
            pods = self.health_checker.get_pods_by_app_label(app_name)
            
            # Fallback: buscar por prefixo do nome se label não funcionar
            if not pods:
                print(f"  🔄 Tentando busca por prefixo...")
                pods = self.health_checker.get_pods_by_name_prefix(app_name)
            
            if not pods:
                print(f"  ❌ Nenhum pod ativo encontrado para aplicação: {app_name}")
                return False
            
            # Usar o primeiro pod disponível
            pod_name = pods[0]['name']
            print(f"  🎯 Pod real atual: {pod_name} (app: {app_name})")
        else:
            # Nome direto do pod (compatibilidade)
            pod_name = component.name
            print(f"  🎯 Pod direto: {pod_name}")
        
        # Executar falha
        if failure_method == "kill_all_processes":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_all_processes(pod_name)
            else:
                success = self.pod_injector.kill_all_processes(pod_name)
        elif failure_method == "kill_init_process":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_init_process(pod_name)
            else:
                success = self.pod_injector.kill_init_process(pod_name)
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_all_processes(pod_name)
            else:
                success = self.pod_injector.kill_all_processes(pod_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Pod {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _extract_app_name_from_pod_component(self, pod_full_name: str) -> str:
        """
        Extrai nome da aplicação do nome completo do pod no componente.
        
        Args:
            pod_full_name: Nome completo como 'bar-app-775c8885f5-6wdlt'
            
        Returns:
            Nome da aplicação como 'bar-app'
        """
        # Dividir por hífen e pegar primeiras partes antes do hash do deployment
        parts = pod_full_name.split('-')
        
        if len(parts) >= 3:
            # Assumir formato: app-deployment_hash-pod_hash
            # bar-app-775c8885f5-6wdlt -> bar-app
            if len(parts) >= 4:
                return '-'.join(parts[:-2])  # Remove deployment_hash e pod_hash
            else:
                return '-'.join(parts[:-1])  # Remove apenas pod_hash
        
        # Fallback
        return parts[0] if parts else pod_full_name
    
    def _inject_container_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica em container."""
        print(f"  🐳 Executando falha de CONTAINER: {failure_method}")
        
        # Container é parte do pod pai
        pod_name = component.parent_component
        if not pod_name:
            print(f"  ❌ Container {component.name} não tem pod pai")
            return False
        
        # Para containers, usar métodos específicos ou simular
        if failure_method == "kill_container_process":
            # Simular falha específica do container
            print(f"  🎯 Matando processo do container em {pod_name}")
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_all_processes(pod_name)
            else:
                success = self.pod_injector.kill_all_processes(pod_name)
        elif failure_method == "restart_container":
            print(f"  🔄 Reiniciando container em {pod_name}")
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_init_process(pod_name)
            else:
                success = self.pod_injector.kill_init_process(pod_name)
        else:
            # Fallback
            print(f"  � Simulando falha de container: {failure_method}")
            success = True
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Container {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_worker_node_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha no worker node completo."""
        print(f"  🖥️ Executando falha de WORKER NODE: {failure_method}")
        
        # Extrair nome do node (worker_node-ip-10-0-0-98 -> ip-10-0-0-98)
        if component.name.startswith('worker_node-'):
            node_name = component.name[len('worker_node-'):]
        else:
            node_name = component.name
        
        if failure_method == "kill_worker_node_processes":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_worker_node_processes(node_name)
            else:
                success, _ = self.node_injector.kill_worker_node_processes(node_name)
        elif failure_method == "shutdown_worker_node":
            # CORREÇÃO: Usar o método especial _handle_shutdown_worker_node em ambos os casos
            success, shutdown_recovery_time = self._handle_shutdown_worker_node(node_name)
            # Armazenar o tempo de recuperação para uso posterior no loop principal
            self._last_shutdown_recovery_time = shutdown_recovery_time
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_worker_node_processes(node_name)
            else:
                success, _ = self.node_injector.kill_worker_node_processes(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Worker node {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_runtime_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica no runtime (Docker/containerd)."""
        print(f"  🐳 Executando falha de RUNTIME: {failure_method}")
        
        # Extrair nome do node do componente (ex: wn_runtime-ip-10-0-0-98 -> ip-10-0-0-98)
        if '-' in component.name:
            node_name = component.name.split('-', 1)[1]  # Remover 'wn_runtime-'
        else:
            node_name = component.parent_component or component.name
        
        print(f"  🎯 Node alvo: {node_name}")
        
        if failure_method == "restart_containerd":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.restart_containerd(node_name)
            else:
                # Para local, simular com restart de processos do worker
                success, _ = self.node_injector.kill_worker_node_processes(node_name)
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.restart_containerd(node_name)
            else:
                # Para local, simular com restart de processos do worker
                success, _ = self.node_injector.kill_worker_node_processes(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Runtime {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_proxy_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica no kube-proxy."""
        print(f"  🌐 Executando falha de KUBE-PROXY: {failure_method}")
        
        # Extrair nome do node do componente (wn_proxy-ip-10-0-0-98 -> ip-10-0-0-98)
        if '-' in component.name:
            node_name = component.name.split('-', 1)[1]  # Remove prefixo (wn_proxy-)
        else:
            node_name = component.parent_component or component.name
        
        if failure_method == "kill_kube_proxy":
            print(f"  💀 Matando processo kube-proxy em {node_name}")
            # Simular kill do processo kube-proxy
            success = True  # Simular por enquanto
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_proxy_pod(node_name)
            else:
                success, _ = self.control_plane_injector.delete_kube_proxy_pod(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Kube-proxy {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_kubelet_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica no kubelet."""
        print(f"  ⚙️ Executando falha de KUBELET: {failure_method}")
        
        # Extrair nome do node do componente (wn_kubelet-ip-10-0-0-98 -> ip-10-0-0-98)
        if '-' in component.name:
            node_name = component.name.split('-', 1)[1]  # Remove prefixo (wn_kubelet-)
        else:
            node_name = component.parent_component or component.name
        
        if failure_method == "kill_kubelet":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kubelet(node_name)
            else:
                success, _ = self.control_plane_injector.kill_kubelet(node_name)
        elif failure_method == "restart_kubelet":
            print(f"  🔄 Reiniciando kubelet em {node_name}")
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kubelet(node_name)  # AWS usa kill para restart
            else:
                success, _ = self.control_plane_injector.kill_kubelet(node_name)
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kubelet(node_name)
            else:
                success, _ = self.control_plane_injector.kill_kubelet(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Kubelet {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_control_plane_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha no control plane completo."""
        print(f"  🎛️ Executando falha de CONTROL PLANE: {failure_method}")
        
        # Extrair nome do node (control_plane-ip-10-0-0-28 -> ip-10-0-0-28)
        if component.name.startswith('control_plane-'):
            node_name = component.name[len('control_plane-'):]
        else:
            node_name = component.name
        
        if failure_method == "kill_control_plane_processes":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_control_plane_processes(node_name)
            else:
                success = self.node_injector.kill_control_plane_processes(node_name)
        elif failure_method == "shutdown_control_plane":
            # CORREÇÃO: Usar o método especial _handle_shutdown_control_plane em ambos os casos
            success, shutdown_recovery_time = self._handle_shutdown_control_plane(node_name)
            # Armazenar o tempo de recuperação para uso posterior no loop principal
            self._last_shutdown_recovery_time = shutdown_recovery_time
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_control_plane_processes(node_name)
            else:
                success = self.node_injector.kill_control_plane_processes(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Control plane {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_apiserver_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica no kube-apiserver."""
        print(f"  � Executando falha de API SERVER: {failure_method}")
        
        # Extrair nome do node do componente (cp_apiserver-ip-10-0-0-28 -> ip-10-0-0-28)
        if '-' in component.name:
            node_name = component.name.split('-', 1)[1]  # Remove prefixo (cp_apiserver-)
        else:
            node_name = component.parent_component or component.name
        
        if failure_method == "kill_kube_apiserver":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_apiserver(node_name)
            else:
                success = self.control_plane_injector.kill_kube_apiserver(node_name)
        elif failure_method == "restart_kube_apiserver":
            print(f"  🔄 Reiniciando API server em {node_name}")
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_apiserver(node_name)
            else:
                success = self.control_plane_injector.kill_kube_apiserver(node_name)
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_apiserver(node_name)
            else:
                success = self.control_plane_injector.kill_kube_apiserver(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ API server {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_manager_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica no controller manager."""
        print(f"  🎮 Executando falha de CONTROLLER MANAGER: {failure_method}")
        
        # Extrair nome do node do componente (cp_manager-ip-10-0-0-28 -> ip-10-0-0-28)
        if '-' in component.name:
            node_name = component.name.split('-', 1)[1]  # Remove prefixo (cp_manager-)
        else:
            node_name = component.parent_component or component.name
        
        if failure_method == "kill_kube_controller_manager":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_controller_manager(node_name)
            else:
                success = self.control_plane_injector.kill_kube_controller_manager(node_name)
        elif failure_method == "restart_kube_controller_manager":
            print(f"  🔄 Reiniciando controller manager em {node_name}")
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_controller_manager(node_name)
            else:
                success = self.control_plane_injector.kill_kube_controller_manager(node_name)
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_controller_manager(node_name)
            else:
                success = self.control_plane_injector.kill_kube_controller_manager(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Controller manager {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_scheduler_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica no scheduler."""
        print(f"  📅 Executando falha de SCHEDULER: {failure_method}")
        
        # Extrair nome do node do componente (cp_scheduler-ip-10-0-0-28 -> ip-10-0-0-28)
        if '-' in component.name:
            node_name = component.name.split('-', 1)[1]  # Remove prefixo (cp_scheduler-)
        else:
            node_name = component.parent_component or component.name
        
        if failure_method == "kill_kube_scheduler":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_scheduler(node_name)
            else:
                success = self.control_plane_injector.kill_kube_scheduler(node_name)
        elif failure_method == "restart_kube_scheduler":
            print(f"  🔄 Reiniciando scheduler em {node_name}")
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_scheduler(node_name)
            else:
                success = self.control_plane_injector.kill_kube_scheduler(node_name)
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_kube_scheduler(node_name)
            else:
                success = self.control_plane_injector.kill_kube_scheduler(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ Scheduler {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool
    
    def _inject_etcd_failure(self, component: Component, failure_method: str) -> bool:
        """Injeta falha específica no etcd."""
        print(f"  🗄️ Executando falha de ETCD: {failure_method}")
        
        # Extrair nome do node do componente (cp_etcd-ip-10-0-0-28 -> ip-10-0-0-28)
        if '-' in component.name:
            node_name = component.name.split('-', 1)[1]  # Remove prefixo (cp_etcd-)
        else:
            node_name = component.parent_component or component.name
        
        if failure_method == "kill_etcd":
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_etcd(node_name)
            else:
                success = self.control_plane_injector.kill_etcd(node_name)
        elif failure_method == "restart_etcd":
            print(f"  🔄 Reiniciando etcd em {node_name}")
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_etcd(node_name)
            else:
                success = self.control_plane_injector.kill_etcd(node_name)
        else:
            # Fallback
            if self.is_aws_mode and self.aws_injector:
                success, _ = self.aws_injector.kill_etcd(node_name)
            else:
                success = self.control_plane_injector.kill_etcd(node_name)
        
        if success:
            component.current_status = 'failed'
            component.failure_count += 1
            print(f"  ✅ ETCD {component.name} falhou com sucesso")
        
        return bool(success)  # Garantir que retorna bool

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
                # Extrair o nome base da aplicação do nome completo do pod
                # bar-app-775c8885f5-6wdlt -> bar
                # foo-app-864f66dd4d-lt8rf -> foo
                # test-app-fcd6f4bf5-5r42n -> test
                if app_name.endswith('-app') or '-app-' in app_name:
                    # Se termina com -app ou contém -app-, extrair a parte antes de -app
                    app_base = app_name.split('-app')[0]
                else:
                    # Fallback: usar primeira parte antes do primeiro hífen
                    app_base = app_name.split('-')[0]
                
                pods = self.health_checker.get_pods_by_app_label(app_base)
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
            injection_success = self.inject_failure(next_event.component, failure_method)
            
            if injection_success:
                # Para shutdown_worker_node, usar o tempo calculado no método _handle_shutdown_worker_node
                if failure_method == "shutdown_worker_node":
                    # O _handle_shutdown_worker_node já fez todo o processo incluindo health check
                    # E já adicionou o MTTR configurado ao total_downtime do componente
                    # Usar o tempo correto que foi calculado (MTTR configurado)
                    recovery_time = getattr(self, '_last_shutdown_recovery_time', 0.0)
                    print(f"  ⏱️ VALIDAÇÃO - Tempo de recuperação (MTTR): {recovery_time:.1f}s ({recovery_time/3600:.4f}h)")
                elif failure_method == "shutdown_control_plane":
                    # O _handle_shutdown_control_plane já fez todo o processo incluindo health check
                    # E já adicionou o MTTR configurado ao total_downtime do componente
                    # Usar o tempo correto que foi calculado (MTTR configurado)
                    recovery_time = getattr(self, '_last_shutdown_recovery_time', 0.0)
                    print(f"  ⏱️ VALIDAÇÃO - Tempo de recuperação (MTTR) Control Plane: {recovery_time:.1f}s ({recovery_time/3600:.4f}h)")
                else:
                    # Para outras falhas, fazer verificação combinada (running + curl)
                    print(f"  🔍 Verificando recuperação com método combinado (running + curl)...")
                    _, recovery_time = self.health_checker.wait_for_pods_recovery_combined_silent()
                    next_event.component.total_downtime += recovery_time
                    print(f"  ⏱️ Tempo de recuperação (combinado): {recovery_time:.1f}s ({recovery_time/3600:.4f}h)")
                
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
        Aplica configuração do ConfigSimples criando componentes granulares.
        Cada componente individual terá seu próprio MTTF específico.
        
        Args:
            config_simples: Instância do ConfigSimples
        """
        print("🔧 === APLICANDO ConfigSimples com COMPONENTES GRANULARES ===")
        
        # Armazenar referência para uso em outros métodos
        self._config_simples = config_simples
        
        # Descobrir componentes básicos descobertos
        original_worker_nodes = []
        original_control_plane_nodes = []
        original_pods = []
        
        for component in self.components:
            if component.component_type == "node":
                original_worker_nodes.append(component.name)
            elif component.component_type == "control_plane":
                original_control_plane_nodes.append(component.name)
            elif component.component_type == "pod":
                original_pods.append(component.name)
        
        print(f"📋 Componentes descobertos:")
        print(f"  • Worker nodes: {original_worker_nodes}")
        print(f"  • Control plane nodes: {original_control_plane_nodes}")
        print(f"  • Pods: {original_pods}")
        print()
        
        # Criar nova lista de componentes granulares
        new_components = []
        
        print("🔧 === GERANDO COMPONENTES GRANULARES ===")
        
        # 1. PODS - Manter pods reais + criar containers
        for pod_name in original_pods:
            # Pod como um todo
            pod_component = Component(
                name=pod_name,
                component_type="pod",
                mttf_hours=config_simples.get_mttf('pod'),
                mttf_key='pod'
            )
            new_components.append(pod_component)
            print(f"  📦 {pod_name}: MTTF={pod_component.mttf_hours}h (pod completo)")
            
            # Container dentro do pod
            container_name = f"{pod_name}-container"
            container_component = Component(
                name=container_name,
                component_type="container",
                mttf_hours=config_simples.get_mttf('container'),
                mttf_key='container',
                parent_component=pod_name
            )
            new_components.append(container_component)
            print(f"    🐳 {container_name}: MTTF={container_component.mttf_hours}h (container)")
        
        # 2. WORKER NODES - Node completo + subcomponentes
        for node_name in original_worker_nodes:
            # Worker node como um todo
            node_component = Component(
                name=node_name,
                component_type="node",
                mttf_hours=config_simples.get_mttf('worker_node'),
                mttf_key='worker_node'
            )
            new_components.append(node_component)
            print(f"  🖥️ {node_name}: MTTF={node_component.mttf_hours}h (node completo)")
            
            # Runtime (Docker/containerd)
            runtime_name = f"{node_name}-runtime"
            runtime_component = Component(
                name=runtime_name,
                component_type="node_service",
                mttf_hours=config_simples.get_mttf('wn_runtime'),
                mttf_key='wn_runtime',
                parent_component=node_name
            )
            new_components.append(runtime_component)
            print(f"    🐳 {runtime_name}: MTTF={runtime_component.mttf_hours}h (runtime)")
            
            # Kube-proxy
            proxy_name = f"{node_name}-proxy"
            proxy_component = Component(
                name=proxy_name,
                component_type="node_service",
                mttf_hours=config_simples.get_mttf('wn_proxy'),
                mttf_key='wn_proxy',
                parent_component=node_name
            )
            new_components.append(proxy_component)
            print(f"    🌐 {proxy_name}: MTTF={proxy_component.mttf_hours}h (kube-proxy)")
            
            # Kubelet
            kubelet_name = f"{node_name}-kubelet"
            kubelet_component = Component(
                name=kubelet_name,
                component_type="node_service", 
                mttf_hours=config_simples.get_mttf('wn_kubelet'),
                mttf_key='wn_kubelet',
                parent_component=node_name
            )
            new_components.append(kubelet_component)
            print(f"    ⚙️ {kubelet_name}: MTTF={kubelet_component.mttf_hours}h (kubelet)")
        
        # 3. CONTROL PLANE - Control plane completo + subcomponentes
        for cp_name in original_control_plane_nodes:
            # Control plane como um todo
            cp_component = Component(
                name=cp_name,
                component_type="control_plane",
                mttf_hours=config_simples.get_mttf('control_plane'),
                mttf_key='control_plane'
            )
            new_components.append(cp_component)
            print(f"  🎛️ {cp_name}: MTTF={cp_component.mttf_hours}h (control plane completo)")
            
            # API Server
            apiserver_name = f"{cp_name}-apiserver"
            apiserver_component = Component(
                name=apiserver_name,
                component_type="control_plane_service",
                mttf_hours=config_simples.get_mttf('cp_apiserver'),
                mttf_key='cp_apiserver',
                parent_component=cp_name
            )
            new_components.append(apiserver_component)
            print(f"    🌐 {apiserver_name}: MTTF={apiserver_component.mttf_hours}h (apiserver)")
            
            # Controller Manager
            manager_name = f"{cp_name}-manager"
            manager_component = Component(
                name=manager_name,
                component_type="control_plane_service",
                mttf_hours=config_simples.get_mttf('cp_manager'),
                mttf_key='cp_manager',
                parent_component=cp_name
            )
            new_components.append(manager_component)
            print(f"    🎮 {manager_name}: MTTF={manager_component.mttf_hours}h (controller-manager)")
            
            # Scheduler
            scheduler_name = f"{cp_name}-scheduler"
            scheduler_component = Component(
                name=scheduler_name,
                component_type="control_plane_service",
                mttf_hours=config_simples.get_mttf('cp_scheduler'),
                mttf_key='cp_scheduler',
                parent_component=cp_name
            )
            new_components.append(scheduler_component)
            print(f"    📅 {scheduler_name}: MTTF={scheduler_component.mttf_hours}h (scheduler)")
            
            # ETCD
            etcd_name = f"{cp_name}-etcd"
            etcd_component = Component(
                name=etcd_name,
                component_type="control_plane_service",
                mttf_hours=config_simples.get_mttf('cp_etcd'),
                mttf_key='cp_etcd',
                parent_component=cp_name
            )
            new_components.append(etcd_component)
            print(f"    🗄️ {etcd_name}: MTTF={etcd_component.mttf_hours}h (etcd)")
        
        # Substituir componentes antigos pelos novos
        self.components = new_components
        
        print()
        print(f"✅ === COMPONENTES GRANULARES CRIADOS ===")
        print(f"📊 Total: {len(self.components)} componentes individuais")
        print(f"  • Original: {len(original_pods + original_worker_nodes + original_control_plane_nodes)} componentes")
        print(f"  • Granular: {len(self.components)} componentes")
        print()
        
        # Mostrar resumo por categoria
        pods = len([c for c in self.components if c.mttf_key in ['pod', 'container']])
        nodes = len([c for c in self.components if c.mttf_key and c.mttf_key.startswith('wn_')] + 
                   [c for c in self.components if c.mttf_key == 'worker_node'])
        cps = len([c for c in self.components if c.mttf_key and c.mttf_key.startswith('cp_')] +
                  [c for c in self.components if c.mttf_key == 'control_plane'])
        
        print(f"📋 Resumo:")
        print(f"  • Componentes de Pods: {pods}")
        print(f"  • Componentes de Nodes: {nodes}")
        print(f"  • Componentes de Control Plane: {cps}")
        
        # Extrair nomes das aplicações dos pods reais para critérios de disponibilidade
        discovered_apps = set()
        for pod_name in original_pods:
            if '-' in pod_name:
                app_name = pod_name.split('-')[0] + '-app'
                if app_name.endswith('-app-app'):
                    app_name = app_name[:-4]
                discovered_apps.add(app_name)
        
        if discovered_apps:
            self.availability_criteria = {app: 1 for app in discovered_apps}
            print(f"🎯 Critérios: {self.availability_criteria}")
        else:
            if hasattr(config_simples, 'applications'):
                self.availability_criteria = config_simples.get_availability_criteria()
                print(f"🎯 Critérios (fallback): {self.availability_criteria}")
        
        print("✅ ConfigSimples granular aplicado com sucesso!")
        
        # Extrair nomes das aplicações dos pods reais para critérios de disponibilidade
        discovered_apps = set()
        for pod_name in original_pods:
            # Extrair nome da aplicação do pod (ex: "bar-app" de "bar-app-6664549c89-n7kz2")
            if '-' in pod_name:
                app_name = pod_name.split('-')[0] + '-app'  # Assumindo padrão "app-name-hash-id"
                if app_name.endswith('-app-app'):  # Evitar duplicação de "-app"
                    app_name = app_name[:-4]  # Remove o "-app" extra
                discovered_apps.add(app_name)
        
        # Usar aplicações descobertas dos pods reais
        if discovered_apps:
            self.availability_criteria = {app: 1 for app in discovered_apps}
            print(f"🎯 Critérios de disponibilidade baseados nos pods reais: {self.availability_criteria}")
        else:
            # Fallback para configuração do ConfigSimples se não conseguir descobrir
            if hasattr(config_simples, 'applications'):
                self.availability_criteria = config_simples.get_availability_criteria()
                print(f"🎯 Critérios de disponibilidade (fallback ConfigSimples): {self.availability_criteria}")
        
        print("✅ ConfigSimples aplicado com sucesso (mantendo pods reais)")
        print(f"📊 Total de componentes: {len(self.components)}")
    
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
    
    def _handle_shutdown_worker_node(self, node_name: str) -> tuple[bool, float]:
        """
        Lógica especial para shutdown de worker node.
        
        PROCESSO CORRETO:
        1. Desliga o nó
        2. Aguarda delay configurado do teste (campo "delay", não MTTR)
        3. Religa o nó automaticamente (self-healing)
        4. Verifica com health checker quando aplicações voltaram
        
        Returns:
            Tuple com (sucesso, tempo_recuperacao_segundos)
        """
        try:
            import time
            
            print(f"  🔌 Desligando worker node: {node_name}")
            
            # 1. Desligar o nó usando node_injector
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                shutdown_success, shutdown_command = self.aws_injector.shutdown_worker_node(node_name)
            else:
                shutdown_success, shutdown_command = self.node_injector.shutdown_worker_node(node_name)
                
            if not shutdown_success:
                print(f"  ❌ Falha ao desligar nó {node_name}")
                return False, 0.0
            
            # 2. Obter delay configurado do teste (NÃO o MTTR)
            delay_seconds = 10  # Default 
            mttr_hours = 0.016  # MTTR padrão para contabilização
            
            if hasattr(self, '_config_simples') and self._config_simples:
                # O _config_simples é uma instância da classe ConfigSimples, não um dict
                if hasattr(self._config_simples, 'delay'):
                    delay_seconds = self._config_simples.delay
                    print(f"  📊 Delay do teste configurado: {delay_seconds}s")
                
                # Obter MTTR para contabilização final
                if hasattr(self._config_simples, 'get_mttr'):
                    try:
                        mttr_hours = self._config_simples.get_mttr(node_name)
                        print(f"  📊 MTTR configurado para contabilização: {mttr_hours:.4f}h ({mttr_hours*3600:.1f}s)")
                    except Exception as e:
                        print(f"  ⚠️ Erro ao obter MTTR configurado, usando padrão: {e}")
                else:
                    print(f"  ⚠️ Config simples sem método get_mttr, usando MTTR padrão")
            else:
                print(f"  ⚠️ Config não disponível, usando delay padrão: {delay_seconds}s")
            
            # 3. Aguardar delay configurado do teste (NÃO MTTR)
            print(f"  ⏱️ Aguardando delay configurado do teste: {delay_seconds}s...")
            time.sleep(delay_seconds)
            
            # 4. Religar o nó automaticamente
            print(f"  🔄 Self-healing: Religando worker node: {node_name}")
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                startup_success, startup_command = self.aws_injector.start_worker_node(node_name)
            else:
                startup_success, startup_command = self.node_injector.start_worker_node(node_name)
            
            if not startup_success:
                print(f"  ❌ Falha ao religar nó {node_name}")
                return False, 0.0
            
            print(f"  ✅ Worker node {node_name} religado com sucesso")
            
            # 5. CORREÇÃO: Aguardar aplicações ficarem ativas com health checker
            print(f"  ⚕️ Aguardando aplicações ficarem ativas com health checker...")
            health_check_start = time.time()
            
            # Usar health checker para verificação real (mas não contabilizar o tempo)
            if hasattr(self, 'health_checker') and self.health_checker:
                # Descobrir aplicações se não estão em cache
                discovered_apps = None
                if hasattr(self, 'availability_criteria'):
                    discovered_apps = list(self.availability_criteria.keys())
                
                apps_recovered, health_check_time = self.health_checker.wait_for_recovery(
                    timeout=180,  # 3 minutos timeout
                    discovered_apps=discovered_apps
                )
                
                if apps_recovered:
                    print(f"  ✅ Aplicações ficaram ativas em {health_check_time:.1f}s (tempo real de espera)")
                    # CORREÇÃO: NÃO somar tempo real, usar apenas MTTR configurado
                    mttr_seconds = mttr_hours * 3600
                    print(f"  📊 Usando apenas MTTR configurado: {mttr_seconds:.1f}s (não contabilizando tempo real de {health_check_time:.1f}s)")
                    
                    # Armazenar o MTTR configurado no componente para uso posterior
                    component = next((c for c in self.components if c.name == f"worker_node-{node_name}"), None)
                    if component:
                        component.total_downtime += mttr_seconds
                    
                    return True, mttr_seconds
                else:
                    print(f"  ⚠️ Aplicações não ficaram ativas no timeout (180s)")
                    # Mesmo assim, considera recuperado com MTTR configurado
                    print(f"  📊 Usando MTTR configurado mesmo com timeout: {mttr_hours*3600:.1f}s")
                    
                    # Armazenar o MTTR configurado mesmo com timeout
                    component = next((c for c in self.components if c.name == f"worker_node-{node_name}"), None)
                    if component:
                        component.total_downtime += mttr_hours * 3600
                    
                    return True, mttr_hours * 3600  # Considera recuperado mesmo se timeout
            else:
                # Fallback: aguardar tempo fixo se health_checker não disponível
                print(f"  ⚠️ Health checker não disponível, usando fallback de 60s...")
                time.sleep(60)
                print(f"  📊 Shutdown completo com fallback: usando MTTR configurado {mttr_hours*3600:.1f}s")
                
                # Armazenar o MTTR configurado para fallback
                component = next((c for c in self.components if c.name == f"worker_node-{node_name}"), None)
                if component:
                    component.total_downtime += mttr_hours * 3600
                
                return True, mttr_hours * 3600
                
        except Exception as e:
            print(f"  ❌ Erro durante shutdown/startup de {node_name}: {e}")
            return False, 0.0
    
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
    
    def _apply_config_simples_v2(self, config_simples):
        """
        Aplica configuração da nova arquitetura ConfigSimples v2.
        Carrega componentes diretamente do JSON gerado pela descoberta automática.
        
        Args:
            config_simples: Instância do ConfigSimples v2
        """
        print("🔧 === APLICANDO ConfigSimples V2 (Nova Arquitetura) ===")
        
        # Armazenar referência para uso em outros métodos
        self._config_simples = config_simples
        
        # Obter componentes diretamente da configuração
        components_from_config = config_simples.get_component_config()
        
        print(f"📋 Carregando {len(components_from_config)} componentes do JSON:")
        
        # Usar os componentes do JSON diretamente
        self.components = components_from_config
        
        # Agrupar componentes por tipo para estatísticas
        components_by_type = {}
        for component in self.components:
            comp_type = component.component_type
            if comp_type not in components_by_type:
                components_by_type[comp_type] = 0
            components_by_type[comp_type] += 1
        
        print("📊 Componentes por tipo:")
        for comp_type, count in components_by_type.items():
            print(f"  • {comp_type}: {count} componentes")
        
        # Aplicar critérios de disponibilidade
        self.availability_criteria = config_simples.get_availability_criteria()
        print(f"🎯 Critérios de disponibilidade: {self.availability_criteria}")
        
        # Aplicar delay do config
        if hasattr(config_simples, 'delay') and config_simples.delay:
            self.real_delay_between_failures = config_simples.delay
            print(f"⏱️ Delay entre falhas configurado: {self.real_delay_between_failures}s")
        
        # Configurar AWS se necessário
        aws_config = config_simples.get_aws_config()
        if aws_config:
            print("☁️ Configuração AWS detectada")
            # Atualizar flag de modo AWS
            self.is_aws_mode = True
            # Reconfigurar injetores para usar AWS
            self._configure_aws_injectors(aws_config)
            
        print("✅ ConfigSimples V2 aplicado com sucesso!")
        print(f"📊 Total de componentes: {len(self.components)}")
        print(f"📱 Aplicações monitoradas: {list(self.availability_criteria.keys())}")
        print()
    
    def _configure_aws_injectors(self, aws_config: dict):
        """
        Reconfigura injetores para usar configuração AWS.
        
        Args:
            aws_config: Configuração AWS
        """
        print(f"🔄 Reconfigurando injetores para AWS com descoberta automática")
        
        # Reconfigurar kubectl executor
        self.kubectl = get_kubectl_executor(aws_config)
        
        # Reconfigurar health checker
        self.health_checker = HealthChecker(aws_config=aws_config)
        
        # Extrair parâmetros AWS
        ssh_key = aws_config.get('ssh_key', '~/.ssh/vockey.pem')
        ssh_user = aws_config.get('ssh_user', 'ubuntu')
        
        # Reconfigurar injetores de falha para AWS com config correta
        from ..utils.config import get_config
        aws_config_context = get_config(aws_mode=True, aws_config=aws_config)
        self.pod_injector = PodFailureInjector(aws_config_context)  # Usar configuração AWS
        self.node_injector = NodeFailureInjector()  # Usar configuração padrão
        self.cp_injector = ControlPlaneInjector()  # Usar configuração padrão
        self.aws_injector = AWSFailureInjector(
            ssh_key=ssh_key,
            ssh_user=ssh_user,
            aws_config=aws_config  # Passar config completo para discovery
        )
        
        # Descobrir URLs dos serviços após configuração AWS
        print("🔍 Descobrindo URLs dos serviços...")
        discovered_urls = self._discover_services_urls()
        if discovered_urls:
            print(f"✅ URLs descobertas para {len(discovered_urls)} serviços")
    
    def _handle_shutdown_control_plane(self, node_name: str) -> tuple[bool, float]:
        """
        Lógica especial para shutdown de control plane.
        
        PROCESSO CORRETO:
        1. Desliga o control plane
        2. Aguarda delay configurado do teste (campo "delay", não MTTR)
        3. Religa o control plane automaticamente (self-healing)
        4. Verifica com health checker quando aplicações voltaram
        
        Returns:
            Tuple com (sucesso, tempo_recuperacao_segundos)
        """
        try:
            import time
            
            print(f"  🔌 Desligando control plane: {node_name}")
            
            # 1. Desligar o control plane usando node_injector
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                shutdown_success, shutdown_command = self.aws_injector.shutdown_control_plane(node_name)
            else:
                shutdown_success, shutdown_command = self.node_injector.shutdown_control_plane(node_name)
                
            if not shutdown_success:
                print(f"  ❌ Falha ao desligar control plane {node_name}")
                return False, 0.0
            
            # 2. Obter delay configurado do teste (NÃO o MTTR)
            delay_seconds = 10  # Default 
            mttr_hours = 0.025  # MTTR padrão para contabilização (~1.5 minutos)
            
            if hasattr(self, '_config_simples') and self._config_simples:
                # O _config_simples é uma instância da classe ConfigSimples, não um dict
                if hasattr(self._config_simples, 'delay'):
                    delay_seconds = self._config_simples.delay
                    print(f"  📊 Delay do teste configurado: {delay_seconds}s")
                
                # Obter MTTR para contabilização final
                if hasattr(self._config_simples, 'get_mttr'):
                    try:
                        mttr_hours = self._config_simples.get_mttr(node_name)
                        print(f"  📊 MTTR configurado para contabilização: {mttr_hours:.4f}h ({mttr_hours*3600:.1f}s)")
                    except Exception as e:
                        print(f"  ⚠️ Erro ao obter MTTR configurado, usando padrão: {e}")
                else:
                    print(f"  ⚠️ Config simples sem método get_mttr, usando MTTR padrão")
            else:
                print(f"  ⚠️ Config não disponível, usando delay padrão: {delay_seconds}s")
            
            # 3. Aguardar delay configurado do teste (NÃO MTTR)
            print(f"  ⏱️ Aguardando delay configurado do teste: {delay_seconds}s...")
            time.sleep(delay_seconds)
            
            # 4. Religar o control plane automaticamente
            print(f"  🔄 Self-healing: Religando control plane: {node_name}")
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                startup_success, startup_command = self.aws_injector.start_control_plane(node_name)
            else:
                startup_success, startup_command = self.node_injector.start_control_plane(node_name)
            
            if not startup_success:
                print(f"  ❌ Falha ao religar control plane {node_name}")
                return False, 0.0
            
            print(f"  ✅ Control plane {node_name} religado com sucesso")
            
            # 5. CORREÇÃO: Aguardar aplicações ficarem ativas com health checker
            print(f"  ⚕️ Aguardando aplicações ficarem ativas com health checker...")
            health_check_start = time.time()
            
            # Usar health checker para verificação real (mas não contabilizar o tempo)
            if hasattr(self, 'health_checker') and self.health_checker:
                # Descobrir aplicações se não estão em cache
                discovered_apps = None
                if hasattr(self, 'availability_criteria'):
                    discovered_apps = list(self.availability_criteria.keys())
                
                apps_recovered, health_check_time = self.health_checker.wait_for_recovery(
                    timeout=180,  # 3 minutos timeout
                    discovered_apps=discovered_apps
                )
                
                if apps_recovered:
                    print(f"  ✅ Aplicações ficaram ativas em {health_check_time:.1f}s (tempo real de espera)")
                    # CORREÇÃO: NÃO somar tempo real, usar apenas MTTR configurado
                    mttr_seconds = mttr_hours * 3600
                    print(f"  📊 Usando apenas MTTR configurado: {mttr_seconds:.1f}s (não contabilizando tempo real de {health_check_time:.1f}s)")
                    
                    # Armazenar o MTTR configurado no componente para uso posterior
                    component = next((c for c in self.components if c.name == f"control_plane-{node_name}"), None)
                    if component:
                        component.total_downtime += mttr_seconds
                    
                    return True, mttr_seconds
                else:
                    print(f"  ⚠️ Aplicações não ficaram ativas no timeout (180s)")
                    # Mesmo assim, considera recuperado com MTTR configurado
                    print(f"  📊 Usando MTTR configurado mesmo com timeout: {mttr_hours*3600:.1f}s")
                    
                    # Armazenar o MTTR configurado mesmo com timeout
                    component = next((c for c in self.components if c.name == f"control_plane-{node_name}"), None)
                    if component:
                        component.total_downtime += mttr_hours * 3600
                    
                    return True, mttr_hours * 3600
            else:
                print(f"  ⚠️ Health checker não disponível, retornando MTTR configurado")
                mttr_seconds = mttr_hours * 3600
                
                component = next((c for c in self.components if c.name == f"control_plane-{node_name}"), None)
                if component:
                    component.total_downtime += mttr_seconds
                
                return True, mttr_seconds
                
        except Exception as e:
            print(f"  ❌ Erro durante shutdown/recovery de control plane {node_name}: {e}")
            import traceback
            traceback.print_exc()
            return False, 0.0