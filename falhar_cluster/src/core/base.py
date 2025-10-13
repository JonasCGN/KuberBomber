#!/usr/bin/env python3
"""
Kubernetes Chaos Engineering Framework
======================================

Um framework completo para injeção de falhas em clusters Kubernetes,
permitindo testar a resiliência de aplicações e infraestrutura.

Autor: Jonas
Data: Outubro 2025
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import time
import logging
from enum import Enum

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FailureType(Enum):
    """Tipos de falhas suportadas pelo framework"""
    POD_DELETE = "pod_delete"
    POD_KILL = "pod_kill"
    POD_RESOURCE_LIMIT = "pod_resource_limit"
    POD_CRASHLOOP = "pod_crashloop"
    
    PROCESS_KILL = "process_kill"
    PROCESS_CPU_STRESS = "process_cpu_stress"
    PROCESS_MEMORY_STRESS = "process_memory_stress"
    PROCESS_IO_STRESS = "process_io_stress"
    
    NODE_REBOOT = "node_reboot"
    NODE_SHUTDOWN = "node_shutdown"
    NODE_NETWORK_PARTITION = "node_network_partition"
    NODE_DISK_FILL = "node_disk_fill"
    NODE_DRAIN = "node_drain"
    NODE_CORDON = "node_cordon"


class FailureStatus(Enum):
    """Status de uma injeção de falha"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass
class FailureMetrics:
    """Métricas coletadas durante uma injeção de falha"""
    failure_id: str
    failure_type: FailureType
    target: str
    start_time: datetime
    end_time: Optional[datetime] = None
    recovery_time: Optional[float] = None  # segundos
    downtime: Optional[float] = None  # segundos
    success: bool = False
    error_message: Optional[str] = None
    additional_metrics: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.additional_metrics is None:
            self.additional_metrics = {}


@dataclass
class RecoveryMetrics:
    """Métricas específicas de recuperação"""
    time_to_detect: float  # tempo para detectar a falha
    time_to_restart: float  # tempo para reiniciar/substituir
    time_to_ready: float  # tempo para ficar ready
    total_recovery_time: float  # tempo total de recuperação
    availability_impact: float  # % de disponibilidade perdida


class BaseFailureInjector(ABC):
    """Classe base abstrata para todos os injetores de falha"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.active_failures: Dict[str, FailureMetrics] = {}
    
    @abstractmethod
    def inject_failure(self, target: str, **kwargs) -> FailureMetrics:
        """Injeta uma falha no target especificado"""
        pass
    
    @abstractmethod
    def recover_failure(self, failure_id: str) -> bool:
        """Recupera de uma falha específica"""
        pass
    
    @abstractmethod
    def list_targets(self) -> List[str]:
        """Lista todos os targets disponíveis para injeção de falha"""
        pass
    
    @abstractmethod
    def validate_target(self, target: str) -> bool:
        """Valida se o target é válido para este tipo de injetor"""
        pass
    
    def get_failure_metrics(self, failure_id: str) -> Optional[FailureMetrics]:
        """Retorna as métricas de uma falha específica"""
        return self.active_failures.get(failure_id)
    
    def list_active_failures(self) -> List[FailureMetrics]:
        """Lista todas as falhas ativas"""
        return list(self.active_failures.values())
    
    def cleanup_completed_failures(self):
        """Remove falhas completadas da lista ativa"""
        to_remove = []
        for failure_id, metrics in self.active_failures.items():
            if metrics.end_time is not None:
                to_remove.append(failure_id)
        
        for failure_id in to_remove:
            del self.active_failures[failure_id]


class BaseMonitor(ABC):
    """Classe base para monitores de sistema"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    @abstractmethod
    def get_status(self, target: str) -> Dict[str, Any]:
        """Retorna o status atual do target"""
        pass
    
    @abstractmethod
    def is_healthy(self, target: str) -> bool:
        """Verifica se o target está saudável"""
        pass
    
    @abstractmethod
    def wait_for_recovery(self, target: str, timeout: int = 300) -> RecoveryMetrics:
        """Aguarda a recuperação do target e coleta métricas"""
        pass


class MetricsCollector:
    """Coletor centralizado de métricas"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.MetricsCollector")
        self.metrics_history: List[FailureMetrics] = []
    
    def record_failure(self, metrics: FailureMetrics):
        """Registra métricas de uma falha"""
        self.metrics_history.append(metrics)
        self.logger.info(f"Recorded failure metrics for {metrics.failure_id}")
    
    def get_metrics_by_type(self, failure_type: FailureType) -> List[FailureMetrics]:
        """Retorna métricas filtradas por tipo de falha"""
        return [m for m in self.metrics_history if m.failure_type == failure_type]
    
    def get_metrics_by_target(self, target: str) -> List[FailureMetrics]:
        """Retorna métricas filtradas por target"""
        return [m for m in self.metrics_history if m.target == target]
    
    def calculate_mttr(self, failure_type: Optional[FailureType] = None) -> float:
        """Calcula o Mean Time To Recovery"""
        metrics = self.metrics_history
        if failure_type:
            metrics = self.get_metrics_by_type(failure_type)
        
        recovery_times = [m.recovery_time for m in metrics if m.recovery_time is not None]
        return sum(recovery_times) / len(recovery_times) if recovery_times else 0.0
    
    def calculate_availability(self, target: str, period_hours: int = 24) -> float:
        """Calcula a disponibilidade de um target em um período"""
        target_metrics = self.get_metrics_by_target(target)
        total_downtime = sum(m.downtime for m in target_metrics if m.downtime is not None)
        total_period = period_hours * 3600  # converter para segundos
        
        return max(0, (total_period - total_downtime) / total_period * 100)


class ChaosOrchestrator:
    """Orquestrador principal para coordenar injeções de falha"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ChaosOrchestrator")
        self.injectors: Dict[str, BaseFailureInjector] = {}
        self.monitors: Dict[str, BaseMonitor] = {}
        self.metrics_collector = MetricsCollector()
    
    def register_injector(self, injector: BaseFailureInjector):
        """Registra um injetor de falha"""
        self.injectors[injector.name] = injector
        self.logger.info(f"Registered injector: {injector.name}")
    
    def register_monitor(self, monitor: BaseMonitor):
        """Registra um monitor"""
        self.monitors[monitor.name] = monitor
        self.logger.info(f"Registered monitor: {monitor.name}")
    
    def execute_failure_scenario(self, 
                                 injector_name: str, 
                                 target: str, 
                                 monitor_name: Optional[str] = None,
                                 **kwargs) -> FailureMetrics:
        """
        Executa um cenário de falha completo com monitoramento
        """
        if injector_name not in self.injectors:
            raise ValueError(f"Injector {injector_name} not found")
        
        injector = self.injectors[injector_name]
        monitor = self.monitors.get(monitor_name) if monitor_name else None
        
        # Injeta a falha
        self.logger.info(f"Executing failure scenario: {injector_name} on {target}")
        metrics = injector.inject_failure(target, **kwargs)
        
        # Monitora a recuperação se um monitor foi especificado
        if monitor:
            try:
                recovery_metrics = monitor.wait_for_recovery(target)
                metrics.recovery_time = recovery_metrics.total_recovery_time
                if metrics.additional_metrics is None:
                    metrics.additional_metrics = {}
                metrics.additional_metrics['recovery'] = {
                    'time_to_detect': recovery_metrics.time_to_detect,
                    'time_to_restart': recovery_metrics.time_to_restart,
                    'time_to_ready': recovery_metrics.time_to_ready,
                    'availability_impact': recovery_metrics.availability_impact
                }
            except Exception as e:
                self.logger.error(f"Error monitoring recovery: {e}")
                metrics.error_message = str(e)
        
        # Registra as métricas
        self.metrics_collector.record_failure(metrics)
        
        return metrics
    
    def list_available_targets(self, injector_name: str) -> List[str]:
        """Lista targets disponíveis para um injetor específico"""
        if injector_name not in self.injectors:
            return []
        return self.injectors[injector_name].list_targets()
    
    def get_system_overview(self) -> Dict[str, Any]:
        """Retorna uma visão geral do sistema"""
        return {
            'registered_injectors': list(self.injectors.keys()),
            'registered_monitors': list(self.monitors.keys()),
            'total_failures_executed': len(self.metrics_collector.metrics_history),
            'active_failures': sum(len(inj.active_failures) for inj in self.injectors.values())
        }


# Funções utilitárias
def generate_failure_id(failure_type: FailureType, target: str) -> str:
    """Gera um ID único para uma falha"""
    timestamp = int(time.time() * 1000)
    return f"{failure_type.value}_{target}_{timestamp}"


def format_duration(seconds: float) -> str:
    """Formata duração em formato legível"""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        return f"{seconds/60:.2f}m"
    else:
        return f"{seconds/3600:.2f}h"


if __name__ == "__main__":
    print("Kubernetes Chaos Engineering Framework - Base Classes")
    print("Use este módulo importando as classes em seu código.")