"""
Configuração Simples para Simulação de Disponibilidade
=====================================================

Classe para carregar configuração JSON gerada automaticamente
pela descoberta de infraestrutura do cluster Kubernetes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Any
import json
import os
from datetime import datetime


class ConfigPresets:
    """Presets de configuração padrão."""
    
    @staticmethod
    def generate_default_config() -> Dict:
        """Gera configuração padrão."""
        return {
            "experiment_config": {
                "applications": {},
                "worker_node": {},
                "control_plane": {}
            },
            "mttf_config": {
                "pods": {},
                "worker_node": {},
                "control_plane": {}
            },
            "mttr_config": {
                "pods": {},
                "worker_node": {},
                "control_plane": {}
            },
            "availability_criteria": {}
        }


@dataclass
class ConfigSimples:
    """
    Configuração simplificada que carrega JSON gerado automaticamente
    pela descoberta de infraestrutura do cluster Kubernetes.
    
    Nova arquitetura:
    - Configuração centralizada em JSON
    - Descoberta automática via kubectl
    - MTTF/MTTR por componente específico
    - Suporte a AWS via arquivo separado
    """
    
    # Configuração carregada do JSON
    config_data: Dict[str, Any] = field(default_factory=dict)
    
    # Metadados
    timestamp: Optional[str] = None
    duration: int = 1000
    iterations: int = 5
    
    # ===== CONFIGURAÇÃO AWS (carregada OBRIGATORIAMENTE de aws_config.json) =====
    aws_enabled: bool = False
    aws_config: Optional[Dict] = None  # Será carregado do arquivo aws_config.json
    
    def __post_init__(self):
        """Inicialização automática."""
        if self.config_data:
            self._load_from_dict(self.config_data)
    
    @classmethod
    def load_from_json(cls, filepath: str) -> 'ConfigSimples':
        """
        Carrega configuração de arquivo JSON gerado pela descoberta.
        
        Args:
            filepath: Caminho para o arquivo JSON
            
        Returns:
            Instância configurada
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            config = cls(config_data=data)
            print(f"✅ Configuração carregada de: {filepath}")
            return config
            
        except FileNotFoundError:
            print(f"❌ Arquivo não encontrado: {filepath}")
            return cls()
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao decodificar JSON: {e}")
            return cls()
    
    @classmethod
    def load_aws_config(cls, aws_config_file: str = "aws_config.json") -> Dict[str, Any]:
        """
        Carrega configuração AWS de arquivo separado.
        
        Args:
            aws_config_file: Caminho para arquivo AWS
            
        Returns:
            Configuração AWS
        """
        try:
            if os.path.exists(aws_config_file):
                with open(aws_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Erro ao carregar AWS config: {e}")
        
        return {}
    
    def configure_aws(self, aws_config_file: str = "aws_config.json"):
        """
        Configura parâmetros AWS a partir de arquivo.
        
        Args:
            aws_config_file: Caminho para arquivo de configuração AWS
        """
        aws_config = self.load_aws_config(aws_config_file)
        
        if aws_config:
            self.aws_enabled = True
            self.aws_public_ip = aws_config.get('ssh_host', '')
            self.aws_ssh_key_path = aws_config.get('ssh_key', '~/.ssh/vockey.pem')
            self.aws_ssh_user = aws_config.get('ssh_user', 'ubuntu')
            
            print(f"✅ AWS configurado: {self.aws_ssh_user}@{self.aws_public_ip}")
        else:
            print("⚠️ Configuração AWS não encontrada")
    
    def _load_from_dict(self, data: Dict[str, Any]):
        """Carrega dados do dicionário JSON."""
        self.timestamp = data.get('timestamp')
        self.duration = data.get('duration', 1000)
        self.iterations = data.get('iterations', 5)
        # Armazenar todo o payload para uso posterior
        self.config_data = data
        # Garantir chaves aninhadas mínimas para compatibilidade
        self.config_data.setdefault('experiment_config', {})
        exp = self.config_data['experiment_config']
        exp.setdefault('applications', {})
        # Suporte tanto worker_nodes quanto worker_node (nova estrutura)
        exp.setdefault('worker_nodes', {})
        exp.setdefault('worker_node', {})
        exp.setdefault('control_plane', {})

        self.config_data.setdefault('mttf_config', {})
        # If mttf_config is flat (old format), keep as-is; if nested, ensure subkeys
        m = self.config_data['mttf_config']
        if isinstance(m, dict):
            # detect nested structure
            if any(k in m for k in ('pods', 'containers', 'worker_nodes', 'worker_node', 'worker_components', 'control_plane')):
                # ensure nested keys exist
                m.setdefault('pods', {})
                m.setdefault('containers', {})
                m.setdefault('worker_nodes', {})
                m.setdefault('worker_node', {})  # nova estrutura
                m.setdefault('worker_components', {})
                m.setdefault('control_plane', {})
                m.setdefault('control_components', {})

        self.config_data.setdefault('mttr_config', {})
        mt = self.config_data['mttr_config']
        if isinstance(mt, dict):
            mt.setdefault('worker_nodes', {})
            mt.setdefault('worker_components', {})
            mt.setdefault('control_components', {})
    
    def get_experiment_config(self) -> Dict[str, Any]:
        """Retorna configuração do experimento."""
        return self.config_data.get('experiment_config', {})
    
    def get_applications(self) -> List[str]:
        """Retorna lista de aplicações configuradas."""
        apps = self.get_experiment_config().get('applications', {})
        return [app for app, enabled in apps.items() if enabled]
    
    def get_mttf_config(self) -> Dict[str, float]:
        """Retorna configuração MTTF."""
        return self.config_data.get('mttf_config', {})
    
    def get_mttr_config(self) -> Dict[str, float]:
        """Retorna configuração MTTR."""
        return self.config_data.get('mttr_config', {})

    def _flatten_mttf(self) -> Dict[str, float]:
        """
        Retorna uma versão 'achatada' do mttf_config, suportando formatos
        antigos (flat) e novos (aninhados).
        """
        flat: Dict[str, float] = {}
        m = self.get_mttf_config()
        if not isinstance(m, dict):
            return flat

        # Caso já seja formato antigo (chaves como 'pod-...')
        simple_keys = [k for k in m.keys() if not isinstance(m.get(k), dict)]
        if simple_keys and not any(k in m for k in ('pods', 'containers')):
            # assume flat format
            for k, v in m.items():
                if isinstance(v, (int, float)):
                    flat[k] = v
            return flat

        # Caso aninhado - suportar tanto estrutura antiga quanto nova
        
        # Pods (podem estar em 'pods' ou misturados com containers)
        pods_map = m.get('pods')
        if isinstance(pods_map, dict):
            for pod_name, v in pods_map.items():
                # Se começa com 'container-', trata como container
                if pod_name.startswith('container-'):
                    flat[pod_name] = v  # já tem prefixo 'container-'
                else:
                    flat[f"pod-{pod_name}"] = v

        # Containers (estrutura antiga - separada)
        cont_map = m.get('containers')
        if isinstance(cont_map, dict):
            for cont_name, v in cont_map.items():
                flat[f"container-{cont_name}"] = v

        # Worker nodes - tanto 'worker_nodes' (antiga) quanto 'worker_node' (nova)
        for wn_key in ['worker_nodes', 'worker_node']:
            wn_map = m.get(wn_key)
            if isinstance(wn_map, dict):
                for node_name, v in wn_map.items():
                    # Se começa com prefixo de componente, manter como está
                    if any(node_name.startswith(prefix) for prefix in ['wn_runtime-', 'wn_proxy-', 'wn_kubelet-']):
                        flat[node_name] = v
                    else:
                        flat[f"worker_node-{node_name}"] = v

        # Worker components (estrutura antiga - separada)
        wn_comp_map = m.get('worker_components')
        if isinstance(wn_comp_map, dict):
            for node_name, comps in wn_comp_map.items():
                if isinstance(comps, dict):
                    for comp_key, comp_v in comps.items():
                        flat[f"{comp_key}-{node_name}"] = comp_v

        cp_map = m.get('control_plane')
        if isinstance(cp_map, dict):
            for cp_name, v in cp_map.items():
                # Se começa com prefixo de componente, manter como está
                if any(cp_name.startswith(prefix) for prefix in ['cp_apiserver-', 'cp_manager-', 'cp_scheduler-', 'cp_etcd-']):
                    flat[cp_name] = v
                else:
                    flat[f"control_plane-{cp_name}"] = v

        # Control components (estrutura antiga - separada)
        cp_comp_map = m.get('control_components')
        if isinstance(cp_comp_map, dict):
            for cp_name, comps in cp_comp_map.items():
                if isinstance(comps, dict):
                    for comp_key, comp_v in comps.items():
                        flat[f"{comp_key}-{cp_name}"] = comp_v

        return flat
    
    def get_availability_criteria(self) -> Dict[str, int]:
        """Retorna critérios de disponibilidade."""
        return self.config_data.get('availability_criteria', {})
    
    def get_mttf(self, component_name: str) -> float:
        """
        Retorna MTTF para um componente específico.
        
        Args:
            component_name: Nome exato do componente no JSON
        Returns:
            MTTF em horas
        """
        flat = self._flatten_mttf()
        return flat.get(component_name, 0.0)
    
    def get_mttr(self, component_name: str) -> float:
        """
        Retorna MTTR para um componente específico.
        
        Args:
            component_name: Nome exato do componente no JSON
        Returns:
            MTTR em horas
        """
        # Flatten mttr_config for common component keys
        mt = self.get_mttr_config()
        if not isinstance(mt, dict):
            return 0.0

        # Direct flat lookup
        if component_name in mt and isinstance(mt[component_name], (int, float)):
            return mt[component_name]

        # Check nested structures - tanto antiga quanto nova estrutura
        
        # Nova estrutura: worker_node: { "wn_runtime": 50.0, "worker_node": 400.0 }
        # Mapear componentes específicos para valores genéricos
        for wn_key in ['worker_node', 'worker_nodes']:
            wn_store = mt.get(wn_key)
            if isinstance(wn_store, dict):
                # Busca direta primeiro
                if component_name in wn_store:
                    val = wn_store[component_name]
                    if isinstance(val, (int, float)):
                        return val
                
                # Mapear componente específico para tipo genérico
                # ex: "wn_runtime-worker-node-1" -> "wn_runtime"
                if '-' in component_name:
                    comp_type = component_name.split('-')[0]
                    if comp_type in wn_store:
                        val = wn_store[comp_type]
                        if isinstance(val, (int, float)):
                            return val

        # Control plane: similar
        cp_store = mt.get('control_plane')
        if isinstance(cp_store, dict):
            # Busca direta primeiro
            if component_name in cp_store:
                val = cp_store[component_name]
                if isinstance(val, (int, float)):
                    return val
            
            # Mapear componente específico para tipo genérico
            if '-' in component_name:
                comp_type = component_name.split('-')[0]
                if comp_type in cp_store:
                    val = cp_store[comp_type]
                    if isinstance(val, (int, float)):
                        return val

        # Estrutura antiga: worker_components: { node: { wn_runtime: val, ... } }
        if isinstance(mt.get('worker_components'), dict):
            # component_name expected like 'wn_runtime-<node>'
            if '-' in component_name:
                key, node = component_name.split('-', 1)
                comp_store = mt.get('worker_components')
                if isinstance(comp_store, dict):
                    comp_map = comp_store.get(node, {})
                    if isinstance(comp_map, dict) and key in comp_map:
                        return comp_map[key]

        # control_components similar
        if isinstance(mt.get('control_components'), dict):
            if '-' in component_name:
                key, node = component_name.split('-', 1)
                comp_store = mt.get('control_components')
                if isinstance(comp_store, dict):
                    comp_map = comp_store.get(node, {})
                    if isinstance(comp_map, dict) and key in comp_map:
                        return comp_map[key]

        # fallback
        return 0.0
    
    def get_component_config(self) -> List:
        """
        Retorna configuração de componentes para o AvailabilitySimulator.
        
        Returns:
            List com componentes configurados baseados no JSON
        """
        from kuber_bomber.simulation.availability_simulator import Component
        
        components = []
        flat_mttf = self._flatten_mttf()

        exp = self.get_experiment_config()
        apps_enabled = exp.get('applications', {})
        # Suportar tanto worker_nodes quanto worker_node
        nodes_enabled = exp.get('worker_nodes', {})
        nodes_enabled.update(exp.get('worker_node', {}))  # merge nova estrutura
        cps_enabled = exp.get('control_plane', {})

        for comp_name, mttf_hours in flat_mttf.items():
            comp_type = self._extract_component_type(comp_name)

            # Filtrar por flags do experiment_config
            include = False
            if comp_type == 'pod':
                # extrair nome do pod sem prefixo
                pod_full = comp_name[len('pod-'):]
                # Verificar se o pod pertence a alguma aplicação habilitada
                for app_key, enabled in apps_enabled.items():
                    if not enabled:
                        continue
                    if pod_full.startswith(app_key):
                        include = True
                        break
            elif comp_type == 'container':
                pod_full = comp_name[len('container-'):]
                for app_key, enabled in apps_enabled.items():
                    if not enabled:
                        continue
                    if pod_full.startswith(app_key):
                        include = True
                        break
            elif comp_type == 'worker_node':
                node_name = comp_name[len('worker_node-'):]
                if nodes_enabled.get(node_name):
                    include = True
            elif comp_type in ('wn_runtime', 'wn_proxy', 'wn_kubelet'):
                # formato: wn_runtime-<node>
                node_name = comp_name.split('-', 1)[1] if '-' in comp_name else ''
                if nodes_enabled.get(node_name):
                    include = True
            elif comp_type == 'control_plane':
                cp_name = comp_name[len('control_plane-'):]
                if cps_enabled.get(cp_name):
                    include = True
            elif comp_type in ('cp_apiserver', 'cp_manager', 'cp_scheduler', 'cp_etcd'):
                cp_name = comp_name.split('-', 1)[1] if '-' in comp_name else ''
                if cps_enabled.get(cp_name):
                    include = True
            else:
                # unknown - by default include
                include = True

            if not include:
                continue

            # Extrair chave MTTF para mapear métodos de falha corretamente
            mttf_key = self._extract_mttf_key(comp_name, comp_type)
            
            # Configurar parent_component para containers
            parent_component = None
            if comp_type == 'container' and comp_name.startswith('container-'):
                # container-bar-app-775c8885f5-6wdlt -> bar-app-775c8885f5-6wdlt
                parent_component = comp_name[len('container-'):]

            component = Component(
                name=comp_name,
                component_type=comp_type,
                mttf_hours=mttf_hours,
                mttf_key=mttf_key,
                parent_component=parent_component
            )
            components.append(component)

        return components
    
    def _extract_component_type(self, component_name: str) -> str:
        """
        Extrai o tipo do componente do nome.
        
        Args:
            component_name: Nome do componente (ex: pod-bar-app-123)
            
        Returns:
            Tipo do componente (ex: pod)
        """
        if component_name.startswith('pod-'):
            return 'pod'
        elif component_name.startswith('container-'):
            return 'container'
        elif component_name.startswith('worker_node-'):
            return 'worker_node'
        elif component_name.startswith('wn_'):
            return component_name.split('-')[0]  # wn_runtime, wn_proxy, etc.
        elif component_name.startswith('control_plane-'):
            return 'control_plane'
        elif component_name.startswith('cp_'):
            return component_name.split('-')[0]  # cp_apiserver, cp_manager, etc.
        else:
            return 'unknown'
    
    def _extract_mttf_key(self, component_name: str, comp_type: str) -> str:
        """
        Extrai a chave MTTF para mapear métodos de falha corretamente.
        
        Args:
            component_name: Nome do componente (ex: wn_runtime-worker-node-1)
            comp_type: Tipo do componente (ex: wn_runtime)
            
        Returns:
            Chave MTTF (ex: wn_runtime, pod, etc.)
        """
        # Para componentes granulares, usar o tipo do componente
        if comp_type in ['wn_runtime', 'wn_proxy', 'wn_kubelet', 
                         'cp_apiserver', 'cp_manager', 'cp_scheduler', 'cp_etcd']:
            return comp_type
        
        # Para componentes principais, usar tipo base
        if comp_type == 'pod':
            return 'pod'
        elif comp_type == 'container':
            return 'container'
        elif comp_type == 'worker_node':
            return 'worker_node'
        elif comp_type == 'control_plane':
            return 'control_plane'
        
        return comp_type
    
    def save_config(self, filepath: Optional[str] = None) -> str:
        """Salva configuração atual."""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"config_simples_used_{timestamp}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.config_data, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def print_summary(self):
        """Imprime resumo da configuração carregada."""
        print("🔧 === CONFIGURAÇÃO CARREGADA DO JSON ===")
        
        if self.timestamp:
            print(f"📅 Timestamp: {self.timestamp}")
        
        print(f"⏱️ Duração: {self.duration}h")
        print(f"🔄 Iterações: {self.iterations}")
        
        # Configuração AWS
        if self.aws_enabled:
            print("\n☁️ === CONFIGURAÇÃO AWS ===")
            print(f"🌐 IP Público: {self.aws_public_ip}")
            print(f"🔑 Chave SSH: {self.aws_ssh_key_path}")
            print(f"👤 Usuário SSH: {self.aws_ssh_user}")
        
        # Aplicações
        apps = self.get_applications()
        print(f"\n📱 === APLICAÇÕES ({len(apps)}) ===")
        for app in apps:
            criteria = self.get_availability_criteria().get(app, 1)
            print(f"  • {app}: ≥{criteria} pod(s)")
        
        # Resumo de componentes
        mttf_config = self.get_mttf_config()
        mttr_config = self.get_mttr_config()
        
        print(f"\n⚙️ === COMPONENTES ===")
        print(f"📊 Total MTTF configurados: {len(mttf_config)}")
        print(f"🔧 Total MTTR configurados: {len(mttr_config)}")
        
        # Agrupar componentes por tipo
        components_by_type = {}
        for comp_name in mttf_config.keys():
            comp_type = self._extract_component_type(comp_name)
            if comp_type not in components_by_type:
                components_by_type[comp_type] = 0
            components_by_type[comp_type] += 1
        
        for comp_type, count in components_by_type.items():
            print(f"  • {comp_type}: {count} componentes")
    
    def get_aws_config(self) -> Dict[str, Any]:
        """Retorna configuração AWS para uso no reliability tester."""
        if not self.aws_enabled:
            return {}
        
        return {
            'ssh_host': self.aws_public_ip,
            'ssh_key': self.aws_ssh_key_path,
            'ssh_user': self.aws_ssh_user
        }


# Funções auxiliares para validação final
def _merge_aws_config(config_data: Dict, aws_config: Dict) -> Dict:
    """Mescla configuração AWS com config de descoberta."""
    merged = config_data.copy()
    if aws_config:
        merged['aws_config'] = aws_config
    return merged


if __name__ == "__main__":
    # Exemplo de uso da nova arquitetura
    
    # 1. Carregar de arquivo JSON existente
    config_file = "config_simples_used.json"
    if os.path.exists(config_file):
        config = ConfigSimples.load_from_json(config_file)
        config.configure_aws()  # Configurar AWS se disponível
        config.print_summary()
    else:
        # 2. Usar configuração padrão
        print("⚠️ Arquivo JSON não encontrado, usando configuração padrão")
        default_config = ConfigPresets.generate_default_config()
        config = ConfigSimples(config_data=default_config)
        config.print_summary()
    
    # 3. Salvar configuração usada
    saved_file = config.save_config()
    print(f"\n💾 Configuração salva: {saved_file}")
    
    # 4. Exemplo de configuração para simulador
    components = config.get_component_config()
    print(f"\n📋 {len(components)} componentes configurados para simulação")