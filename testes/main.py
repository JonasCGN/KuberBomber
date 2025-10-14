#!/usr/bin/env python3
"""
Script de Teste de Resiliência para Kubernetes
Testa recuperação de falhas de processos e shutdown de pods
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
from typing import Dict, List, Optional

class KubernetesResilienceTest:
    def __init__(self):
        self.pods = []
        self.services = {
            'foo': {'port': 8080, 'endpoint': '/foo'},
            'bar': {'port': 8081, 'endpoint': '/bar'},
            'test': {'port': 8082, 'endpoint': '/test'}
        }
        self.test_results = []
    
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
            # Fallback para sistemas que não suportam termios
            return input("Pressione Enter: ")[0] if input("Pressione Enter: ") else '\n'
    
    def select_pod_interactive(self, pods: List[str], action: str = "testar") -> Optional[str]:
        """Seleção interativa de pod com setas"""
        if not pods:
            print("❌ Nenhum pod disponível")
            return None
        
        if len(pods) == 1:
            print(f"🎯 Apenas um pod disponível: {pods[0]}")
            return pods[0]
        
        current_selection = 0
        
        def draw_menu():
            """Desenha o menu limpo"""
            subprocess.run(['clear'], shell=True)  # Limpar tela completamente
            print(f"🎯 Selecione o pod para {action}:")
            print("Use ↑/↓ (ou w/s) para navegar, Enter para confirmar, q para cancelar\n")
            
            for i, pod in enumerate(pods):
                if i == current_selection:
                    print(f"➤ {pod} ⭐")
                else:
                    print(f"  {pod}")
            
            print(f"\n🎯 Pod selecionado: {pods[current_selection]}")
            print("📋 Controles: ↑/↓ ou w/s (navegar), Enter (confirmar), q (cancelar)")
        
        # Desenhar menu inicial
        draw_menu()
        
        while True:
            try:
                char = self.get_single_char()
                
                if char in ['\r', '\n']:  # Enter
                    selected_pod = pods[current_selection]
                    subprocess.run(['clear'], shell=True)
                    print(f"✅ Pod selecionado: {selected_pod}")
                    return selected_pod
                
                elif char in ['q', 'Q']:  # Quit
                    subprocess.run(['clear'], shell=True)
                    print("❌ Seleção cancelada")
                    return None
                
                elif char in ['w', 'W']:  # W para cima
                    current_selection = (current_selection - 1) % len(pods)
                    draw_menu()
                
                elif char in ['s', 'S']:  # S para baixo
                    current_selection = (current_selection + 1) % len(pods)
                    draw_menu()
                
                elif ord(char) == 27:  # ESC (início da sequência da seta)
                    try:
                        next_chars = sys.stdin.read(2)
                        if next_chars == '[A':  # Seta para cima
                            current_selection = (current_selection - 1) % len(pods)
                            draw_menu()
                        elif next_chars == '[B':  # Seta para baixo
                            current_selection = (current_selection + 1) % len(pods)
                            draw_menu()
                    except:
                        pass  # Ignorar sequências de escape inválidas
                
            except KeyboardInterrupt:
                subprocess.run(['clear'], shell=True)
                print("❌ Seleção cancelada (Ctrl+C)")
                return None
            except:
                # Em caso de erro, continuar sem atualizar
                pass
    
    def select_pod_simple(self, pods: List[str], action: str = "testar") -> Optional[str]:
        """Seleção simples de pod com números (fallback)"""
        if not pods:
            print("❌ Nenhum pod disponível")
            return None
        
        if len(pods) == 1:
            print(f"🎯 Apenas um pod disponível: {pods[0]}")
            return pods[0]
        
        print(f"\n🎯 Selecione o pod para {action}:")
        for i, pod in enumerate(pods, 1):
            print(f"{i}. {pod}")
        
        while True:
            try:
                choice = input(f"\nEscolha um número (1-{len(pods)}) ou 'q' para cancelar: ").strip()
                
                if choice.lower() == 'q':
                    print("❌ Seleção cancelada")
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(pods):
                    selected_pod = pods[choice_num - 1]
                    print(f"✅ Pod selecionado: {selected_pod}")
                    return selected_pod
                else:
                    print(f"❌ Número inválido. Escolha entre 1 e {len(pods)}")
                    
            except ValueError:
                print("❌ Entrada inválida. Digite um número ou 'q'")
            except KeyboardInterrupt:
                print("\n❌ Seleção cancelada")
                return None
        
    def show_pod_status(self, highlight_pod: str = None):
        """Mostra status dos pods com kubectl get pods"""
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pods', '-l', 'app in (foo,bar,test)',
                '-o', 'wide'
            ], capture_output=True, text=True, check=True)
            
            print("📋 Status dos Pods:")
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if highlight_pod and highlight_pod in line:
                    print(f"🎯 {line}")  # Destacar o pod alvo
                else:
                    print(f"   {line}")
            print()
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter status dos pods: {e}")
    
    def get_pods(self) -> List[str]:
        """Obtém lista de pods das aplicações"""
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pods', '-l', 'app in (foo,bar,test)', 
                '-o', 'jsonpath={.items[*].metadata.name}'
            ], capture_output=True, text=True, check=True)
            
            pods = result.stdout.strip().split()
            self.pods = [pod for pod in pods if pod]
            print(f"📋 Pods encontrados: {self.pods}")
            return self.pods
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao obter pods: {e}")
            return []
    
    def check_application_health(self, service: str) -> Dict:
        """Verifica se a aplicação está respondendo"""
        config = self.services[service]
        url = f"http://localhost:{config['port']}{config['endpoint']}"
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {
                    'status': 'healthy',
                    'response_time': response.elapsed.total_seconds(),
                    'data': data
                }
            else:
                return {
                    'status': 'unhealthy',
                    'error': f"HTTP {response.status_code}"
                }
        except requests.exceptions.RequestException as e:
            return {
                'status': 'unreachable',
                'error': str(e)
            }
    
    def check_all_applications(self) -> Dict:
        """Verifica saúde de todas as aplicações"""
        results = {}
        for service in self.services.keys():
            results[service] = self.check_application_health(service)
        return results
    
    def wait_for_recovery(self, timeout: int = 300, target_pod: str = None) -> bool:
        """Aguarda todas as aplicações ficarem saudáveis novamente"""
        print(f"⏳ Aguardando recuperação (timeout: {timeout}s)...")
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout:
            check_count += 1
            elapsed = time.time() - start_time
            
            print(f"\n🔍 Verificação #{check_count} (tempo: {elapsed:.1f}s)")
            
            # Mostrar status dos pods
            if target_pod:
                self.show_pod_status(target_pod)
            else:
                self.show_pod_status()
            
            # Verificar saúde das aplicações
            health = self.check_all_applications()
            healthy_count = sum(1 for status in health.values() if status['status'] == 'healthy')
            
            print(f"🏥 Status das aplicações: {healthy_count}/3 saudáveis")
            for app, status in health.items():
                icon = "✅" if status['status'] == 'healthy' else "❌"
                if status['status'] == 'healthy':
                    rt = f" (tempo: {status.get('response_time', 0):.3f}s)"
                else:
                    rt = f" (erro: {status.get('error', 'N/A')})"
                print(f"  {icon} {app}: {status['status']}{rt}")
            
            if healthy_count == 3:
                recovery_time = time.time() - start_time
                print(f"\n✅ Todas as aplicações recuperadas em {recovery_time:.2f}s")
                return True
            
            print(f"⏸️ Aguardando 5s antes da próxima verificação...")
            time.sleep(5)
        
        print(f"\n❌ Timeout: Aplicações não se recuperaram em {timeout}s")
        return False
    
    def kill_all_processes(self, pod_name: str) -> bool:
        """Mata todos os processos em um pod"""
        print(f"💀 Matando todos os processos no pod: {pod_name}")
        
        try:
            # Usar kill -9 -1 para matar todos os processos
            result = subprocess.run([
                'kubectl', 'exec', pod_name, '--', 
                'sh', '-c', 'kill -9 -1'
            ], capture_output=True, text=True)
            
            print(f"🔪 Comando executado no pod {pod_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao matar processos no pod {pod_name}: {e}")
            return False
    
    def shutdown_pod(self, pod_name: str) -> bool:
        """Faz shutdown do pod usando sudo shutdown now"""
        print(f"🔌 Fazendo shutdown do pod: {pod_name}")
        
        try:
            # Usar sudo shutdown now para fazer shutdown real
            result = subprocess.run([
                'kubectl', 'exec', pod_name, '--', 
                'sh', '-c', 'sudo shutdown now'
            ], capture_output=True, text=True)
            
            print(f"� Comando shutdown executado no pod {pod_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erro ao fazer shutdown do pod {pod_name}: {e}")
            return False
    
    def run_kill_process_test(self, target_pod: Optional[str] = None):
        """Executa teste de matar processos"""
        print("🧪 === TESTE: KILL ALL PROCESSES ===")
        
        # Verificar estado inicial
        print("1️⃣ Verificando estado inicial...")
        self.show_pod_status()
        initial_health = self.check_all_applications()
        healthy_before = sum(1 for status in initial_health.values() if status['status'] == 'healthy')
        print(f"📊 Aplicações saudáveis antes do teste: {healthy_before}/3")
        
        if healthy_before == 0:
            print("❌ Nenhuma aplicação está saudável. Execute o deploy primeiro.")
            return
        
        # Escolher pod alvo
        if target_pod:
            pod_to_kill = target_pod
        else:
            pods = self.get_pods()
            if not pods:
                print("❌ Nenhum pod encontrado")
                return
            
            # Seleção interativa do pod
            print("\n🎯 Selecione o pod para matar processos:")
            try:
                pod_to_kill = self.select_pod_interactive(pods, "matar processos")
            except:
                print("⚠️ Modo interativo não disponível, usando seleção simples...")
                pod_to_kill = self.select_pod_simple(pods, "matar processos")
            
            if not pod_to_kill:
                print("❌ Nenhum pod selecionado. Teste cancelado.")
                return
        
        print(f"🎯 Pod selecionado para teste: {pod_to_kill}")
        
        # Registrar tempo de início
        start_time = time.time()
        start_timestamp = datetime.now().isoformat()
        
        # Matar processos
        print(f"\n2️⃣ Matando processos no pod: {pod_to_kill}")
        comando_executado = f"kubectl exec {pod_to_kill} -- sh -c 'kill -9 -1'"
        if not self.kill_all_processes(pod_to_kill):
            return
        
        # Mostrar status imediatamente após o kill
        print(f"\n📋 Status imediatamente após kill:")
        self.show_pod_status(pod_to_kill)
        
        # Aguardar um pouco para o pod reiniciar
        print("3️⃣ Aguardando reinício do pod...")
        time.sleep(10)
        
        # Aguardar recuperação
        print("4️⃣ Aguardando recuperação das aplicações...")
        recovered = self.wait_for_recovery(target_pod=pod_to_kill)
        
        # Calcular métricas
        total_time = time.time() - start_time
        
        # Resultado do teste
        result = {
            'test_type': 'kill_processes',
            'comando_executado': comando_executado,
            'target_pod': pod_to_kill,
            'start_time': start_timestamp,
            'total_time': total_time,
            'tempo_recuperacao': total_time,
            'recovered': recovered,
            'initial_healthy': healthy_before,
            'final_health': self.check_all_applications()
        }
        
        self.test_results.append(result)
        self.print_test_summary(result)
    
    def run_shutdown_test(self, target_pod: Optional[str] = None):
        """Executa teste de shutdown"""
        print("🧪 === TESTE: SHUTDOWN POD ===")
        
        # Verificar estado inicial
        print("1️⃣ Verificando estado inicial...")
        self.show_pod_status()
        initial_health = self.check_all_applications()
        healthy_before = sum(1 for status in initial_health.values() if status['status'] == 'healthy')
        print(f"📊 Aplicações saudáveis antes do teste: {healthy_before}/3")
        
        if healthy_before == 0:
            print("❌ Nenhuma aplicação está saudável. Execute o deploy primeiro.")
            return
        
        # Escolher pod alvo
        if target_pod:
            pod_to_shutdown = target_pod
        else:
            pods = self.get_pods()
            if not pods:
                print("❌ Nenhum pod encontrado")
                return
            
            # Seleção interativa do pod
            print("\n🎯 Selecione o pod para shutdown:")
            try:
                pod_to_shutdown = self.select_pod_interactive(pods, "fazer shutdown")
            except:
                print("⚠️ Modo interativo não disponível, usando seleção simples...")
                pod_to_shutdown = self.select_pod_simple(pods, "fazer shutdown")
            
            if not pod_to_shutdown:
                print("❌ Nenhum pod selecionado. Teste cancelado.")
                return
        
        print(f"🎯 Pod selecionado para shutdown: {pod_to_shutdown}")
        
        # Registrar tempo de início
        start_time = time.time()
        start_timestamp = datetime.now().isoformat()
        
        # Fazer shutdown
        print(f"\n2️⃣ Fazendo shutdown do pod: {pod_to_shutdown}")
        comando_executado = f"kubectl exec {pod_to_shutdown} -- sh -c 'sudo shutdown now'"
        if not self.shutdown_pod(pod_to_shutdown):
            return
        
        # Mostrar status imediatamente após o shutdown
        print(f"\n📋 Status imediatamente após shutdown:")
        self.show_pod_status()
        
        # Aguardar um pouco para o Kubernetes recriar o pod
        print("3️⃣ Aguardando Kubernetes recriar o pod...")
        time.sleep(15)
        
        # Aguardar recuperação
        print("4️⃣ Aguardando recuperação das aplicações...")
        recovered = self.wait_for_recovery(target_pod=pod_to_shutdown)
        
        # Calcular métricas
        total_time = time.time() - start_time
        
        # Resultado do teste
        result = {
            'test_type': 'shutdown',
            'comando_executado': comando_executado,
            'target_pod': pod_to_shutdown,
            'start_time': start_timestamp,
            'total_time': total_time,
            'tempo_recuperacao': total_time,
            'recovered': recovered,
            'initial_healthy': healthy_before,
            'final_health': self.check_all_applications()
        }
        
        self.test_results.append(result)
        self.print_test_summary(result)
    
    def print_test_summary(self, result: Dict):
        """Imprime resumo do teste"""
        print("\n" + "="*50)
        print("📋 RESUMO DO TESTE")
        print("="*50)
        print(f"🔬 Tipo: {result['test_type']}")
        print(f"🎯 Pod alvo: {result['target_pod']}")
        print(f"⏱️ Tempo total: {result['total_time']:.2f}s")
        print(f"✅ Recuperou: {'Sim' if result['recovered'] else 'Não'}")
        print(f"📊 Estado inicial: {result['initial_healthy']}/3 saudáveis")
        
        final = result['final_health']
        final_healthy = sum(1 for status in final.values() if status['status'] == 'healthy')
        print(f"📊 Estado final: {final_healthy}/3 saudáveis")
        
        print("\n🔍 Detalhes finais por aplicação:")
        for app, status in final.items():
            icon = "✅" if status['status'] == 'healthy' else "❌"
            print(f"  {icon} {app}: {status['status']}")
        
        print("="*50 + "\n")
    
    def save_results(self):
        """Salva resultados em arquivo JSON e CSV"""
        if not self.test_results:
            return
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Salvar JSON (mantendo compatibilidade)
        json_filename = f"test_results_{timestamp}.json"
        json_filepath = os.path.join(os.path.dirname(__file__), json_filename)
        
        with open(json_filepath, 'w') as f:
            json.dump(self.test_results, f, indent=2)
        
        print(f"💾 Resultados JSON salvos em: {json_filepath}")
        
        # Salvar CSV com as colunas solicitadas
        csv_filename = f"test_results_{timestamp}.csv"
        csv_filepath = os.path.join(os.path.dirname(__file__), csv_filename)
        
        with open(csv_filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Escrever cabeçalho
            writer.writerow(['comando_executado', 'name_pod', 'tempo_inicio', 'tempo_recuperacao'])
            
            # Escrever dados
            for result in self.test_results:
                writer.writerow([
                    result.get('comando_executado', ''),
                    result.get('target_pod', ''),
                    result.get('start_time', ''),
                    f"{result.get('tempo_recuperacao', 0):.2f}"
                ])
        
        print(f"� Resultados CSV salvos em: {csv_filepath}")
        
        # Mostrar resumo dos dados salvos
        print("\n📋 Dados salvos no CSV:")
        print("comando_executado,name_pod,tempo_inicio,tempo_recuperacao")
        for result in self.test_results:
            print(f"{result.get('comando_executado', '')},{result.get('target_pod', '')},{result.get('start_time', '')},{result.get('tempo_recuperacao', 0):.2f}")
        print()

def main():
    parser = argparse.ArgumentParser(description='Testes de Resiliência Kubernetes')
    parser.add_argument('--kill_process', action='store_true', 
                       help='Executa teste de matar todos os processos')
    parser.add_argument('--shutdown', action='store_true', 
                       help='Executa teste de shutdown do pod')
    parser.add_argument('--pod', type=str, 
                       help='Nome específico do pod para testar (opcional)')
    parser.add_argument('--check', action='store_true', 
                       help='Apenas verifica status das aplicações')
    
    args = parser.parse_args()
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    tester = KubernetesResilienceTest()
    
    if args.check:
        print("🔍 Verificando status das aplicações...")
        health = tester.check_all_applications()
        for app, status in health.items():
            icon = "✅" if status['status'] == 'healthy' else "❌"
            print(f"{icon} {app}: {status['status']}")
        return
    
    if args.kill_process:
        tester.run_kill_process_test(args.pod)
    
    if args.shutdown:
        tester.run_shutdown_test(args.pod)
    
    tester.save_results()

if __name__ == "__main__":
    main()