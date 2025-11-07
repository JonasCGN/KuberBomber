"""
Framework de Testes de Confiabilidade para Kubernetes
=====================================================

Framework modular para testes de MTTF (Mean Time To Failure) e 
MTTR (Mean Time To Recovery) em ambientes Kubernetes.

Módulos:
- core: Classes principais do framework
- monitoring: Monitoramento de saúde e sistema
- reports: Geração de relatórios CSV e análises
- failure_injectors: Injetores de falha para pods e nós
- simulation: Simulação acelerada de confiabilidade
- utils: Utilitários e configurações
- cli: Interface de linha de comando
"""

__version__ = "2.0.0"
__author__ = "Reliability Testing Framework"

from .core.reliability_tester import ReliabilityTester
from .utils.config import get_config, update_global_config, DEFAULT_CONFIG

__all__ = [
    'ReliabilityTester',
    'get_config', 
    'update_global_config',
    'DEFAULT_CONFIG'
]