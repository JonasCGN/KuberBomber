#!/usr/bin/env python3
"""
Sistema de Testes de Confiabilidade para Kubernetes
Testa MTTF (Mean Time To Failure) e MTTR (Mean Time To Recovery) 
de diferentes componentes: pods, processos, worker nodes e control plane
"""

import argparse
import subprocess
import time
import requests
import json
import sys
import os
import csv
import select
import termios
import tty
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import statistics

class ReliabilityTester:
    def __init__(self):
        self.services = {
            'foo': {'port': 8080, 'endpoint': '/foo'},
            'bar': {'port': 8081, 'endpoint': '/bar'},
            'test': {'port': 8082, 'endpoint': '/test'}
        }
        self.test_results = []
        self.component_metrics = {}  # Armazena métricas por componente individual
        self.failure_methods = {
            'kill_processes': self.kill_all_processes,
            'kill_init': self.kill_init_process,
            'delete_pod': self.delete_pod,
            'restart_worker_node': self.restart_worker_node,
            'restart_control_plane': self.restart_control_plane
        }
        
    def get_single_char(self):
        """Lê um único caractere do terminal sem pressionar Enter"""
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                char = sys.stdin.read(1)
                return char
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except:
            return input("Pressione Enter: ")[0] if input("Pressione Enter: ") else '\n'
    
    def select_interactive(self, options: List[str], title: str) -> Optional[str]:
        """Seleção interativa genérica"""
        if not options:
            print(f"❌ Nenhuma opção disponível para {title}")
            return None
        
        if len(options) == 1:
            print(f"🎯 Apenas uma opção disponível: {options[0]}")
            return options[0]
        
        current_selection = 0
        
        def draw_menu():
            subprocess.run(['clear'], shell=True)
            print(f"🎯 {title}:")
            print("Use ↑/↓ (ou w/s) para navegar, Enter para confirmar, q para cancelar\n")
            
            for i, option in enumerate(options):
                if i == current_selection:
                    print(f"➤ {option} ⭐")
                else:
                    print(f"  {option}")
            
            print(f"\n🎯 Selecionado: {options[current_selection]}")
            print("📋 Controles: ↑/↓ ou w/s (navegar), Enter (confirmar), q (cancelar)")
        
        draw_menu()
        
        while True:
            try:
                char = self.get_single_char()
                
                if char in ['\r', '\n']:
                    selected = options[current_selection]
                    subprocess.run(['clear'], shell=True)
                    print(f"✅ Selecionado: {selected}")
                    return selected
                
                elif char in ['q', 'Q']:
                    subprocess.run(['clear'], shell=True)
                    print("❌ Seleção cancelada")
                    return None
                
                elif char in ['w', 'W']:
                    current_selection = (current_selection - 1) % len(options)
                    draw_menu()
                
                elif char in ['s', 'S']:
                    current_selection = (current_selection + 1) % len(options)
                    draw_menu()
                
                elif ord(char) == 27:
                    try:
                        next_chars = sys.stdin.read(2)
                        if next_chars == '[A':
                            current_selection = (current_selection - 1) % len(options)
                            draw_menu()
                        elif next_chars == '[B':
                            current_selection = (current_selection + 1) % len(options)
                            draw_menu()
                    except:
                        pass
                
            except KeyboardInterrupt:
                subprocess.run(['clear'], shell=True)
                print("❌ Teste cancelado")
                return None
    
    def get_pods(self) -> List[str]:
        """Obtém lista de pods das aplicações"""
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pods', '-l', 'app in (foo,bar,test)', 
                '-o', 'jsonpath={.items[*].metadata.name}', '--context=local-k8s'
            ], capture_output=True, text=True, check=True)
            
            pods = result.stdout.strip().split()
            return [pod for pod in pods if pod]
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter pods: {e}")
            return []
    
    def get_worker_nodes(self) -> List[str]:
        """Obtém lista de worker nodes"""
        try:
            result = subprocess.run([
                'kubectl', 'get', 'nodes', '-l', '!node-role.kubernetes.io/control-plane',
                '-o', 'jsonpath={.items[*].metadata.name}', '--context=local-k8s'
            ], capture_output=True, text=True, check=True)
            
            nodes = result.stdout.strip().split()
            return [node for node in nodes if node]
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter worker nodes: {e}")
            return []
    
    def check_application_health(self, service: str) -> Dict:
        """Verifica se uma aplicação está respondendo"""
        config = self.services[service]
        url = f"http://localhost:{config['port']}{config['endpoint']}"
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=5)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                return {
                    'status': 'healthy',
                    'response_time': response_time,
                    'status_code': response.status_code
                }
            else:
                return {
                    'status': 'unhealthy',
                    'response_time': response_time,
                    'status_code': response.status_code,
                    'error': f"HTTP {response.status_code}"
                }
        except requests.exceptions.RequestException as e:
            return {
                'status': 'unreachable',
                'response_time': None,
                'error': str(e)
            }
    
    def update_component_metrics(self, component_id: str, component_type: str, 
                               recovery_time: float, recovered: bool):
        """Atualiza métricas individuais de um componente específico"""
        if component_id not in self.component_metrics:
            self.component_metrics[component_id] = {
                'component_type': component_type,
                'total_failures': 0,
                'successful_recoveries': 0,
                'recovery_times': [],
                'failure_timestamps': [],
                'mttr_current': 0.0,
                'availability': 0.0
            }
        
        metrics = self.component_metrics[component_id]
        metrics['total_failures'] += 1
        metrics['failure_timestamps'].append(datetime.now().isoformat())
        
        if recovered:
            metrics['successful_recoveries'] += 1
            metrics['recovery_times'].append(recovery_time)
            metrics['mttr_current'] = statistics.mean(metrics['recovery_times'])
        
        # Calcular disponibilidade (% de recuperações bem-sucedidas)
        metrics['availability'] = (metrics['successful_recoveries'] / metrics['total_failures']) * 100
    
    def get_component_statistics(self, component_id: str) -> Dict:
        """Retorna estatísticas detalhadas de um componente específico"""
        if component_id not in self.component_metrics:
            return {}
        
        metrics = self.component_metrics[component_id]
        recovery_times = metrics['recovery_times']
        
        stats = {
            'component_id': component_id,
            'component_type': metrics['component_type'],
            'total_failures': metrics['total_failures'],
            'successful_recoveries': metrics['successful_recoveries'],
            'availability_percent': metrics['availability'],
            'mttr_mean': statistics.mean(recovery_times) if recovery_times else 0,
            'mttr_median': statistics.median(recovery_times) if recovery_times else 0,
            'mttr_min': min(recovery_times) if recovery_times else 0,
            'mttr_max': max(recovery_times) if recovery_times else 0,
            'mttr_std_dev': statistics.stdev(recovery_times) if len(recovery_times) > 1 else 0
        }
        
        return stats
    
    def print_individual_component_stats(self):
        """Imprime estatísticas individuais de cada componente testado"""
        if not self.component_metrics:
            print("📊 Nenhuma métrica de componente individual disponível")
            return
        
        print(f"\n📊 === MÉTRICAS INDIVIDUAIS POR COMPONENTE ===")
        
        for component_id, metrics in self.component_metrics.items():
            stats = self.get_component_statistics(component_id)
            
            print(f"\n🔧 Componente: {component_id}")
            print(f"   📝 Tipo: {stats['component_type']}")
            print(f"   💥 Total de falhas: {stats['total_failures']}")
            print(f"   ✅ Recuperações bem-sucedidas: {stats['successful_recoveries']}")
            print(f"   📈 Disponibilidade: {stats['availability_percent']:.2f}%")
            
            if stats['mttr_mean'] > 0:
                print(f"   ⏱️ MTTR Médio: {stats['mttr_mean']:.2f}s")
                print(f"   📊 MTTR Mediano: {stats['mttr_median']:.2f}s")
                print(f"   📉 MTTR Mínimo: {stats['mttr_min']:.2f}s")
                print(f"   📈 MTTR Máximo: {stats['mttr_max']:.2f}s")
                if stats['mttr_std_dev'] > 0:
                    print(f"   📏 Desvio Padrão: {stats['mttr_std_dev']:.2f}s")
            else:
                print(f"   ❌ Nenhuma recuperação bem-sucedida para calcular MTTR")
        
        print("="*60)
        """Verifica saúde de todas as aplicações"""
        results = {}
        for service in self.services.keys():
            results[service] = self.check_application_health(service)
        return results
    
    def wait_for_recovery(self, timeout: int = 300) -> Tuple[bool, float]:
        """Aguarda todas as aplicações ficarem saudáveis e retorna tempo de recuperação"""
        print(f"⏳ Aguardando recuperação (timeout: {timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            health_status = self.check_all_applications()
            healthy_count = sum(1 for status in health_status.values() if status['status'] == 'healthy')
            
            if healthy_count == len(self.services):
                recovery_time = time.time() - start_time
                print(f"✅ Todas as aplicações recuperadas em {recovery_time:.2f}s")
                return True, recovery_time
            
            print(f"🔍 Verificação: {healthy_count}/{len(self.services)} saudáveis (tempo: {time.time() - start_time:.1f}s)")
            time.sleep(2)
        
        print(f"❌ Timeout: Aplicações não se recuperaram em {timeout}s")
        return False, timeout
    
    # ============ MÉTODOS DE FALHA ============
    
    def kill_all_processes(self, target: str) -> Tuple[bool, str]:
        """Mata todos os processos em um pod"""
        command = f"kubectl exec {target} --context=local-k8s -- sh -c 'kill -9 -1'"
        print(f"💀 Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'exec', target, '--context=local-k8s', '--', 
                'sh', '-c', 'kill -9 -1'
            ], capture_output=True, text=True)
            
            print(f"✅ Comando executado no pod {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def kill_init_process(self, target: str) -> Tuple[bool, str]:
        """Mata o processo init (PID 1) do container"""
        command = f"kubectl exec {target} --context=local-k8s -- kill -9 1"
        print(f"🔌 Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'exec', target, '--context=local-k8s', '--', 
                'kill', '-9', '1'
            ], capture_output=True, text=True)
            
            print(f"✅ Comando executado no pod {target}")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def delete_pod(self, target: str) -> Tuple[bool, str]:
        """Deleta um pod (será recriado pelo ReplicaSet)"""
        command = f"kubectl delete pod {target} --context=local-k8s"
        print(f"🗑️ Executando: {command}")
        
        try:
            result = subprocess.run([
                'kubectl', 'delete', 'pod', target, '--context=local-k8s'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Pod {target} deletado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def restart_worker_node(self, target: str) -> Tuple[bool, str]:
        """Simula restart de worker node (via docker restart em Kind)"""
        command = f"docker restart {target}"
        print(f"🔄 Executando: {command}")
        
        try:
            result = subprocess.run([
                'docker', 'restart', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Worker node {target} reiniciado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    def restart_control_plane(self, target: str = "local-k8s-control-plane") -> Tuple[bool, str]:
        """Simula restart do control plane (via docker restart em Kind)"""
        command = f"docker restart {target}"
        print(f"🎛️ Executando: {command}")
        
        try:
            result = subprocess.run([
                'docker', 'restart', target
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ Control plane {target} reiniciado")
            return True, command
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro: {e}")
            return False, command
    
    # ============ TESTE DE CONFIABILIDADE ============
    
    def run_reliability_test(self, component_type: str, failure_method: str, 
                           target: Optional[str] = None, iterations: int = 30, 
                           interval: int = 60) -> List[Dict]:
        """
        Executa teste de confiabilidade sistemático
        
        Args:
            component_type: Tipo do componente (pod, worker_node, control_plane)
            failure_method: Método de falha a usar
            target: Alvo específico (opcional)
            iterations: Número de falhas a simular (default: 30)
            interval: Intervalo entre testes em segundos (default: 60)
        """
        
        print(f"\n🧪 === TESTE DE CONFIABILIDADE ===")
        print(f"📊 Componente: {component_type}")
        print(f"🔨 Método de falha: {failure_method}")
        print(f"🔢 Iterações: {iterations}")
        print(f"⏱️ Intervalo: {interval}s")
        print("="*50)
        
        # Verificar se o método de falha existe
        if failure_method not in self.failure_methods:
            print(f"❌ Método de falha '{failure_method}' não encontrado")
            return []
        
        # Selecionar alvo se não especificado
        if not target:
            if component_type == 'pod':
                pods = self.get_pods()
                if not pods:
                    print("❌ Nenhum pod encontrado")
                    return []
                target = self.select_interactive(pods, f"Selecione o pod para testar")
            elif component_type == 'worker_node':
                nodes = self.get_worker_nodes()
                if not nodes:
                    print("❌ Nenhum worker node encontrado")
                    return []
                target = self.select_interactive(nodes, f"Selecione o worker node para testar")
            elif component_type == 'control_plane':
                target = "local-k8s-control-plane"  # Padrão para Kind
        
        if not target:
            print("❌ Nenhum alvo selecionado")
            return []
        
        print(f"🎯 Alvo selecionado: {target}")
        
        # Executar teste iterativo
        results = []
        
        for iteration in range(1, iterations + 1):
            print(f"\n🔄 === ITERAÇÃO {iteration}/{iterations} ===")
            
            # Verificar estado inicial
            initial_health = self.check_all_applications()
            healthy_before = sum(1 for status in initial_health.values() if status['status'] == 'healthy')
            
            if healthy_before == 0:
                print("⚠️ Nenhuma aplicação saudável antes do teste, aguardando recuperação...")
                recovered, _ = self.wait_for_recovery(timeout=120)
                if not recovered:
                    print("❌ Sistema não se recuperou, parando teste")
                    break
            
            # Executar falha
            failure_start = time.time()
            failure_timestamp = datetime.now().isoformat()
            
            failure_success, executed_command = self.failure_methods[failure_method](target)
            
            if not failure_success:
                print(f"❌ Falha não executada corretamente na iteração {iteration}")
                continue
            
            # Aguardar recuperação
            print("⏳ Aguardando recuperação...")
            recovered, recovery_time = self.wait_for_recovery(timeout=300)
            
            # Calcular MTTR
            total_time = time.time() - failure_start
            
            # Atualizar métricas do componente individual
            self.update_component_metrics(target, component_type, recovery_time, recovered)
            
            # Salvar resultado
            result = {
                'iteration': iteration,
                'component_type': component_type,
                'component_id': target,  # ID específico do componente
                'failure_method': failure_method,
                'executed_command': executed_command,
                'failure_timestamp': failure_timestamp,
                'recovery_time_seconds': recovery_time,
                'total_time_seconds': total_time,
                'recovered': recovered,
                'initial_healthy_apps': healthy_before,
                'component_stats': self.get_component_statistics(target)  # Stats atuais do componente
            }
            
            results.append(result)
            
            print(f"📋 Resultado Iteração {iteration}:")
            print(f"   ⏱️ MTTR: {recovery_time:.2f}s")
            print(f"   ✅ Recuperou: {'Sim' if recovered else 'Não'}")
            print(f"   📊 Apps saudáveis antes: {healthy_before}/3")
            
            # Aguardar intervalo antes da próxima iteração (exceto na última)
            if iteration < iterations:
                print(f"⏸️ Aguardando {interval}s antes da próxima iteração...")
                time.sleep(interval)
        
        # Calcular estatísticas finais
        self.calculate_and_print_statistics(results)
        
        # Mostrar métricas individuais por componente
        self.print_individual_component_stats()
        
        # Salvar resultados
        self.save_reliability_results(results, component_type, failure_method, target)
        
        return results
    
    def calculate_and_print_statistics(self, results: List[Dict]):
        """Calcula e exibe estatísticas do teste"""
        if not results:
            return
        
        recovery_times = [r['recovery_time_seconds'] for r in results if r['recovered']]
        success_rate = len(recovery_times) / len(results) * 100
        
        print(f"\n📊 === ESTATÍSTICAS DO TESTE ===")
        print(f"🔢 Total de iterações: {len(results)}")
        print(f"✅ Taxa de sucesso: {success_rate:.1f}% ({len(recovery_times)}/{len(results)})")
        
        if recovery_times:
            print(f"⏱️ MTTR Médio: {statistics.mean(recovery_times):.2f}s")
            print(f"📈 MTTR Máximo: {max(recovery_times):.2f}s")
            print(f"📉 MTTR Mínimo: {min(recovery_times):.2f}s")
            if len(recovery_times) > 1:
                print(f"📊 Desvio Padrão: {statistics.stdev(recovery_times):.2f}s")
                print(f"📏 Mediana: {statistics.median(recovery_times):.2f}s")
        else:
            print("❌ Nenhuma recuperação bem-sucedida para calcular MTTR")
        
        print("="*50)
    
    def save_reliability_results(self, results: List[Dict], component_type: str, 
                               failure_method: str, target: str):
        """Salva resultados em CSV e métricas individuais"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Salvar resultados das iterações
        filename = f"reliability_test_{component_type}_{failure_method}_{timestamp}.csv"
        filepath = os.path.join(os.path.dirname(__file__), filename)
        
        fieldnames = [
            'iteration', 'component_type', 'component_id', 'failure_method',
            'executed_command', 'failure_timestamp', 'recovery_time_seconds',
            'total_time_seconds', 'recovered', 'initial_healthy_apps'
        ]
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                # Remover component_stats do CSV (muito complexo)
                csv_result = {k: v for k, v in result.items() if k != 'component_stats'}
                writer.writerow(csv_result)
        
        print(f"💾 Resultados das iterações salvos em: {filepath}")
        
        # Salvar métricas individuais por componente
        if self.component_metrics:
            metrics_filename = f"component_metrics_{component_type}_{failure_method}_{timestamp}.csv"
            metrics_filepath = os.path.join(os.path.dirname(__file__), metrics_filename)
            
            metrics_fieldnames = [
                'component_id', 'component_type', 'total_failures', 'successful_recoveries',
                'availability_percent', 'mttr_mean', 'mttr_median', 'mttr_min', 'mttr_max', 'mttr_std_dev'
            ]
            
            with open(metrics_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=metrics_fieldnames)
                writer.writeheader()
                
                for component_id in self.component_metrics:
                    stats = self.get_component_statistics(component_id)
                    writer.writerow(stats)
            
            print(f"💾 Métricas individuais por componente salvos em: {metrics_filepath}")
        
        # Salvar JSON completo para análise detalhada
        json_filename = f"reliability_test_{component_type}_{failure_method}_{timestamp}.json"
        json_filepath = os.path.join(os.path.dirname(__file__), json_filename)
        
        full_data = {
            'test_info': {
                'component_type': component_type,
                'failure_method': failure_method,
                'target': target,
                'timestamp': timestamp
            },
            'iterations': results,
            'component_metrics': self.component_metrics
        }
        
        with open(json_filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(full_data, jsonfile, indent=2, ensure_ascii=False)
        
        print(f"💾 Dados completos salvos em: {json_filepath}")
    
    def run_multi_component_test(self, component_type: str, failure_method: str,
                                iterations: int = 10, interval: int = 30):
        """
        Executa teste em TODOS os componentes do tipo especificado
        para comparar MTTR individual de cada um
        """
        print(f"\n🧪 === TESTE MULTI-COMPONENTE ===")
        print(f"📊 Testando TODOS os componentes do tipo: {component_type}")
        print(f"🔨 Método de falha: {failure_method}")
        print(f"🔢 Iterações por componente: {iterations}")
        print(f"⏱️ Intervalo: {interval}s")
        print("="*60)
        
        # Obter todos os componentes do tipo
        if component_type == 'pod':
            targets = self.get_pods()
        elif component_type == 'worker_node':
            targets = self.get_worker_nodes()
        else:
            print(f"❌ Tipo de componente '{component_type}' não suporta teste multi-componente")
            return
        
        if not targets:
            print(f"❌ Nenhum {component_type} encontrado")
            return
        
        print(f"🎯 Componentes encontrados: {targets}")
        
        # Testar cada componente individualmente
        for target in targets:
            print(f"\n🔄 === TESTANDO COMPONENTE: {target} ===")
            
            # Executar teste para este componente específico
            self.run_reliability_test(
                component_type=component_type,
                failure_method=failure_method,
                target=target,
                iterations=iterations,
                interval=interval
            )
            
            # Mostrar métricas deste componente
            stats = self.get_component_statistics(target)
            if stats:
                print(f"\n📊 Resumo para {target}:")
                print(f"   ⏱️ MTTR Médio: {stats['mttr_mean']:.2f}s")
                print(f"   📈 Disponibilidade: {stats['availability_percent']:.1f}%")
        
        # Comparação final entre todos os componentes
        self.compare_component_reliability()
    
    def compare_component_reliability(self):
        """Compara métricas de confiabilidade entre diferentes componentes"""
        if len(self.component_metrics) < 2:
            print("📊 Não há componentes suficientes para comparação")
            return
        
        print(f"\n📊 === COMPARAÇÃO DE CONFIABILIDADE ===")
        
        # Criar lista ordenada por MTTR
        components_stats = []
        for component_id in self.component_metrics:
            stats = self.get_component_statistics(component_id)
            if stats['mttr_mean'] > 0:
                components_stats.append(stats)
        
        # Ordenar por MTTR (menor = melhor)
        components_stats.sort(key=lambda x: x['mttr_mean'])
        
        print("🏆 Ranking por MTTR (Menor = Mais Confiável):")
        for i, stats in enumerate(components_stats, 1):
            print(f"{i}. {stats['component_id']}")
            print(f"   ⏱️ MTTR: {stats['mttr_mean']:.2f}s")
            print(f"   📈 Disponibilidade: {stats['availability_percent']:.1f}%")
            print(f"   💥 Falhas testadas: {stats['total_failures']}")
        
        # Estatísticas comparativas
        mttr_values = [s['mttr_mean'] for s in components_stats]
        availability_values = [s['availability_percent'] for s in components_stats]
        
        print(f"\n📈 Estatísticas Comparativas:")
        print(f"⏱️ MTTR - Melhor: {min(mttr_values):.2f}s | Pior: {max(mttr_values):.2f}s | Média: {statistics.mean(mttr_values):.2f}s")
        print(f"📊 Disponibilidade - Melhor: {max(availability_values):.1f}% | Pior: {min(availability_values):.1f}% | Média: {statistics.mean(availability_values):.1f}%")
        
        # Identificar componentes problemáticos
        mean_mttr = statistics.mean(mttr_values)
        problematic = [s for s in components_stats if s['mttr_mean'] > mean_mttr * 1.5]
        
        if problematic:
            print(f"\n⚠️ Componentes com MTTR acima da média (>{mean_mttr * 1.5:.2f}s):")
            for comp in problematic:
                print(f"   🔴 {comp['component_id']}: {comp['mttr_mean']:.2f}s")
        
        print("="*60)

def main():
    parser = argparse.ArgumentParser(description='Testes de Confiabilidade Kubernetes')
    parser.add_argument('--component', 
                       choices=['pod', 'worker_node', 'control_plane'],
                       help='Tipo de componente a testar')
    parser.add_argument('--failure-method',
                       choices=['kill_processes', 'kill_init', 'delete_pod', 
                               'restart_worker_node', 'restart_control_plane'],
                       help='Método de falha a usar')
    parser.add_argument('--target', type=str,
                       help='Alvo específico (nome do pod/node)')
    parser.add_argument('--iterations', type=int, default=30,
                       help='Número de iterações (default: 30)')
    parser.add_argument('--interval', type=int, default=60,
                       help='Intervalo entre testes em segundos (default: 60)')
    parser.add_argument('--list-targets', action='store_true',
                       help='Lista alvos disponíveis')
    parser.add_argument('--multi-component', action='store_true',
                       help='Testa TODOS os componentes do tipo especificado para comparar MTTRs individuais')
    parser.add_argument('--compare-only', action='store_true',
                       help='Apenas compara componentes já testados (não executa novos testes)')
    
    args = parser.parse_args()
    
    tester = ReliabilityTester()
    
    if args.list_targets:
        print("🎯 === ALVOS DISPONÍVEIS ===")
        print("📋 Pods:")
        for pod in tester.get_pods():
            print(f"  • {pod}")
        print("🖥️ Worker Nodes:")
        for node in tester.get_worker_nodes():
            print(f"  • {node}")
        print("🎛️ Control Plane: local-k8s-control-plane")
        return
    
    if args.compare_only:
        tester.compare_component_reliability()
        return
    
    if args.multi_component:
        if not args.component or not args.failure_method:
            print("❌ Para teste multi-componente, especifique --component e --failure-method")
            return
        
        tester.run_multi_component_test(
            component_type=args.component,
            failure_method=args.failure_method,
            iterations=args.iterations,
            interval=args.interval
        )
        return
    
    if not args.component or not args.failure_method:
        # Modo interativo
        print("🎯 === MODO INTERATIVO ===")
        
        # Selecionar componente
        components = ['pod', 'worker_node', 'control_plane']
        component = tester.select_interactive(components, "Selecione o tipo de componente")
        if not component:
            return
        
        # Selecionar método de falha baseado no componente
        if component == 'pod':
            methods = ['kill_processes', 'kill_init', 'delete_pod']
        elif component == 'worker_node':
            methods = ['restart_worker_node']
        else:  # control_plane
            methods = ['restart_control_plane']
        
        failure_method = tester.select_interactive(methods, "Selecione o método de falha")
        if not failure_method:
            return
    else:
        component = args.component
        failure_method = args.failure_method
    
    # Executar teste
    tester.run_reliability_test(
        component_type=component,
        failure_method=failure_method,
        target=args.target,
        iterations=args.iterations,
        interval=args.interval
    )

if __name__ == "__main__":
    main()