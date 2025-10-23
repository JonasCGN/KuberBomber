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
                    "stop_worker_node",
                    "pause_worker_node",
                    "simulate_network_partition"
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
    """
    
    def __init__(self, components: Optional[List[Component]] = None, min_pods_required: int = 2):
        """
        Inicializa o simulador.
        
        Args:
            components: Lista de componentes personalizados (opcional)
            min_pods_required: Número mínimo de pods necessários para disponibilidade
        """
        self.min_pods_required = min_pods_required
        
        # Critérios de disponibilidade por aplicação (configurado pelo CLI)
        self.availability_criteria = {
            "foo-app": 1,
            "bar-app": 1, 
            "test-app": 1
        }
        
        # ========== CONFIGURAÇÃO DE COMPONENTES ==========
        # VOCÊ PODE ALTERAR OS MTTFs AQUI
        if components:
            self.components = components
        else:
            self.components = [
                # Pods
                Component("foo-app", "pod", mttf_hours=100.0),
                Component("bar-app", "pod", mttf_hours=120.0),
                Component("test-app", "pod", mttf_hours=80.0),
                
                # Worker Nodes
                Component("local-k8s-worker", "node", mttf_hours=500.0),
                Component("local-k8s-worker2", "node", mttf_hours=500.0),
                
                # Control Plane
                Component("local-k8s-control-plane", "control_plane", mttf_hours=800.0),
            ]
        
        # Injetores de falha
        self.pod_injector = PodFailureInjector()
        self.node_injector = NodeFailureInjector()
        self.control_plane_injector = ControlPlaneInjector()
        
        # Monitor de saúde
        self.health_checker = HealthChecker()
        
        # Reporter CSV
        self.csv_reporter = CSVReporter()
        
        # Estado da simulação
        self.current_simulated_time = 0.0  # horas simuladas
        self.event_queue = []  # heap de eventos
        self.availability_history = []  # histórico de disponibilidade
        self.simulation_logs = []  # logs detalhados
        
        # Configurações
        self.real_delay_between_failures = 60  # 1 minuto em segundos
        
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
                    success = self.node_injector.kill_worker_node_processes(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (kill processes)")
                elif failure_method == "stop_worker_node":
                    success = self.node_injector.stop_worker_node(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (stop node)")
                elif failure_method == "pause_worker_node":
                    success = self.node_injector.pause_worker_node(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (pause node)")
                elif failure_method == "simulate_network_partition":
                    success = self.node_injector.simulate_network_partition(component.name)
                    print(f"  🎯 Falha injetada no node: {component.name} (network partition)")
                else:
                    # Fallback
                    success = self.node_injector.kill_worker_node_processes(component.name)
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
        Aguarda recuperação real do componente.
        
        Args:
            component: Componente a aguardar recuperação
            
        Returns:
            Tempo real de recuperação em segundos
        """
        print(f"⏳ Aguardando recuperação de {component.name}...")
        
        start_time = time.time()
        max_recovery_time = 300  # 5 minutos máximo
        check_interval = 5  # verificar a cada 5 segundos
        
        while time.time() - start_time < max_recovery_time:
            try:
                if component.component_type == "pod":
                    # Verificar se pod está Ready
                    pods = self.health_checker.get_pods_by_app_label(component.name.replace("-app", ""))
                    if pods and pods[0]['ready']:
                        recovery_time = time.time() - start_time
                        print(f"  ✅ {component.name} recuperado em {recovery_time:.1f}s")
                        component.current_status = 'healthy'
                        return recovery_time
                        
                elif component.component_type in ["node", "control_plane"]:
                    # Verificar se node está Ready
                    if self.health_checker.is_node_ready(component.name):
                        recovery_time = time.time() - start_time
                        print(f"  ✅ {component.name} recuperado em {recovery_time:.1f}s")
                        component.current_status = 'healthy'
                        return recovery_time
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"  ⚠️ Erro verificando recuperação: {e}")
                time.sleep(check_interval)
        
        # Timeout - assumir recuperado
        recovery_time = time.time() - start_time
        print(f"  ⏰ Timeout: assumindo {component.name} recuperado após {recovery_time:.1f}s")
        component.current_status = 'healthy'
        return recovery_time
    
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