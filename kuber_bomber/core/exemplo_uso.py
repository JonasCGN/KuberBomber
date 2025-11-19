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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        
        Este método:
        1. Descobre automaticamente todos os componentes do cluster
        2. Define MTTF padrão se não tiver análise MTTR
        3. Opcionalmente executa análise MTTR completa (2 iterações por componente)
        
        Args:
            iterations: Número de iterações para simulação (padrão: 5)
            run_mttr_analysis: Se deve executar análise MTTR completa (padrão: False)
            
        Returns:
            ConfigSimples com configuração completa ou None se falhar
            
        Exemplo:
            >>> exemplo = ExemploUso()
            >>> config = exemplo.get_config(iterations=10, run_mttr_analysis=True)
            >>> print(f"✅ Configuração carregada com {len(config.components)} componentes")
        """
        print("\n📋 === ETAPA 1: OBTER CONFIGURAÇÃO ===\n")
        
        try:
            # Carregar config AWS se necessário
            aws_config = None
            if self.use_aws:
                # arquivo aws_config.json deve estar em kuber_bomber/configs/
                path_aws_config = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "configs",
                    "aws_config.json"
                )
                
                if os.path.exists(path_aws_config):
                    with open(path_aws_config, 'r') as f:
                        aws_config_data = json.load(f)
                    aws_config = {
                        'ssh_host': aws_config_data.get('ssh_host'),
                        'ssh_key': aws_config_data.get('ssh_key'),
                        'ssh_user': aws_config_data.get('ssh_user')
                    }
                    print(f"☁️ AWS config carregado: {aws_config['ssh_user']}@{aws_config['ssh_host']}")
                else:
                    print(f"❌ aws_config.json não encontrado em {path_aws_config}")
                    print("   Configure o arquivo aws_config.json e tente novamente")
                    return None
            
            # Descobrir infraestrutura
            print("🔍 Descobrindo infraestrutura...")
            discovery = InfrastructureDiscovery(use_aws=self.use_aws, aws_config=aws_config)
            config, config_filepath = discovery.discover_and_generate_config(iterations=iterations)
            
            # Executar análise MTTR se solicitado
            if run_mttr_analysis:
                print("\n🧪 Executando análise MTTR completa...")
                print("   ⏰ Esto pode levar 10-20 minutos...")
                
                try:
                    analyzer = MTTRAnalyzer(
                        use_aws=self.use_aws,
                        aws_config=aws_config,
                        iterations=2  # 2 iterações por componente
                    )
                    config = analyzer.run_complete_analysis(config)
                    
                    # Salvar config atualizado
                    with open(config_filepath, 'w') as f:
                        if hasattr(config, 'to_dict') and callable(config.to_dict):
                            json.dump(config.to_dict(), f, indent=2)
                        elif isinstance(config, dict):
                            json.dump(config, f, indent=2)
                        else:
                            json.dump(vars(config) if hasattr(config, '__dict__') else str(config), f, indent=2)
                    
                    print("✅ Análise MTTR completa!")
                except Exception as e:
                    print(f"❌ Erro na análise MTTR: {e}")
                    print("   Continuando com MTTF padrão...")
            
            self.config = config
            print(f"\n✅ Configuração obtida com sucesso!")
            print(f"   📁 Arquivo: {config_filepath}")
            
            return config
            
        except Exception as e:
            print(f"❌ Erro ao obter configuração: {e}")
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
    
    def check_availability(self) -> Optional[Dict]:
        """
        Verifica a disponibilidade atual do sistema.
        
        Este método:
        1. Verifica status dos pods
        2. Testa conectividade das aplicações
        3. Retorna métricas de disponibilidade
        
        Returns:
            Dicionário com métricas de disponibilidade ou None se falhar
            
        Exemplo:
            >>> exemplo = ExemploUso()
            >>> disponibilidade = exemplo.check_availability()
            >>> if disponibilidade:
            ...     print(f"✅ Disponibilidade: {disponibilidade['percentage']:.1f}%")
        """
        print("\n🔍 === ETAPA 3: VERIFICAR DISPONIBILIDADE ===\n")
        
        try:
            if not self.tester:
                print("⚠️ Testador não inicializado, criando novo...")
                aws_config = None
                if self.use_aws and self.config:
                    try:
                        aws_config = self.config.get_aws_config()
                    except:
                        pass
                self.tester = ReliabilityTester(aws_config=aws_config)
            
            # Executar verificação inicial do sistema
            print("📋 Verificando status do sistema...")
            healthy_count, health_status, discovered_apps = self.tester.initial_system_check()
            
            self.discovered_apps = discovered_apps
            
            # Calcular disponibilidade
            total_services = len(health_status) if health_status else 0
            availability = (healthy_count / total_services * 100) if total_services > 0 else 0
            
            result = {
                'percentage': availability,
                'healthy_count': healthy_count,
                'total_services': total_services,
                'services': health_status or {}
            }
            
            print(f"\n✅ Verificação concluída!")
            print(f"   🟢 Serviços saudáveis: {healthy_count}/{total_services}")
            print(f"   📊 Disponibilidade: {availability:.1f}%")
            
            return result
            
        except Exception as e:
            print(f"❌ Erro ao verificar disponibilidade: {e}")
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
    
    # Menu interativo
    use_aws = False
    try:
        modo = input("Modo de execução (1=Local/Kind, 2=AWS): ").strip()
        use_aws = modo == '2'
    except:
        pass
    
    # Criar exemplo
    exemplo = ExemploUso(use_aws=use_aws)
    
    # Menu de operações
    while True:
        print("\n" + "="*60)
        print("MENU PRINCIPAL")
        print("="*60)
        print("1. Obter configuração (descoberta automática)")
        print("2. Verificar disponibilidade")
        print("3. Executar teste de confiabilidade")
        print("4. Executar fluxo completo (recomendado)")
        print("0. Sair")
        print()
        
        try:
            opcao = input("Escolha uma opção: ").strip()
            
            if opcao == '1':
                exemplo.get_config(run_mttr_analysis=True)
            elif opcao == '2':
                exemplo.check_availability()
            elif opcao == '3':
                exemplo.run_test(
                    component_type='control_plane',
                    failure_method='shutdown_control_plane',
                    iterations=5
                )
            elif opcao == '4':
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
