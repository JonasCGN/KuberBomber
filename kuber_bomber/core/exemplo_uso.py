#!/usr/bin/env python3
"""
Classe de Exemplo - Como Usar o Kuber Bomber
=============================================

Esta classe demonstra como usar os métodos principais do framework Kuber Bomber
para testes de confiabilidade em Kubernetes.

Exemplo básico:
    from kuber_bomber.core.exemplo_uso import ExemploUso
    
    exemplo = ExemploUso()
    exemplo.executar_fluxo_completo()
"""

import sys
import os
import json
from typing import Dict, List, Optional, Tuple

# Adicionar path para imports
current_dir = os.path.dirname(os.path.abspath(__file__))
kuber_bomber_dir = os.path.dirname(current_dir)
project_dir = os.path.dirname(kuber_bomber_dir)
sys.path.insert(0, kuber_bomber_dir)
sys.path.insert(0, project_dir)

from kuber_bomber.core.reliability_tester import ReliabilityTester
from kuber_bomber.core.config_simples import ConfigSimples, ConfigPresets
from kuber_bomber.utils.infrastructure_discovery import InfrastructureDiscovery
from kuber_bomber.utils.mttr_analyzer import MTTRAnalyzer


class ExemploUso:
    """
    Classe de exemplo que demonstra o fluxo completo de testes com Kuber Bomber.
    
    Métodos principais:
    - get_config(): Obtém ou gera configuração da infraestrutura
    - run_test(get_config_all=False): Executa teste de confiabilidade
    - check_availability(): Verifica disponibilidade do sistema
    
    Uso recomendado:
    
        # 1. Criar instância
        exemplo = ExemploUso()
        
        # 2. Obter configuração (descoberta automática)
        config = exemplo.get_config()
        
        # 3. Executar testes completos com análise MTTR
        exemplo.run_test(get_config_all=True)
        
        # 4. Verificar disponibilidade
        disponibilidade = exemplo.check_availability()
    """
    
    def __init__(self, use_aws: bool = False):
        """
        Inicializa a classe de exemplo.
        
        Args:
            use_aws: Se deve usar ambiente AWS (padrão: False para Kind/local)
        """
        self.use_aws = use_aws
        self.tester = None
        self.config = None
        self.discovered_apps = []
        
        print(f"✅ Exemplo initializado - Modo: {'AWS' if use_aws else 'Local'}")
    
    def get_config(self, iterations: int = 5, run_mttr_analysis: bool = False) -> Optional[ConfigSimples]:
        """
        Obtém a configuração da infraestrutura via descoberta automática.
        
        Este método usa os comandos make que já implementam toda a lógica:
        - make generate_config: Descoberta básica com MTTF padrão
        - make generate_config_all: Descoberta + análise MTTR completa (executa testes reais)
        
        Args:
            iterations: Número de iterações para simulação (padrão: 5)
            run_mttr_analysis: Se deve executar análise MTTR completa (padrão: False)
            
        Returns:
            ConfigSimples com configuração completa ou None se falhar
        """
        print("\n📋 === ETAPA 1: OBTER CONFIGURAÇÃO ===\n")
        
        try:
            import subprocess
            import os
            
            # Preparar comando make
            if run_mttr_analysis:
                print("🧪 Executando descoberta + análise MTTR completa...")
                print("   📊 Isso irá executar testes reais para medir tempos de recuperação")
                print("   ⏰ Tempo estimado: 10-20 minutos dependendo do cluster")
                
                if self.use_aws:
                    make_target = 'generate_config_all_aws'
                else:
                    make_target = 'generate_config_all'
            else:
                print("🔍 Executando descoberta básica com MTTF padrão...")
                
                if self.use_aws:
                    make_target = 'generate_config_aws'
                else:
                    make_target = 'generate_config'
            
            print(f"🚀 Executando: make {make_target}")
            print()
            
            # Executar comando make
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            result = subprocess.run(
                ['make', make_target],
                cwd=project_root,
                text=True,
                timeout=1800  # 30 minutos de timeout
            )
            
            if result.returncode == 0:
                print("\n✅ Comando make executado com sucesso!")
                
                # Carregar configuração gerada
                config_file = os.path.join(project_root, "kuber_bomber", "configs", "config_simples_used.json")
                
                if os.path.exists(config_file):
                    print(f"📂 Carregando configuração de: {config_file}")
                    
                    with open(config_file, 'r') as f:
                        config_data = json.load(f)
                    
                    # Criar objeto ConfigSimples
                    from kuber_bomber.core.config_simples import ConfigSimples
                    config = ConfigSimples(config_data=config_data)
                    
                    # Configurar AWS se necessário
                    if self.use_aws:
                        config.configure_aws()
                    
                    self.config = config
                    
                    print("✅ Configuração carregada com sucesso!")
                    if run_mttr_analysis:
                        print("📊 Análise MTTR completa executada - tempos reais medidos")
                    
                    return config
                else:
                    print(f"❌ Arquivo de configuração não encontrado: {config_file}")
                    return None
            else:
                print(f"❌ Comando make falhou com código: {result.returncode}")
                return None
                
        except subprocess.TimeoutExpired:
            print("❌ Timeout - processo demorou mais que 30 minutos")
            return None
        except Exception as e:
            print(f"❌ Erro ao executar comando: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def run_test(self, 
                 component_type: str = 'control_plane',
                 failure_method: str = 'shutdown_control_plane',
                 iterations: int = 5,
                 interval: int = 10,
                 get_config_all: bool = False) -> List[Dict]:
        """
        Executa teste de confiabilidade para um componente específico.
        
        Este método:
        1. Obtém configuração se necessário
        2. Inicializa o testador de confiabilidade
        3. Executa iterações do teste
        4. Retorna resultados com MTTR e recuperação
        
        Args:
            component_type: Tipo de componente ('pod', 'worker_node', 'control_plane')
            failure_method: Método de falha ('shutdown_control_plane', 'kill_control_plane_processes', etc.)
            iterations: Número de iterações do teste
            interval: Intervalo entre testes em segundos
            get_config_all: Se deve executar descoberta + análise MTTR antes
            
        Returns:
            Lista com resultados de cada iteração
            
        Exemplo:
            >>> exemplo = ExemploUso()
            >>> resultados = exemplo.run_test(
            ...     component_type='control_plane',
            ...     failure_method='shutdown_control_plane',
            ...     iterations=5,
            ...     get_config_all=True  # Fazer descoberta + MTTR
            ... )
            >>> print(f"✅ Teste completado com {len(resultados)} iterações")
        """
        print("\n🧪 === ETAPA 2: EXECUTAR TESTE ===\n")
        
        try:
            # Etapa 0: Descoberta + MTTR se solicitado
            if get_config_all:
                print("📊 Executando descoberta + análise MTTR...")
                self.config = self.get_config(run_mttr_analysis=True)
                if not self.config:
                    print("❌ Falha ao obter configuração")
                    return []
            
            # Etapa 1: Obter ou usar configuração existente
            if not self.config:
                print("📋 Obtendo configuração...")
                self.config = self.get_config()
                if not self.config:
                    print("❌ Falha ao obter configuração")
                    return []
            
            # Etapa 2: Criar testador
            print("🔧 Inicializando testador de confiabilidade...")
            aws_config = None
            if self.use_aws:
                try:
                    aws_config = self.config.get_aws_config()
                except:
                    pass
            
            self.tester = ReliabilityTester(aws_config=aws_config)
            
            # Etapa 3: Executar teste
            print(f"\n🎯 Executando teste:")
            print(f"   📦 Componente: {component_type}")
            print(f"   🔨 Método: {failure_method}")
            print(f"   🔢 Iterações: {iterations}")
            print(f"   ⏱️ Intervalo: {interval}s")
            
            results = self.tester.run_reliability_test(
                component_type=component_type,
                failure_method=failure_method,
                iterations=iterations,
                interval=interval
            )
            
            print(f"\n✅ Teste completado!")
            print(f"   📊 Resultados: {len(results)} iterações executadas")
            
            if results:
                recovery_times = [r['recovery_time_seconds'] for r in results if r['recovered']]
                if recovery_times:
                    avg_mttr = sum(recovery_times) / len(recovery_times)
                    print(f"   ⏱️ MTTR médio: {avg_mttr:.2f}s")
                    print(f"   ✅ Taxa de sucesso: {len(recovery_times)}/{len(results)} ({len(recovery_times)/len(results)*100:.1f}%)")
            
            return results
            
        except Exception as e:
            print(f"❌ Erro ao executar teste: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def check_pods_health(self) -> Dict:
        """
        Demonstra os novos métodos de verificação de pods (running + curl).
        
        Este método executa:
        1. Verificação via status 'Running'
        2. Verificação via curl nos IPs dos pods
        3. Verificação combinada (ambos os métodos)
        
        Returns:
            Dicionário com resultados das verificações
        """
        print("\n🔍 === VERIFICAÇÃO DE SAÚDE DOS PODS ===\n")
        
        try:
            # Inicializar health_checker se necessário
            if not hasattr(self, 'health_checker') or not self.health_checker:
                from kuber_bomber.monitoring.health_checker import HealthChecker
                aws_config = None
                if self.use_aws and self.config:
                    aws_config = self.config.get_aws_config()
                self.health_checker = HealthChecker(aws_config=aws_config)
            
            results = {}
            
            # 1. Verificação via status Running
            print("📋 MÉTODO 1: Verificando status 'Running' dos pods...")
            print("-" * 50)
            all_running, running_details = self.health_checker.check_pods_running_status(verbose=True)
            results['running_check'] = {
                'all_running': all_running,
                'details': running_details
            }
            
            # 2. Verificação via curl
            print("\n🌐 MÉTODO 2: Verificando pods via curl...")
            print("-" * 50)
            all_responding, curl_details = self.health_checker.check_pods_via_curl(verbose=True)
            results['curl_check'] = {
                'all_responding': all_responding,
                'details': curl_details
            }
            
            # 3. Verificação combinada
            print("\n🔍 MÉTODO 3: Verificação combinada (Running + Curl)...")
            print("-" * 50)
            all_healthy, combined_details = self.health_checker.check_pods_combined(verbose=True)
            results['combined_check'] = {
                'all_healthy': all_healthy,
                'details': combined_details
            }
            
            # Resumo
            print("\n📊 === RESUMO DA VERIFICAÇÃO ===")
            print(f"✅ Todos Running: {'Sim' if all_running else 'Não'}")
            print(f"🌐 Todos respondendo curl: {'Sim' if all_responding else 'Não'}")
            print(f"🔍 Todos saudáveis (combinado): {'Sim' if all_healthy else 'Não'}")
            
            if not all_healthy:
                print("\n⚠️ PROBLEMAS DETECTADOS:")
                for pod_name, details in combined_details.items():
                    if not details['healthy']:
                        issues = []
                        if not details['running_and_ready']:
                            issues.append(f"Status: {details['status']}")
                        if not details['responding_curl']:
                            issues.append("Não responde curl")
                        print(f"   ❌ {pod_name}: {', '.join(issues)}")
            
            return results
            
        except Exception as e:
            print(f"❌ Erro ao verificar saúde dos pods: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def test_recovery_methods(self) -> Dict:
        """
        Demonstra os diferentes métodos de aguardar recuperação.
        
        Este método compara:
        1. wait_for_recovery (método original)
        2. wait_for_pods_recovery (via curl)
        3. wait_for_pods_recovery_combined (running + curl)
        
        Returns:
            Dicionário com tempos de cada método
        """
        print("\n⏱️ === TESTE DOS MÉTODOS DE RECUPERAÇÃO ===\n")
        print("Este teste verifica os diferentes métodos de aguardar recuperação.")
        print("NOTA: Execute apenas quando o sistema estiver estável!")
        print()
        
        confirm = input("Continuar com teste de recuperação? (s/N): ").lower().strip()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print("Teste cancelado.")
            return {}
        
        try:
            # Inicializar health_checker se necessário
            if not hasattr(self, 'health_checker') or not self.health_checker:
                from kuber_bomber.monitoring.health_checker import HealthChecker
                aws_config = None
                if self.use_aws and self.config:
                    aws_config = self.config.get_aws_config()
                self.health_checker = HealthChecker(aws_config=aws_config)
            
            results = {}
            
            # 1. Método original (HTTP applications)
            print("1️⃣ MÉTODO ORIGINAL: wait_for_recovery")
            print("   Verifica aplicações via HTTP endpoints")
            import time
            start_time = time.time()
            recovered, recovery_time = self.health_checker.wait_for_recovery(timeout=30)
            method1_time = time.time() - start_time
            results['original_method'] = {
                'recovered': recovered,
                'recovery_time': recovery_time,
                'total_time': method1_time
            }
            print(f"   ✅ Resultado: {'Recuperado' if recovered else 'Timeout'} em {recovery_time:.2f}s")
            
            # 2. Método via curl
            print("\n2️⃣ MÉTODO CURL: wait_for_pods_recovery")
            print("   Verifica pods via curl direto nos IPs")
            start_time = time.time()
            recovered, recovery_time = self.health_checker.wait_for_pods_recovery()
            method2_time = time.time() - start_time
            results['curl_method'] = {
                'recovered': recovered,
                'recovery_time': recovery_time,
                'total_time': method2_time
            }
            print(f"   ✅ Resultado: {'Recuperado' if recovered else 'Timeout'} em {recovery_time:.2f}s")
            
            # 3. Método combinado
            print("\n3️⃣ MÉTODO COMBINADO: wait_for_pods_recovery_combined")
            print("   Verifica pods via status Running + curl")
            start_time = time.time()
            recovered, recovery_time = self.health_checker.wait_for_pods_recovery_combined(timeout=30)
            method3_time = time.time() - start_time
            results['combined_method'] = {
                'recovered': recovered,
                'recovery_time': recovery_time,
                'total_time': method3_time
            }
            print(f"   ✅ Resultado: {'Recuperado' if recovered else 'Timeout'} em {recovery_time:.2f}s")
            
            # Comparação
            print("\n📊 === COMPARAÇÃO DOS MÉTODOS ===")
            print(f"{'Método':<20} {'Recuperado':<12} {'Tempo (s)':<12} {'Total (s)':<12}")
            print("-" * 56)
            print(f"{'Original':<20} {'Sim' if results['original_method']['recovered'] else 'Não':<12} {results['original_method']['recovery_time']:<12.2f} {results['original_method']['total_time']:<12.2f}")
            print(f"{'Curl':<20} {'Sim' if results['curl_method']['recovered'] else 'Não':<12} {results['curl_method']['recovery_time']:<12.2f} {results['curl_method']['total_time']:<12.2f}")
            print(f"{'Combinado':<20} {'Sim' if results['combined_method']['recovered'] else 'Não':<12} {results['combined_method']['recovery_time']:<12.2f} {results['combined_method']['total_time']:<12.2f}")
            
            return results
            
        except Exception as e:
            print(f"❌ Erro ao testar métodos de recuperação: {e}")
            import traceback
            traceback.print_exc()
            return {}
        """
        Executa simulação de disponibilidade usando configuração existente.
        
        Este método usa o comando make run_simulation_aws/run_simulation que executa
        a simulação completa de disponibilidade baseada no config_simples_used.json.
        
        Returns:
            Dicionário com resultados da simulação ou None se falhar
        """
        print("\n🔍 === ETAPA 3: EXECUTAR SIMULAÇÃO DE DISPONIBILIDADE ===\n")
        
        try:
            import subprocess
            import os
            
            # Verificar se há configuração
            config_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "kuber_bomber", "configs", "config_simples_used.json"
            )
            
            if not os.path.exists(config_file):
                print("❌ Configuração não encontrada!")
                print("� Execute primeiro 'Get_Config' ou 'get_config_all' para gerar a configuração")
                return None
            
            print("📊 Executando simulação de disponibilidade...")
            print("   📋 Usando configuração existente")
            print("   ⏰ Aguarde enquanto a simulação é executada...")
            
            # Escolher comando baseado no contexto
            if self.use_aws:
                make_target = 'run_simulation_aws'
                print("☁️ Modo: Simulação AWS")
            else:
                make_target = 'run_simulation'
                print("🏠 Modo: Simulação Local")
            
            print(f"🚀 Executando: make {make_target}")
            print()
            
            # Executar comando make
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            result = subprocess.run(
                ['make', make_target],
                cwd=project_root,
                text=True,
                timeout=1800  # 30 minutos de timeout
            )
            
            if result.returncode == 0:
                print("\n✅ Simulação de disponibilidade executada com sucesso!")
                print("📊 Resultados:")
                print("   📁 Verifique os arquivos CSV gerados na pasta reports/")
                print("   📈 Métricas de disponibilidade calculadas")
                
                # Retornar resultado básico
                return {
                    'simulation_completed': True,
                    'command': f'make {make_target}',
                    'reports_location': 'reports/',
                    'status': 'success'
                }
            else:
                print(f"❌ Simulação falhou com código: {result.returncode}")
                return None
                
        except subprocess.TimeoutExpired:
            print("❌ Timeout - simulação demorou mais que 30 minutos")
            return None
        except Exception as e:
            print(f"❌ Erro ao executar simulação: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def executar_fluxo_completo(self):
        """
        Executa o fluxo completo recomendado de testes.
        
        Fluxo:
        1. get_config() -> Descobrir infraestrutura com análise MTTR
        2. check_availability() -> Verificar disponibilidade inicial
        3. run_test() -> Executar teste de confiabilidade
        
        Exemplo:
            >>> exemplo = ExemploUso()
            >>> exemplo.executar_fluxo_completo()
        """
        print("\n" + "="*60)
        print("🚀 FLUXO COMPLETO DE TESTES - KUBER BOMBER")
        print("="*60)
        
        # Passo 1: Configuração
        config = self.get_config(run_mttr_analysis=True)
        if not config:
            print("❌ Falha na obtenção de configuração. Abortando.")
            return
        
        # Passo 2: Verificar disponibilidade
        availability = self.check_availability()
        if not availability:
            print("❌ Falha na verificação de disponibilidade. Abortando.")
            return
        
        if availability['percentage'] < 80:
            print(f"⚠️ ATENÇÃO: Disponibilidade baixa ({availability['percentage']:.1f}%)")
            print("   Recomenda-se verificar o cluster antes de continuar")
            confirmacao = input("Continuar com teste mesmo assim? (s/N): ").lower().strip()
            if confirmacao not in ['s', 'sim', 'y', 'yes']:
                print("Teste cancelado.")
                return
        
        # Passo 3: Executar teste
        print("\n" + "="*60)
        print("Iniciando teste de confiabilidade...")
        print("="*60)
        
        resultados = self.run_test(
            component_type='control_plane',
            failure_method='shutdown_control_plane',
            iterations=5,
            interval=10
        )
        
        # Resumo final
        print("\n" + "="*60)
        print("📊 RESUMO FINAL")
        print("="*60)
        print(f"✅ Teste concluído com sucesso!")
        print(f"   📁 Resultados: {len(resultados)} iterações")
        print(f"   🎯 Próximos passos:")
        print(f"      1. Revisar os CSV gerados em reports/")
        print(f"      2. Analisar os tempos de recuperação (MTTR)")
        print(f"      3. Ajustar configuração se necessário")
        print()


def main():
    """Função principal para executar exemplo interativo."""
    print("="*60)
    print("KUBER BOMBER - EXEMPLO DE USO")
    print("="*60)
    print()
    
    # Detectar contexto de execução
    use_aws = False
    print("🔍 CONFIGURAÇÃO DO AMBIENTE")
    print("-" * 60)
    print("Em qual contexto você está executando?")
    print()
    print("1. Cluster Local (minikube, kind, k3s, etc.)")
    print("2. AWS EKS (cluster na nuvem)")
    print()
    
    while True:
        try:
            modo = input("Escolha o contexto (1 ou 2): ").strip()
            if modo == '1':
                use_aws = False
                print("✅ Contexto configurado: Cluster Local")
                break
            elif modo == '2':
                use_aws = True
                print("✅ Contexto configurado: AWS EKS")
                print("   📋 Certifique-se de que aws_config.json está configurado")
                break
            else:
                print("❌ Opção inválida. Digite 1 ou 2.")
        except KeyboardInterrupt:
            print("\n❌ Interrompido pelo usuário")
            return
        except:
            print("❌ Erro na entrada. Digite 1 ou 2.")
    
    print()
    
    # Criar exemplo
    exemplo = ExemploUso(use_aws=use_aws)
    
    # Verificar conectividade do contexto escolhido
    print("🔍 Verificando conectividade...")
    if use_aws:
        # Verificar se aws_config.json existe
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "configs",
            "aws_config.json"
        )
        if not os.path.exists(config_path):
            print(f"❌ ERRO: aws_config.json não encontrado em {config_path}")
            print("   Configure o arquivo e tente novamente.")
            return
        print("✅ aws_config.json encontrado")
    else:
        # Verificar se kubectl está funcionando
        import subprocess
        try:
            result = subprocess.run(['kubectl', 'cluster-info'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("✅ Cluster local conectado")
            else:
                print("⚠️ ATENÇÃO: Problema de conectividade com cluster local")
                print("   Certifique-se de que o cluster está rodando (minikube start, kind create cluster, etc.)")
                continuar = input("Continuar mesmo assim? (s/N): ").lower().strip()
                if continuar not in ['s', 'sim', 'y', 'yes']:
                    print("Operação cancelada.")
                    return
        except Exception as e:
            print("⚠️ ATENÇÃO: Não foi possível verificar conectividade do cluster")
            print(f"   Erro: {e}")
            continuar = input("Continuar mesmo assim? (s/N): ").lower().strip()
            if continuar not in ['s', 'sim', 'y', 'yes']:
                print("Operação cancelada.")
                return
    
    # Menu de operações
    while True:
        print("\n" + "="*60)
        print("MENU PRINCIPAL")
        print("="*60)
        print("1. Get_Config")
        print("2. Teste de disponibilidade")
        print("3. get_config_all")
        print("4. Verificar saúde dos pods (Running + Curl)")
        print("5. Testar métodos de recuperação")
        print("6. Executar fluxo completo (recomendado)")
        print("0. Sair")
        print()
        
        try:
            opcao = input("Escolha uma opção: ").strip()
            
            if opcao == '1':
                exemplo.get_config(run_mttr_analysis=False)
            elif opcao == '2':
                exemplo.check_availability()
            elif opcao == '3':
                exemplo.get_config(run_mttr_analysis=True)
            elif opcao == '4':
                exemplo.check_pods_health()
            elif opcao == '5':
                exemplo.test_recovery_methods()
            elif opcao == '6':
                exemplo.executar_fluxo_completo()
            elif opcao == '0':
                print("\n✅ Até logo!")
                break
            else:
                print("❌ Opção inválida")
        except KeyboardInterrupt:
            print("\n❌ Interrompido pelo usuário")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")


if __name__ == "__main__":
    main()
