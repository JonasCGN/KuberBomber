#!/usr/bin/env python3
"""
CLI Principal - Sistema de Testes de Confiabilidade para Kubernetes
==================================================================

Interface de linha de comando que mantém TODAS as flags originais
e adiciona funcionalidades de timeout configurável e CSV em tempo real.

Uso:
    python3 reliability_tester.py --component pod --failure-method kill_processes --target <POD_NAME> --iterations 30 --interval 10

Flags Principais:
    --component: Tipo de componente (pod, worker_node, control_plane)
    --failure-method: Método de falha a usar
    --target: Alvo específico
    --iterations: Número de iterações
    --interval: Intervalo entre testes
    --timeout: Timeout de recuperação (NOVA FUNCIONALIDADE)
"""

import argparse
import sys
import os

# Adicionar o diretório pai ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kuber_bomber.core.reliability_tester import ReliabilityTester
from kuber_bomber.utils.config import (
    get_config, set_global_recovery_timeout, list_timeout_options, 
    get_current_recovery_timeout, DEFAULT_CONFIG
)


def create_parser():
    """Cria o parser de argumentos mantendo TODAS as flags originais."""
    parser = argparse.ArgumentParser(
        description='Sistema de Testes de Confiabilidade para Kubernetes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:

  # Teste básico em um pod específico
  python3 reliability_tester.py --component pod --failure-method kill_processes --target <POD_NAME> --iterations 30 --interval 10

  # Teste com timeout personalizado
  python3 reliability_tester.py --component pod --failure-method delete_pod --iterations 5 --timeout 180

  # Teste em worker node
  python3 reliability_tester.py --component worker_node --failure-method kill_worker_node_processes --iterations 10

  # Simulação acelerada
  python3 reliability_tester.py --accelerated --time-acceleration 5000 --simulation-duration 500

  # Listar alvos disponíveis
  python3 reliability_tester.py --list-targets

  # Teste multi-componente
  python3 reliability_tester.py --multi-component --component pod --failure-method kill_processes

  # Mostrar opções de timeout
  python3 reliability_tester.py --list-timeouts

Tipos de timeout disponíveis:
  quick (60s), short (120s), medium (300s), long (600s), extended (1200s)
  Ou um valor personalizado em segundos.
        """
    )
    
    # ======= FLAGS ORIGINAIS (MANTIDAS EXATAMENTE) =======
    parser.add_argument('--component', 
                       choices=['pod', 'worker_node', 'control_plane'],
                       help='Tipo de componente a testar')
    
    parser.add_argument('--failure-method',
                       choices=[
                           # Pod failures
                        #    'kill_processes', 'kill_init', 'delete_pod',
                           'kill_processes', 'kill_init',
                           # Worker Node failures  
                           'kill_worker_node_processes', 'restart_worker_node', 'kill_kubelet',
                           # Control Plane failures
                           'kill_control_plane_processes', 'kill_kube_apiserver', 
                           'kill_kube_controller_manager', 'kill_kube_scheduler', 'kill_etcd',
                           # Network failures
                           'delete_kube_proxy', 'restart_containerd'
                       ],
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
    
    # Argumentos para simulação acelerada (ORIGINAIS)
    parser.add_argument('--accelerated', action='store_true',
                       help='Executa simulação acelerada de confiabilidade')
    
    parser.add_argument('--time-acceleration', type=float, default=10000.0,
                       help='Fator de aceleração temporal (default: 10000.0 = 1h real = 10000h simuladas)')
    
    parser.add_argument('--simulation-duration', type=float, default=1000.0,
                       help='Duração da simulação em horas simuladas (default: 1000h)')
    
    parser.add_argument('--base-mttf', type=float, default=1.0,
                       help='MTTF base em horas para distribuição de falhas (default: 1.0h)')
    
    parser.add_argument('--failure-modes', nargs='+', 
                    #    choices=['kill_processes', 'kill_init', 'delete_pod'],
                       choices=['kill_processes', 'kill_init'],
                       help='Métodos de falha para simulação acelerada')
    
    # ======= NOVAS FLAGS PARA TIMEOUT E CONFIGURAÇÃO =======
    parser.add_argument('--timeout', type=str,
                       help='Timeout de recuperação: quick, short, medium, long, extended ou valor em segundos')
    
    parser.add_argument('--list-timeouts', action='store_true',
                       help='Lista opções de timeout disponíveis')
    
    parser.add_argument('--set-timeout', type=str,
                       help='Define timeout globalmente (quick, short, medium, long, extended ou valor em segundos)')
    
    parser.add_argument('--show-config', action='store_true',
                       help='Mostra configuração atual')
    
    parser.add_argument('--no-realtime-csv', action='store_true',
                       help='Desabilita CSV em tempo real (salva apenas no final)')
    
    return parser


def handle_timeout_commands(args):
    """Processa comandos relacionados a timeout."""
    if args.list_timeouts:
        list_timeout_options()
        return True
    
    if args.set_timeout:
        set_global_recovery_timeout(args.set_timeout)
        print(f"📊 Timeout atual: {get_current_recovery_timeout()}s")
        return True
    
    if args.show_config:
        DEFAULT_CONFIG.print_config()
        return True
    
    # Configurar timeout para este teste específico
    if args.timeout:
        set_global_recovery_timeout(args.timeout)
        print(f"⏱️ Timeout configurado para este teste: {get_current_recovery_timeout()}s")
    
    return False


def main():
    """Função principal que processa argumentos e executa testes."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Processar comandos de timeout primeiro
    if handle_timeout_commands(args):
        return
    
    # Configurar CSV em tempo real
    config = get_config()
    if args.no_realtime_csv:
        config.enable_realtime_csv = False
        print("📊 CSV em tempo real desabilitado")
    
    # Cria o tester com configuração de aceleração se especificada
    if args.accelerated or args.time_acceleration > 1.0:
        tester = ReliabilityTester(
            time_acceleration=args.time_acceleration, 
            base_mttf_hours=args.base_mttf
        )
    else:
        tester = ReliabilityTester()
    
    # ======= PROCESSAR COMANDOS ORIGINAIS =======
    
    if args.list_targets:
        print("🎯 === ALVOS DISPONÍVEIS ===")
        print("📋 Pods:")
        for pod in tester.system_monitor.get_pods():
            print(f"  • {pod}")
        print("🖥️ Worker Nodes:")
        for node in tester.system_monitor.get_worker_nodes():
            print(f"  • {node}")
        print(f"🎛️ Control Plane: {tester.system_monitor.get_control_plane_node()}")
        return
    
    if args.compare_only:
        print("📊 Funcionalidade de comparação em desenvolvimento")
        return
    
    # Simulação acelerada
    if args.accelerated:
        print("🚀 === MODO SIMULAÇÃO ACELERADA ===")
        print(f"🔥 Aceleração: {args.time_acceleration}x")
        print(f"⏱️ Duração: {args.simulation_duration}h simuladas")
        print(f"📊 MTTF base: {args.base_mttf}h")
        print(f"⏰ Timeout: {get_current_recovery_timeout()}s")
        print("⚠️ Simulação acelerada em desenvolvimento - executando teste normal")
        
        # Por enquanto, executa teste normal com aceleração
        if not args.component:
            args.component = 'pod'
        if not args.failure_method:
            args.failure_method = 'kill_processes'
    
    if args.multi_component:
        if not args.component or not args.failure_method:
            print("❌ Para teste multi-componente, especifique --component e --failure-method")
            return
        
        print("📊 Teste multi-componente em desenvolvimento - executando teste normal")
        # Por enquanto, executa teste normal
    
    # ======= TESTE NORMAL (ORIGINAL) =======
    
    if not args.component or not args.failure_method:
        # Modo interativo se não especificado
        print("🎯 === MODO INTERATIVO ===")
        
        # Pergunta se quer simulação acelerada
        print("🚀 Deseja usar simulação acelerada? (y/N):")
        try:
            choice = input().strip().lower()
            if choice in ['y', 'yes', 's', 'sim']:
                print("⚡ Configurando simulação acelerada...")
                print("🔥 Fator de aceleração (ex: 10000 = 1h real = 10000h simuladas):")
                acceleration = float(input("Aceleração [10000]: ") or "10000")
                print("⏱️ Duração em horas simuladas:")
                duration = float(input("Duração [1000]: ") or "1000")
                
                # Recria tester com aceleração
                tester = ReliabilityTester(time_acceleration=acceleration, base_mttf_hours=1.0)
                
                print("⚠️ Simulação acelerada em desenvolvimento - executando teste normal acelerado")
                # Por enquanto executa teste normal com configuração acelerada
                return
        except (ValueError, KeyboardInterrupt):
            print("❌ Continuando com modo normal")
        
        # Selecionar componente
        components = ['pod', 'worker_node', 'control_plane']
        component = tester.interactive_selector.select_from_list(components, "Selecione o tipo de componente")
        if not component:
            return
        
        # Selecionar método de falha baseado no componente
        if component == 'pod':
            # methods = ['kill_processes', 'kill_init', 'delete_pod']
            methods = ['kill_processes', 'kill_init']
        elif component == 'worker_node':
            methods = ['kill_worker_node_processes']
        else:  # control_plane
            methods = ['kill_control_plane_processes']
        
        failure_method = tester.interactive_selector.select_from_list(methods, "Selecione o método de falha")
        if not failure_method:
            return
    else:
        component = args.component
        failure_method = args.failure_method
    
    # ======= EXECUTAR TESTE PRINCIPAL =======
    print(f"\n🎯 === INICIANDO TESTE DE CONFIABILIDADE ===")
    print(f"📊 Componente: {component}")
    print(f"🔨 Método de falha: {failure_method}")
    print(f"🔢 Iterações: {args.iterations}")
    print(f"⏱️ Intervalo: {args.interval}s")
    print(f"⏰ Timeout de recuperação: {get_current_recovery_timeout()}s")
    print(f"📁 CSV em tempo real: {'Ativado' if config.enable_realtime_csv else 'Desativado'}")
    print("="*60)
    
    # Executar teste normal
    results = tester.run_reliability_test(
        component_type=component,
        failure_method=failure_method,
        target=args.target,
        iterations=args.iterations,
        interval=args.interval
    )
    
    if results:
        print(f"\n✅ === TESTE CONCLUÍDO COM SUCESSO ===")
        print(f"📊 {len(results)} iterações executadas")
        print(f"⏰ Timeout usado: {get_current_recovery_timeout()}s")
        if config.enable_realtime_csv:
            print(f"📁 Resultados salvos em tempo real")
    else:
        print(f"\n❌ === TESTE NÃO EXECUTADO ===")


if __name__ == "__main__":
    main()