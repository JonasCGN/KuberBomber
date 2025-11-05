#!/usr/bin/env python3
"""
Sistema de Testes de Confiabilidade AWS - VERSÃO MODULAR
========================================================

Usa framework kuber_bomber com modo AWS ativado automaticamente.

Comando compatível:
python3 aws_reliability_tester.py --component pod --failure-method kill_processes --target bar-app-775c8885f5-l6m59 --iterations 5 --interval 10
"""

import sys
import os

# Adicionar ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Ponto de entrada principal - usa kuber_bomber com modo AWS."""
    try:
        # Usar o framework kuber_bomber com AWS automaticamente
        from kuber_bomber.cli.main import main as cli_main
        
        # Adicionar --aws automaticamente se não estiver presente
        if '--aws' not in sys.argv:
            sys.argv.insert(1, '--aws')
        
        # Chamar CLI do kuber_bomber que já tem integração AWS
        cli_main()
        
    except KeyboardInterrupt:
        print("\n🛑 Teste interrompido pelo usuário")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()