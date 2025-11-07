#!/usr/bin/env python3
"""
Analisador MTTR - Executa testes de confiabilidade e mede tempos de recuperação
============================================================================

Executa uma suite completa de testes para medir MTTR real de cada componente.
"""

import json
import time
import subprocess
import statistics
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import os


class MTTRAnalyzer:
    """Analisador de tempos de recuperação (MTTR) via testes de confiabilidade."""
    
    def __init__(self, use_aws: bool = False, aws_config: Optional[Dict] = None, iterations: int = 2):
        """
        Inicializa o analisador MTTR.
        
        Args:
            use_aws: Se deve usar modo AWS
            aws_config: Configuração AWS
            iterations: Número de iterações por teste (reduzido para 2 para ser mais rápido)
        """
        self.use_aws = use_aws
        self.aws_config = aws_config or {}
        self.iterations = iterations
        print(f"📊 MTTR Analyzer inicializado: {iterations} iterações por componente")
        self.iterations = iterations
        self.results: Dict[str, Dict[str, List[float]]] = {
            'pods': {},
            'worker_node': {},
            'control_plane': {}
        }
        
    def run_complete_analysis(self, config: Dict) -> Dict:
        """
        Executa análise MTTR completa em todos os componentes.
        
        Args:
            config: Configuração descoberta
            
        Returns:
            Configuração atualizada com MTTR medidos
        """
        print(f"🧪 === ANÁLISE MTTR COMPLETA ({self.iterations} iterações) ===")
        print("📊 Medindo tempos reais de recuperação...")
        print()
        
        # Extrair componentes do config
        experiment_config = config.get('experiment_config', {})
        
        # Testar pods/containers
        if 'applications' in experiment_config:
            self._test_application_components(experiment_config['applications'])
        
        # Testar worker nodes
        if 'worker_node' in experiment_config:
            self._test_worker_node_components(experiment_config['worker_node'])
            
        # Testar control plane
        if 'control_plane' in experiment_config:
            self._test_control_plane_components(experiment_config['control_plane'])
        
        # Calcular médias e atualizar config
        mttr_config = self._calculate_mttr_averages()
        config['mttr_config'] = mttr_config
        
        return config
    
    def _test_application_components(self, applications: Dict[str, bool]):
        """Testa componentes de aplicação (pods/containers)."""
        print("📦 === TESTANDO COMPONENTES DE APLICAÇÃO ===")
        
        for app_name, enabled in applications.items():
            if not enabled:
                continue
                
            print(f"🎯 Testando aplicação: {app_name}")
            
            # Descobrir pods da aplicação
            pods = self._discover_app_pods(app_name)
            
            for pod_name in pods:
                # Testar pod
                self._test_pod_component(pod_name, 'kill_processes')
                # Testar container
                self._test_pod_component(f"container-{pod_name}", 'kill_init')
    
    def _test_worker_node_components(self, worker_nodes: Dict[str, bool]):
        """Testa componentes de worker node."""
        print("🖥️ === TESTANDO WORKER NODES ===")
        
        for node_name, enabled in worker_nodes.items():
            if not enabled:
                continue
                
            print(f"🎯 Testando worker node: {node_name}")
            
            # Diferentes tipos de falha para worker nodes
            test_cases = [
                ('kill_worker_node_processes', 'worker_node'),
                ('kill_kubelet', 'wn_kubelet'),
                ('delete_kube_proxy', 'wn_proxy'),
                ('restart_containerd', 'wn_runtime')
            ]
            
            for failure_method, component_type in test_cases:
                self._test_worker_node_component(node_name, failure_method, component_type)
    
    def _test_control_plane_components(self, control_planes: Dict[str, bool]):
        """Testa componentes de control plane."""
        print("🎛️ === TESTANDO CONTROL PLANE ===")
        
        for node_name, enabled in control_planes.items():
            if not enabled:
                continue
                
            print(f"🎯 Testando control plane: {node_name}")
            
            # Diferentes tipos de falha para control plane
            test_cases = [
                ('kill_kube_apiserver', 'cp_apiserver'),
                ('kill_kube_controller_manager', 'cp_manager'),
                ('kill_kube_scheduler', 'cp_scheduler'),
                ('kill_etcd', 'cp_etcd')
            ]
            
            for failure_method, component_type in test_cases:
                timeout = 'extended' if failure_method == 'kill_etcd' else 'normal'
                self._test_control_plane_component(node_name, failure_method, component_type, timeout)
    
    def _test_pod_component(self, target: str, failure_method: str):
        """Executa teste em componente de pod."""
        recovery_times = []
        
        print(f"  🎯 Testando pod: {target}")
        for i in range(self.iterations):
            print(f"  📋 {target} - Iteração {i+1}/{self.iterations}")
            
            recovery_time = self._execute_reliability_test(
                component='pod',
                failure_method=failure_method,
                target=target,
                timeout='normal'
            )
            
            if recovery_time:
                recovery_times.append(recovery_time)
                print(f"    ✅ Sucesso: {recovery_time:.1f}s")
            else:
                print(f"    ❌ Falha na iteração {i+1}")
        
        # Calcular e salvar média se houver dados
        if recovery_times:
            avg_time = statistics.mean(recovery_times)
            print(f"  📊 Média para {target}: {avg_time:.1f}s ({len(recovery_times)}/{self.iterations} sucessos)")
            
            # Atualizar configuração de MTTR
            mttr_data = {
                'target': target,
                'failure_method': failure_method,
                'avg_recovery_time': avg_time,
                'successful_tests': len(recovery_times),
                'total_tests': self.iterations
            }
            
            return mttr_data
        else:
            print(f"  ⚠️ Nenhum teste bem-sucedido para {target}")
            return None
    
    def _test_worker_node_component(self, node_name: str, failure_method: str, component_type: str):
        """Executa teste em componente de worker node."""
        recovery_times = []
        
        print(f"  🎯 Testando worker node: {node_name} ({component_type})")
        for i in range(self.iterations):
            print(f"  📋 {component_type} - Iteração {i+1}/{self.iterations}")
            
            recovery_time = self._execute_reliability_test(
                component='worker_node',
                failure_method=failure_method,
                target=node_name,
                timeout='normal'
            )
            
            if recovery_time:
                recovery_times.append(recovery_time)
                print(f"    ✅ Sucesso: {recovery_time:.1f}s")
            else:
                print(f"    ❌ Falha na iteração {i+1}")
        
        # Calcular e salvar média se houver dados
        if recovery_times:
            avg_time = statistics.mean(recovery_times)
            print(f"  � Média para {node_name} ({component_type}): {avg_time:.1f}s ({len(recovery_times)}/{self.iterations} sucessos)")
            
            # Atualizar configuração de MTTR
            mttr_data = {
                'target': node_name,
                'failure_method': failure_method,
                'component_type': component_type,
                'avg_recovery_time': avg_time,
                'successful_tests': len(recovery_times),
                'total_tests': self.iterations
            }
            
            return mttr_data
        else:
            print(f"  ⚠️ Nenhum teste bem-sucedido para {node_name} ({component_type})")
            return None
    
    def _test_control_plane_component(self, node_name: str, failure_method: str, component_type: str, timeout: str):
        """Executa teste em componente de control plane."""
        recovery_times = []
        
        print(f"  🎯 Testando control plane: {node_name} ({component_type})")
        for i in range(self.iterations):
            print(f"  📋 {component_type} - Iteração {i+1}/{self.iterations}")
            
            recovery_time = self._execute_reliability_test(
                component='control_plane',
                failure_method=failure_method,
                target=node_name,
                timeout=timeout
            )
            
            if recovery_time:
                recovery_times.append(recovery_time)
                print(f"    ✅ Sucesso: {recovery_time:.1f}s")
            else:
                print(f"    ❌ Falha na iteração {i+1}")
        
        # Calcular e salvar média se houver dados
        if recovery_times:
            avg_time = statistics.mean(recovery_times)
            print(f"  � Média para {node_name} ({component_type}): {avg_time:.1f}s ({len(recovery_times)}/{self.iterations} sucessos)")
            
            # Atualizar configuração de MTTR
            mttr_data = {
                'target': node_name,
                'failure_method': failure_method,
                'component_type': component_type,
                'avg_recovery_time': avg_time,
                'successful_tests': len(recovery_times),
                'total_tests': self.iterations
            }
            
            return mttr_data
        else:
            print(f"  ⚠️ Nenhum teste bem-sucedido para {node_name} ({component_type})")
            return None
    
    def _execute_reliability_test(self, component: str, failure_method: str, target: str, timeout: str = 'normal') -> Optional[float]:
        """
        Executa teste de confiabilidade e mede tempo de recuperação.
        
        Args:
            component: Tipo do componente
            failure_method: Método de falha
            target: Alvo específico
            timeout: 'normal' ou 'extended'
        
        Returns:
            Tempo de recuperação em segundos ou None se falhou
        """
        start_time = time.time()  # Inicializar no início
        try:
            # Usar sempre o reliability_tester.py com flag --aws quando necessário
            cmd = [
                'python3', 'reliability_tester.py',
                '--component', component,
                '--failure-method', failure_method,
                '--target', target,
                '--iterations', '1',
                '--interval', '5'  # Reduzido para ser mais rápido
            ]
            
            if timeout == 'extended':
                cmd.extend(['--timeout', 'extended'])
            
            # Adicionar flag --aws quando em modo AWS
            if self.use_aws:
                cmd.append('--aws')
            
            # 🔍 MOSTRAR COMANDO SENDO EXECUTADO
            cmd_str = ' '.join(cmd)
            print(f"    🚀 Executando: {cmd_str}")
            
            # Definir timeout baseado no tipo e método de falha
            if failure_method in ['kill_worker_node_processes', 'kill_control_plane_processes'] and self.use_aws:
                # Testes AWS com reboot precisam de mais tempo
                test_timeout = 180  # 3 minutos para permitir reboot completo
            elif timeout == 'extended':
                test_timeout = 150
            else:
                test_timeout = 90
            print(f"    ⏰ Timeout: {test_timeout}s")
            
            # Executar teste
            result = subprocess.run(
                cmd,
                cwd='/mnt/Jonas/Projetos/Artigos/1_Artigo/testes',
                capture_output=True,
                text=True,
                timeout=test_timeout,
                input='y\n'  # Resposta automática para perguntas interativas
            )
            end_time = time.time()
            
            execution_time = end_time - start_time
            print(f"    ⏱️ Tempo de execução: {execution_time:.1f}s")
            
            if result.returncode == 0:
                # Extrair tempo de recuperação do output
                recovery_time = self._extract_recovery_time(result.stdout)
                recovered_time = recovery_time if recovery_time else execution_time
                print(f"    ✅ Recuperação detectada: {recovered_time:.1f}s")
                return recovered_time
            else:
                print(f"    ❌ Erro no teste (código {result.returncode})")
                if result.stderr.strip():
                    # Mostrar apenas as primeiras linhas do erro para não poluir
                    error_lines = result.stderr.strip().split('\n')[:3]
                    for line in error_lines:
                        print(f"      🔴 {line}")
                return None
                
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            print(f"    ⏰ Timeout após {elapsed:.1f}s - teste muito lento")
            return None
        except Exception as e:
            print(f"    ❌ Exceção: {e}")
            return None
    
    def _extract_recovery_time(self, output: str) -> Optional[float]:
        """Extrai tempo de recuperação do output do teste."""
        # Procurar por padrões de tempo no output
        lines = output.split('\n')
        for line in lines:
            if 'tempo de recuperação' in line.lower() or 'recovery time' in line.lower():
                # Extrair número
                import re
                match = re.search(r'(\d+\.?\d*)', line)
                if match:
                    return float(match.group(1))
        
        return None
    
    def _discover_app_pods(self, app_name: str) -> List[str]:
        """Descobre pods de uma aplicação."""
        try:
            if self.use_aws:
                cmd = f"ssh -o StrictHostKeyChecking=no {self.aws_config['ssh_user']}@{self.aws_config['ssh_host']} 'kubectl get pods -o name | grep {app_name}'"
            else:
                cmd = f"kubectl get pods -o name | grep {app_name}"
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                pods = []
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('pod/') and app_name in line:
                        pod_name = line.replace('pod/', '')
                        pods.append(pod_name)
                return pods[:1]  # Pegar apenas o primeiro pod por app
            
        except Exception as e:
            print(f"❌ Erro ao descobrir pods de {app_name}: {e}")
        
        return []
    
    def _calculate_mttr_averages(self) -> Dict:
        """Calcula médias dos tempos de recuperação."""
        print("\n📊 === CALCULANDO MÉDIAS MTTR ===")
        
        mttr_config = {
            'pods': {},
            'worker_node': {},
            'control_plane': {}
        }
        
        # Processar resultados
        for category, components in self.results.items():
            print(f"\n{category.upper()}:")
            
            for component, times in components.items():
                if times:
                    avg_time = statistics.mean(times)
                    mttr_config[category][component] = round(avg_time, 1)
                    
                    print(f"  {component}: {avg_time:.1f}s (média de {len(times)} medições)")
                    print(f"    📈 Min: {min(times):.1f}s, Max: {max(times):.1f}s")
                else:
                    print(f"  {component}: SEM DADOS")
        
        return mttr_config