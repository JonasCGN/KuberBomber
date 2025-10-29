"""
Configuração Simples para Simulação de Disponibilidade
=====================================================

Classe extremamente simplificada para configurar MTTF e MTTR
dos componentes para experimentos de 30 iterações.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
import json
import os
from datetime import datetime


@dataclass
class ConfigSimples:
    """
    Configuração simplificada para experimentos de disponibilidade.
    
    Configuração padrão:
    - 3 worker nodes com distribuição flexível de pods
    - 30 iterações 
    - Falhas aleatórias
    - MTTF e MTTR detalhados para todos os componentes Kubernetes
    """
    
    # Configuração flexível do cluster
    # Pode ser int (mesmo número para todos) ou Dict {worker_name: num_pods}
    worker_nodes_config: Union[int, Dict[str, int]] = field(default_factory=lambda: {
        'worker-1': 1,
        'worker-2': 3, 
        'worker-3': 2
    })
    iterations: int = 30
    
    # ===== CONFIGURAÇÃO DETALHADA MTTF/MTTR =====
    
    # MTTF (Mean Time To Failure) em horas para cada componente
    mttf_config: Dict[str, float] = field(default_factory=lambda: {
        # === PODS ===
        'pod': 100.0,                          # Pods de aplicação
        'container': 150.0,                    # Containers dentro dos pods
        
        # === WORKER NODES ===
        'worker_node': 200.0,                  # Worker node completo
        'wn_runtime': 300.0,                   # Container runtime (Docker/containerd)
        'wn_proxy': 400.0,                     # kube-proxy
        'wn_kubelet': 350.0,                   # kubelet
        
        # === CONTROL PLANE ===
        'control_plane': 500.0,                # Control plane completo
        'cp_apiserver': 600.0,                 # kube-apiserver
        'cp_manager': 550.0,                   # kube-controller-manager
        'cp_scheduler': 580.0,                 # kube-scheduler
        'cp_etcd': 800.0                       # etcd
    })
    
    # MTTR (Mean Time To Recovery) em horas para componentes que precisam intervenção
    mttr_config: Dict[str, float] = field(default_factory=lambda: {
        'worker_node': 400.0,                  # Shutdown/restart worker node
        'wn_runtime': 50.0,                    # Restart container runtime
        'wn_kubelet': 30.0,                    # Restart kubelet
        'cp_apiserver': 60.0,                  # Restart API server
        'cp_manager': 45.0,                    # Restart controller manager
        'cp_scheduler': 40.0,                  # Restart scheduler
        'cp_etcd': 120.0                       # Restore etcd
        # Nota: pods e containers têm self-healing automático
    })
    
    # Aplicações a serem monitoradas
    applications: List[str] = field(default_factory=lambda: ['bar-app', 'foo-app', 'test-app'])
    
    def __post_init__(self):
        """Inicialização automática."""
        # Converter worker_nodes_config para dict se for int
        if isinstance(self.worker_nodes_config, int):
            num_workers = self.worker_nodes_config
            self.worker_nodes_config = {
                f'worker-{i}': 3 for i in range(1, num_workers + 1)
            }
    
    def get_total_pods(self) -> int:
        """Retorna total de pods de aplicação."""
        if isinstance(self.worker_nodes_config, dict):
            return sum(self.worker_nodes_config.values())
        return 0
    
    def get_worker_nodes(self) -> List[str]:
        """Retorna lista de nomes dos worker nodes."""
        if isinstance(self.worker_nodes_config, dict):
            return list(self.worker_nodes_config.keys())
        return []
    
    def get_worker_count(self) -> int:
        """Retorna número total de worker nodes."""
        if isinstance(self.worker_nodes_config, dict):
            return len(self.worker_nodes_config)
        return 0
    
    def get_mttf(self, component_type: str) -> float:
        """
        Retorna MTTF para um tipo de componente.
        
        Args:
            component_type: Tipo do componente (pod, worker_node, etc.)
        Returns:
            MTTF em horas
        """
        return self.mttf_config.get(component_type, 0.0)
    
    def get_mttr(self, component_type: str) -> float:
        """
        Retorna MTTR para um tipo de componente.
        
        Args:
            component_type: Tipo do componente (worker_node, wn_runtime, etc.)
        Returns:
            MTTR em horas, 0.0 se self-healing
        """
        return self.mttr_config.get(component_type, 0.0)
    
    def set_mttf(self, component_type: str, hours: float):
        """
        Define MTTF para um tipo de componente.
        
        Args:
            component_type: Tipo do componente
            hours: MTTF em horas
        """
        self.mttf_config[component_type] = hours
    
    def set_mttr(self, component_type: str, hours: float):
        """
        Define MTTR para um tipo de componente.
        
        Args:
            component_type: Tipo do componente
            hours: MTTR em horas
        """
        self.mttr_config[component_type] = hours
    
    def get_component_config(self) -> List:
        """
        Retorna configuração de componentes para o AvailabilitySimulator.
        
        Returns:
            List com componentes configurados
        """
        from kuber_bomber.simulation.availability_simulator import Component
        
        components = []
        
        # Adicionar pods de aplicação com distribuição flexível
        if isinstance(self.worker_nodes_config, dict):
            for worker_name, pod_count in self.worker_nodes_config.items():
                for app in self.applications:
                    for pod_idx in range(pod_count):
                        component = Component(
                            name=f"{app}-pod-{pod_idx+1}-{worker_name}",
                            component_type="pod", 
                            mttf_hours=self.mttf_config['pod']
                        )
                        components.append(component)
        
        # Adicionar worker nodes
        if isinstance(self.worker_nodes_config, dict):
            for worker_name in self.worker_nodes_config.keys():
                component = Component(
                    name=worker_name,
                    component_type="node",
                    mttf_hours=self.mttf_config['worker_node']
                )
                components.append(component)
        
        # Adicionar componentes detalhados do worker node
        if isinstance(self.worker_nodes_config, dict):
            for worker_name in self.worker_nodes_config.keys():
                # Container runtime
                components.append(Component(
                    name=f"{worker_name}-runtime",
                    component_type="wn_runtime",
                    mttf_hours=self.mttf_config['wn_runtime']
                ))
                # kube-proxy
                components.append(Component(
                    name=f"{worker_name}-proxy",
                    component_type="wn_proxy", 
                    mttf_hours=self.mttf_config['wn_proxy']
                ))
                # kubelet
                components.append(Component(
                    name=f"{worker_name}-kubelet",
                    component_type="wn_kubelet",
                    mttf_hours=self.mttf_config['wn_kubelet']
                ))
        
        # Adicionar control plane
        component = Component(
            name="control-plane",
            component_type="control_plane",
            mttf_hours=self.mttf_config['control_plane']
        )
        components.append(component)
        
        # Adicionar componentes detalhados do control plane
        control_components = [
            ("cp-apiserver", "cp_apiserver", self.mttf_config['cp_apiserver']),
            ("cp-manager", "cp_manager", self.mttf_config['cp_manager']), 
            ("cp-scheduler", "cp_scheduler", self.mttf_config['cp_scheduler']),
            ("cp-etcd", "cp_etcd", self.mttf_config['cp_etcd'])
        ]
        
        for name, comp_type, mttf in control_components:
            component = Component(
                name=name,
                component_type=comp_type,
                mttf_hours=mttf
            )
            components.append(component)
        
        return components
    
    def get_availability_criteria(self) -> Dict[str, int]:
        """
        Retorna critérios de disponibilidade para cada aplicação.
        
        Por padrão, cada aplicação precisa de pelo menos 1 pod funcionando.
        """
        return {app: 1 for app in self.applications}
    
    def save_config(self, filepath: Optional[str] = None) -> str:
        """Salva configuração usada no experimento."""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"config_simples_{timestamp}.json"
        
        config_dict = {
            'timestamp': datetime.now().isoformat(),
            'cluster_config': {
                'worker_nodes_distribution': dict(self.worker_nodes_config) if isinstance(self.worker_nodes_config, dict) else {},
                'total_worker_nodes': self.get_worker_count(),
                'total_pods': self.get_total_pods()
            },
            'experiment_config': {
                'iterations': self.iterations,
                'applications': self.applications
            },
            'mttf_config': self.mttf_config,
            'mttr_config': self.mttr_config,
            'availability_criteria': self.get_availability_criteria()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def print_summary(self):
        """Imprime resumo da configuração."""
        print("🔧 === CONFIGURAÇÃO SIMPLES DETALHADA ===")
        print(f"📊 Cluster: {self.get_worker_count()} worker nodes com {self.get_total_pods()} pods total")
        print("   Distribuição de pods por worker:")
        if isinstance(self.worker_nodes_config, dict):
            for worker_name, pod_count in self.worker_nodes_config.items():
                print(f"   • {worker_name}: {pod_count} pods")
        print(f"🔄 Experimento: {self.iterations} iterações")
        print()
        print("⏱️ MTTF (Mean Time To Failure):")
        print(f"  📦 Pods: {self.mttf_config['pod']}h")
        print(f"  🐳 Containers: {self.mttf_config['container']}h") 
        print(f"  🖥️ Worker nodes: {self.mttf_config['worker_node']}h")
        print(f"     • Runtime: {self.mttf_config['wn_runtime']}h")
        print(f"     • Proxy: {self.mttf_config['wn_proxy']}h") 
        print(f"     • Kubelet: {self.mttf_config['wn_kubelet']}h")
        print(f"  🎛️ Control plane: {self.mttf_config['control_plane']}h")
        print(f"     • API Server: {self.mttf_config['cp_apiserver']}h")
        print(f"     • Manager: {self.mttf_config['cp_manager']}h")
        print(f"     • Scheduler: {self.mttf_config['cp_scheduler']}h")
        print(f"     • etcd: {self.mttf_config['cp_etcd']}h")
        print()
        print("🔧 MTTR (Mean Time To Recovery):")
        print(f"  🖥️ Worker nodes (shutdown): {self.mttr_config['worker_node']}h")
        print(f"  🐳 Runtime restart: {self.mttr_config['wn_runtime']}h")
        print(f"  🔧 Kubelet restart: {self.mttr_config['wn_kubelet']}h")
        print(f"  🎛️ API Server restart: {self.mttr_config['cp_apiserver']}h")
        print(f"  📋 Manager restart: {self.mttr_config['cp_manager']}h")
        print(f"  📅 Scheduler restart: {self.mttr_config['cp_scheduler']}h")
        print(f"  💾 etcd restore: {self.mttr_config['cp_etcd']}h")
        print(f"  📦 Pods/Containers: self-healing automático")
        print()
        print("🎯 Aplicações monitoradas:")
        for app in self.applications:
            print(f"  • {app}: ≥1 pod")


# Configurações predefinidas
class ConfigPresets:
    """Configurações predefinidas para diferentes cenários."""
    
    @staticmethod
    def padrao() -> ConfigSimples:
        """Configuração padrão."""
        return ConfigSimples()
    
    @staticmethod
    def teste_rapido() -> ConfigSimples:
        """Configuração para teste rápido."""
        config = ConfigSimples()
        config.iterations = 5
        # Atualizar MTTF para valores menores
        config.mttf_config.update({
            'pod': 10.0,
            'worker_node': 20.0,
            'control_plane': 50.0
        })
        return config
    
    @staticmethod
    def cluster_pequeno() -> ConfigSimples:
        """Configuração para cluster menor."""
        return ConfigSimples(
            worker_nodes_config={'worker-1': 2, 'worker-2': 2},
            applications=['test-app']
        )
    
    @staticmethod
    def foco_shutdown() -> ConfigSimples:
        """Configuração focada em shutdown de worker nodes."""
        config = ConfigSimples()
        # Atualizar MTTF/MTTR para foco em worker nodes
        config.mttf_config['worker_node'] = 50.0  # Falhas mais frequentes
        config.mttr_config['worker_node'] = 100.0  # MTTR menor para teste mais rápido
        return config
    
    @staticmethod
    def distribuicao_customizada() -> ConfigSimples:
        """Configuração com distribuição customizada de pods."""
        return ConfigSimples(
            worker_nodes_config={
                'worker-1': 1,  # 1 pod
                'worker-2': 3,  # 3 pods  
                'worker-3': 2,  # 2 pods
                'worker-4': 4   # 4 pods
            }
        )
    
    @staticmethod
    def cluster_grande() -> ConfigSimples:
        """Configuração para cluster maior."""
        config = {}
        for i in range(1, 6):  # 5 worker nodes
            config[f'worker-{i}'] = 3  # 3 pods cada
        
        return ConfigSimples(
            worker_nodes_config=config,
            iterations=50
        )


if __name__ == "__main__":
    # Exemplo de uso
    config = ConfigSimples()
    config.print_summary()
    
    # Salvar configuração
    config_file = config.save_config()
    print(f"\n💾 Configuração salva: {config_file}")
    
    # Exemplo de configuração para simulador
    components = config.get_component_config()
    print(f"\n📋 {len(components)} componentes configurados para simulação")