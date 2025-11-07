"""
Simulação Modular - Kubernetes Availability Simulator
=====================================================

Módulos simplificados para simulação de disponibilidade:

- core_simulator: Lógica principal da simulação
- event_manager: Gestão de eventos de falha
- recovery_manager: Gestão de recuperação
- report_manager: Geração de relatórios

Uso:
    from kuber_bomber.simulation import CoreSimulator
    
    simulator = CoreSimulator(aws_config=None)  # ou aws_config para modo AWS
    simulator.run_simulation(duration_hours=24, iterations=1)
"""

# from .core_simulator import CoreSimulator, Component
# from .event_manager import EventManager, Event
# from .recovery_manager import RecoveryManager
# from .report_manager import ReportManager

# __all__ = [
#     'CoreSimulator',
#     'Component', 
#     'EventManager',
#     'Event',
#     'RecoveryManager',
#     'ReportManager'
# ]