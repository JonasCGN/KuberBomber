#!/usr/bin/env python3
"""
Kubernetes Chaos Engineering Framework - Main Entry Point
=========================================================

Sistema completo para injeção de falhas e teste de resiliência em clusters Kubernetes.

Autor: Jonas
Data: Outubro 2025

Uso:
    python main.py --help                    # Mostra ajuda geral
    python main.py pod list                  # Lista pods disponíveis
    python main.py pod delete <pod-name>     # Deleta um pod específico
    python main.py node drain <node-name>    # Draina um nó
    python main.py monitor status            # Mostra status do cluster
    python main.py metrics report            # Gera relatório de métricas
    python main.py scenario --interactive    # Mode interativo de cenários
"""

import sys
import os
from pathlib import Path


# Adiciona o diretório atual ao path para importar módulos
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Ponto de entrada principal"""
    # Verifica se as dependências estão disponíveis
    missing_deps = []
    
    try:
        import kubernetes
    except ImportError:
        missing_deps.append('kubernetes')
    
    try:
        import click
    except ImportError:
        missing_deps.append('click')
    
    try:
        from rich.console import Console
    except ImportError:
        missing_deps.append('rich')
    
    if missing_deps:
        print("❌ Dependências faltando:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\n💡 Instale com: pip install -r requirements.txt")
        sys.exit(1)
    
    # Importa e executa CLI
    try:
        from src.cli.chaos_cli import cli
        cli()
    except Exception as e:
        print(f"❌ Erro ao executar: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()