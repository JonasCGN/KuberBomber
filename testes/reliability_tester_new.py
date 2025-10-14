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
import sys
import os
import csv
import select
import termios
import tty
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import statistics
import threading
import signal
import math
import random

class AcceleratedSimulation:
    """
    Classe para simulação temporal acelerada
    Permite simular milhares de horas em minutos reais
    """
    def __init__(self, time_acceleration: float = 10000.0, base_mttf_hours: float = 1.0):
        self.time_acceleration = time_acceleration
        self.base_mttf_hours = base_mttf_hours
        self.simulation_start_time = None
        self.failure_intervals = []
        
    def start_simulation(self):
        """Inicia a simulação temporal acelerada"""
        self.simulation_start_time = time.time()
    
    def get_simulation_time_hours(self) -> float:
        """Retorna o tempo simulado em horas"""
        if self.simulation_start_time is None:
            return 0.0
        
        real_elapsed = time.time() - self.simulation_start_time
        simulated_hours = real_elapsed * self.time_acceleration / 3600.0
        return simulated_hours
    
    def calculate_next_failure_interval(self) -> float:
        """
        Calcula o próximo intervalo até falha usando distribuição exponencial
        Retorna intervalo em horas simuladas
        """
        current_mttf = self._calculate_current_mttf()
        
        # Usar distribuição exponencial para simular falhas realistas
        # lambda = 1/MTTF para distribuição exponencial
        lambda_param = 1.0 / current_mttf if current_mttf > 0 else 1.0
        
        # Gerar intervalo usando distribuição exponencial
        # Usar método simples sem numpy
        u = random.random()
        interval_hours = -math.log(1 - u) / lambda_param
        
        return interval_hours
    
    def _calculate_current_mttf(self) -> float:
        """Calcula MTTF atual baseado no histórico de falhas"""
        if len(self.failure_intervals) < 2:
            return self.base_mttf_hours
        
        # Usar média dos últimos 5 intervalos para calcular MTTF atual
        recent_intervals = self.failure_intervals[-5:]
        return sum(recent_intervals) / len(recent_intervals)
    
    def wait_for_next_failure_time(self, interval_hours: float) -> bool:
        """
        Aguarda o tempo real equivalente ao intervalo simulado
        Retorna True se deve continuar, False se deve parar
        """
        # Converter horas simuladas para segundos reais
        real_seconds = (interval_hours * 3600.0) / self.time_acceleration
        
        print(f"⏳ Aguardando {interval_hours:.2f}h simuladas ({real_seconds:.1f}s reais) até próxima falha...")
        time.sleep(real_seconds)
        return True
    
    def register_failure_interval(self, interval_hours: float):
        """Registra um intervalo de falha observado"""
        self.failure_intervals.append(interval_hours)
    
    def get_acceleration_stats(self) -> Dict:
        """Retorna estatísticas da aceleração temporal"""
        return {
            'time_acceleration': self.time_acceleration,
            'simulated_hours': self.get_simulation_time_hours(),
            'base_mttf_hours': self.base_mttf_hours,
            'current_mttf_hours': self._calculate_current_mttf(),
            'total_failures': len(self.failure_intervals)
        }

class ReliabilityTester:
    def __init__(self, time_acceleration: float = 1.0, base_mttf_hours: float = 1.0):
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
            'kill_worker_node_processes': self.kill_worker_node_processes,
            'kill_control_plane_processes': self.kill_control_plane_processes
        }
        
        # Simulação acelerada
        self.accelerated_sim = AcceleratedSimulation(time_acceleration, base_mttf_hours)
        self.simulation_mode = time_acceleration > 1.0
        
        # Controle de threading para simulação contínua
        self.simulation_running = False
        self.simulation_thread = None
        self.stop_simulation_event = threading.Event()
        
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
            print(f"📋 Pods encontrados: {[pod for pod in pods if pod]}")
            return [pod for pod in pods if pod]
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter pods: {e}")
            return []
    
    def show_pod_status(self, highlight_pod: Optional[str] = None):
        """Mostra status dos pods com kubectl get pods"""
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pods', '--context=local-k8s', '-o', 'wide'
            ], capture_output=True, text=True, check=True)
            
            print("📋 === STATUS DOS PODS ===")
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if highlight_pod and highlight_pod in line:
                    print(f"🎯 {line}")  # Destacar o pod alvo
                else:
                    print(f"   {line}")
            print()
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter status dos pods: {e}")
    
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
    
    def check_application_health(self, service: str, verbose: bool = True) -> Dict:
        """Verifica se uma aplicação está respondendo"""
        config = self.services[service]
        url = f"http://localhost:{config['port']}{config['endpoint']}"
        
        if verbose:
            print(f"🔍 Testando {service} em {url}")
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=5)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                if verbose:
                    print(f"✅ {service}: OK (HTTP {response.status_code}, {response_time:.3f}s)")
                return {
                    'status': 'healthy',
                    'response_time': response_time,
                    'status_code': response.status_code
                }
            else:
                if verbose:
                    print(f"⚠️ {service}: HTTP {response.status_code} ({response_time:.3f}s)")
                return {
                    'status': 'unhealthy',
                    'response_time': response_time,
                    'status_code': response.status_code,
                    'error': f"HTTP {response.status_code}"
                }
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"❌ {service}: {str(e)}")
            return {
                'status': 'unreachable',
                'response_time': None,
                'error': str(e)
            }
    
    def check_all_applications(self, verbose: bool = True) -> Dict:
        """Verifica saúde de todas as aplicações"""
        results = {}
        for service in self.services.keys():
            results[service] = self.check_application_health(service, verbose)
        return results
    
    def check_port_forwards(self):
        """Verifica se os port-forwards estão ativos"""
        print("🔍 === VERIFICANDO PORT-FORWARDS ===")
        
        import socket
        for service, config in self.services.items():
            port = config['port']
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                
                if result == 0:
                    print(f"✅ Porta {port} ({service}): Ativa")
                else:
                    print(f"❌ Porta {port} ({service}): Não disponível")
            except Exception as e:
                print(f"❌ Porta {port} ({service}): Erro - {e}")
        print()
    
    def initial_system_check(self):
        """Verificação inicial completa do sistema"""
        print("1️⃣ === VERIFICAÇÃO INICIAL DO SISTEMA ===")
        
        # Mostrar status dos pods
        self.show_pod_status()
        
        # Verificar port-forwards
        self.check_port_forwards()
        
        # Verificar saúde das aplicações
        print("🔍 Verificando saúde das aplicações via HTTP...")
        health_status = self.check_all_applications(verbose=True)
        healthy_count = sum(1 for status in health_status.values() if status['status'] == 'healthy')
        
        print(f"\n📊 === RESULTADO DA VERIFICAÇÃO ===")
        print(f"✅ Aplicações saudáveis: {healthy_count}/3")
        
        for service, status in health_status.items():
            emoji = "✅" if status['status'] == 'healthy' else "❌"
            print(f"   {emoji} {service}: {status['status']}")
            if 'error' in status:
                print(f"      🔍 Detalhes: {status['error']}")
        
        print("="*50)
        return healthy_count, health_status
    
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
    
    def wait_for_recovery(self, timeout: int = 300) -> Tuple[bool, float]:
        """Aguarda todas as aplicações ficarem saudáveis e retorna tempo de recuperação"""
        print(f"⏳ Aguardando recuperação (timeout: {timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            print(f"\n🔍 Verificação #{int(elapsed//2 + 1)} (tempo: {elapsed:.1f}s)")
            
            # Mostrar status dos pods a cada verificação
            print("📋 kubectl get pods:")
            try:
                result = subprocess.run([
                    'kubectl', 'get', 'pods', '--context=local-k8s'
                ], capture_output=True, text=True, check=True)
                
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    print(f"   {line}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Erro ao executar kubectl get pods: {e}")
            
            print()  # Linha em branco
            
            # Verificar saúde das aplicações (modo silencioso)
            health_status = self.check_all_applications(verbose=False)
            healthy_count = sum(1 for status in health_status.values() if status['status'] == 'healthy')
            
            print(f"🏥 Status das aplicações: {healthy_count}/3 saudáveis")
            for service, status in health_status.items():
                emoji = "✅" if status['status'] == 'healthy' else "❌"
                if status['status'] == 'healthy':
                    print(f"  {emoji} {service}: {status['status']} (tempo: {status['response_time']:.3f}s)")
                else:
                    print(f"  {emoji} {service}: {status['status']}")
                    if 'error' in status:
                        # Mostrar apenas parte do erro para não poluir
                        error_msg = str(status['error'])
                        if len(error_msg) > 80:
                            error_msg = error_msg[:80] + "..."
                        print(f"      🔍 Erro: {error_msg}")
            
            if healthy_count == len(self.services):
                recovery_time = time.time() - start_time
                print(f"\n✅ Todas as aplicações recuperadas em {recovery_time:.2f}s")
                return True, recovery_time
            
            print(f"⏸️ Aguardando 2s antes da próxima verificação...")
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
    
    def kill_worker_node_processes(self, target: str) -> Tuple[bool, str]:
        """Mata processos críticos do worker node via docker exec (Kind cluster)"""
        # Lista de processos críticos do Kubernetes no worker node
        critical_processes = [
            "kubelet",      # Processo principal do worker node
            "kube-proxy",   # Proxy de rede do Kubernetes
            "containerd",   # Runtime de containers
            "dockerd"       # Docker daemon (se estiver rodando)
        ]
        
        commands_executed = []
        
        print(f"💀 Matando processos críticos do worker node {target}...")
        
        for process in critical_processes:
            print(f"🔪 Executando: docker exec {target} pkill -9 {process}")
            
            try:
                result = subprocess.run([
                    'docker', 'exec', target, 'sh', '-c', f'pkill -9 {process}'
                ], capture_output=True, text=True)
                
                # pkill retorna 1 se não encontrou o processo, mas isso é normal
                if result.returncode == 0 or result.returncode == 1:
                    commands_executed.append(f"pkill -9 {process}")
                    print(f"✅ Comando executado para processo {process}")
                else:
                    print(f"⚠️ Erro ao executar pkill para {process}: {result.stderr}")
                    
            except Exception as e:
                print(f"⚠️ Erro ao executar comando para {process}: {e}")
                
        # Comando consolidado para logs
        full_command = f"docker exec {target} sh -c '" + "; ".join([f"pkill -9 {p}" for p in critical_processes]) + "'"
        
        if commands_executed:
            print(f"✅ Comandos executados no worker node {target}: {', '.join(commands_executed)}")
            print(f"🔄 Worker node pode precisar de alguns segundos para se recuperar...")
            return True, full_command
        else:
            print(f"❌ Nenhum comando foi executado com sucesso no worker node {target}")
            return False, full_command
    
    def kill_control_plane_processes(self, target: str = "local-k8s-control-plane") -> Tuple[bool, str]:
        """Mata processos críticos do control plane via docker exec (Kind cluster)"""
        # Lista de processos críticos do Kubernetes no control plane
        critical_processes = [
            "kube-apiserver",        # API Server
            "kube-controller-manager", # Controller Manager
            "kube-scheduler",        # Scheduler
            "etcd"                   # etcd database
        ]
        
        commands_executed = []
        
        print(f"💀 Matando processos críticos do control plane {target}...")
        
        for process in critical_processes:
            print(f"🔪 Executando: docker exec {target} pkill -9 {process}")
            
            try:
                result = subprocess.run([
                    'docker', 'exec', target, 'sh', '-c', f'pkill -9 {process}'
                ], capture_output=True, text=True)
                
                # pkill retorna 1 se não encontrou o processo, mas isso é normal
                if result.returncode == 0 or result.returncode == 1:
                    commands_executed.append(f"pkill -9 {process}")
                    print(f"✅ Comando executado para processo {process}")
                else:
                    print(f"⚠️ Erro ao executar pkill para {process}: {result.stderr}")
                    
            except Exception as e:
                print(f"⚠️ Erro ao executar comando para {process}: {e}")
                
        # Comando consolidado para logs
        full_command = f"docker exec {target} sh -c '" + "; ".join([f"pkill -9 {p}" for p in critical_processes]) + "'"
        
        if commands_executed:
            print(f"✅ Comandos executados no control plane {target}: {', '.join(commands_executed)}")
            print(f"🔄 Control plane pode precisar de alguns segundos para se recuperar...")
            return True, full_command
        else:
            print(f"❌ Nenhum comando foi executado com sucesso no control plane {target}")
            return False, full_command

    # ============ MÉTODOS DE TESTE DE CONFIABILIDADE ============
    
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
        
        # Verificação inicial completa do sistema
        healthy_count, initial_health = self.initial_system_check()
        
        if healthy_count == 0:
            print("⚠️ NENHUMA APLICAÇÃO ESTÁ SAUDÁVEL!")
            print("💡 Possíveis soluções:")
            print("   1. Verifique se os pods estão rodando: kubectl get pods")
            print("   2. Configure port-forwards:")
            print("      kubectl port-forward svc/foo-service 8080:9898 &")
            print("      kubectl port-forward svc/bar-service 8081:9898 &")
            print("      kubectl port-forward svc/test-service 8082:9898 &")
            print("   3. Ou execute o script port-forward-monitor.sh")
            print("\n🔧 Deseja continuar mesmo assim? (y/N):")
            
            try:
                choice = input().strip().lower()
                if choice not in ['y', 'yes', 's', 'sim']:
                    print("❌ Teste cancelado pelo usuário")
                    return []
            except KeyboardInterrupt:
                print("\n❌ Teste cancelado")
                return []
        
        # Executar teste iterativo
        results = []
        
        for iteration in range(1, iterations + 1):
            print(f"\n🔄 === ITERAÇÃO {iteration}/{iterations} ===")
            
            # Verificar estado inicial
            initial_health = self.check_all_applications(verbose=True)
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
        """Salva resultados em CSV organizados por data (ano/mes/dia/)"""
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        
        # Criar estrutura de pastas: ano/mes/dia/
        year = now.strftime('%Y')
        month = now.strftime('%m')
        day = now.strftime('%d')
        
        base_dir = os.path.dirname(__file__)
        date_dir = os.path.join(base_dir, year, month, day)
        
        # Criar diretórios se não existirem
        os.makedirs(date_dir, exist_ok=True)
        
        # Salvar resultados das iterações
        filename = f"reliability_test_{component_type}_{failure_method}_{timestamp}.csv"
        filepath = os.path.join(date_dir, filename)
        
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
            metrics_filepath = os.path.join(date_dir, metrics_filename)
            
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

def main():
    parser = argparse.ArgumentParser(description='Testes de Confiabilidade Kubernetes')
    parser.add_argument('--component', 
                       choices=['pod', 'worker_node', 'control_plane'],
                       help='Tipo de componente a testar')
    parser.add_argument('--failure-method',
                       choices=['kill_processes', 'kill_init', 'delete_pod', 
                               'kill_worker_node_processes', 'kill_control_plane_processes'],
                       help='Método de falha a usar')
    parser.add_argument('--target', type=str,
                       help='Alvo específico (nome do pod/node)')
    parser.add_argument('--iterations', type=int, default=30,
                       help='Número de iterações (default: 30)')
    parser.add_argument('--interval', type=int, default=60,
                       help='Intervalo entre testes em segundos (default: 60)')
    parser.add_argument('--list-targets', action='store_true',
                       help='Lista alvos disponíveis')
    
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
            methods = ['kill_worker_node_processes']
        else:  # control_plane
            methods = ['kill_control_plane_processes']
        
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