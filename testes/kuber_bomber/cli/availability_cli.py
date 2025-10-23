#!/usr/bin/env python3
"""
CLI do Simulador de Disponibilidade
===================================

Interface de linha de comando para executar simulações de disponibilidade
da infraestrutura Kubernetes.
"""

import argparse
import sys
import os

# Adicionar path do kuber_bomber
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kuber_bomber.simulation.availability_simulator import AvailabilitySimulator


def get_availability_criteria():
    """
    Pergunta ao usuário sobre os critérios de disponibilidade para cada tipo de pod.
    
    Returns:
        Dict com critérios de disponibilidade por aplicação
    """
    print("🎯 === CONFIGURAÇÃO DE CRITÉRIOS DE DISPONIBILIDADE ===")
    print()
    print("Para cada aplicação, defina quantos pods precisam estar funcionando")
    print("para considerar o sistema DISPONÍVEL:")
    print()
    
    criteria = {}
    pod_apps = ["foo-app", "bar-app", "test-app"]
    
    for app in pod_apps:
        while True:
            try:
                print(f"📦 {app}:")
                min_pods = int(input(f"   Quantos pods de {app} precisam estar Ready? (mín: 1): "))
                if min_pods >= 1:
                    criteria[app] = min_pods
                    print(f"   ✅ {app}: mínimo {min_pods} pod(s)")
                    break
                else:
                    print("   ❌ Precisa ser pelo menos 1 pod")
            except ValueError:
                print("   ❌ Digite um número válido")
            except KeyboardInterrupt:
                print("\n🚫 Operação cancelada")
                sys.exit(0)
    
    print()
    print("📋 Critérios configurados:")
    total_min_pods = sum(criteria.values())
    for app, min_pods in criteria.items():
        print(f"  • {app}: mínimo {min_pods} pod(s)")
    print(f"  • Total mínimo: {total_min_pods} pods")
    print()
    
    confirm = input("✅ Confirmar configuração? (s/N): ").lower().strip()
    if confirm not in ['s', 'sim', 'y', 'yes']:
        print("🔄 Reconfigurando...")
        return get_availability_criteria()
    
    return criteria


def main():
    """Função principal do CLI."""
    parser = argparse.ArgumentParser(
        description="Simulador de Disponibilidade de Infraestrutura Kubernetes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python availability_cli.py --duration 24 --iterations 5
  python availability_cli.py --duration 48 --iterations 10 --delay 30
  
IMPORTANTE - Duração:
  A duração é em HORAS FICTÍCIAS (simuladas), não tempo real.
  Exemplo: --duration 168 simula 1 semana de operação em minutos reais.
  
O simulador irá:
1. Perguntar quantos pods de cada app precisam estar disponíveis
2. Usar distribuição exponencial baseada nos MTTFs configurados  
3. Aplicar falhas reais com kubectl (timing: 1min real entre falhas)
4. Medir tempo real de recuperação
5. Gerar relatórios CSV detalhados
        """
    )
    
    parser.add_argument(
        '--duration',
        type=float,
        default=24.0,
        help='Duração da simulação em HORAS FICTÍCIAS (padrão: 24). '
             'Exemplo: 168 = simula 1 semana de operação'
    )
    
    parser.add_argument(
        '--iterations',
        type=int,
        default=1,
        help='Número de iterações da simulação (padrão: 1)'
    )
    
    parser.add_argument(
        '--delay',
        type=int,
        default=60,
        help='Delay em segundos REAIS entre falhas (padrão: 60s)'
    )
    
    parser.add_argument(
        '--show-components',
        action='store_true',
        help='Mostrar componentes configurados e seus MTTFs'
    )
    
    args = parser.parse_args()
    
    # Criar simulador
    simulator = AvailabilitySimulator()
    
    # Configurar delay se especificado
    if args.delay != 60:
        simulator.real_delay_between_failures = args.delay
    
    # Mostrar componentes se solicitado
    if args.show_components:
        print("🔧 === COMPONENTES CONFIGURADOS ===")
        for component in simulator.components:
            print(f"  📦 {component.name} ({component.component_type})")
            print(f"    • MTTF: {component.mttf_hours}h")
        print()
        return
    
    # Validar argumentos
    if args.duration <= 0:
        print("❌ Duração deve ser maior que 0")
        return
    
    if args.iterations <= 0:
        print("❌ Iterações deve ser maior que 0")
        return
    
    # Executar simulação
    try:
        print("🎯 === SIMULADOR DE DISPONIBILIDADE KUBERNETES ===")
        print()
        print("📋 Componentes configurados:")
        
        for component in simulator.components:
            print(f"  • {component.name} ({component.component_type}): MTTF={component.mttf_hours}h")
        
        print()
        print(f"⏰ Configuração da simulação:")
        print(f"  • Duração: {args.duration} horas FICTÍCIAS")
        print(f"  • Iterações: {args.iterations}")
        print(f"  • Delay entre falhas: {args.delay} segundos REAIS")
        print()
        
        # Obter critérios de disponibilidade do usuário
        availability_criteria = get_availability_criteria()
        
        # Atualizar o simulador com os critérios
        simulator.availability_criteria = availability_criteria
        
        print("🚀 Iniciando simulação...")
        print("💡 Pressione Ctrl+C para interromper")
        print()
        
        simulator.run_simulation(
            duration_hours=args.duration,
            iterations=args.iterations
        )
        
        print("🎉 Simulação concluída com sucesso!")
        
    except KeyboardInterrupt:
        print("\n⏹️ Simulação interrompida pelo usuário")
    except Exception as e:
        print(f"❌ Erro durante simulação: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()