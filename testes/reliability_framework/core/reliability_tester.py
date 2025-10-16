"""
Sistema de Testes de Confiabilidade para Kubernetes

Classe principal que coordena testes de MTTF (Mean Time To Failure) 
e MTTR (Mean Time To Recovery) em diferentes componentes com CSV em tempo real.
"""

import time
import sys
import threading
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..failure_injectors.pod_injector import PodFailureInjector
from ..failure_injectors.node_injector import NodeFailureInjector
from ..monitoring.health_checker import HealthChecker
from ..monitoring.system_monitor import SystemMonitor
from ..reports.csv_reporter import CSVReporter
from ..reports.metrics_analyzer import MetricsAnalyzer
from ..simulation.accelerated_simulation import AcceleratedSimulation
from ..utils.interactive_selector import InteractiveSelector
from ..utils.config import get_config


class ReliabilityTester:
    """
    ⭐ TESTADOR DE CONFIABILIDADE COM CSV EM TEMPO REAL ⭐
    
    Orquestra testes de confiabilidade em ambientes Kubernetes
    com escrita de resultados em tempo real durante a execução.
    
    Coordena injetores de falha, monitoramento e relatórios para
    medir a confiabilidade de diferentes componentes do sistema.
    """
    
    def __init__(self, time_acceleration: float = 1.0, base_mttf_hours: float = 1.0):
        """
        Inicializa o testador de confiabilidade.
        
        Args:
            time_acceleration: Fator de aceleração temporal para simulação
            base_mttf_hours: MTTF base em horas para distribuição de falhas
        """
        # Componentes do framework
        self.config = get_config()
        self.health_checker = HealthChecker()
        self.system_monitor = SystemMonitor()
        self.csv_reporter = CSVReporter()
        self.metrics_analyzer = MetricsAnalyzer()
        self.interactive_selector = InteractiveSelector()
        
        # Injetores de falha
        self.pod_injector = PodFailureInjector()
        self.node_injector = NodeFailureInjector()
        
        # Simulação acelerada
        self.accelerated_sim = AcceleratedSimulation(time_acceleration, base_mttf_hours)
        self.simulation_mode = time_acceleration > 1.0
        
        # Estado do teste
        self.test_results = []
        
        # Controle de threading para simulação contínua
        self.simulation_running = False
        self.simulation_thread = None
        self.stop_simulation_event = threading.Event()
        
        # Mapeamento de métodos de falha
        self.failure_methods = {
            'kill_processes': self.pod_injector.kill_all_processes,
            'kill_init': self.pod_injector.kill_init_process,
            'delete_pod': self.pod_injector.delete_pod,
            'kill_worker_node_processes': self.node_injector.kill_worker_node_processes,
            'kill_control_plane_processes': self.node_injector.kill_control_plane_processes
        }
    
    def initial_system_check(self) -> Tuple[int, Dict]:
        """
        Verificação inicial completa do sistema.
        
        Returns:
            Tuple com (número de apps saudáveis, status detalhado)
        """
        print("1️⃣ === VERIFICAÇÃO INICIAL DO SISTEMA ===")
        
        # Mostrar status dos pods
        self.system_monitor.show_pod_status()
        
        # Verificar port-forwards
        self.health_checker.check_port_forwards()
        
        # Verificar saúde das aplicações
        print("🔍 Verificando saúde das aplicações via HTTP...")
        health_status = self.health_checker.check_all_applications(verbose=True)
        healthy_count = sum(1 for status in health_status.values() if status['status'] == 'healthy')
        
        if self.config.services:
            total_services = len(self.config.services)
            print(f"\n📊 === RESULTADO DA VERIFICAÇÃO ===")
            print(f"✅ Aplicações saudáveis: {healthy_count}/{total_services}")
            
            for service, status in health_status.items():
                emoji = "✅" if status['status'] == 'healthy' else "❌"
                print(f"   {emoji} {service}: {status['status']}")
                if 'error' in status:
                    print(f"      🔍 Detalhes: {status['error']}")
        
        print("="*50)
        return healthy_count, health_status
    
    def run_reliability_test(self, component_type: str, failure_method: str, 
                           target: Optional[str] = None, iterations: int = 30, 
                           interval: int = 60) -> List[Dict]:
        """
        ⭐ EXECUTA TESTE DE CONFIABILIDADE COM CSV EM TEMPO REAL ⭐
        
        Executa teste de confiabilidade sistemático salvando cada
        resultado imediatamente no CSV durante a execução.
        
        Args:
            component_type: Tipo do componente (pod, worker_node, control_plane)
            failure_method: Método de falha a usar
            target: Alvo específico (opcional)
            iterations: Número de falhas a simular
            interval: Intervalo entre testes em segundos
            
        Returns:
            Lista com resultados de cada iteração
        """
        print(f"\n🧪 === TESTE DE CONFIABILIDADE COM CSV EM TEMPO REAL ===")
        print(f"📊 Componente: {component_type}")
        print(f"🔨 Método de falha: {failure_method}")
        print(f"🔢 Iterações: {iterations}")
        print(f"⏱️ Intervalo: {interval}s")
        print(f"⏰ Timeout de recuperação: {self.config.current_recovery_timeout}s")
        print("="*60)
        
        # Verificar se o método de falha existe
        if failure_method not in self.failure_methods:
            print(f"❌ Método de falha '{failure_method}' não encontrado")
            return []
        
        # Selecionar alvo se não especificado
        if not target:
            target = self._select_target(component_type)
        
        if not target:
            print("❌ Nenhum alvo selecionado")
            return []
        
        print(f"🎯 Alvo selecionado: {target}")
        
        # ⭐ INICIAR CSV EM TEMPO REAL ⭐
        csv_file = self.csv_reporter.start_realtime_report(component_type, failure_method, target)
        if not csv_file:
            print("⚠️ Erro ao iniciar CSV em tempo real, continuando sem ele")
        
        # Verificação inicial completa do sistema
        healthy_count, initial_health = self.initial_system_check()
        
        if healthy_count == 0:
            if not self._handle_unhealthy_system():
                self.csv_reporter.finish_realtime_report()
                return []
        
        # Executar teste iterativo
        results = []
        test_start_time = time.time()
        
        try:
            for iteration in range(1, iterations + 1):
                print(f"\n🔄 === ITERAÇÃO {iteration}/{iterations} ===")
                
                # Executar uma iteração de teste
                result = self._execute_test_iteration(
                    iteration, component_type, failure_method, target
                )
                
                if result:
                    results.append(result)
                    
                    # ⭐ SALVAR RESULTADO EM TEMPO REAL ⭐
                    if self.csv_reporter.is_realtime_active():
                        self.csv_reporter.add_realtime_result(result, iterations)
                    
                    self._print_iteration_result(result, iteration)
                
                # Aguardar intervalo antes da próxima iteração (exceto na última)
                if iteration < iterations:
                    print(f"⏸️ Aguardando {interval}s antes da próxima iteração...")
                    
                    # Mostrar progresso durante a espera
                    for remaining in range(interval, 0, -1):
                        if remaining <= 10 or remaining % 10 == 0:
                            print(f"⏳ {remaining}s restantes...")
                        time.sleep(1)
        
        except KeyboardInterrupt:
            print("\n⚠️ Teste interrompido pelo usuário")
        
        finally:
            # Calcular estatísticas finais
            total_test_time = time.time() - test_start_time
            self._process_final_results(results, component_type, failure_method, target, total_test_time)
            
            # ⭐ FINALIZAR CSV EM TEMPO REAL ⭐
            if self.csv_reporter.is_realtime_active():
                summary_stats = self._calculate_summary_stats(results, component_type, failure_method, target, total_test_time)
                self.csv_reporter.finish_realtime_report(summary_stats)
        
        return results
    
    def _calculate_summary_stats(self, results: List[Dict], component_type: str, 
                               failure_method: str, target: str, total_test_time: float) -> Dict:
        """Calcula estatísticas de resumo para o CSV."""
        if not results:
            return {}
        
        recovery_times = [r['recovery_time_seconds'] for r in results if r['recovered']]
        success_rate = len(recovery_times) / len(results) * 100 if results else 0
        average_mttr = statistics.mean(recovery_times) if recovery_times else 0
        
        return {
            'component_type': component_type,
            'failure_method': failure_method,
            'target': target,
            'total_iterations': len(results),
            'successful_recoveries': len(recovery_times),
            'success_rate': success_rate,
            'average_mttr': average_mttr,
            'total_test_time': total_test_time
        }
    
    def _select_target(self, component_type: str) -> Optional[str]:
        """Seleciona alvo baseado no tipo de componente."""
        if component_type == 'pod':
            pods = self.system_monitor.get_pods()
            if not pods:
                print("❌ Nenhum pod encontrado")
                return None
            return self.interactive_selector.select_from_list(pods, f"Selecione o pod para testar")
        elif component_type == 'worker_node':
            nodes = self.system_monitor.get_worker_nodes()
            if not nodes:
                print("❌ Nenhum worker node encontrado")
                return None
            return self.interactive_selector.select_from_list(nodes, f"Selecione o worker node para testar")
        elif component_type == 'control_plane':
            return self.system_monitor.get_control_plane_node()
        
        return None
    
    def _handle_unhealthy_system(self) -> bool:
        """Lida com sistema não saudável."""
        print("⚠️ NENHUMA APLICAÇÃO ESTÁ SAUDÁVEL!")
        print("💡 Possíveis soluções:")
        print("   1. Verifique se os pods estão rodando: kubectl get pods")
        print("   2. Configure port-forwards:")
        print("      kubectl port-forward svc/foo-service 8080:80 &")
        print("      kubectl port-forward svc/bar-service 8081:80 &")
        print("      kubectl port-forward svc/test-service 8082:80 &")
        print("   3. Ou execute o script port-forward-monitor.sh")
        print("\n🔧 Deseja continuar mesmo assim? (y/N):")
        
        try:
            choice = input().strip().lower()
            return choice in ['y', 'yes', 's', 'sim']
        except KeyboardInterrupt:
            print("\n❌ Teste cancelado")
            return False
    
    def _execute_test_iteration(self, iteration: int, component_type: str, 
                              failure_method: str, target: str) -> Optional[Dict]:
        """Executa uma iteração individual de teste."""
        # Verificar estado inicial
        initial_health = self.health_checker.check_all_applications(verbose=True)
        healthy_before = sum(1 for status in initial_health.values() if status['status'] == 'healthy')
        
        if healthy_before == 0:
            print("⚠️ Nenhuma aplicação saudável antes do teste, aguardando recuperação...")
            recovered, _ = self.health_checker.wait_for_recovery()  # Usar timeout da configuração
            if not recovered:
                print("❌ Sistema não se recuperou, parando teste")
                return None
        
        # Executar falha
        failure_start = time.time()
        failure_timestamp = datetime.now().isoformat()
        
        failure_success, executed_command = self.failure_methods[failure_method](target)
        
        if not failure_success:
            print(f"❌ Falha não executada corretamente na iteração {iteration}")
            return None
        
        # Aguardar recuperação usando timeout configurado globalmente
        print(f"⏳ Aguardando recuperação (timeout: {self.config.current_recovery_timeout}s)...")
        recovered, recovery_time = self.health_checker.wait_for_recovery()
        
        # Calcular MTTR
        total_time = time.time() - failure_start
        
        # Atualizar métricas do componente individual
        self.metrics_analyzer.update_component_metrics(target, component_type, recovery_time, recovered)
        
        # Criar resultado
        result = {
            'iteration': iteration,
            'component_type': component_type,
            'component_id': target,
            'failure_method': failure_method,
            'executed_command': executed_command,
            'failure_timestamp': failure_timestamp,
            'recovery_time_seconds': recovery_time,
            'total_time_seconds': total_time,
            'recovered': recovered,
            'initial_healthy_apps': healthy_before,
            'component_stats': self.metrics_analyzer.get_component_statistics(target)
        }
        
        return result
    
    def _print_iteration_result(self, result: Dict, iteration: int):
        """Imprime resultado de uma iteração."""
        print(f"📋 Resultado Iteração {iteration}:")
        print(f"   ⏱️ MTTR: {result['recovery_time_seconds']:.2f}s")
        print(f"   ✅ Recuperou: {'Sim' if result['recovered'] else 'Não'}")
        print(f"   📊 Apps saudáveis antes: {result['initial_healthy_apps']}")
        if self.config.services:
            print(f"   📈 Timeout usado: {self.config.current_recovery_timeout}s")
    
    def _process_final_results(self, results: List[Dict], component_type: str, 
                             failure_method: str, target: str, total_test_time: float):
        """Processa e exibe resultados finais."""
        # Calcular estatísticas finais
        self.metrics_analyzer.calculate_and_print_statistics(results)
        
        # Mostrar métricas individuais por componente
        self.metrics_analyzer.print_individual_component_stats()
        
        # Salvar métricas de componentes
        if self.metrics_analyzer.component_metrics:
            suffix = f"{component_type}_{failure_method}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.csv_reporter.save_component_metrics(self.metrics_analyzer.component_metrics, suffix)
        
        # Imprimir resumo do teste
        print(f"\n⏱️ === RESUMO DO TESTE ===")
        print(f"🕐 Tempo total de teste: {total_test_time:.1f}s ({total_test_time/60:.1f}min)")
        print(f"📊 Timeout configurado: {self.config.current_recovery_timeout}s")
        if self.csv_reporter.get_current_file_path():
            print(f"📁 Arquivo CSV: {self.csv_reporter.get_current_file_path()}")
        print("="*50)
    
    @property
    def component_metrics(self):
        """Propriedade para acessar métricas de componentes."""
        return self.metrics_analyzer.component_metrics