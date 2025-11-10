#!/usr/bin/env python3
"""
CLI do Simulador de Disponibilidade - Nova Arquitetura
=====================================================

Interface de linha de comando com descoberta automática de infraestrutura
e configuração centralizada em JSON.
"""

import argparse
import sys
import json
import os
from typing import List, Optional, Dict, Any

# Adicionar path do kuber_bomber
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kuber_bomber.simulation.availability_simulator import AvailabilitySimulator
from kuber_bomber.core.config_simples import ConfigSimples, ConfigPresets
from kuber_bomber.utils.infrastructure_discovery import InfrastructureDiscovery


def generate_config_with_discovery(use_aws: bool = False, 
                                 iterations: int = 5, 
                                 run_mttr_analysis: bool = False) -> str:
    """
    Gera configuração via descoberta automática da infraestrutura.
    
    Args:
        use_aws: Se deve usar ambiente AWS
        iterations: Número de iterações
        run_mttr_analysis: Se deve executar análise MTTR breve
        
    Returns:
        Caminho do arquivo de configuração gerado
    """
    print("🔍 === DESCOBERTA AUTOMÁTICA DA INFRAESTRUTURA ===")
    print()
    
    # Carregar configuração AWS se necessário
    aws_config = None
    if use_aws:
        # arquivo aws_config.json na pasta 'configs' um nível acima deste script
        path_aws_config = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "configs",
            "aws_config.json"
        )
        
        aws_config_data = ConfigSimples.load_aws_config(path_aws_config)
        if aws_config_data:
            aws_config = {
                'ssh_host': aws_config_data.get('ssh_host'),
                'ssh_key': aws_config_data.get('ssh_key'),
                'ssh_user': aws_config_data.get('ssh_user')
            }
            print(f"☁️ Modo AWS ativado: {aws_config['ssh_user']}@{aws_config['ssh_host']}")
        else:
            print(f"❌ Configuração AWS não encontrada em {path_aws_config}")
            return ""
    
    # Criar discovery
    discovery = InfrastructureDiscovery(use_aws=use_aws, aws_config=aws_config)
    
    # Gerar configuração básica
    print("📋 Gerando configuração com MTTF padrão...")
    config, filepath = discovery.discover_and_generate_config(iterations=iterations)
    
    # Executar análise MTTR se solicitado
    if run_mttr_analysis:
        print()
        print("🧪 === ANÁLISE MTTR COMPLETA (2 iterações por componente) ===")
        print("⚠️ Isso executará testes de confiabilidade em TODOS os componentes...")
        print("⏰ Tempo estimado: 10-20 minutos dependendo do cluster")
        print("📊 Cada componente será testado 2 vezes para obter média confiável")
        
        confirm = input("Continuar com análise MTTR completa? (s/N): ").lower().strip()
        if confirm in ['s', 'sim', 'y', 'yes']:
            print("🚀 Executando análise MTTR completa...")
            
            try:
                from kuber_bomber.utils.mttr_analyzer import MTTRAnalyzer
                
                analyzer = MTTRAnalyzer(
                    use_aws=use_aws,
                    aws_config=aws_config,
                    iterations=2  # Reduzido para 2 para ser mais rápido
                )
                
                # Executar análise e atualizar config
                config = analyzer.run_complete_analysis(config)
                
                # Salvar config atualizado
                with open(filepath, 'w') as f:
                    json.dump(config, f, indent=2)
                
                print("✅ Análise MTTR completa! Config atualizado com tempos reais.")
                
            except Exception as e:
                print(f"❌ Erro na análise MTTR: {e}")
                print("⚠️ Usando valores MTTR padrão")
        else:
            print("⏭️ Pulando análise MTTR - usando valores padrão")
    
    print()
    print(f"✅ Configuração gerada em: {filepath}")
    return filepath


def load_or_generate_config(args) -> ConfigSimples:
    """
    Carrega configuração existente ou gera nova via descoberta.
    
    Args:
        args: Argumentos do CLI
        
    Returns:
        Configuração carregada
    """
    config_file = os.getcwd() + "/kuber_bomber/configs/config_simples_used.json"
    
    print(f"📁 Arquivo de configuração padrão: {config_file}")
    # Se forçar geração de nova configuração
    if args.get_config or args.get_config_all:
        print("🏗️ Gerando nova configuração...")
        
        # Determinar parâmetros
        iterations = getattr(args, 'iterations', 5)
        use_aws = getattr(args, 'force_aws', False)
        run_mttr = args.get_config_all if hasattr(args, 'get_config_all') else False
        
        # Gerar configuração
        config_file = generate_config_with_discovery(
            use_aws=use_aws,
            iterations=iterations,
            run_mttr_analysis=run_mttr
        )
        
        if not config_file:
            print("❌ Falha ao gerar configuração")
            sys.exit(1)
    
    # Carregar configuração
    if os.path.exists(config_file):
        print(f"📂 Carregando configuração de: {config_file}")
        config = ConfigSimples.load_from_json(config_file)
        
        # Configurar AWS se necessário
        if getattr(args, 'force_aws', False):
            config.configure_aws()
        
        return config
    else:
        print("⚠️ Arquivo de configuração não encontrado, gerando padrão...")
        default_data = ConfigPresets.generate_default_config()
        config = ConfigSimples(config_data=default_data)
        
        # Salvar configuração padrão
        saved_file = config.save_config(config_file)
        print(f"💾 Configuração padrão salva em: {saved_file}")
        
        return config

def main():
    """Função principal do CLI."""
    parser = argparse.ArgumentParser(
        description="Simulador de Disponibilidade - Nova Arquitetura com Descoberta Automática",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:

# Gerar configuração descobrindo infraestrutura local
python3 -m kuber_bomber.cli.availability_cli --get-config

# Gerar configuração completa com análise MTTR (local)
python3 -m kuber_bomber.cli.availability_cli --get-config-all

# Gerar configuração para AWS
python3 -m kuber_bomber.cli.availability_cli --get-config --force-aws

# Executar simulação com configuração existente (local)
python3 -m kuber_bomber.cli.availability_cli --use-config-simples

# Executar simulação com configuração existente (AWS)
python3 -m kuber_bomber.cli.availability_cli --use-config-simples --force-aws

# Executar simulação tradicional (compatibilidade)
python3 -m kuber_bomber.cli.availability_cli --duration 1000 --iterations 5
"""
    )
    
    # ===== ARGUMENTOS DE CONFIGURAÇÃO =====
    config_group = parser.add_argument_group('Configuração')
    config_group.add_argument(
        '--get-config', 
        action='store_true',
        help='Descobrir infraestrutura e gerar configuração com MTTF padrão'
    )
    config_group.add_argument(
        '--get-config-all', 
        action='store_true',
        help='Descobrir infraestrutura e executar análise MTTR breve (5 iterações)'
    )
    config_group.add_argument(
        '--use-config-simples', 
        action='store_true',
        help='Usar configuração JSON existente (config_simples_used.json)'
    )
    
    # ===== ARGUMENTOS DE AMBIENTE =====
    env_group = parser.add_argument_group('Ambiente')
    env_group.add_argument(
        '--force-aws', 
        action='store_true',
        help='Forçar uso do ambiente AWS (via SSH)'
    )
    
    # ===== ARGUMENTOS TRADICIONAIS (compatibilidade) =====
    compat_group = parser.add_argument_group('Modo Tradicional')
    compat_group.add_argument(
        '--duration', 
        type=int, 
        default=1000,
        help='Duração da simulação em horas fictícias (padrão: 1000)'
    )
    compat_group.add_argument(
        '--iterations', 
        type=int, 
        default=5,
        help='Número de iterações (padrão: 5)'
    )
    compat_group.add_argument(
        '--delay', 
        type=int, 
        default=60,
        help='Delay real entre falhas em segundos (padrão: 60)'
    )
    
    # ===== ARGUMENTOS DE DEBUG =====
    debug_group = parser.add_argument_group('Debug e Informações')
    debug_group.add_argument(
        '--show-components', 
        action='store_true',
        help='Mostrar componentes configurados e sair'
    )
    debug_group.add_argument(
        '--print-config', 
        action='store_true',
        help='Mostrar configuração carregada e sair'
    )
    
    args = parser.parse_args()
    
    # ===== LÓGICA PRINCIPAL =====
    
    # Modo de geração de configuração apenas
    if args.get_config or args.get_config_all:
        if args.get_config:
            print("📋 Modo: Geração de configuração com MTTF padrão")
        else:
            print("📋 Modo: Geração de configuração completa com análise MTTR")
        
        config_file = generate_config_with_discovery(
            use_aws=args.force_aws,
            iterations=args.iterations,
            run_mttr_analysis=args.get_config_all
        )
        
        if config_file:
            print()
            print("🎉 Configuração gerada com sucesso!")
            print(f"📁 Arquivo: {config_file}")
            print()
            print("Para executar a simulação, use:")
            if args.force_aws:
                print("python3 -m kuber_bomber.cli.availability_cli --use-config-simples --force-aws")
            else:
                print("python3 -m kuber_bomber.cli.availability_cli --use-config-simples")
        else:
            print("❌ Falha ao gerar configuração")
            sys.exit(1)
        
        return
    
    # Modo de execução de simulação
    print("🎯 === SIMULADOR DE DISPONIBILIDADE KUBERNETES ===")
    print()
    
    # Carregar configuração
    if args.use_config_simples:
        print("📂 Modo: Usar configuração JSON existente")
        config = load_or_generate_config(args)
    else:
        print("📂 Modo: Compatibilidade (configuração tradicional)")
        # Usar configuração padrão para compatibilidade
        default_data = ConfigPresets.generate_default_config()
        default_data['duration'] = args.duration
        default_data['iterations'] = args.iterations
        config = ConfigSimples(config_data=default_data)
        
        if args.force_aws:
            config.configure_aws()
    
    # Mostrar configuração se solicitado
    if args.print_config:
        config.print_summary()
        return
    
    # Criar simulador
    try:
        # Verificar se deve usar AWS
        aws_config_for_simulator = None
        if args.force_aws:
            try:
                aws_config_for_simulator = config.get_aws_config()
                print(f"🔧 Criando simulador AWS com config: {aws_config_for_simulator.get('ssh_host', 'N/A')}")
            except Exception as e:
                print(f"⚠️ Erro ao obter AWS config: {e}")
        
        simulator = AvailabilitySimulator(aws_config=aws_config_for_simulator)
        
        # Aplicar configuração
        if hasattr(simulator, '_apply_config_simples_v2'):
            simulator._apply_config_simples_v2(config)
        else:
            # Fallback para método antigo se existir
            print("⚠️ Usando método de configuração legado")
            if hasattr(simulator, '_apply_config_simples'):
                simulator._apply_config_simples(config)
            else:
                # Fallback manual
                components = config.get_component_config()
                simulator.components = components
                simulator.availability_criteria = config.get_availability_criteria()
        
        # Mostrar componentes se solicitado
        if args.show_components:
            print("🔧 === COMPONENTES CONFIGURADOS ===")
            for component in simulator.components:
                mttf = config.get_mttf(component.name)
                print(f"  📦 {component.name} ({component.component_type})")
                print(f"    • MTTF: {mttf}h")
            print()
            return
        
        # Configurar delay entre falhas
        if not args.use_config_simples and hasattr(args, 'delay') and args.delay != 60:
            # Só aplicar delay do CLI se NÃO estiver usando config simples
            simulator.real_delay_between_failures = args.delay
        elif args.use_config_simples:
            # Se usar config simples, o delay já foi aplicado no _apply_config_simples_v2
            print(f"📄 Usando delay do config: {simulator.real_delay_between_failures}s")
        
        # Executar simulação
        print("📊 Configuração da simulação:")
        print(f"  • Duração: {config.duration} horas fictícias")
        print(f"  • Iterações: {config.iterations}")
        
        # Mostrar delay correto baseado na fonte
        if args.use_config_simples:
            print(f"  • Delay entre falhas: {simulator.real_delay_between_failures}s (do config)")
        else:
            print(f"  • Delay entre falhas: {getattr(args, 'delay', 60)}s (CLI)")
        
        print(f"  • Componentes: {len(simulator.components)}")
        print(f"  • Aplicações: {len(config.get_applications())}")
        
        if config.aws_enabled:
            print(f"  • Ambiente: AWS ({config.aws_public_ip})")
        else:
            print(f"  • Ambiente: Local")
        print()
        
        print("🚀 Iniciando simulação...")
        
        simulator.run_simulation(
            duration_hours=config.duration,
            iterations=config.iterations
        )
        
        print()
        print("🎉 Simulação concluída com sucesso!")
        
    except KeyboardInterrupt:
        print("\n⏹️ Simulação interrompida pelo usuário")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Erro durante simulação: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()