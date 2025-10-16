#!/usr/bin/env python3
"""
Sistema de Testes de Confiabilidade para Kubernetes - VERSÃO MODULAR
====================================================================

Mantém TODAS as flags originais + timeout configurável + CSV em tempo real

Seu comando original funciona exatamente igual:
python3 reliability_tester.py --component pod --failure-method kill_processes --target test-app-549846444f-pbsgl --iterations 30 --interval 10
"""

import sys
import os

# Adicionar path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Ponto de entrada principal."""
    try:
        from reliability_framework.cli.main import main as cli_main
        cli_main()
    except ImportError as e:
        print(f"❌ Erro ao importar módulos: {e}")
        print("🔧 Verificando estrutura do framework...")
        
        # Debug das importações
        framework_path = os.path.join(os.path.dirname(__file__), 'reliability_framework')
        if not os.path.exists(framework_path):
            print(f"❌ Diretório não encontrado: {framework_path}")
            return
        
        print(f"✅ Framework encontrado em: {framework_path}")
        
        # Tentar importação manual
        try:
            from reliability_framework.core.reliability_tester import ReliabilityTester
            from reliability_framework.utils.config import get_current_recovery_timeout
            
            print("✅ Importações básicas funcionando")
            print(f"⏰ Timeout atual: {get_current_recovery_timeout()}s")
            
            # Fallback simples
            print("\n🎯 === MODO FALLBACK ===")
            print("Executando com configuração padrão...")
            
            tester = ReliabilityTester()
            
            # Verificar argumentos da linha de comando
            if len(sys.argv) > 1:
                print(f"📋 Argumentos recebidos: {sys.argv[1:]}")
                
                # Parse básico para seu comando original
                if '--list-targets' in sys.argv:
                    print("🎯 Alvos disponíveis:")
                    pods = tester.system_monitor.get_pods()
                    for pod in pods:
                        print(f"  📦 {pod}")
                    return
                
                # Verificar se tem argumentos necessários
                component = None
                failure_method = None
                target = None
                iterations = 30
                interval = 10
                
                for i, arg in enumerate(sys.argv):
                    if arg == '--component' and i + 1 < len(sys.argv):
                        component = sys.argv[i + 1]
                    elif arg == '--failure-method' and i + 1 < len(sys.argv):
                        failure_method = sys.argv[i + 1]
                    elif arg == '--target' and i + 1 < len(sys.argv):
                        target = sys.argv[i + 1]
                    elif arg == '--iterations' and i + 1 < len(sys.argv):
                        iterations = int(sys.argv[i + 1])
                    elif arg == '--interval' and i + 1 < len(sys.argv):
                        interval = int(sys.argv[i + 1])
                
                if component and failure_method:
                    print(f"\n🚀 Executando teste:")
                    print(f"   📊 Componente: {component}")
                    print(f"   🔨 Método: {failure_method}")
                    print(f"   🎯 Alvo: {target or 'Auto-selecionado'}")
                    print(f"   🔢 Iterações: {iterations}")
                    print(f"   ⏱️ Intervalo: {interval}s")
                    print("="*60)
                    
                    results = tester.run_reliability_test(
                        component_type=component,
                        failure_method=failure_method,
                        target=target,
                        iterations=iterations,
                        interval=interval
                    )
                    
                    if results:
                        print(f"\n✅ Teste concluído com {len(results)} iterações")
                    else:
                        print("\n⚠️ Teste interrompido")
                else:
                    print("\n❌ Argumentos insuficientes")
                    print("💡 Uso: python3 reliability_tester.py --component pod --failure-method kill_processes --iterations 30")
            else:
                print("\n📋 Nenhum argumento fornecido - modo interativo")
                # Modo interativo básico
                print("Componentes disponíveis: pod, worker_node, control_plane")
                
        except Exception as fallback_error:
            print(f"❌ Erro no fallback: {fallback_error}")
            import traceback
            traceback.print_exc()
    
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
