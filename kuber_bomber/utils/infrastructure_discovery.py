"""
Infrastructure Discovery
========================

Descobre automaticamente a infraestrutura do cluster Kubernetes via kubectl
e gera a estrutura JSON de configuração com todos os componentes encontrados.
"""

import json
import subprocess
import sys
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import os


class InfrastructureDiscovery:
    """
    Classe responsável por descobrir automaticamente a infraestrutura
    do cluster Kubernetes e gerar configuração JSON estruturada.
    """
    
    def __init__(self, use_aws: bool = False, aws_config: Optional[Dict] = None):
        """
        Inicializa o descobridor de infraestrutura.
        
        Args:
            use_aws: Se deve usar conexão AWS via SSH
            aws_config: Configuração AWS (ip, ssh_key, user)
        """
        self.use_aws = use_aws
        self.aws_config = aws_config or {}
        self.discovered_components = {
            'pods': {},
            'worker_nodes': [],
            'control_plane': []
        }
        
        # MTTF padrão para componentes (em horas)
        self.default_mttf = {
            'pod': 100.0,
            'container': 150.0,
            'worker_node': 200.0,
            'wn_runtime': 300.0,
            'wn_proxy': 400.0,
            'wn_kubelet': 350.0,
            'control_plane': 500.0,
            'cp_apiserver': 600.0,
            'cp_manager': 550.0,
            'cp_scheduler': 580.0,
            'cp_etcd': 800.0
        }
        
        # MTTR padrão para componentes que precisam intervenção (em horas)
        self.default_mttr = {
            'worker_node': 400.0,
            'wn_runtime': 50.0,
            'wn_kubelet': 30.0,
            'cp_apiserver': 60.0,
            'cp_manager': 45.0,
            'cp_scheduler': 40.0,
            'cp_etcd': 120.0
        }
    
    def _run_kubectl_command(self, command: str) -> str:
        """
        Executa comando kubectl local ou via SSH (AWS).
        
        Args:
            command: Comando kubectl para executar
            
        Returns:
            Output do comando
        """
        try:
            if self.use_aws:
                # Para AWS, usar sudo para acessar kubectl
                ssh_cmd = f"ssh -i {self.aws_config.get('ssh_key', '~/.ssh/vockey.pem')} " \
                         f"-o StrictHostKeyChecking=no " \
                         f"{self.aws_config.get('ssh_user', 'ubuntu')}@{self.aws_config.get('ssh_host')} " \
                         f"'sudo {command}'"
                result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)
            else:
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"❌ Erro ao executar comando: {command}")
                print(f"❌ Erro: {result.stderr}")
                return ""
            
            return result.stdout.strip()
        
        except Exception as e:
            print(f"❌ Erro ao executar kubectl: {e}")
            return ""
    
    def discover_pods(self) -> Dict[str, List[str]]:
        """
        Descobre todos os pods de aplicação no cluster.
        
        Returns:
            Dict com aplicações e seus pods
        """
        print("🔍 Descobrindo pods de aplicação...")
        
        # Pegar todos os pods exceto sistema
        cmd = "kubectl get pods --all-namespaces -o json"
        output = self._run_kubectl_command(cmd)
        
        if not output:
            return {}
        
        try:
            pods_data = json.loads(output)
            pods_by_app = {}
            
            for pod in pods_data.get('items', []):
                namespace = pod.get('metadata', {}).get('namespace', '')
                pod_name = pod.get('metadata', {}).get('name', '')
                
                # Filtrar pods do sistema
                if namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue
                
                # Filtrar pods de sistema por padrão de nome
                if self._is_system_pod(pod_name):
                    continue
                
                # Extrair nome da aplicação (antes do primeiro hífen com hash)
                app_name = pod_name
                
                if app_name:
                    if app_name not in pods_by_app:
                        pods_by_app[app_name] = []
                    pods_by_app[app_name].append(pod_name)
            
            print(f"✅ Encontradas {len(pods_by_app)} aplicações:")
            for app, pods in pods_by_app.items():
                print(f"   • {app}: {len(pods)} pods")
            
            self.discovered_components['pods'] = pods_by_app
            return pods_by_app
            
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao parsear JSON dos pods: {e}")
            return {}
    
    def discover_worker_nodes(self) -> List[str]:
        """
        Descobre todos os worker nodes do cluster.
        
        Returns:
            Lista de nomes dos worker nodes
        """
        print("🔍 Descobrindo worker nodes...")
        
        cmd = "kubectl get nodes -o json"
        output = self._run_kubectl_command(cmd)
        
        if not output:
            return []
        
        try:
            nodes_data = json.loads(output)
            worker_nodes = []
            
            for node in nodes_data.get('items', []):
                node_name = node.get('metadata', {}).get('name', '')
                labels = node.get('metadata', {}).get('labels', {})
                
                # Identificar worker nodes (não são control plane)
                is_control_plane = 'node-role.kubernetes.io/control-plane' in labels or \
                                 'node-role.kubernetes.io/master' in labels
                
                if not is_control_plane and node_name:
                    worker_nodes.append(node_name)
            
            print(f"✅ Encontrados {len(worker_nodes)} worker nodes:")
            for node in worker_nodes:
                print(f"   • {node}")
            
            self.discovered_components['worker_nodes'] = worker_nodes
            return worker_nodes
            
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao parsear JSON dos nodes: {e}")
            return []
    
    def discover_control_plane(self) -> List[str]:
        """
        Descobre os control plane nodes do cluster.
        
        Returns:
            Lista de nomes dos control plane nodes
        """
        print("🔍 Descobrindo control plane nodes...")
        
        cmd = "kubectl get nodes -o json"
        output = self._run_kubectl_command(cmd)
        
        if not output:
            return []
        
        try:
            nodes_data = json.loads(output)
            control_plane_nodes = []
            
            for node in nodes_data.get('items', []):
                node_name = node.get('metadata', {}).get('name', '')
                labels = node.get('metadata', {}).get('labels', {})
                
                # Identificar control plane nodes
                is_control_plane = 'node-role.kubernetes.io/control-plane' in labels or \
                                 'node-role.kubernetes.io/master' in labels
                
                if is_control_plane and node_name:
                    control_plane_nodes.append(node_name)
            
            print(f"✅ Encontrados {len(control_plane_nodes)} control plane nodes:")
            for node in control_plane_nodes:
                print(f"   • {node}")
            
            self.discovered_components['control_plane'] = control_plane_nodes
            return control_plane_nodes
            
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao parsear JSON dos nodes: {e}")
            return []
    
    def _extract_app_name(self, pod_name: str) -> Optional[str]:
        """
        Extrai o nome da aplicação do nome do pod.
        
        Args:
            pod_name: Nome completo do pod
            
        Returns:
            Nome da aplicação ou None
        """
        # Padrões comuns: app-deployment-hash-pod ou app-hash-pod
        parts = pod_name.split('-')
        
        if len(parts) >= 2:
            # Remover sufixos de deployment e hash
            if len(parts) >= 3:
                # Verificar se os últimos dois são hash+pod
                if len(parts[-1]) <= 5 and len(parts[-2]) >= 8:
                    return '-'.join(parts[:-2])
            
            # Verificar se o último é pod ID
            if len(parts[-1]) <= 5:
                return '-'.join(parts[:-1])
            
            # Fallback: primeiras partes
            return '-'.join(parts[:2])
        
        return pod_name if pod_name else None
    
    def _is_system_pod(self, pod_name: str) -> bool:
        """
        Verifica se um pod é de sistema baseado em padrões de nome.
        
        Args:
            pod_name: Nome do pod
            
        Returns:
            True se for pod de sistema, False caso contrário
        """
        # Pods de sistema comuns
        system_prefixes = [
            'nginx-ingress-controller',  # Ingress controller
            'node-debugger',            # Debug nodes
            'coredns',                  # DNS
            'calico',                   # Network plugin
            'flannel',                  # Network plugin
            'weave',                    # Network plugin
            'kube-proxy',              # Kubernetes proxy
            'metrics-server',          # Metrics
            'dashboard',               # Dashboard
            'etcd',                    # etcd clusters
        ]
        
        # Verificar se o pod começa com algum prefixo de sistema
        for prefix in system_prefixes:
            if pod_name.startswith(prefix):
                return True
        
        return False
    
    def generate_config_structure(self, iterations: int = 5) -> Dict[str, Any]:
        """
        Gera a estrutura completa de configuração JSON.
        
        Args:
            iterations: Número de iterações para o experimento
            
        Returns:
            Estrutura completa de configuração
        """
        print("🏗️ Gerando estrutura de configuração (aninhada)...")

        # Descobrir toda a infraestrutura
        pods_by_app = self.discover_pods()
        worker_nodes = self.discover_worker_nodes()
        control_plane_nodes = self.discover_control_plane()

        # Estrutura base do config (conforme o template do usuário)
        config = {
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

        # Preencher experiment_config.applications e availability_criteria
        for app_name, pods in pods_by_app.items():
            for pod_name in pods:
                # print(f"   • Adicionando aplicação: {pod_name}")
                config["experiment_config"]["applications"][pod_name] = True
                # critério padrão: pelo menos 1 pod
                config["availability_criteria"][pod_name] = 1

        # Preencher experiment_config.worker_node (singular como no exemplo)
        for node_name in worker_nodes:
            config["experiment_config"]["worker_node"][node_name] = True

        # Preencher experiment_config.control_plane
        for cp_name in control_plane_nodes:
            config["experiment_config"]["control_plane"][cp_name] = True

        # Preencher mttf_config.pods (pods + containers juntos)
        for app_name, pods in pods_by_app.items():
            for pod_name in pods:
                config["mttf_config"]["pods"][pod_name] = self.default_mttf["pod"]
                config["mttf_config"]["pods"][f"container-{pod_name}"] = self.default_mttf["container"]

        # Preencher mttf_config.worker_node (nodes + componentes juntos)
        for node_name in worker_nodes:
            config["mttf_config"]["worker_node"][node_name] = self.default_mttf["worker_node"]
            config["mttf_config"]["worker_node"][f"wn_runtime-{node_name}"] = self.default_mttf["wn_runtime"]
            config["mttf_config"]["worker_node"][f"wn_proxy-{node_name}"] = self.default_mttf["wn_proxy"]
            config["mttf_config"]["worker_node"][f"wn_kubelet-{node_name}"] = self.default_mttf["wn_kubelet"]

        # Preencher mttf_config.control_plane (cp + componentes juntos)
        for cp_name in control_plane_nodes:
            config["mttf_config"]["control_plane"][cp_name] = self.default_mttf["control_plane"]
            config["mttf_config"]["control_plane"][f"cp_apiserver-{cp_name}"] = self.default_mttf["cp_apiserver"]
            config["mttf_config"]["control_plane"][f"cp_manager-{cp_name}"] = self.default_mttf["cp_manager"]
            config["mttf_config"]["control_plane"][f"cp_scheduler-{cp_name}"] = self.default_mttf["cp_scheduler"]
            config["mttf_config"]["control_plane"][f"cp_etcd-{cp_name}"] = self.default_mttf["cp_etcd"]

        # Preencher mttr_config (valores padrão por categoria)
        config["mttr_config"]["pods"] = {}  # pods têm self-healing, mttr = 0 geralmente
        config["mttr_config"]["worker_node"] = {
            "worker_node": self.default_mttr.get("worker_node", 400.0),
            "wn_runtime": self.default_mttr.get("wn_runtime", 50.0),
            "wn_kubelet": self.default_mttr.get("wn_kubelet", 30.0)
        }
        config["mttr_config"]["control_plane"] = {
            "cp_apiserver": self.default_mttr.get("cp_apiserver", 60.0),
            "cp_manager": self.default_mttr.get("cp_manager", 45.0),
            "cp_scheduler": self.default_mttr.get("cp_scheduler", 40.0),
            "cp_etcd": self.default_mttr.get("cp_etcd", 120.0)
        }

        print("✅ Estrutura de configuração gerada (aninhada)!")
        print(f"   • {len(pods_by_app)} aplicações")
        print(f"   • {sum(len(pods) for pods in pods_by_app.values())} pods total")
        print(f"   • {len(worker_nodes)} worker nodes")
        print(f"   • {len(control_plane_nodes)} control plane nodes")

        return config
    
    def save_config(self, config: Dict[str, Any], filepath: Optional[str] = None) -> str:
        """
        Salva a configuração em arquivo JSON.
        
        Args:
            config: Configuração para salvar
            filepath: Caminho do arquivo (opcional)
            
        Returns:
            Caminho do arquivo salvo
        """
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"config_generated_{timestamp}.json"
        
        # Garantir que o diretório existe
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Configuração salva em: {filepath}")
        return filepath
    
    def discover_and_generate_config(self, iterations: int = 5, 
                                   output_file: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        """
        Processo completo: descobrir infraestrutura e gerar configuração.
        
        Args:
            iterations: Número de iterações
            output_file: Arquivo de saída (opcional)
            
        Returns:
            Tuple com (config_dict, filepath)
        """
        print("🚀 Iniciando descoberta completa da infraestrutura...")
        print()
        
        if self.use_aws:
            print("☁️ Modo AWS ativado")
            print(f"🌐 Conectando em: {self.aws_config.get('ssh_host', 'N/A')}")
            print()
        
        # Gerar configuração
        config = self.generate_config_structure(iterations)
        
        # Salvar arquivo
        if output_file is None:
            output_file = os.getcwd() + "/kuber_bomber/configs/config_simples_used.json"
        
        filepath = self.save_config(config, output_file)
        
        print()
        print("🎉 Descoberta e geração de configuração concluída!")
        
        return config, filepath


def load_aws_config(config_file: str = "aws_config.json") -> Dict[str, Any]:
    """
    Carrega configuração AWS de arquivo separado.
    
    Args:
        config_file: Caminho para o arquivo de configuração AWS
        
    Returns:
        Configuração AWS ou dicionário vazio
    """
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Erro ao carregar configuração AWS: {e}")
    
    return {}


def create_aws_config_template(filepath: str = "aws_config.json"):
    """
    Cria template de configuração AWS.
    
    Args:
        filepath: Caminho para criar o template
    """
    template = {
        "ssh_host": "SEU_IP_AWS_AQUI",
        "ssh_key": "~/.ssh/vockey.pem", 
        "ssh_user": "ubuntu",
        "description": "⚠️ EDITE ssh_host com seu IP AWS real! Arquivo usado por TODOS os componentes."
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
    
    print(f"📝 Template AWS criado em: {filepath}")
    print("✏️ Edite o arquivo com suas configurações AWS")


if __name__ == "__main__":
    # Exemplo de uso
    
    # Criar template AWS se não existir
    if not os.path.exists("aws_config.json"):
        create_aws_config_template()
    
    # Modo local
    print("=== MODO LOCAL ===")
    discovery = InfrastructureDiscovery()
    config, filepath = discovery.discover_and_generate_config()
    
    print("\n" + "="*50)
    
    # Modo AWS (se configurado)
    aws_config = load_aws_config()
    if aws_config.get("aws_public_ip"):
        print("=== MODO AWS ===")
        discovery_aws = InfrastructureDiscovery(
            use_aws=True, 
            aws_config={
                'ssh_host': aws_config['aws_public_ip'],
                'ssh_key': aws_config['aws_ssh_key_path'],
                'ssh_user': aws_config['aws_ssh_user']
            }
        )
        config_aws, filepath_aws = discovery_aws.discover_and_generate_config(
            output_file="config_simples_aws.json"
        )