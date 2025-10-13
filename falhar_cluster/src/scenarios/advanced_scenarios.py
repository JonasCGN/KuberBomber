#!/usr/bin/env python3
"""
Advanced Chaos Scenarios
========================

Implementa cenários complexos de falhas para testes avançados de resiliência.
"""

import time
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import random

from ..core.base import (
    BaseFailureInjector, FailureMetrics, FailureType, 
    ChaosOrchestrator, logger, generate_failure_id
)
from ..injectors.pod_injector import PodFailureInjector, PodMonitor
from ..injectors.process_injector import ProcessFailureInjector, ProcessMonitor
from ..injectors.node_injector import NodeFailureInjector, NodeMonitor
from ..monitoring.system_monitor import SystemMonitor
from ..monitoring.metrics_collector import AdvancedMetricsCollector


class ScenarioType(Enum):
    """Tipos de cenários de chaos"""
    CASCADE_FAILURE = "cascade_failure"
    ROLLING_RESTART = "rolling_restart"
    NETWORK_PARTITION = "network_partition"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    SPLIT_BRAIN = "split_brain"
    BLAST_RADIUS = "blast_radius"
    TIME_TRAVEL = "time_travel"
    DEPENDENCY_FAILURE = "dependency_failure"


@dataclass
class ScenarioStep:
    """Um passo individual em um cenário"""
    name: str
    injector_type: str  # 'pod', 'node', 'process'
    target: str
    failure_type: str
    parameters: Dict[str, Any]
    delay_before: int = 0  # segundos
    wait_for_completion: bool = False
    condition: Optional[Callable] = None  # Condição para executar o passo


@dataclass
class ScenarioResult:
    """Resultado de execução de um cenário"""
    scenario_name: str
    scenario_type: ScenarioType
    start_time: datetime
    end_time: Optional[datetime] = None
    success: bool = False
    steps_executed: Optional[List[str]] = None
    total_recovery_time: float = 0
    failures_injected: int = 0
    recovery_metrics: Optional[List[FailureMetrics]] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.steps_executed is None:
            self.steps_executed = []
        if self.recovery_metrics is None:
            self.recovery_metrics = []


class AdvancedChaosScenarios:
    """Gerenciador de cenários avançados de chaos engineering"""
    
    def __init__(self, namespace: str = "default", 
                 kubeconfig_path: Optional[str] = None,
                 metrics_db_path: str = "chaos_metrics.db"):
        self.namespace = namespace
        self.logger = logger.getChild("AdvancedChaosScenarios")
        
        # Inicializa injetores e monitores
        self.pod_injector = PodFailureInjector(namespace, kubeconfig_path)
        self.pod_monitor = PodMonitor(namespace, kubeconfig_path)
        
        self.node_injector = NodeFailureInjector(kubeconfig_path)
        self.node_monitor = NodeMonitor(kubeconfig_path)
        
        self.process_injector = ProcessFailureInjector()
        self.process_monitor = ProcessMonitor()
        
        self.system_monitor = SystemMonitor(kubeconfig_path)
        self.metrics_collector = AdvancedMetricsCollector(metrics_db_path)
        
        # Orquestrador
        self.orchestrator = ChaosOrchestrator()
        self.orchestrator.register_injector(self.pod_injector)
        self.orchestrator.register_injector(self.node_injector)
        self.orchestrator.register_injector(self.process_injector)
        
        self.orchestrator.register_monitor(self.pod_monitor)
        self.orchestrator.register_monitor(self.node_monitor)
        self.orchestrator.register_monitor(self.process_monitor)
        
        # Cenários ativos
        self.active_scenarios: Dict[str, threading.Thread] = {}
    
    def cascade_failure_scenario(self, app_label: str = "test-app", 
                                intensity: str = "medium") -> ScenarioResult:
        """
        Simula falha em cascata: falha em um componente causa falhas em outros
        """
        scenario_name = f"cascade_failure_{app_label}_{intensity}"
        result = ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.CASCADE_FAILURE,
            start_time=datetime.now()
        )
        
        try:
            self.logger.info(f"Starting cascade failure scenario for {app_label}")
            
            # 1. Identifica pods do app
            pods = [p for p in self.pod_injector.list_targets() 
                   if app_label in p or "test" in p]
            
            if not pods:
                raise ValueError(f"No pods found for app {app_label}")
            
            # 2. Define intensidade
            if intensity == "low":
                failure_percentage = 0.2
                delay_between_failures = 60
            elif intensity == "medium":
                failure_percentage = 0.5
                delay_between_failures = 30
            else:  # high
                failure_percentage = 0.8
                delay_between_failures = 10
            
            num_failures = max(1, int(len(pods) * failure_percentage))
            targets = random.sample(pods, num_failures)
            
            # 3. Executa falhas em cascata
            for i, target in enumerate(targets):
                if i > 0:
                    time.sleep(delay_between_failures)
                
                self.logger.info(f"Cascade step {i+1}: Failing {target}")
                
                metrics = self.pod_injector.inject_failure(target, failure_type="delete")
                result.recovery_metrics.append(metrics)
                result.steps_executed.append(f"Failed pod {target}")
                result.failures_injected += 1
                
                # Monitora impacto no sistema
                cluster_health = self.system_monitor.get_cluster_health()
                if cluster_health.cluster_score < 50:
                    self.logger.warning(f"Cluster health critical: {cluster_health.cluster_score}")
                    break
            
            # 4. Aguarda recuperação completa
            self.logger.info("Waiting for system recovery...")
            total_recovery_start = time.time()
            
            all_recovered = False
            max_wait_time = 600  # 10 minutos
            
            while not all_recovered and (time.time() - total_recovery_start) < max_wait_time:
                cluster_health = self.system_monitor.get_cluster_health()
                
                if cluster_health.cluster_score >= 90:
                    all_recovered = True
                else:
                    time.sleep(10)
            
            result.total_recovery_time = time.time() - total_recovery_start
            result.success = all_recovered
            result.end_time = datetime.now()
            
            self.logger.info(f"Cascade scenario completed. Recovery time: {result.total_recovery_time:.2f}s")
            
        except Exception as e:
            result.error_message = str(e)
            result.end_time = datetime.now()
            self.logger.error(f"Cascade scenario failed: {e}")
        
        # Salva métricas
        for metrics in result.recovery_metrics:
            self.metrics_collector.record_failure(metrics)
        
        return result
    
    def rolling_restart_scenario(self, deployment_name: str = "test-deployment",
                                restart_interval: int = 30) -> ScenarioResult:
        """
        Executa rolling restart controlado de uma aplicação
        """
        scenario_name = f"rolling_restart_{deployment_name}"
        result = ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.ROLLING_RESTART,
            start_time=datetime.now()
        )
        
        try:
            self.logger.info(f"Starting rolling restart for {deployment_name}")
            
            # Identifica pods do deployment
            pods = [p for p in self.pod_injector.list_targets() 
                   if deployment_name.replace("-deployment", "") in p]
            
            if not pods:
                raise ValueError(f"No pods found for deployment {deployment_name}")
            
            # Executa restart em rolling fashion
            for i, pod in enumerate(pods):
                self.logger.info(f"Rolling restart step {i+1}/{len(pods)}: Restarting {pod}")
                
                # Delete pod
                metrics = self.pod_injector.inject_failure(pod, failure_type="delete")
                result.recovery_metrics.append(metrics)
                result.steps_executed.append(f"Restarted pod {pod}")
                result.failures_injected += 1
                
                # Aguarda pod ficar ready novamente antes de continuar
                recovery_metrics = self.pod_monitor.wait_for_recovery(pod, timeout=300)
                metrics.recovery_time = recovery_metrics.total_recovery_time
                
                if i < len(pods) - 1:  # Não espera após o último pod
                    time.sleep(restart_interval)
            
            result.success = True
            result.end_time = datetime.now()
            result.total_recovery_time = sum(m.recovery_time for m in result.recovery_metrics if m.recovery_time)
            
            self.logger.info(f"Rolling restart completed successfully")
            
        except Exception as e:
            result.error_message = str(e)
            result.end_time = datetime.now()
            self.logger.error(f"Rolling restart failed: {e}")
        
        # Salva métricas
        for metrics in result.recovery_metrics:
            self.metrics_collector.record_failure(metrics)
        
        return result
    
    def pod_reboot_rolling_scenario(self, deployment_name: str = "test-deployment",
                                   restart_interval: int = 30) -> ScenarioResult:
        """
        Executa rolling restart usando POD_REBOOT (delete + recreate)
        Mais realístico que o delete simples pois simula reboot completo
        """
        scenario_name = f"pod_reboot_rolling_{deployment_name}"
        result = ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.ROLLING_RESTART,
            start_time=datetime.now()
        )
        
        try:
            self.logger.info(f"Starting POD_REBOOT rolling restart for {deployment_name}")
            
            # Identifica pods do deployment
            pods = [p for p in self.pod_injector.list_targets() 
                   if deployment_name.replace("-deployment", "") in p]
            
            if not pods:
                raise ValueError(f"No pods found for deployment {deployment_name}")
            
            # Importa e usa o reliability simulator para POD_REBOOT
            from ..reliability.reliability_simulator import ReliabilitySimulator
            simulator = ReliabilitySimulator(namespace=self.namespace)
            
            # Executa reboot em rolling fashion
            for i, pod in enumerate(pods):
                self.logger.info(f"POD_REBOOT rolling step {i+1}/{len(pods)}: Rebooting {pod}")
                
                # Usa o método _reboot_pod que força delete + recreate
                success = simulator._reboot_pod(pod)
                
                # Cria metrics fake para compatibilidade
                from ..core.base import FailureMetrics
                metrics = FailureMetrics(
                    target=pod,
                    failure_type="pod_reboot",
                    start_time=datetime.now(),
                    success=success,
                    recovery_time=None
                )
                result.recovery_metrics.append(metrics)
                result.steps_executed.append(f"Rebooted pod {pod} (delete+recreate)")
                
                # Aguarda intervalo entre restarts
                if i < len(pods) - 1:  # Não aguarda após o último
                    self.logger.info(f"Waiting {restart_interval}s before next reboot...")
                    time.sleep(restart_interval)
            
            result.end_time = datetime.now()
            result.success = True
            self.logger.info(f"POD_REBOOT rolling restart completed successfully")
            
        except Exception as e:
            result.end_time = datetime.now()
            result.success = False
            result.error_message = str(e)
            self.logger.error(f"POD_REBOOT rolling restart failed: {e}")
        
        # Salva métricas
        for metrics in result.recovery_metrics:
            self.metrics_collector.record_failure(metrics)
        
        return result
    
    def network_partition_scenario(self, duration: int = 300) -> ScenarioResult:
        """
        Simula partição de rede isolando nós
        """
        scenario_name = f"network_partition_{duration}s"
        result = ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.NETWORK_PARTITION,
            start_time=datetime.now()
        )
        
        try:
            self.logger.info(f"Starting network partition scenario for {duration}s")
            
            # Identifica nós worker (evita master)
            all_nodes = self.node_injector.list_targets()
            worker_nodes = []
            
            for node in all_nodes:
                try:
                    node_obj = self.node_injector.v1.read_node(name=node)
                    labels = node_obj.metadata.labels or {}
                    
                    # Pula nós master/control-plane
                    if not any(key in labels for key in [
                        'node-role.kubernetes.io/master',
                        'node-role.kubernetes.io/control-plane'
                    ]):
                        worker_nodes.append(node)
                except:
                    continue
            
            if len(worker_nodes) < 2:
                raise ValueError("Need at least 2 worker nodes for network partition")
            
            # Seleciona nó para particionar
            target_node = random.choice(worker_nodes)
            
            self.logger.info(f"Applying network partition to {target_node}")
            
            # Aplica partição de rede
            metrics = self.node_injector.inject_failure(
                target_node,
                failure_type="network_partition",
                duration=duration,
                block_ports=[6443, 2379, 2380, 10250]  # API server, etcd, kubelet
            )
            
            result.recovery_metrics.append(metrics)
            result.steps_executed.append(f"Network partition applied to {target_node}")
            result.failures_injected += 1
            
            # Monitora impacto durante a partição
            self.logger.info("Monitoring system during network partition...")
            
            start_monitoring = time.time()
            min_cluster_score = 100
            
            while (time.time() - start_monitoring) < duration:
                cluster_health = self.system_monitor.get_cluster_health()
                min_cluster_score = min(min_cluster_score, cluster_health.cluster_score)
                time.sleep(10)
            
            # Aguarda recuperação após partição
            self.logger.info("Waiting for recovery after network partition...")
            
            recovery_start = time.time()
            recovery_metrics = self.node_monitor.wait_for_recovery(target_node, timeout=600)
            
            result.total_recovery_time = time.time() - recovery_start
            result.success = recovery_metrics.total_recovery_time > 0
            result.end_time = datetime.now()
            
            self.logger.info(f"Network partition scenario completed. "
                           f"Min cluster score: {min_cluster_score}, "
                           f"Recovery time: {result.total_recovery_time:.2f}s")
            
        except Exception as e:
            result.error_message = str(e)
            result.end_time = datetime.now()
            self.logger.error(f"Network partition scenario failed: {e}")
        
        # Salva métricas
        for metrics in result.recovery_metrics:
            self.metrics_collector.record_failure(metrics)
        
        return result
    
    def resource_exhaustion_scenario(self, target_type: str = "cpu",
                                   intensity: str = "medium",
                                   duration: int = 300) -> ScenarioResult:
        """
        Simula esgotamento de recursos (CPU, memória, disco)
        """
        scenario_name = f"resource_exhaustion_{target_type}_{intensity}_{duration}s"
        result = ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.RESOURCE_EXHAUSTION,
            start_time=datetime.now()
        )
        
        try:
            self.logger.info(f"Starting resource exhaustion scenario: {target_type} ({intensity})")
            
            # Define parâmetros baseados na intensidade
            if intensity == "low":
                stress_params = {"duration": duration, f"{target_type}_percent": 50}
            elif intensity == "medium":
                stress_params = {"duration": duration, f"{target_type}_percent": 80}
            else:  # high
                stress_params = {"duration": duration, f"{target_type}_percent": 95}
            
            # Aplica stress em múltiplos nós/processos
            targets_to_stress = []
            
            if target_type == "cpu":
                # Stress CPU em nós worker
                nodes = self.node_injector.list_targets()
                for node in nodes[:2]:  # Limita a 2 nós
                    targets_to_stress.append(("process", f"1:stress_cpu_{node}"))
            
            elif target_type == "memory":
                # Stress memória
                stress_params["memory_mb"] = 2048 if intensity == "high" else 1024
                targets_to_stress.append(("process", "1:stress_memory"))
            
            elif target_type == "disk":
                # Stress disco
                stress_params = {
                    "duration": duration,
                    "size_gb": 10 if intensity == "high" else 5
                }
                targets_to_stress.append(("node", random.choice(self.node_injector.list_targets())))
            
            # Executa stress em paralelo
            stress_threads = []
            
            for target_type_str, target in targets_to_stress:
                def run_stress(tt, t, params):
                    try:
                        if tt == "process":
                            if "cpu" in t:
                                metrics = self.process_injector.inject_failure(
                                    t, failure_type="cpu_stress", **params
                                )
                            elif "memory" in t:
                                metrics = self.process_injector.inject_failure(
                                    t, failure_type="memory_stress", **params
                                )
                        elif tt == "node" and target_type == "disk":
                            metrics = self.node_injector.inject_failure(
                                t, failure_type="disk_fill", **params
                            )
                        
                        result.recovery_metrics.append(metrics)
                        result.failures_injected += 1
                        
                    except Exception as e:
                        self.logger.error(f"Stress failed for {t}: {e}")
                
                thread = threading.Thread(target=run_stress, args=(target_type_str, target, stress_params))
                thread.start()
                stress_threads.append(thread)
                
                result.steps_executed.append(f"Applied {target_type} stress to {target}")
            
            # Monitora sistema durante stress
            self.logger.info(f"Monitoring system during {target_type} stress...")
            
            start_monitoring = time.time()
            min_cluster_score = 100
            
            while (time.time() - start_monitoring) < duration:
                cluster_health = self.system_monitor.get_cluster_health()
                min_cluster_score = min(min_cluster_score, cluster_health.cluster_score)
                time.sleep(15)
            
            # Aguarda conclusão do stress
            for thread in stress_threads:
                thread.join(timeout=duration + 60)
            
            # Aguarda recuperação do sistema
            recovery_start = time.time()
            
            while True:
                cluster_health = self.system_monitor.get_cluster_health()
                if cluster_health.cluster_score >= 90:
                    break
                
                if (time.time() - recovery_start) > 300:  # Max 5 min recovery
                    break
                
                time.sleep(10)
            
            result.total_recovery_time = time.time() - recovery_start
            result.success = True
            result.end_time = datetime.now()
            
            self.logger.info(f"Resource exhaustion scenario completed. "
                           f"Min cluster score: {min_cluster_score}")
            
        except Exception as e:
            result.error_message = str(e)
            result.end_time = datetime.now()
            self.logger.error(f"Resource exhaustion scenario failed: {e}")
        
        # Salva métricas
        for metrics in result.recovery_metrics:
            self.metrics_collector.record_failure(metrics)
        
        return result
    
    def blast_radius_test(self, failure_types: Optional[List[str]] = None,
                         max_concurrent_failures: int = 3) -> ScenarioResult:
        """
        Testa o raio de explosão (blast radius) - quantas falhas simultâneas 
        o sistema pode suportar antes de falha catastrófica
        """
        if failure_types is None:
            failure_types = ["pod_delete", "node_drain", "process_kill"]
        
        scenario_name = f"blast_radius_test_{max_concurrent_failures}_failures"
        result = ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.BLAST_RADIUS,
            start_time=datetime.now()
        )
        
        try:
            self.logger.info(f"Starting blast radius test with up to {max_concurrent_failures} concurrent failures")
            
            active_failures = []
            system_still_functional = True
            
            for failure_count in range(1, max_concurrent_failures + 1):
                if not system_still_functional:
                    break
                
                self.logger.info(f"Injecting failure #{failure_count}")
                
                # Seleciona tipo de falha aleatoriamente
                failure_type = random.choice(failure_types)
                
                if failure_type == "pod_delete":
                    targets = self.pod_injector.list_targets()
                    if targets:
                        target = random.choice(targets)
                        metrics = self.pod_injector.inject_failure(target, failure_type="delete")
                        active_failures.append(("pod", target, metrics))
                
                elif failure_type == "node_drain":
                    nodes = self.node_injector.list_targets()
                    worker_nodes = [n for n in nodes if "master" not in n.lower() and "control" not in n.lower()]
                    if worker_nodes:
                        target = random.choice(worker_nodes)
                        metrics = self.node_injector.inject_failure(target, failure_type="cordon")  # Menos agressivo que drain
                        active_failures.append(("node", target, metrics))
                
                result.failures_injected += 1
                result.steps_executed.append(f"Injected {failure_type} ({failure_count}/{max_concurrent_failures})")
                
                # Aguarda um pouco para falha se propagar
                time.sleep(30)
                
                # Verifica se sistema ainda funcional
                cluster_health = self.system_monitor.get_cluster_health()
                
                if cluster_health.cluster_score < 30:  # Threshold crítico
                    system_still_functional = False
                    self.logger.warning(f"System critical after {failure_count} failures. "
                                      f"Cluster score: {cluster_health.cluster_score}")
                else:
                    self.logger.info(f"System still functional after {failure_count} failures. "
                                   f"Cluster score: {cluster_health.cluster_score}")
            
            # Recupera todas as falhas
            self.logger.info("Recovering all injected failures...")
            
            recovery_start = time.time()
            
            for failure_type, target, metrics in active_failures:
                try:
                    if failure_type == "pod":
                        # Pods se recuperam automaticamente
                        pass
                    elif failure_type == "node":
                        self.node_injector.recover_failure(metrics.failure_id)
                    
                    result.recovery_metrics.append(metrics)
                    
                except Exception as e:
                    self.logger.error(f"Failed to recover {failure_type} {target}: {e}")
            
            # Aguarda recuperação completa do sistema
            while True:
                cluster_health = self.system_monitor.get_cluster_health()
                if cluster_health.cluster_score >= 80:
                    break
                
                if (time.time() - recovery_start) > 900:  # Max 15 min
                    break
                
                time.sleep(15)
            
            result.total_recovery_time = time.time() - recovery_start
            result.success = system_still_functional or cluster_health.cluster_score >= 80
            result.end_time = datetime.now()
            
            max_failures_handled = len(active_failures) if system_still_functional else len(active_failures) - 1
            
            self.logger.info(f"Blast radius test completed. "
                           f"Max concurrent failures handled: {max_failures_handled}")
            
        except Exception as e:
            result.error_message = str(e)
            result.end_time = datetime.now()
            self.logger.error(f"Blast radius test failed: {e}")
        
        # Salva métricas
        for metrics in result.recovery_metrics:
            self.metrics_collector.record_failure(metrics)
        
        return result
    
    def run_scenario_async(self, scenario_func: Callable, *args, **kwargs) -> str:
        """
        Executa cenário de forma assíncrona
        """
        scenario_id = f"scenario_{int(time.time())}"
        
        def run_scenario():
            try:
                result = scenario_func(*args, **kwargs)
                self.logger.info(f"Async scenario {scenario_id} completed: {result.scenario_name}")
            except Exception as e:
                self.logger.error(f"Async scenario {scenario_id} failed: {e}")
        
        thread = threading.Thread(target=run_scenario, daemon=True)
        thread.start()
        
        self.active_scenarios[scenario_id] = thread
        
        return scenario_id
    
    def get_active_scenarios(self) -> List[str]:
        """Retorna lista de cenários ativos"""
        # Remove cenários que já terminaram
        finished = []
        for scenario_id, thread in self.active_scenarios.items():
            if not thread.is_alive():
                finished.append(scenario_id)
        
        for scenario_id in finished:
            del self.active_scenarios[scenario_id]
        
        return list(self.active_scenarios.keys())


# Funções utilitárias para execução rápida
def run_cascade_failure_test(app_label: str = "test-app", intensity: str = "medium") -> ScenarioResult:
    """Executa teste de falha em cascata"""
    scenarios = AdvancedChaosScenarios()
    return scenarios.cascade_failure_scenario(app_label, intensity)


def run_blast_radius_test(max_failures: int = 3) -> ScenarioResult:
    """Executa teste de raio de explosão"""
    scenarios = AdvancedChaosScenarios()
    return scenarios.blast_radius_test(max_concurrent_failures=max_failures)


def run_full_resilience_suite() -> List[ScenarioResult]:
    """Executa suite completa de testes de resiliência"""
    scenarios = AdvancedChaosScenarios()
    results = []
    
    try:
        # 1. Teste de falha em cascata
        logger.info("Running cascade failure test...")
        results.append(scenarios.cascade_failure_scenario(intensity="medium"))
        
        time.sleep(60)  # Pausa entre testes
        
        # 2. Teste de rolling restart
        logger.info("Running rolling restart test...")
        results.append(scenarios.rolling_restart_scenario())
        
        time.sleep(60)
        
        # 2b. Teste de POD_REBOOT rolling restart (novo)
        logger.info("Running POD_REBOOT rolling restart test...")
        results.append(scenarios.pod_reboot_rolling_scenario())
        
        time.sleep(60)
        
        # 3. Teste de esgotamento de recursos
        logger.info("Running resource exhaustion test...")
        results.append(scenarios.resource_exhaustion_scenario("cpu", "medium", 180))
        
        time.sleep(60)
        
        # 4. Teste de raio de explosão
        logger.info("Running blast radius test...")
        results.append(scenarios.blast_radius_test(max_concurrent_failures=2))
        
    except Exception as e:
        logger.error(f"Resilience suite failed: {e}")
    
    return results


if __name__ == "__main__":
    # Exemplo de uso
    print("Advanced Chaos Scenarios - Example Usage")
    
    scenarios = AdvancedChaosScenarios()
    
    # Executa um teste simples
    result = scenarios.cascade_failure_scenario(intensity="low")
    
    print(f"Scenario: {result.scenario_name}")
    print(f"Success: {result.success}")
    print(f"Failures injected: {result.failures_injected}")
    print(f"Recovery time: {result.total_recovery_time:.2f}s")