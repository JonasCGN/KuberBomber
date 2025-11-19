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
from ..utils.kubectl_executor import KubectlExecutor


class ReliabilityTester:
    """
    ⭐ TESTADOR DE CONFIABILIDADE COM CSV EM TEMPO REAL ⭐
    
    Orquestra testes de confiabilidade em ambientes Kubernetes
    com escrita de resultados em tempo real durante a execução.
    
    Coordena injetores de falha, monitoramento e relatórios para
    medir a confiabilidade de diferentes componentes do sistema.
    """
    
    def __init__(self, time_acceleration: float = 1.0, base_mttf_hours: float = 1.0, aws_config: Optional[Dict] = None):
        """
        Inicializa o testador de confiabilidade.
        
        Args:
            time_acceleration: Fator de aceleração temporal para simulação
            base_mttf_hours: MTTF base em horas para distribuição de falhas
            aws_config: Configuração para uso em ambiente AWS (ssh_host, ssh_key, ssh_user, applications)
        """
        # Configuração AWS
        self.aws_config = aws_config
        self.is_aws_mode = aws_config is not None
        
        # Inicializar KubectlExecutor
        self.kubectl = KubectlExecutor(aws_config=aws_config if self.is_aws_mode else None)
        
        # Componentes do framework - PASSANDO aws_config para detecção correta de contexto
        if self.is_aws_mode:
            self.config = get_config(aws_mode=True, aws_config=aws_config)
        else:
            self.config = get_config(aws_mode=False)
        
        # Obter config com AWS mode PRIMEIRO
        self.config = get_config(aws_mode=self.is_aws_mode, aws_config=aws_config)
        
        # Inicializar componentes com configuração AWS se disponível
        if self.is_aws_mode:
            self.health_checker = HealthChecker(aws_config=aws_config)
            self.system_monitor = SystemMonitor(aws_config=aws_config)
        else:
            self.health_checker = HealthChecker()
            self.system_monitor = SystemMonitor()
            
        self.csv_reporter = CSVReporter()
        self.metrics_analyzer = MetricsAnalyzer(self.config)
        self.interactive_selector = InteractiveSelector()
        
        # ===== INJETORES DE FALHA: ESCOLHER AWS OU LOCAL =====
        if self.is_aws_mode and aws_config:
            # MODO AWS: Usar APENAS aws_injector
            print("🔧 Inicializando APENAS AWS injector...")
            from ..failure_injectors.aws_injector import AWSFailureInjector
            self.aws_injector = AWSFailureInjector(
                ssh_key=aws_config['ssh_key'],
                ssh_host=aws_config['ssh_host'],
                ssh_user=aws_config['ssh_user']
            )
            print("✅ AWS injector configurado - injetores locais não serão usados")
        else:
            # MODO LOCAL: Usar injetores locais
            print("🔧 Inicializando injetores locais...")
            self.pod_injector = PodFailureInjector(self.config)
            self.node_injector = NodeFailureInjector(self.config)
            # Importar ControlPlaneInjector dinamicamente
            from ..failure_injectors.control_plane_injector import ControlPlaneInjector
            self.control_plane_injector = ControlPlaneInjector(aws_config=aws_config)
            print("✅ Injetores locais configurados")
        
        # Simulação acelerada
        self.accelerated_sim = AcceleratedSimulation(time_acceleration, base_mttf_hours)
        self.simulation_mode = time_acceleration > 1.0
        
        # Estado do teste
        self.test_results = []
        
        # Controle de threading para simulação contínua
        self.simulation_running = False
        self.simulation_thread = None
        self.stop_simulation_event = threading.Event()
        
        # Mapeamento de métodos de falha - TODOS da tabela
        if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
            self.failure_methods = {
                # === POD FAILURES ===
                'kill_processes': self.aws_injector.kill_all_processes,
                'kill_init': self.aws_injector.kill_init_process,
                
                # === WORKER NODE FAILURES ===
                # 'kill_worker_node_processes': self.aws_injector.kill_worker_node_processes,
                'shutdown_worker_node': self._shutdown_worker_node_wrapper,  # Wrapper para passar delay configurado
                'restart_worker_node': self.aws_injector.kill_worker_node_processes,  # Usa mesmo método 
                'kill_kubelet': self.aws_injector.kill_kubelet,
                'delete_kube_proxy': self.aws_injector.kill_kube_proxy_pod,
                'restart_containerd': self.aws_injector.restart_containerd,
                
                # === CONTROL PLANE FAILURES ===
                'kill_control_plane_processes': self.aws_injector.kill_control_plane_processes,
                'shutdown_control_plane': self._shutdown_control_plane_wrapper,  # Wrapper para passar delay configurado
                'kill_kube_apiserver': self.aws_injector.kill_kube_apiserver,
                'kill_kube_controller_manager': self.aws_injector.kill_kube_controller_manager,
                'kill_kube_scheduler': self.aws_injector.kill_kube_scheduler,
                'kill_etcd': self.aws_injector.kill_etcd,
            }
        else:
            self.failure_methods = {
                # === POD FAILURES ===
                'kill_processes': self.pod_injector.kill_all_processes,
                'kill_init': self.pod_injector.kill_init_process,
                # 'delete_pod': self.pod_injector.delete_pod,
                
                # === WORKER NODE FAILURES ===
                'kill_worker_node_processes': self.node_injector.kill_worker_node_processes,
                'restart_worker_node': self.node_injector.kill_worker_node_processes,  # Mesmo que kill (docker restart)
                'kill_kubelet': self.control_plane_injector.kill_kubelet,
                'shutdown_worker_node': self._shutdown_worker_node_wrapper,  # Wrapper para passar delay configurado
                
                # === CONTROL PLANE FAILURES ===
                'kill_control_plane_processes': self.node_injector.kill_control_plane_processes,
                'shutdown_control_plane': self._shutdown_control_plane_wrapper,  # Wrapper para passar delay configurado
                'kill_kube_apiserver': self.control_plane_injector.kill_kube_apiserver,
                'kill_kube_controller_manager': self.control_plane_injector.kill_kube_controller_manager,
                'kill_kube_scheduler': self.control_plane_injector.kill_kube_scheduler,
                'kill_etcd': self.control_plane_injector.kill_etcd,
                
                # === NETWORK/RUNTIME FAILURES ===
                'delete_kube_proxy': self.control_plane_injector.delete_kube_proxy_pod,
                'restart_containerd': self.control_plane_injector.restart_containerd
            }
    
    def initial_system_check(self) -> Tuple[int, Dict, List[str]]:
        """
        Verificação inicial completa do sistema.
        
        Returns:
            Tuple com (número de apps saudáveis, status detalhado, aplicações descobertas)
        """
        print("1️⃣ === VERIFICAÇÃO INICIAL DO SISTEMA ===")
        
        # Mostrar status dos pods
        self.system_monitor.show_pod_status()
        
        # Verificar port-forwards (comentado - usando IP público AWS)
        # self.health_checker.check_port_forwards()
        
        # Verificar saúde das aplicações
        print("🔍 Verificando saúde das aplicações via HTTP...")
        health_status = self.health_checker.check_all_applications(verbose=True)
        healthy_count = sum(1 for status in health_status.values() if status.get('healthy', False))
        
        # Extrair nomes das aplicações descobertas
        discovered_apps = list(health_status.keys()) if health_status else []
        
        if health_status:
            total_services = len(health_status)
            print(f"\n📊 === RESULTADO DA VERIFICAÇÃO ===")
            print(f"✅ Aplicações saudáveis: {healthy_count}/{total_services}")
            
            for service, status in health_status.items():
                emoji = "✅" if status.get('healthy', False) else "❌"
                health_msg = "saudável" if status.get('healthy', False) else "indisponível"
                print(f"   {emoji} {service}: {health_msg}")
                if 'error' in status:
                    print(f"      🔍 Detalhes: {status['error']}")
        
        print("="*50)
        return healthy_count, health_status, discovered_apps
    
    def _shutdown_worker_node_wrapper(self, target: str) -> Tuple[bool, str]:
        """
        Wrapper para shutdown_worker_node que obtém delay da configuração.
        """
        # Obter delay da configuração
        delay_seconds = 10  # Default
        
        if hasattr(self, 'config') and self.config:
            config_simples = getattr(self.config, 'config_simples', None)
            if config_simples and isinstance(config_simples, dict):
                delay_seconds = config_simples.get('delay', delay_seconds)
        
        # Chamar o handler real com delay configurado
        return self._shutdown_worker_node_handler(target, delay_seconds)
    
    def _shutdown_control_plane_wrapper(self, target: str) -> Tuple[bool, str]:
        """
        Wrapper para shutdown_control_plane que obtém delay da configuração.
        Segue a mesma lógica do shutdown_worker_node.
        """
        # Obter delay da configuração
        delay_seconds = 10  # Default
        
        if hasattr(self, 'config') and self.config:
            config_simples = getattr(self.config, 'config_simples', None)
            if config_simples and isinstance(config_simples, dict):
                delay_seconds = config_simples.get('delay', delay_seconds)
        
        # Chamar o handler real com delay configurado
        return self._shutdown_control_plane_handler(target, delay_seconds)
    
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
        healthy_count, initial_health, discovered_apps = self.initial_system_check()
        
        # Armazenar as aplicações descobertas para uso posterior
        self.discovered_apps = discovered_apps
        
        if healthy_count == 0:
            # Em modo AWS, pular validação de aplicações (testamos infraestrutura)
            if self.is_aws_mode:
                print("⚠️ Modo AWS: Pulando validação de aplicações para testes de infraestrutura")
                print("🚀 Continuando com teste mesmo com aplicações não saudáveis...")
            elif not self._handle_unhealthy_system():
                self.csv_reporter.finish_realtime_report()
                return []
        
        # Executar teste iterativo
        results = []
        test_start_time = time.time()
        
        try:
            for iteration in range(1, iterations + 1):
                print(f"\n🔄 === ITERAÇÃO {iteration}/{iterations} ===")
                
                # Executar uma iteração de teste
                if self.is_aws_mode:
                    print("🚀 Modo AWS: Usando verificação de pods via control plane...")
                    
                    # Mostrar pods atuais das aplicações
                    # all_pods = self.system_monitor.get_pods()
                    # print(f"📋 Pods das aplicações encontrados: {all_pods}")
                    
                    # Verificar saúde das aplicações via control plane
                    # print("🔍 Verificando saúde das aplicações via control plane...")
                    # health_status = self.health_checker.check_all_applications(verbose=True)
                    # healthy_count = sum(1 for status in health_status.values() if status.get('healthy', False))
                    # total_services = len(health_status) if health_status else 0
                    
                    # print(f"📊 Aplicações saudáveis: {healthy_count}/{total_services}")
                    # for service, status in health_status.items():
                    #     emoji = "✅" if status.get('healthy', False) else "❌"
                    #     health_msg = "saudável" if status.get('healthy', False) else "indisponível"
                    #     print(f"   {emoji} {service}: {health_msg}")
                
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
        if not self.is_aws_mode:
            print("   2. Configure port-forwards:")
            print("      kubectl port-forward svc/foo-service 8080:80 &")
            print("      kubectl port-forward svc/bar-service 8081:80 &")
            print("      kubectl port-forward svc/test-service 8082:80 &")
            print("   3. Ou execute o script port-forward-monitor.sh")
        else:
            print("   2. Verifique se as aplicações estão acessíveis via IP público")
            print("   3. Verifique se os serviços NodePort estão configurados")
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
        
        # ========== CABEÇALHO DA ITERAÇÃO ==========
        print(f"\n{'='*60}")
        print(f"🎯 ITERAÇÃO {iteration} - {component_type.upper()}: {failure_method}")
        print(f"🎭 Target: {target}")
        print(f"{'='*60}")
        
        iteration_start = time.time()
        
        # ========== STATUS INICIAL CONCISO ==========
        print(f"\n📋 STATUS INICIAL:")
        self._show_quick_pod_status()
        
        # ========== INJEÇÃO DE FALHA ==========
        print(f"\n🔴 INJETANDO FALHA: {failure_method}")
        print(f"🎯 Alvo: {target}")
        
        failure_start = time.time()
        failure_timestamp = datetime.now().isoformat()
        
        failure_success, executed_command = self.failure_methods[failure_method](target)
        
        if not failure_success:
            print(f"❌ FALHA na injeção de falha para {target}")
            return None
        
        injection_time = time.time() - failure_start
        print(f"✅ FALHA INJETADA com sucesso em {injection_time:.2f}s!")
        
        # ========== AGUARDANDO RECUPERAÇÃO ==========
        print(f"\n⏳ AGUARDANDO RECUPERAÇÃO...")
        recovery_start = time.time()
        
        # CORREÇÃO: Usar SEMPRE o método do health_checker que já funciona
        # O health_checker.wait_for_recovery() já tem suporte AWS completo
        recovered, recovery_time = self.health_checker.wait_for_recovery(
            discovered_apps=getattr(self, 'discovered_apps', None)
        )
        
        # ========== RESULTADO ==========
        total_time = time.time() - iteration_start
        
        if recovered:
            print(f"\n🎉 SUCESSO - Iteração {iteration} completada!")
            print(f"⏱️ Tempo de recuperação: {recovery_time:.2f}s")
            print(f"🕐 Tempo total: {total_time:.2f}s")
        else:
            print(f"\n❌ FALHA - Iteração {iteration} não recuperou")
            print(f"⏰ Timeout após {recovery_time:.2f}s")
            print(f"🕐 Tempo total: {total_time:.2f}s")
        
        # ========== STATUS FINAL CONCISO ==========
        print(f"\n📊 STATUS FINAL:")
        self._show_quick_pod_status()
        
        # Atualizar métricas
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
            'injection_time': injection_time,
            'initial_healthy_apps': 1,  # Para compatibilidade
            'component_stats': self.metrics_analyzer.get_component_statistics(target)
        }
        
        return result
    
    def _show_quick_pod_status(self):
        """Mostra status conciso dos pods principais."""
        try:
            if self.is_aws_mode:
                # AWS: Usar kubectl via SSH
                instances = self.aws_injector._get_aws_instances()
            
                # Encontrar o node_name do ControlPlane dentro do dicionário instances
                control_plane_node = next(
                    (k for k, v in instances.items() if v.get('Name') == 'ControlPlane' or v.get('Name', '').lower().startswith('control')),
                    None
                )
                if not control_plane_node:
                    print("   ❌ ControlPlane não encontrado em instances")
                    return False

                node_name = control_plane_node  # Ex.: 'ip-10-0-0-28'
                
                result = self.aws_injector._execute_ssh_command(
                    node_name,
                    'sudo kubectl get pods --no-headers -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[*].ready'
                )
                
                if result[0] and result[1].strip():
                    lines = result[1].strip().split('\n')
                    for line in lines:
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 3:
                                pod_name = parts[0]
                                pod_phase = parts[1]
                                ready_status = parts[2] if len(parts) > 2 else "unknown"
                                
                                # Emojis baseados no status
                                if pod_phase == 'Running' and 'true' in ready_status:
                                    emoji = "✅"
                                elif pod_phase in ['CrashLoopBackOff', 'Error', 'Failed']:
                                    emoji = "❌"
                                elif pod_phase in ['Pending', 'ContainerCreating']:
                                    emoji = "🔄"
                                else:
                                    emoji = "❓"
                                
                                # Mostrar apenas pods das apps principais
                                if any(app in pod_name for app in ['bar-app', 'foo-app', 'test-app']):
                                    print(f"   {emoji} {pod_name}: {pod_phase} ({ready_status})")
                else:
                    print("   ❌ Erro ao verificar pods via SSH")
            else:
                # Local: kubectl direto
                import subprocess
                result = subprocess.run(
                    ['kubectl', 'get', 'pods', '--no-headers', 
                     '-o', 'custom-columns=NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[*].ready'],
                    capture_output=True, text=True, timeout=10
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 3:
                                pod_name = parts[0]
                                pod_phase = parts[1]
                                ready_status = parts[2] if len(parts) > 2 else "unknown"
                                
                                if pod_phase == 'Running' and 'true' in ready_status:
                                    emoji = "✅"
                                elif pod_phase in ['CrashLoopBackOff', 'Error', 'Failed']:
                                    emoji = "❌"
                                elif pod_phase in ['Pending', 'ContainerCreating']:
                                    emoji = "🔄"
                                else:
                                    emoji = "❓"
                                
                                print(f"   {emoji} {pod_name}: {pod_phase} ({ready_status})")
                else:
                    print("   ❌ Erro ao verificar pods localmente")
                    
        except Exception as e:
            print(f"   ⚠️ Erro ao verificar status dos pods: {e}")
    
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
    
    def _shutdown_worker_node_handler(self, target: str, delay_seconds: int = 10) -> Tuple[bool, str]:
        """
        Handler especial para shutdown de worker node com delay configurado + auto-start.
        
        Processo CORRETO:
        1. Desliga o worker node (shutdown ou docker stop)
        2. Aguarda delay configurado do teste de simulação (não MTTR)
        3. Religa automaticamente (auto-start ou docker start) - self-healing
        4. Verifica com health checker quando aplicações voltaram
        
        Tempo de recuperação = MTTR configurado + tempo real de health check
        
        Args:
            target: Nome do worker node para desligar
            delay_seconds: Delay configurado do teste (campo "delay" do config_simples)
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        try:
            import time
            
            # 1. Obter MTTR configurado para contabilização final
            mttr_hours = 0.016  # MTTR padrão de ~1 minuto se não encontrar configuração
            
            # Verificar se existe configuração MTTR
            if hasattr(self, 'config') and self.config:
                config_simples = getattr(self.config, 'config_simples', None)
                if config_simples and isinstance(config_simples, dict):
                    mttr_config = config_simples.get('mttr_config', {})
                    worker_mttr = mttr_config.get('worker_node', {})
                    mttr_hours = worker_mttr.get(target, mttr_hours)
                    print(f"📊 MTTR configurado para contabilização: {mttr_hours:.4f}h ({mttr_hours*3600:.1f}s)")
                    
                    # CORREÇÃO: Usar delay do teste, não MTTR
                    test_delay = config_simples.get('delay', delay_seconds)
                    print(f"📊 Delay do teste configurado: {test_delay}s")
                    delay_seconds = test_delay
                else:
                    print(f"⚠️ Configuração não encontrada, usando delay padrão: {delay_seconds}s")
            else:
                print(f"⚠️ Config não disponível, usando delay padrão: {delay_seconds}s")
            
            # 2. Executar shutdown do worker node
            print(f"🔌 Desligando worker node: {target}")
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                shutdown_success, shutdown_command = self.aws_injector.shutdown_worker_node(target)
            else:
                shutdown_success, shutdown_command = self.node_injector.shutdown_worker_node(target)
            
            if not shutdown_success:
                print(f"❌ Falha ao desligar nó {target}")
                return False, f"shutdown_worker_node {target}"
            
            print(f"✅ Worker node {target} desligado com sucesso")
            
            # 3. Aguardar delay configurado do teste (NÃO o MTTR)
            print(f"⏱️ Aguardando delay configurado do teste: {delay_seconds}s...")
            time.sleep(delay_seconds)
            
            # 4. Self-healing: Religar automaticamente
            print(f"🔄 Self-healing: Religando worker node {target}...")
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                startup_success, startup_command = self.aws_injector.start_worker_node(target)
            else:
                startup_success, startup_command = self.node_injector.start_worker_node(target)
            
            if not startup_success:
                print(f"❌ Falha no self-healing de {target}")
                print(f"🚨 ATENÇÃO: Node {target} pode estar offline permanentemente!")
                return False, f"shutdown_worker_node {target} (recovery-failed)"
            
            print(f"✅ Worker node {target} religado com sucesso")
            
            # 5. CORREÇÃO ESPECÍFICA PARA KIND: Reiniciar networking no container (apenas para modo local)
            if not self.is_aws_mode:
                print(f"🌐 Corrigindo conectividade de rede no Kind para {target}...")
                self._fix_kind_networking(target)
            
            # 6. Aguardar node ficar Ready
            print(f"⏱️ Aguardando node {target} ficar Ready...")
            node_ready = self._wait_for_node_ready(target, timeout=180)  # 3 minutos para AWS
            
            if not node_ready:
                print(f"⚠️ Node {target} não ficou Ready no tempo esperado")
            
            # 7. CORREÇÃO: Aguardar aplicações ficarem ativas com health checker
            print(f"⚕️ Aguardando aplicações ficarem ativas com health checker...")
            health_check_start = time.time()
            
            # Usar health checker para verificar recuperação real (mas não contabilizar o tempo)
            apps_recovered, health_check_time = self.health_checker.wait_for_recovery(
                timeout=self.config.current_recovery_timeout,
                discovered_apps=getattr(self, 'discovered_apps', None)
            )
            
            if apps_recovered:
                print(f"✅ Aplicações ficaram ativas em {health_check_time:.1f}s (tempo real de espera)")
                # CORREÇÃO: Retornar apenas o MTTR configurado, não somar tempos reais
                mttr_seconds = mttr_hours * 3600
                print(f"📊 Retornando MTTR configurado: {mttr_seconds:.1f}s (não contabilizando tempo real de {health_check_time:.1f}s)")
                return True, f"shutdown_worker_node {target} (recovered, MTTR: {mttr_seconds:.1f}s)"
            else:
                print(f"⚠️ Aplicações não ficaram ativas no timeout configurado ({self.config.current_recovery_timeout}s)")
                # Mesmo assim, retornar MTTR configurado 
                mttr_seconds = mttr_hours * 3600
                print(f"📊 Retornando MTTR configurado mesmo com recovery parcial: {mttr_seconds:.1f}s")
                return True, f"shutdown_worker_node {target} (partial-recovery, MTTR: {mttr_seconds:.1f}s)"
                
        except Exception as e:
            print(f"❌ Erro durante shutdown/recovery de {target}: {e}")
            return False, f"shutdown_worker_node {target} (error: {e})"
    
    def _fix_kind_networking(self, node_name: str):
        """
        Corrige problemas de conectividade de rede específicos do Kind após restart.
        
        Args:
            node_name: Nome do node para corrigir
        """
        try:
            import subprocess
            import time
            
            print(f"🔧 Aplicando correções de rede no Kind para {node_name}...")
            
            # 0. CORRIGIR DNS DO KIND (problema mais comum)
            print("   🌐 Corrigindo DNS do Kind...")
            
            # Obter IP do control plane
            cp_ip_result = subprocess.run([
                'docker', 'inspect', 'local-k8s-control-plane', 
                '--format', '{{.NetworkSettings.Networks.kind.IPAddress}}'
            ], capture_output=True, text=True, timeout=10)
            
            if cp_ip_result.returncode == 0:
                cp_ip = cp_ip_result.stdout.strip()
                print(f"      Control plane IP: {cp_ip}")
                
                # Adicionar entrada ao /etc/hosts se não existir
                subprocess.run([
                    'docker', 'exec', node_name, 'bash', '-c',
                    f'grep -q "local-k8s-control-plane" /etc/hosts || echo "{cp_ip} local-k8s-control-plane" >> /etc/hosts'
                ], capture_output=True, timeout=30)
                
                print("      ✅ DNS mapping adicionado ao /etc/hosts")
            else:
                print("      ⚠️ Não foi possível obter IP do control plane")
            
            # 1. Reiniciar systemd-resolved no container (corrige DNS) - opcional no Kind
            print("   📡 Reiniciando DNS resolver...")
            subprocess.run([
                'docker', 'exec', node_name, 'systemctl', 'restart', 'systemd-resolved'
            ], capture_output=True, timeout=30)
            
            # 2. Reiniciar containerd para recriar bridges de rede
            print("   🔄 Reiniciando containerd...")
            subprocess.run([
                'docker', 'exec', node_name, 'systemctl', 'restart', 'containerd'
            ], capture_output=True, timeout=60)
            
            # 3. Aguardar containerd estabilizar
            time.sleep(10)
            
            # 4. Reiniciar kubelet para reconectar ao cluster
            print("   ⚙️ Reiniciando kubelet...")
            
            # Primeiro, parar o kubelet para limpar file descriptors
            subprocess.run([
                'docker', 'exec', node_name, 'systemctl', 'stop', 'kubelet'
            ], capture_output=True, timeout=30)
            
            # Limpar processos órfãos que podem estar mantendo file descriptors
            print("   🧹 Limpando processos órfãos...")
            subprocess.run([
                'docker', 'exec', node_name, 'bash', '-c', 
                'pkill -f "kubelet" || true; pkill -f "crio" || true'
            ], capture_output=True, timeout=30)
            
            # Aguardar limpeza de recursos
            time.sleep(5)
            
            subprocess.run([
                'docker', 'exec', node_name, 'systemctl', 'start', 'kubelet'
            ], capture_output=True, timeout=30)
            
            # 5. Aguardar kubelet estabilizar mais tempo devido ao file descriptor issue
            time.sleep(15)
            
            # 6. Aplicar flush nas tabelas iptables para limpar regras antigas
            print("   🔥 Limpando regras iptables antigas...")
            subprocess.run([
                'docker', 'exec', node_name, 'iptables', '-F'
            ], capture_output=True, timeout=30)
            
            subprocess.run([
                'docker', 'exec', node_name, 'iptables', '-t', 'nat', '-F'
            ], capture_output=True, timeout=30)
            
            print(f"✅ Correções de rede aplicadas em {node_name}")
            
        except Exception as e:
            print(f"⚠️ Erro ao aplicar correções de rede em {node_name}: {e}")

    def _wait_for_node_ready(self, node_name: str, timeout: int = 60) -> bool:
        """
        Aguarda um node ficar Ready.
        
        Args:
            node_name: Nome do node
            timeout: Timeout em segundos
            
        Returns:
            True se o node ficou Ready, False caso contrário
        """
        import subprocess
        import time
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Para AWS, usar SSH direto
                if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                    cmd = f"sudo kubectl get node {node_name} -o jsonpath='{{.status.conditions[?(@.type==\"Ready\")].status}}'"
                    result = self.aws_injector.run_remote_command(cmd)
                    
                    print(f"🔍 Debug: cmd='{cmd}'")
                    print(f"🔍 Debug: returncode={result.returncode}")
                    print(f"🔍 Debug: output='{result.stdout.strip()}'")
                    print(f"🔍 Debug: stderr='{result.stderr.strip()}'")
                    
                    if result.returncode == 0 and result.stdout.strip() == 'True':
                        print(f"✅ Node {node_name} está Ready!")
                        return True
                        
                    # Verificação alternativa via get nodes
                    cmd_alt = f"sudo kubectl get nodes | grep {node_name}"
                    result_alt = self.aws_injector.run_remote_command(cmd_alt)
                    print(f"🔍 Debug alternativo: '{result_alt.stdout.strip()}'")
                    
                    if result_alt.returncode == 0 and 'Ready' in result_alt.stdout:
                        print(f"✅ Node {node_name} está Ready (verificação alternativa)!")
                        return True
                else:
                    # Para local, usar kubectl normal
                    result = self.kubectl.execute_kubectl([
                        'get', 'node', node_name, 
                        '-o', 'jsonpath={.status.conditions[?(@.type=="Ready")].status}'
                    ])
                    
                    if result['success'] and result['output'].strip() == 'True':
                        print(f"✅ Node {node_name} está Ready!")
                        return True
                        
            except Exception as e:
                print(f"🔍 Debug: Exceção ao verificar node: {e}")
            
            print(f"⏳ Node {node_name} ainda não está Ready, aguardando...")
            time.sleep(5)
        
        return False

    def _shutdown_control_plane_handler(self, target: str, delay_seconds: int = 10) -> Tuple[bool, str]:
        """
        Handler especial para shutdown de control plane com delay configurado + auto-start.
        
        Processo CORRETO:
        1. Desliga o control plane (shutdown ou docker stop)
        2. Aguarda delay configurado do teste de simulação (não MTTR)
        3. Religa automaticamente (auto-start ou docker start) - self-healing
        4. Verifica com health checker quando aplicações voltaram
        
        Tempo de recuperação = MTTR configurado + tempo real de health check
        
        Args:
            target: Nome do control plane para desligar
            delay_seconds: Delay configurado do teste (campo "delay" do config_simples)
            
        Returns:
            Tuple com (sucesso, comando_executado)
        """
        try:
            import time
            
            # 1. Obter MTTR configurado para contabilização final
            mttr_hours = 0.025  # MTTR padrão de ~1.5 minutos se não encontrar configuração
            
            # Verificar se existe configuração MTTR
            if hasattr(self, 'config') and self.config:
                config_simples = getattr(self.config, 'config_simples', None)
                if config_simples and isinstance(config_simples, dict):
                    mttr_config = config_simples.get('mttr_config', {})
                    control_plane_mttr = mttr_config.get('control_plane', {})
                    mttr_hours = control_plane_mttr.get(target, mttr_hours)
                    print(f"📊 MTTR configurado para contabilização: {mttr_hours:.4f}h ({mttr_hours*3600:.1f}s)")
                    
                    # CORREÇÃO: Usar delay do teste, não MTTR
                    test_delay = config_simples.get('delay', delay_seconds)
                    print(f"📊 Delay do teste configurado: {test_delay}s")
                    delay_seconds = test_delay
                else:
                    print(f"⚠️ Configuração não encontrada, usando delay padrão: {delay_seconds}s")
            else:
                print(f"⚠️ Config não disponível, usando delay padrão: {delay_seconds}s")
            
            # 2. Executar shutdown do control plane
            print(f"🔌 Desligando control plane: {target}")
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                shutdown_success, shutdown_command = self.aws_injector.shutdown_control_plane(target)
            else:
                shutdown_success, shutdown_command = self.node_injector.shutdown_control_plane(target)
            
            if not shutdown_success:
                print(f"❌ Falha ao desligar control plane {target}")
                return False, f"shutdown_control_plane {target}"
            
            print(f"✅ Control plane {target} desligado com sucesso")
            
            # 3. Aguardar delay configurado do teste (NÃO o MTTR)
            print(f"⏱️ Aguardando delay configurado do teste: {delay_seconds}s...")
            time.sleep(delay_seconds)
            
            # 4. Self-healing: Religar automaticamente
            print(f"🔄 Self-healing: Religando control plane {target}...")
            if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                startup_success, startup_command = self.aws_injector.start_control_plane(target)
            else:
                startup_success, startup_command = self.node_injector.start_control_plane(target)
            
            if not startup_success:
                print(f"❌ Falha no self-healing de {target}")
                print(f"🚨 ATENÇÃO: Control plane {target} pode estar offline permanentemente!")
                return False, f"shutdown_control_plane {target} (recovery-failed)"
            
            print(f"✅ Control plane {target} religado com sucesso")
            
            # 5. CORREÇÃO ESPECÍFICA PARA KIND: Reiniciar networking (apenas para modo local)
            if not self.is_aws_mode:
                print(f"🌐 Corrigindo conectividade de rede no Kind para {target}...")
                self._fix_kind_networking(target)
            
            # 6. Aguardar control plane ficar Ready
            print(f"⏱️ Aguardando control plane {target} ficar Ready...")
            node_ready = self._wait_for_node_ready(target, timeout=180)  # 3 minutos para AWS
            
            if not node_ready:
                print(f"⚠️ Control plane {target} não ficou Ready no tempo esperado")
            
            # 7. CORREÇÃO: Aguardar aplicações ficarem ativas com health checker
            print(f"⚕️ Aguardando aplicações ficarem ativas com health checker...")
            
            # Usar health checker para verificar recuperação real (mas não contabilizar o tempo)
            apps_recovered, health_check_time = self.health_checker.wait_for_recovery(
                timeout=self.config.current_recovery_timeout,
                discovered_apps=getattr(self, 'discovered_apps', None)
            )
            
            if apps_recovered:
                print(f"✅ Aplicações ficaram ativas em {health_check_time:.1f}s (tempo real de espera)")
                # CORREÇÃO: Retornar apenas o MTTR configurado, não somar tempos reais
                mttr_seconds = mttr_hours * 3600
                print(f"📊 Retornando MTTR configurado: {mttr_seconds:.1f}s (não contabilizando tempo real de {health_check_time:.1f}s)")
                return True, f"shutdown_control_plane {target} (recovered, MTTR: {mttr_seconds:.1f}s)"
            else:
                print(f"⚠️ Aplicações não ficaram ativas no timeout configurado ({self.config.current_recovery_timeout}s)")
                # Mesmo assim, retornar MTTR configurado 
                mttr_seconds = mttr_hours * 3600
                print(f"📊 Retornando MTTR configurado mesmo com recovery parcial: {mttr_seconds:.1f}s")
                return True, f"shutdown_control_plane {target} (partial-recovery, MTTR: {mttr_seconds:.1f}s)"
                
        except Exception as e:
            print(f"❌ Erro durante shutdown/recovery de control plane {target}: {e}")
            return False, f"shutdown_control_plane {target} (error: {e})"

    @property
    def component_metrics(self):
        """Propriedade para acessar métricas de componentes."""
        return self.metrics_analyzer.component_metrics