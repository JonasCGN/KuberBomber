#!/usr/bin/env python3
"""
Process Failure Injector
========================

Implementa diversos tipos de falhas em processos para testes de resiliência.
Pode ser usado tanto em containers quanto em hosts diretamente.
"""

import os
import signal
import time
import subprocess
import psutil
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import paramiko

from ..core.base import (
    BaseFailureInjector, BaseMonitor, FailureMetrics, RecoveryMetrics,
    FailureType, FailureStatus, generate_failure_id, logger
)


class ProcessFailureInjector(BaseFailureInjector):
    """Injetor de falhas específico para processos do sistema"""
    
    def __init__(self, target_host: Optional[str] = None, ssh_config: Optional[Dict] = None):
        super().__init__("ProcessFailureInjector")
        self.target_host = target_host
        self.ssh_config = ssh_config or {}
        self.ssh_client = None
        self.active_stress_jobs: Dict[str, threading.Thread] = {}
        
        # Se target_host é especificado, configura SSH
        if target_host:
            self._setup_ssh_connection()
    
    def _setup_ssh_connection(self):
        """Configura conexão SSH para host remoto"""
        if not self.target_host:
            return
            
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh_client.connect(
                hostname=self.target_host,
                username=self.ssh_config.get('username', 'ubuntu'),
                password=self.ssh_config.get('password'),
                key_filename=self.ssh_config.get('key_file'),
                port=self.ssh_config.get('port', 22),
                timeout=self.ssh_config.get('timeout', 30)
            )
            self.logger.info(f"SSH connection established to {self.target_host}")
        except Exception as e:
            self.logger.error(f"Failed to establish SSH connection: {e}")
            self.ssh_client = None
    
    def _execute_command(self, command: str, background: bool = False) -> Tuple[int, str, str]:
        """Executa comando local ou remotamente via SSH"""
        if self.ssh_client:
            # Execução remota via SSH
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            if not background:
                return_code = stdout.channel.recv_exit_status()
                stdout_data = stdout.read().decode('utf-8')
                stderr_data = stderr.read().decode('utf-8')
                return return_code, stdout_data, stderr_data
            else:
                return 0, "", ""  # Para comandos em background
        else:
            # Execução local
            if background:
                subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return 0, "", ""
            else:
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                return result.returncode, result.stdout, result.stderr
    
    def list_targets(self) -> List[str]:
        """Lista processos em execução que podem ser targets"""
        try:
            if self.ssh_client:
                # Lista processos remotamente
                _, stdout, _ = self._execute_command("ps aux --no-headers")
                processes = []
                for line in stdout.split('\n'):
                    if line.strip():
                        parts = line.split(None, 10)
                        if len(parts) >= 11:
                            pid = parts[1]
                            command = parts[10]
                            processes.append(f"{pid}:{command[:50]}")
                return processes
            else:
                # Lista processos localmente
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        pid = proc.info['pid']
                        name = proc.info['name']
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        processes.append(f"{pid}:{name} {cmdline[:50]}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return processes
        except Exception as e:
            self.logger.error(f"Error listing processes: {e}")
            return []
    
    def validate_target(self, target: str) -> bool:
        """Valida se o processo existe"""
        try:
            if ':' in target:
                pid = int(target.split(':')[0])
            else:
                pid = int(target)
            
            if self.ssh_client:
                # Verifica remotamente
                return_code, _, _ = self._execute_command(f"kill -0 {pid}")
                return return_code == 0
            else:
                # Verifica localmente
                return psutil.pid_exists(pid)
        except (ValueError, Exception):
            return False
    
    def inject_failure(self, target: str, failure_type: str = "kill", **kwargs) -> FailureMetrics:
        """
        Injeta falha em um processo específico
        
        Args:
            target: PID do processo ou PID:nome
            failure_type: Tipo de falha ('kill', 'cpu_stress', 'memory_stress', 'io_stress')
            **kwargs: Parâmetros específicos do tipo de falha
        """
        if ':' in target:
            pid = int(target.split(':')[0])
            process_name = target.split(':')[1]
        else:
            pid = int(target)
            process_name = f"process_{pid}"
        
        if not self.validate_target(str(pid)):
            raise ValueError(f"Process {pid} not found or not accessible")
        
        failure_id = generate_failure_id(FailureType.PROCESS_KILL, f"{pid}")
        metrics = FailureMetrics(
            failure_id=failure_id,
            failure_type=FailureType.PROCESS_KILL,  # Default, será atualizado
            target=target,
            start_time=datetime.now()
        )
        
        try:
            if failure_type == "kill":
                metrics.failure_type = FailureType.PROCESS_KILL
                self._kill_process(pid, metrics, **kwargs)
            elif failure_type == "cpu_stress":
                metrics.failure_type = FailureType.PROCESS_CPU_STRESS
                self._stress_cpu(pid, metrics, **kwargs)
            elif failure_type == "memory_stress":
                metrics.failure_type = FailureType.PROCESS_MEMORY_STRESS
                self._stress_memory(pid, metrics, **kwargs)
            elif failure_type == "io_stress":
                metrics.failure_type = FailureType.PROCESS_IO_STRESS
                self._stress_io(pid, metrics, **kwargs)
            else:
                raise ValueError(f"Unknown failure type: {failure_type}")
            
            metrics.success = True
            self.active_failures[failure_id] = metrics
            self.logger.info(f"Successfully injected {failure_type} failure in process {pid}")
            
        except Exception as e:
            metrics.error_message = str(e)
            metrics.end_time = datetime.now()
            self.logger.error(f"Failed to inject failure in process {pid}: {e}")
        
        return metrics
    
    def _kill_process(self, pid: int, metrics: FailureMetrics, **kwargs):
        """Mata um processo com sinal especificado"""
        signal_name = kwargs.get('signal', 'SIGTERM')
        signal_num = getattr(signal, signal_name, signal.SIGTERM)
        
        try:
            if self.ssh_client:
                # Mata processo remotamente
                command = f"kill -{signal_name} {pid}"
                return_code, stdout, stderr = self._execute_command(command)
                if return_code != 0:
                    raise Exception(f"Remote kill failed: {stderr}")
            else:
                # Mata processo localmente
                os.kill(pid, signal_num)
            
            metrics.additional_metrics = {
                "signal": signal_name,
                "signal_number": signal_num
            }
            self.logger.info(f"Sent {signal_name} to process {pid}")
            
        except Exception as e:
            raise Exception(f"Failed to kill process: {e}")
    
    def _stress_cpu(self, pid: int, metrics: FailureMetrics, **kwargs):
        """Aplica stress de CPU no sistema (afeta indiretamente o processo)"""
        duration = kwargs.get('duration', 60)  # segundos
        cpu_percent = kwargs.get('cpu_percent', 90)
        cores = kwargs.get('cores', 1)
        
        try:
            if self.ssh_client:
                # Stress remoto usando stress-ng ou similar
                command = f"timeout {duration} stress-ng --cpu {cores} --cpu-load {cpu_percent} &"
                self._execute_command(command, background=True)
            else:
                # Stress local usando thread Python
                stress_thread = threading.Thread(
                    target=self._cpu_stress_worker,
                    args=(duration, cpu_percent, cores),
                    daemon=True
                )
                stress_thread.start()
                self.active_stress_jobs[metrics.failure_id] = stress_thread
            
            metrics.additional_metrics = {
                "duration": duration,
                "cpu_percent": cpu_percent,
                "cores": cores
            }
            self.logger.info(f"Applied CPU stress: {cpu_percent}% on {cores} cores for {duration}s")
            
        except Exception as e:
            raise Exception(f"Failed to apply CPU stress: {e}")
    
    def _stress_memory(self, pid: int, metrics: FailureMetrics, **kwargs):
        """Aplica stress de memória no sistema"""
        duration = kwargs.get('duration', 60)  # segundos
        memory_mb = kwargs.get('memory_mb', 512)
        
        try:
            if self.ssh_client:
                # Stress remoto
                command = f"timeout {duration} stress-ng --vm 1 --vm-bytes {memory_mb}M &"
                self._execute_command(command, background=True)
            else:
                # Stress local
                stress_thread = threading.Thread(
                    target=self._memory_stress_worker,
                    args=(duration, memory_mb),
                    daemon=True
                )
                stress_thread.start()
                self.active_stress_jobs[metrics.failure_id] = stress_thread
            
            metrics.additional_metrics = {
                "duration": duration,
                "memory_mb": memory_mb
            }
            self.logger.info(f"Applied memory stress: {memory_mb}MB for {duration}s")
            
        except Exception as e:
            raise Exception(f"Failed to apply memory stress: {e}")
    
    def _stress_io(self, pid: int, metrics: FailureMetrics, **kwargs):
        """Aplica stress de I/O no sistema"""
        duration = kwargs.get('duration', 60)  # segundos
        io_workers = kwargs.get('io_workers', 2)
        
        try:
            if self.ssh_client:
                # Stress remoto
                command = f"timeout {duration} stress-ng --io {io_workers} &"
                self._execute_command(command, background=True)
            else:
                # Stress local
                stress_thread = threading.Thread(
                    target=self._io_stress_worker,
                    args=(duration, io_workers),
                    daemon=True
                )
                stress_thread.start()
                self.active_stress_jobs[metrics.failure_id] = stress_thread
            
            metrics.additional_metrics = {
                "duration": duration,
                "io_workers": io_workers
            }
            self.logger.info(f"Applied I/O stress: {io_workers} workers for {duration}s")
            
        except Exception as e:
            raise Exception(f"Failed to apply I/O stress: {e}")
    
    def _cpu_stress_worker(self, duration: int, cpu_percent: int, cores: int):
        """Worker thread para stress de CPU local"""
        import multiprocessing
        
        def cpu_stress():
            end_time = time.time() + duration
            while time.time() < end_time:
                # Consume CPU cycles
                pass
        
        processes = []
        for _ in range(min(cores, multiprocessing.cpu_count())):
            p = multiprocessing.Process(target=cpu_stress)
            p.start()
            processes.append(p)
        
        # Aguarda conclusão
        time.sleep(duration)
        for p in processes:
            p.terminate()
            p.join()
    
    def _memory_stress_worker(self, duration: int, memory_mb: int):
        """Worker thread para stress de memória local"""
        try:
            # Aloca memória
            memory_data = bytearray(memory_mb * 1024 * 1024)
            
            # Escreve na memória para garantir alocação
            for i in range(0, len(memory_data), 4096):
                memory_data[i] = 1
            
            # Mantém por duração especificada
            time.sleep(duration)
            
            # Libera memória
            del memory_data
            
        except MemoryError:
            self.logger.warning("Not enough memory available for stress test")
    
    def _io_stress_worker(self, duration: int, io_workers: int):
        """Worker thread para stress de I/O local"""
        import tempfile
        import threading
        
        def io_worker():
            end_time = time.time() + duration
            while time.time() < end_time:
                try:
                    with tempfile.NamedTemporaryFile(delete=True) as f:
                        # Escreve dados aleatórios
                        data = os.urandom(1024 * 1024)  # 1MB
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                        
                        # Lê dados de volta
                        f.seek(0)
                        f.read()
                except Exception:
                    pass
        
        threads = []
        for _ in range(io_workers):
            t = threading.Thread(target=io_worker, daemon=True)
            t.start()
            threads.append(t)
        
        # Aguarda conclusão
        for t in threads:
            t.join(timeout=duration + 10)
    
    def recover_failure(self, failure_id: str) -> bool:
        """Recupera de uma falha específica"""
        if failure_id not in self.active_failures:
            return False
        
        metrics = self.active_failures[failure_id]
        
        try:
            # Para stress tests, simplesmente aguarda conclusão
            if failure_id in self.active_stress_jobs:
                thread = self.active_stress_jobs[failure_id]
                thread.join(timeout=5)
                del self.active_stress_jobs[failure_id]
            
            # Para processos mortos, não há recuperação automática
            # O sistema/orquestrador deve reiniciar o processo
            
            metrics.end_time = datetime.now()
            self.logger.info(f"Recovered from failure {failure_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to recover from failure {failure_id}: {e}")
            return False
    
    def get_process_metrics(self, pid: int) -> Dict[str, Any]:
        """Obtém métricas detalhadas de um processo"""
        try:
            if self.ssh_client:
                # Métricas remotas via SSH
                _, stdout, _ = self._execute_command(f"ps -p {pid} -o pid,ppid,pcpu,pmem,vsz,rss,tty,stat,start,time,comm --no-headers")
                if stdout.strip():
                    parts = stdout.strip().split(None, 10)
                    return {
                        'pid': int(parts[0]),
                        'ppid': int(parts[1]),
                        'cpu_percent': float(parts[2]),
                        'memory_percent': float(parts[3]),
                        'vsz': int(parts[4]),  # Virtual memory size
                        'rss': int(parts[5]),  # Resident memory size
                        'status': parts[7],
                        'command': parts[10] if len(parts) > 10 else 'unknown'
                    }
            else:
                # Métricas locais usando psutil
                proc = psutil.Process(pid)
                return {
                    'pid': proc.pid,
                    'ppid': proc.ppid(),
                    'name': proc.name(),
                    'status': proc.status(),
                    'cpu_percent': proc.cpu_percent(interval=1),
                    'memory_percent': proc.memory_percent(),
                    'memory_info': proc.memory_info()._asdict(),
                    'create_time': proc.create_time(),
                    'cmdline': proc.cmdline(),
                    'connections': len(proc.connections()) if hasattr(proc, 'connections') else 0
                }
        except Exception as e:
            self.logger.error(f"Error getting process metrics for PID {pid}: {e}")
            return {}
        
        return {}
    
    def __del__(self):
        """Cleanup SSH connection"""
        if self.ssh_client:
            self.ssh_client.close()


class ProcessMonitor(BaseMonitor):
    """Monitor específico para processos do sistema"""
    
    def __init__(self, target_host: Optional[str] = None, ssh_config: Optional[Dict] = None):
        super().__init__("ProcessMonitor")
        self.target_host = target_host
        self.ssh_config = ssh_config or {}
        self.ssh_client = None
        
        if target_host:
            self._setup_ssh_connection()
    
    def _setup_ssh_connection(self):
        """Configura conexão SSH (mesmo método do injector)"""
        if not self.target_host:
            return
            
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh_client.connect(
                hostname=self.target_host,
                username=self.ssh_config.get('username', 'ubuntu'),
                password=self.ssh_config.get('password'),
                key_filename=self.ssh_config.get('key_file'),
                port=self.ssh_config.get('port', 22),
                timeout=self.ssh_config.get('timeout', 30)
            )
        except Exception as e:
            self.logger.error(f"Failed to establish SSH connection: {e}")
            self.ssh_client = None
    
    def _execute_command(self, command: str) -> Tuple[int, str, str]:
        """Executa comando local ou remotamente"""
        if self.ssh_client:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            return_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')
            return return_code, stdout_data, stderr_data
        else:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            return result.returncode, result.stdout, result.stderr
    
    def get_status(self, target: str) -> Dict[str, Any]:
        """Retorna status detalhado de um processo"""
        try:
            if ':' in target:
                pid = int(target.split(':')[0])
            else:
                pid = int(target)
            
            if self.ssh_client:
                return_code, stdout, _ = self._execute_command(f"ps -p {pid} -o pid,stat --no-headers")
                if return_code == 0 and stdout.strip():
                    parts = stdout.strip().split()
                    return {
                        'pid': int(parts[0]),
                        'exists': True,
                        'status': parts[1] if len(parts) > 1 else 'unknown'
                    }
                else:
                    return {'exists': False}
            else:
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    return {
                        'pid': pid,
                        'exists': True,
                        'status': proc.status(),
                        'name': proc.name()
                    }
                else:
                    return {'exists': False}
                    
        except Exception:
            return {'exists': False}
    
    def is_healthy(self, target: str) -> bool:
        """Verifica se um processo está rodando"""
        status = self.get_status(target)
        return status.get('exists', False)
    
    def wait_for_recovery(self, target: str, timeout: int = 300) -> RecoveryMetrics:
        """
        Aguarda a recuperação de um processo
        """
        start_time = time.time()
        detect_time = None
        restart_time = None
        
        if ':' in target:
            pid = int(target.split(':')[0])
            process_name = target.split(':')[1]
        else:
            pid = int(target)
            process_name = f"process_{pid}"
        
        # Detecta quando o processo original morre
        original_exists = self.is_healthy(target)
        
        while time.time() - start_time < timeout:
            current_status = self.get_status(target)
            current_exists = current_status.get('exists', False)
            
            # Detecta morte do processo original
            if detect_time is None and original_exists and not current_exists:
                detect_time = time.time() - start_time
                self.logger.info(f"Process death detected at {detect_time:.2f}s")
            
            # Para processos, a "recuperação" seria um novo processo com o mesmo nome
            # Isso é mais complexo e depende do contexto (systemd, kubernetes, etc.)
            if restart_time is None and not original_exists and current_exists:
                restart_time = time.time() - start_time
                self.logger.info(f"Process restart detected at {restart_time:.2f}s")
                break
            
            time.sleep(1)
        
        total_recovery_time = restart_time if restart_time else time.time() - start_time
        
        return RecoveryMetrics(
            time_to_detect=detect_time or 0,
            time_to_restart=restart_time or total_recovery_time,
            time_to_ready=restart_time or total_recovery_time,
            total_recovery_time=total_recovery_time,
            availability_impact=(total_recovery_time / timeout) * 100
        )
    
    def __del__(self):
        """Cleanup SSH connection"""
        if self.ssh_client:
            self.ssh_client.close()


# Funções utilitárias
def kill_process_by_name(process_name: str, signal_name: str = "SIGTERM") -> List[FailureMetrics]:
    """Mata todos os processos com nome específico"""
    injector = ProcessFailureInjector()
    results = []
    
    targets = injector.list_targets()
    matching_processes = [t for t in targets if process_name.lower() in t.lower()]
    
    for target in matching_processes:
        try:
            metrics = injector.inject_failure(target, failure_type="kill", signal=signal_name)
            results.append(metrics)
        except Exception as e:
            logger.error(f"Failed to kill process {target}: {e}")
    
    return results


def stress_system(duration: int = 60, cpu_percent: int = 80, memory_mb: int = 512) -> FailureMetrics:
    """Aplica stress geral no sistema"""
    injector = ProcessFailureInjector()
    
    # Usa PID 1 como referência (init process)
    return injector.inject_failure(
        "1:init",
        failure_type="cpu_stress",
        duration=duration,
        cpu_percent=cpu_percent,
        cores=2
    )


if __name__ == "__main__":
    # Exemplo de uso
    injector = ProcessFailureInjector()
    monitor = ProcessMonitor()
    
    print("Processos em execução (primeiros 10):")
    for proc in injector.list_targets()[:10]:
        print(f"  - {proc}")
        pid = proc.split(':')[0]
        if monitor.is_healthy(pid):
            print(f"    Status: Healthy")