#!/usr/bin/env python3
"""
Reliability Simulator for Kubernetes
====================================

Simulador de confiabilidade para análise acadêmica com métricas MTTF/MTBF/MTTR.
Implementa escala temporal acelerada e logging detalhado em CSV.
"""

import csv
import time
import random
import threading
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import os
import signal
import subprocess

from ..core.base import logger, generate_failure_id
from ..injectors.pod_injector import PodFailureInjector
from ..injectors.node_injector import NodeFailureInjector
from ..monitoring.system_monitor import SystemMonitor


class FailureMode(Enum):
    """Tipos de falha para simulação"""
    POD_KILL = "pod_kill"                    # Kill da aplicação no pod
    POD_REBOOT = "pod_reboot"                # Reboot forçado do pod (delete + recreate)
    NODE_REBOOT = "node_reboot"              # Reboot do nó
    NODE_KILL_ALL = "node_kill_all"          # Kill todos processos não-críticos do nó
    NODE_KILL_CRITICAL = "node_kill_critical"  # Kill processos CRÍTICOS do nó (muito destrutivo)

class EventType(Enum):
    """Tipos de eventos no log"""
    FAILURE_INITIATED = "failure_initiated"
    FAILURE_DETECTED = "failure_detected"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    SIMULATION_STARTED = "simulation_started"
    SIMULATION_STOPPED = "simulation_stopped"

@dataclass
class ReliabilityEvent:
    """Evento de confiabilidade para logging"""
    timestamp: str
    simulation_time: float  # Tempo simulado em horas
    real_time: float       # Tempo real em segundos
    event_type: EventType
    failure_mode: Optional[FailureMode]
    target: str
    target_type: str       # 'pod' ou 'node'
    failure_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    duration_hours: Optional[float] = None
    mttf_hours: Optional[float] = None
    mtbf_hours: Optional[float] = None
    mttr_seconds: Optional[float] = None
    mttr_hours: Optional[float] = None
    next_failure_in_hours: Optional[float] = None
    cluster_health_before: Optional[float] = None
    cluster_health_after: Optional[float] = None
    additional_info: Optional[str] = None


@dataclass
class ReliabilityMetrics:
    """Métricas de confiabilidade calculadas"""
    total_failures: int = 0
    total_recovery_time: float = 0  # segundos
    total_uptime: float = 0         # horas simuladas
    total_downtime: float = 0       # horas simuladas
    
    # Métricas principais
    mttf: float = 0     # Mean Time To Failure (horas)
    mtbf: float = 0     # Mean Time Between Failures (horas)
    mttr: float = 0     # Mean Time To Recovery (segundos)
    
    # Métricas derivadas
    availability: float = 0         # %
    reliability_at_1000h: float = 0 # Confiabilidade em 1000h
    failure_rate: float = 0         # falhas/hora
    
    # Histórico de tempos
    failure_intervals: Optional[List[float]] = None     # Intervalos entre falhas
    recovery_times: Optional[List[float]] = None        # Tempos de recuperação
    failure_timestamps: Optional[List[float]] = None    # Timestamps de falhas
    
    def __post_init__(self):
        if self.failure_intervals is None:
            self.failure_intervals = []
        if self.recovery_times is None:
            self.recovery_times = []
        if self.failure_timestamps is None:
            self.failure_timestamps = []


class ReliabilitySimulator:
    """
    Simulador de confiabilidade para clusters Kubernetes
    
    Implementa:
    - Escala temporal acelerada (1h real = X horas simuladas)
    - Métricas MTTF, MTBF, MTTR
    - Logging detalhado em CSV
    - Scheduler automático de falhas
    - Distribuições estatísticas para intervalos de falha
    """
    
    def __init__(self, 
                 namespace: str = "default",
                 kubeconfig_path: Optional[str] = None,
                 csv_log_path: str = "reliability_simulation.csv",
                 time_acceleration: float = 10000.0,  # 1h real = 10000h simuladas
                 base_mttf_hours: float = 1.0,        # 1 hora base (muito agressivo para testes)
                 base_mttr_seconds: float = 300.0):   # 5 min base
        
        self.namespace = namespace
        self.csv_log_path = csv_log_path
        self.time_acceleration = time_acceleration
        self.base_mttf_hours = base_mttf_hours
        self.base_mttr_seconds = base_mttr_seconds
        
        self.logger = logger.getChild("ReliabilitySimulator")
        
        # Inicializa componentes
        self.pod_injector = PodFailureInjector(namespace, kubeconfig_path)
        self.node_injector = NodeFailureInjector(kubeconfig_path)
        self.system_monitor = SystemMonitor(kubeconfig_path)
        
        # Estado da simulação
        self.simulation_start_time = None
        self.simulation_start_real = None
        self.is_running = False
        self.current_failures: Dict[str, Dict] = {}  # failure_id -> info
        self.metrics = ReliabilityMetrics()
        
        # Controle de threading
        self.scheduler_thread = None
        self.stop_event = threading.Event()
        
        # Configuração de falhas
        self.failure_modes = [
            FailureMode.POD_KILL,
            FailureMode.POD_REBOOT, 
            FailureMode.NODE_REBOOT,
            FailureMode.NODE_KILL_ALL,
            FailureMode.NODE_KILL_CRITICAL
        ]
        self.failure_distribution = "exponential"  # exponential, weibull, normal
        
        self._init_csv_log()
    
    def _init_csv_log(self):
        """Inicializa arquivo CSV de log"""
        if not os.path.exists(self.csv_log_path):
            with open(self.csv_log_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'simulation_time_hours', 'real_time_seconds',
                    'event_type', 'failure_mode', 'target', 'target_type',
                    'failure_id', 'start_time', 'end_time', 
                    'duration_seconds', 'duration_hours',
                    'mttf_hours', 'mtbf_hours', 'mttr_seconds', 'mttr_hours',
                    'next_failure_in_hours', 'cluster_health_before', 
                    'cluster_health_after', 'additional_info'
                ])
    
    def _log_event(self, event: ReliabilityEvent):
        """Registra evento no CSV"""
        try:
            with open(self.csv_log_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                row = [
                    event.timestamp,
                    event.simulation_time,
                    event.real_time,
                    event.event_type.value if event.event_type else "",
                    event.failure_mode.value if event.failure_mode else "",
                    event.target,
                    event.target_type,
                    event.failure_id,
                    event.start_time or "",
                    event.end_time or "",
                    event.duration_seconds or "",
                    event.duration_hours or "",
                    event.mttf_hours or "",
                    event.mtbf_hours or "",
                    event.mttr_seconds or "",
                    event.mttr_hours or "",
                    event.next_failure_in_hours or "",
                    event.cluster_health_before or "",
                    event.cluster_health_after or "",
                    event.additional_info or ""
                ]
                writer.writerow(row)
        except Exception as e:
            self.logger.error(f"Error logging event: {e}")
    
    def _get_simulation_time(self) -> float:
        """Retorna tempo simulado atual em horas"""
        if not self.simulation_start_real:
            return 0.0
        
        real_elapsed = time.time() - self.simulation_start_real
        return (real_elapsed / 3600.0) * self.time_acceleration
    
    def _calculate_next_failure_time(self) -> float:
        """Calcula próximo tempo de falha baseado na distribuição"""
        current_mttf = self._calculate_current_mttf()
        
        if self.failure_distribution == "exponential":
            # Distribuição exponencial (mais comum para falhas)
            return np.random.exponential(current_mttf)
        
        elif self.failure_distribution == "weibull":
            # Distribuição Weibull (para desgaste)
            shape = 2.0  # β > 1 = taxa de falha crescente
            scale = current_mttf * np.power(np.log(2), 1.0/shape)
            return np.random.weibull(shape) * scale
        
        elif self.failure_distribution == "normal":
            # Distribuição normal (para falhas previsíveis)
            std_dev = current_mttf * 0.2  # 20% de variação
            return max(0.1, np.random.normal(current_mttf, std_dev))
        
        else:
            return current_mttf
    
    def _calculate_current_mttf(self) -> float:
        """Calcula MTTF atual baseado no histórico"""
        if len(self.metrics.failure_intervals) < 2:
            return self.base_mttf_hours
        
        # Média dos intervalos recentes (últimas 10 falhas)
        recent_intervals = self.metrics.failure_intervals[-10:]
        return float(np.mean(recent_intervals))
    
    def _update_metrics(self):
        """Atualiza métricas de confiabilidade"""
        if self.metrics.total_failures == 0:
            return
        
        # MTTF - Média dos intervalos entre falhas
        if len(self.metrics.failure_intervals) > 0:
            self.metrics.mttf = float(np.mean(self.metrics.failure_intervals))
        
        # MTBF - Tempo total / número de falhas
        sim_time = self._get_simulation_time()
        if self.metrics.total_failures > 0:
            self.metrics.mtbf = sim_time / self.metrics.total_failures
        
        # MTTR - Média dos tempos de recuperação
        if len(self.metrics.recovery_times) > 0:
            self.metrics.mttr = float(np.mean(self.metrics.recovery_times))
        
        # Disponibilidade
        if sim_time > 0:
            downtime_hours = self.metrics.total_recovery_time / 3600.0  # Convert to hours
            self.metrics.availability = max(0, (sim_time - downtime_hours) / sim_time * 100)
        
        # Taxa de falha
        if sim_time > 0:
            self.metrics.failure_rate = self.metrics.total_failures / sim_time
        
        # Confiabilidade em 1000h (usando distribuição exponencial)
        if self.metrics.mttf > 0:
            lambda_rate = 1.0 / self.metrics.mttf
            self.metrics.reliability_at_1000h = np.exp(-lambda_rate * 1000.0)
    
    def _select_target(self, failure_mode: FailureMode) -> Optional[Tuple[str, str]]:
        """Seleciona alvo para falha"""
        try:
            if failure_mode in [FailureMode.POD_KILL, FailureMode.POD_REBOOT]:
                pods = self.pod_injector.list_targets()
                if pods:
                    return random.choice(pods), "pod"
            
            elif failure_mode in [FailureMode.NODE_REBOOT, FailureMode.NODE_KILL_ALL, FailureMode.NODE_KILL_CRITICAL]:
                nodes = self.node_injector.list_targets()
                # Filtra nós worker (evita master)
                worker_nodes = []
                for node in nodes:
                    try:
                        node_obj = self.node_injector.v1.read_node(name=node)
                        labels = node_obj.metadata.labels or {}
                        if not any(key in labels for key in [
                            'node-role.kubernetes.io/master',
                            'node-role.kubernetes.io/control-plane'
                        ]):
                            worker_nodes.append(node)
                    except:
                        continue
                
                if worker_nodes:
                    return random.choice(worker_nodes), "node"
            
        except Exception as e:
            self.logger.error(f"Error selecting target for {failure_mode}: {e}")
        
        return None
    
    def _kill_pod_application(self, pod_name: str) -> bool:
        """Kill da aplicação principal dentro do pod"""
        try:
            self.logger.info(f"Killing application in pod {pod_name}")
            
            # Executa comando para matar processo principal (PID 1)
            cmd = [
                "kubectl", "exec", pod_name, 
                "-n", self.namespace,
                "--", "kill", "-9", "1"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully killed application in pod {pod_name}")
                return True
            else:
                self.logger.error(f"Failed to kill application in pod {pod_name}: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout killing application in pod {pod_name}")
            return False
        except Exception as e:
            self.logger.error(f"Error killing application in pod {pod_name}: {e}")
            return False
    
    def _reboot_pod(self, pod_name: str) -> bool:
        """Reboot forçado do pod via delete + recreate automático"""
        try:
            self.logger.info(f"Rebooting pod {pod_name} via delete")
            
            # Primeiro, obtém informações do pod para verificar se é gerenciado por deployment
            cmd_get = [
                "kubectl", "get", "pod", pod_name,
                "-n", self.namespace,
                "-o", "jsonpath={.metadata.ownerReferences[0].kind}"
            ]
            
            result_get = subprocess.run(cmd_get, capture_output=True, text=True, timeout=15)
            owner_kind = result_get.stdout.strip() if result_get.returncode == 0 else ""
            
            # Força delete do pod
            cmd_delete = [
                "kubectl", "delete", "pod", pod_name,
                "-n", self.namespace,
                "--force", "--grace-period=0"
            ]
            
            result_delete = subprocess.run(cmd_delete, capture_output=True, text=True, timeout=30)
            
            if result_delete.returncode == 0:
                if owner_kind in ["Deployment", "ReplicaSet", "DaemonSet", "StatefulSet"]:
                    self.logger.info(f"Pod {pod_name} deleted, will be recreated by {owner_kind}")
                else:
                    self.logger.warning(f"Pod {pod_name} deleted but has no controller to recreate it")
                return True
            else:
                self.logger.error(f"Failed to delete pod {pod_name}: {result_delete.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout deleting pod {pod_name}")
            return False
        except Exception as e:
            self.logger.error(f"Error rebooting pod {pod_name}: {e}")
            return False
    
    def _kill_all_node_processes(self, node_name: str) -> bool:
        """Kill todos os processos não-críticos do nó"""
        try:
            self.logger.info(f"Killing all processes on node {node_name}")
            
            # Comando para matar processos não-críticos
            # Preserva kernel, systemd, kubelet, docker
            cmd = [
                "kubectl", "debug", f"node/{node_name}",
                "-it", "--image=busybox",
                "--", "chroot", "/host", "bash", "-c",
                "pkill -f -9 '(?!systemd|kubelet|dockerd|containerd).*'"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully killed processes on node {node_name}")
                return True
            else:
                self.logger.warning(f"Partial success killing processes on node {node_name}")
                return True  # Considera sucesso mesmo com avisos
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout killing processes on node {node_name}")
            return False
        except Exception as e:
            self.logger.error(f"Error killing processes on node {node_name}: {e}")
            return False

    def _kill_critical_node_processes(self, node_name: str) -> bool:
        """Kill processos CRÍTICOS do nó - muito mais destrutivo"""
        try:
            self.logger.warning(f"Killing CRITICAL processes on node {node_name} - DESTRUCTIVE OPERATION")
            
            # Lista de processos críticos para matar sequencialmente
            critical_processes = [
                "kubelet",        # Agente Kubernetes no nó
                "containerd",     # Runtime de containers
                "dockerd",        # Docker daemon (se presente)
                "kube-proxy",     # Proxy de rede Kubernetes
                "calico-node",    # CNI (se usando Calico)
                "flannel",        # CNI (se usando Flannel)
                "coredns",        # DNS interno
                "etcd",           # Banco de dados (se executando no worker)
            ]
            
            killed_processes = []
            
            for process in critical_processes:
                try:
                    self.logger.info(f"Attempting to kill critical process: {process}")
                    
                    # Comando para matar processo específico crítico
                    cmd = [
                        "kubectl", "debug", f"node/{node_name}",
                        "-it", "--image=busybox", "--rm",
                        "--", "chroot", "/host", "bash", "-c",
                        f"pkill -f -9 '{process}' || killall -9 {process} || true"
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    
                    if result.returncode == 0 or "killed" in result.stdout.lower():
                        self.logger.warning(f"Successfully killed critical process: {process}")
                        killed_processes.append(process)
                    else:
                        self.logger.debug(f"Process {process} may not exist or already dead")
                        
                except subprocess.TimeoutExpired:
                    self.logger.error(f"Timeout killing process {process}")
                except Exception as e:
                    self.logger.error(f"Error killing process {process}: {e}")
                
                # Pequena pausa entre kills para observar efeito sequencial
                time.sleep(2)
            
            # Ataque final: mata todos os processos relacionados a containers
            try:
                self.logger.warning(f"Final attack: killing all container-related processes")
                
                cmd = [
                    "kubectl", "debug", f"node/{node_name}",
                    "-it", "--image=busybox", "--rm",
                    "--", "chroot", "/host", "bash", "-c",
                    "pkill -f -9 'containerd|docker|runc|cri-o|kubelet|kube-proxy' || true"
                ]
                
                subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                
            except Exception as e:
                self.logger.error(f"Error in final attack: {e}")
            
            if killed_processes:
                self.logger.warning(f"Killed critical processes on {node_name}: {killed_processes}")
                return True
            else:
                self.logger.warning(f"No critical processes killed on {node_name} - may already be dead")
                return False
                
        except Exception as e:
            self.logger.error(f"Error killing critical processes on node {node_name}: {e}")
            return False
    
    def _inject_failure(self, failure_mode: FailureMode, target: str, target_type: str) -> str:
        """Injeta falha específica"""
        failure_id = f"{failure_mode.value}_{target}_{int(time.time() * 1000)}"
        start_time = time.time()
        timestamp = datetime.now().isoformat()
        
        # Mede saúde do cluster antes
        try:
            health_before = self.system_monitor.get_cluster_health().cluster_score
        except:
            health_before = None
        
        self.logger.info(f"Injecting {failure_mode.value} on {target}")
        
        # Log início da falha
        event = ReliabilityEvent(
            timestamp=timestamp,
            simulation_time=self._get_simulation_time(),
            real_time=time.time() - self.simulation_start_real,
            event_type=EventType.FAILURE_INITIATED,
            failure_mode=failure_mode,
            target=target,
            target_type=target_type,
            failure_id=failure_id,
            start_time=timestamp,
            cluster_health_before=health_before,
            additional_info=f"Initiated {failure_mode.value} on {target_type} {target}"
        )
        self._log_event(event)
        
        # Executa falha
        success = False
        try:
            if failure_mode == FailureMode.POD_KILL:
                success = self._kill_pod_application(target)
            
            elif failure_mode == FailureMode.POD_REBOOT:
                success = self._reboot_pod(target)
            
            elif failure_mode == FailureMode.NODE_REBOOT:
                # Usa o injetor existente
                metrics = self.node_injector.inject_failure(target, failure_type="reboot")
                success = metrics.success
            
            elif failure_mode == FailureMode.NODE_KILL_ALL:
                success = self._kill_all_node_processes(target)
            
            elif failure_mode == FailureMode.NODE_KILL_CRITICAL:
                success = self._kill_critical_node_processes(target)
            
        except Exception as e:
            self.logger.error(f"Failed to inject {failure_mode.value}: {e}")
            success = False
        
        # Registra informações da falha
        self.current_failures[failure_id] = {
            'failure_mode': failure_mode,
            'target': target,
            'target_type': target_type,
            'start_time': start_time,
            'start_timestamp': timestamp,
            'success': success
        }
        
        if success:
            self.logger.info(f"Successfully injected {failure_mode.value} on {target}")
            
            # Log detecção da falha
            event = ReliabilityEvent(
                timestamp=datetime.now().isoformat(),
                simulation_time=self._get_simulation_time(),
                real_time=time.time() - self.simulation_start_real,
                event_type=EventType.FAILURE_DETECTED,
                failure_mode=failure_mode,
                target=target,
                target_type=target_type,
                failure_id=failure_id,
                start_time=timestamp,
                additional_info=f"Failure detected and confirmed"
            )
            self._log_event(event)
            
        else:
            self.logger.error(f"Failed to inject {failure_mode.value} on {target}")
        
        return failure_id
    
    def _monitor_recovery(self, failure_id: str):
        """Monitora recuperação de uma falha"""
        if failure_id not in self.current_failures:
            return
        
        failure_info = self.current_failures[failure_id]
        failure_mode = failure_info['failure_mode']
        target = failure_info['target']
        target_type = failure_info['target_type']
        start_time = failure_info['start_time']
        
        self.logger.info(f"Monitoring recovery for {failure_mode.value} on {target}")
        
        # Log início do monitoramento de recuperação
        event = ReliabilityEvent(
            timestamp=datetime.now().isoformat(),
            simulation_time=self._get_simulation_time(),
            real_time=time.time() - self.simulation_start_real,
            event_type=EventType.RECOVERY_STARTED,
            failure_mode=failure_mode,
            target=target,
            target_type=target_type,
            failure_id=failure_id,
            start_time=failure_info['start_timestamp'],
            additional_info=f"Started monitoring recovery"
        )
        self._log_event(event)
        
        max_wait_time = 1800  # 30 minutos máximo
        check_interval = 10   # Verifica a cada 10 segundos
        recovered = False
        
        elapsed = 0
        while elapsed < max_wait_time and not self.stop_event.is_set():
            time.sleep(check_interval)
            elapsed += check_interval
            
            try:
                if failure_mode == FailureMode.POD_KILL:
                    # Verifica se pod está running novamente
                    pod_obj = self.pod_injector.v1.read_namespaced_pod(
                        name=target, namespace=self.namespace
                    )
                    if pod_obj.status.phase == "Running":
                        # Verifica se todos containers estão ready
                        all_ready = True
                        if pod_obj.status.container_statuses:
                            for container in pod_obj.status.container_statuses:
                                if not container.ready:
                                    all_ready = False
                                    break
                        
                        if all_ready:
                            recovered = True
                            break
                
                elif failure_mode in [FailureMode.NODE_REBOOT, FailureMode.NODE_KILL_ALL]:
                    # Verifica se nó está ready
                    node_obj = self.node_injector.v1.read_node(name=target)
                    if node_obj.status.conditions:
                        for condition in node_obj.status.conditions:
                            if (condition.type == "Ready" and 
                                condition.status == "True"):
                                recovered = True
                                break
                    
                    if recovered:
                        break
                        
            except Exception as e:
                self.logger.debug(f"Error checking recovery status: {e}")
                continue
        
        # Calcula tempo de recuperação
        recovery_time = time.time() - start_time
        end_timestamp = datetime.now().isoformat()
        
        # Mede saúde do cluster após recuperação
        try:
            health_after = self.system_monitor.get_cluster_health().cluster_score
        except:
            health_after = None
        
        # Atualiza métricas
        self.metrics.total_failures += 1
        self.metrics.total_recovery_time += recovery_time
        self.metrics.recovery_times.append(recovery_time)
        
        # Calcula intervalo desde última falha
        sim_time = self._get_simulation_time()
        if len(self.metrics.failure_timestamps) > 0:
            interval = sim_time - self.metrics.failure_timestamps[-1]
            self.metrics.failure_intervals.append(interval)
        
        self.metrics.failure_timestamps.append(sim_time)
        
        # Atualiza métricas calculadas
        self._update_metrics()
        
        # Calcula próxima falha
        next_failure_in = self._calculate_next_failure_time()
        
        # Log recuperação completa
        event = ReliabilityEvent(
            timestamp=end_timestamp,
            simulation_time=sim_time,
            real_time=time.time() - self.simulation_start_real,
            event_type=EventType.RECOVERY_COMPLETED,
            failure_mode=failure_mode,
            target=target,
            target_type=target_type,
            failure_id=failure_id,
            start_time=failure_info['start_timestamp'],
            end_time=end_timestamp,
            duration_seconds=recovery_time,
            duration_hours=recovery_time / 3600.0,
            mttf_hours=self.metrics.mttf,
            mtbf_hours=self.metrics.mtbf,
            mttr_seconds=self.metrics.mttr,
            mttr_hours=self.metrics.mttr / 3600.0,
            next_failure_in_hours=next_failure_in,
            cluster_health_before=failure_info.get('health_before'),
            cluster_health_after=health_after,
            additional_info=f"Recovery {'successful' if recovered else 'timeout'} after {recovery_time:.1f}s"
        )
        self._log_event(event)
        
        # Remove da lista de falhas ativas
        del self.current_failures[failure_id]
        
        status = "recovered" if recovered else "timeout"
        self.logger.info(f"Recovery monitoring completed for {target}: {status} "
                        f"(duration: {recovery_time:.1f}s)")
    
    def _failure_scheduler(self):
        """Thread principal do scheduler de falhas"""
        self.logger.info("Failure scheduler started")
        
        while not self.stop_event.is_set():
            try:
                # Calcula tempo até próxima falha
                next_failure_in_hours = self._calculate_next_failure_time()
                next_failure_in_seconds = (next_failure_in_hours / self.time_acceleration) * 3600
                
                self.logger.info(f"Next failure scheduled in {next_failure_in_hours:.2f} simulated hours "
                               f"({next_failure_in_seconds:.1f} real seconds)")
                
                # Aguarda até próxima falha
                if self.stop_event.wait(timeout=next_failure_in_seconds):
                    break  # Parado pelo usuário
                
                # Seleciona modo de falha e alvo
                failure_mode = random.choice(self.failure_modes)
                target_result = self._select_target(failure_mode)
                
                if not target_result:
                    self.logger.warning(f"No targets available for {failure_mode.value}")
                    continue
                
                target, target_type = target_result
                
                # Injeta falha
                failure_id = self._inject_failure(failure_mode, target, target_type)
                
                # Inicia monitoramento de recuperação em thread separada
                recovery_thread = threading.Thread(
                    target=self._monitor_recovery,
                    args=(failure_id,),
                    daemon=True
                )
                recovery_thread.start()
                
            except Exception as e:
                self.logger.error(f"Error in failure scheduler: {e}")
                time.sleep(10)  # Aguarda antes de tentar novamente
        
        self.logger.info("Failure scheduler stopped")
    
    def start_simulation(self, duration_hours: Optional[float] = None,
                        failure_modes: Optional[List[FailureMode]] = None) -> bool:
        """
        Inicia simulação de confiabilidade
        
        Args:
            duration_hours: Duração em horas reais (None = infinito)
            failure_modes: Lista de modos de falha a usar
        """
        if self.is_running:
            self.logger.warning("Simulation already running")
            return False
        
        self.logger.info("Starting reliability simulation")
        
        # Configuração
        if failure_modes:
            self.failure_modes = failure_modes
        
        # Reset estado
        self.simulation_start_time = datetime.now()
        self.simulation_start_real = time.time()
        self.current_failures = {}
        self.metrics = ReliabilityMetrics()
        self.stop_event.clear()
        self.is_running = True
        
        # Log início da simulação
        event = ReliabilityEvent(
            timestamp=self.simulation_start_time.isoformat(),
            simulation_time=0.0,
            real_time=0.0,
            event_type=EventType.SIMULATION_STARTED,
            failure_mode=None,
            target="cluster",
            target_type="cluster",
            failure_id="simulation_start",
            additional_info=f"Started simulation with acceleration {self.time_acceleration}x, "
                          f"modes: {[fm.value for fm in self.failure_modes]}"
        )
        self._log_event(event)
        
        # Inicia scheduler
        self.scheduler_thread = threading.Thread(
            target=self._failure_scheduler,
            daemon=True
        )
        self.scheduler_thread.start()
        
        # Aguarda duração específica se fornecida
        if duration_hours:
            def stop_after_duration():
                time.sleep(duration_hours * 3600)  # Converte para segundos
                self.stop_simulation()
            
            timer_thread = threading.Thread(target=stop_after_duration, daemon=True)
            timer_thread.start()
        
        self.logger.info(f"Simulation started successfully. Time acceleration: {self.time_acceleration}x")
        return True
    
    def stop_simulation(self) -> bool:
        """Para a simulação"""
        if not self.is_running:
            self.logger.warning("Simulation not running")
            return False
        
        self.logger.info("Stopping reliability simulation")
        
        # Sinaliza parada
        self.stop_event.set()
        self.is_running = False
        
        # Aguarda threads terminarem
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=10)
        
        # Log fim da simulação
        event = ReliabilityEvent(
            timestamp=datetime.now().isoformat(),
            simulation_time=self._get_simulation_time(),
            real_time=time.time() - self.simulation_start_real,
            event_type=EventType.SIMULATION_STOPPED,
            failure_mode=None,
            target="cluster",
            target_type="cluster",
            failure_id="simulation_stop",
            mttf_hours=self.metrics.mttf,
            mtbf_hours=self.metrics.mtbf,
            mttr_seconds=self.metrics.mttr,
            additional_info=f"Stopped simulation. Total failures: {self.metrics.total_failures}, "
                          f"Final MTTF: {self.metrics.mttf:.2f}h, "
                          f"Final MTTR: {self.metrics.mttr:.1f}s"
        )
        self._log_event(event)
        
        self.logger.info("Simulation stopped successfully")
        return True
    
    def get_current_metrics(self) -> ReliabilityMetrics:
        """Retorna métricas atuais"""
        self._update_metrics()
        return self.metrics
    
    def get_simulation_status(self) -> Dict[str, Any]:
        """Retorna status atual da simulação"""
        sim_time = self._get_simulation_time()
        real_time = time.time() - self.simulation_start_real if self.simulation_start_real else 0
        
        return {
            'is_running': self.is_running,
            'simulation_time_hours': sim_time,
            'real_time_seconds': real_time,
            'time_acceleration': self.time_acceleration,
            'active_failures': len(self.current_failures),
            'total_failures': self.metrics.total_failures,
            'current_mttf_hours': self.metrics.mttf,
            'current_mtbf_hours': self.metrics.mtbf,
            'current_mttr_seconds': self.metrics.mttr,
            'availability_percent': self.metrics.availability,
            'csv_log_path': self.csv_log_path
        }


# Funções utilitárias para uso rápido
def run_reliability_simulation(duration_hours: float = 1.0,
                             time_acceleration: float = 10000.0,
                             csv_path: str = "reliability_test.csv") -> ReliabilityMetrics:
    """Executa simulação de confiabilidade por tempo determinado"""
    
    simulator = ReliabilitySimulator(
        csv_log_path=csv_path,
        time_acceleration=time_acceleration
    )
    
    logger.info(f"Starting {duration_hours}h reliability simulation "
               f"(acceleration: {time_acceleration}x)")
    
    try:
        # Inicia simulação
        simulator.start_simulation(duration_hours=duration_hours)
        
        # Aguarda conclusão
        while simulator.is_running:
            time.sleep(10)
            status = simulator.get_simulation_status()
            logger.info(f"Simulation progress: {status['simulation_time_hours']:.1f}h simulated, "
                       f"{status['total_failures']} failures")
        
        # Retorna métricas finais
        return simulator.get_current_metrics()
        
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
        simulator.stop_simulation()
        return simulator.get_current_metrics()


if __name__ == "__main__":
    # Exemplo de uso
    print("Reliability Simulator - Example Usage")
    
    # Simulação de 1 hora real = 10.000 horas simuladas
    metrics = run_reliability_simulation(
        duration_hours=0.1,  # 6 minutos reais
        time_acceleration=10000.0,
        csv_path="example_reliability.csv"
    )
    
    print(f"""
📊 SIMULATION RESULTS
==================
Total Failures: {metrics.total_failures}
MTTF: {metrics.mttf:.2f} hours
MTBF: {metrics.mtbf:.2f} hours  
MTTR: {metrics.mttr:.1f} seconds
Availability: {metrics.availability:.2f}%
Reliability at 1000h: {metrics.reliability_at_1000h:.4f}

Check CSV log: example_reliability.csv
""")