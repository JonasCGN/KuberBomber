"""
Configurações
============

Configurações gerais do framework de confiabilidade com variável global
para timeout de recuperação personalizável.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ReliabilityConfig:
    """
    Configurações para testes de confiabilidade.
    """
    # Configurações de simulação
    time_acceleration: int = 10000  # Aceleração temporal (10000x)
    default_mtbf_hours: float = 8760.0  # 1 ano em horas
    default_mttr_minutes: float = 30.0  # Tempo padrão de recuperação
    
    # Configurações de Kubernetes
    namespace: str = "default"
    context: str = "local-k8s"
    
    # Serviços para monitoramento
    services: Optional[Dict[str, Dict[str, Any]]] = None
    
    # Configurações de monitoramento
    health_check_interval: float = 2.0  # segundos entre verificações
    max_health_check_attempts: int = 150  # máximo de tentativas
    
    # ⭐ VARIÁVEL GLOBAL DE TIMEOUT PERSONALIZÁVEL ⭐
    # Esta é a variável que você pode alterar para controlar o timeout
    current_recovery_timeout: int = 600  # TIMEOUT PADRÃO (5 minutos)
    
    # Opções predefinidas de timeout
    recovery_timeout_quick: int = 60      # 1 minuto - testes rápidos
    recovery_timeout_short: int = 120     # 2 minutos - casos rápidos
    recovery_timeout_medium: int = 300    # 5 minutos - casos normais  
    recovery_timeout_long: int = 600      # 10 minutos - casos complexos
    recovery_timeout_extended: int = 1200 # 20 minutos - casos críticos
    
    # Configurações de relatórios em tempo real
    enable_realtime_csv: bool = True      # Ativar CSV em tempo real
    reports_dir: str = "."
    csv_filename_pattern: str = "reliability_test_{timestamp}.csv"
    
    # Configurações de logs
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Configurações de CLI
    default_iterations: int = 30
    default_interval: int = 60
    default_scenario: str = "pod_failure"
    
    def __post_init__(self):
        """Inicialização pós-criação do objeto."""
        # Configurar serviços padrão se não especificados
        if self.services is None:
            # URLs corretas usando LoadBalancer (MetalLB)
            self.services = {
                'foo': {
                    'loadbalancer_url': 'http://172.18.255.201/foo',
                    'ingress_url': 'http://172.18.255.200/foo',
                    'port': 8080, 
                    'endpoint': '/foo'
                },
                'bar': {
                    'loadbalancer_url': 'http://172.18.255.202:81/bar',
                    'ingress_url': 'http://172.18.255.200/bar',
                    'port': 8081, 
                    'endpoint': '/bar'
                },
                'test': {
                    'loadbalancer_url': 'http://172.18.255.203:82/test',
                    'ingress_url': 'http://172.18.255.200/test',
                    'port': 8082, 
                    'endpoint': '/test'
                }
            }
        
        # Criar diretório de relatórios se não existir
        os.makedirs(self.reports_dir, exist_ok=True)


class ConfigManager:
    """
    Gerenciador de configurações do framework.
    
    Carrega configurações de arquivos, variáveis de ambiente
    e permite sobreposição de valores dinamicamente.
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Inicializa o gerenciador de configurações.
        
        Args:
            config_file: Caminho para arquivo de configuração (opcional)
        """
        self.config = ReliabilityConfig()
        self.config_file = config_file
        self._load_from_environment()
        
        if config_file and os.path.exists(config_file):
            self._load_from_file(config_file)
    
    def _load_from_environment(self):
        """Carrega configurações de variáveis de ambiente."""
        env_mappings = {
            'RELIABILITY_TIME_ACCELERATION': ('time_acceleration', int),
            'RELIABILITY_MTBF_HOURS': ('default_mtbf_hours', float),
            'RELIABILITY_MTTR_MINUTES': ('default_mttr_minutes', float),
            'RELIABILITY_NAMESPACE': ('namespace', str),
            'RELIABILITY_CONTEXT': ('context', str),
            'RELIABILITY_HEALTH_INTERVAL': ('health_check_interval', float),
            'RELIABILITY_MAX_ATTEMPTS': ('max_health_check_attempts', int),
            
            # ⭐ VARIÁVEL DE AMBIENTE PARA TIMEOUT GLOBAL ⭐
            'RELIABILITY_RECOVERY_TIMEOUT': ('current_recovery_timeout', int),
            
            'RELIABILITY_TIMEOUT_QUICK': ('recovery_timeout_quick', int),
            'RELIABILITY_TIMEOUT_SHORT': ('recovery_timeout_short', int),
            'RELIABILITY_TIMEOUT_MEDIUM': ('recovery_timeout_medium', int),
            'RELIABILITY_TIMEOUT_LONG': ('recovery_timeout_long', int),
            'RELIABILITY_TIMEOUT_EXTENDED': ('recovery_timeout_extended', int),
            'RELIABILITY_ENABLE_REALTIME_CSV': ('enable_realtime_csv', lambda x: x.lower() == 'true'),
            'RELIABILITY_REPORTS_DIR': ('reports_dir', str),
            'RELIABILITY_LOG_LEVEL': ('log_level', str),
            'RELIABILITY_DEFAULT_ITERATIONS': ('default_iterations', int),
            'RELIABILITY_DEFAULT_INTERVAL': ('default_interval', int),
            'RELIABILITY_DEFAULT_SCENARIO': ('default_scenario', str),
        }
        
        for env_var, (attr_name, type_func) in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    setattr(self.config, attr_name, type_func(env_value))
                except (ValueError, TypeError) as e:
                    print(f"⚠️ Erro ao converter variável de ambiente {env_var}: {e}")
    
    def _load_from_file(self, config_file: str):
        """
        Carrega configurações de arquivo.
        
        Args:
            config_file: Caminho para arquivo de configuração
        """
        try:
            import json
            with open(config_file, 'r') as f:
                file_config = json.load(f)
            
            for key, value in file_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    
        except Exception as e:
            print(f"⚠️ Erro ao carregar arquivo de configuração {config_file}: {e}")
    
    def get_config(self) -> ReliabilityConfig:
        """
        Retorna configuração atual.
        
        Returns:
            Objeto de configuração
        """
        return self.config
    
    def update_config(self, **kwargs):
        """
        Atualiza configurações dinamicamente.
        
        Args:
            **kwargs: Pares chave-valor para atualizar
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                print(f"✅ Configuração '{key}' atualizada para: {value}")
            else:
                print(f"⚠️ Configuração '{key}' não reconhecida")
    
    def set_recovery_timeout(self, timeout_type_or_value):
        """
        ⭐ FUNÇÃO PRINCIPAL PARA ALTERAR TIMEOUT DE RECUPERAÇÃO ⭐
        
        Define o timeout de recuperação baseado em tipo predefinido ou valor personalizado.
        
        Args:
            timeout_type_or_value: Tipo de timeout predefinido ou valor em segundos
                                 Tipos: 'quick', 'short', 'medium', 'long', 'extended'
                                 Ou um número (int/str) em segundos
        
        Exemplos:
            set_recovery_timeout('short')    # 120 segundos
            set_recovery_timeout('medium')   # 300 segundos  
            set_recovery_timeout(450)        # 450 segundos personalizado
            set_recovery_timeout('600')      # 600 segundos como string
        """
        timeout_map = {
            'quick': self.config.recovery_timeout_quick,
            'short': self.config.recovery_timeout_short,
            'medium': self.config.recovery_timeout_medium,
            'long': self.config.recovery_timeout_long,
            'extended': self.config.recovery_timeout_extended
        }
        
        if str(timeout_type_or_value).lower() in timeout_map:
            self.config.current_recovery_timeout = timeout_map[str(timeout_type_or_value).lower()]
            print(f"⏱️ Timeout definido para {timeout_type_or_value}: {self.config.current_recovery_timeout}s")
        else:
            try:
                # Tentar converter para inteiro
                timeout_value = int(timeout_type_or_value)
                if timeout_value <= 0:
                    print("❌ Timeout deve ser maior que 0")
                    return
                    
                self.config.current_recovery_timeout = timeout_value
                print(f"⏱️ Timeout personalizado definido: {timeout_value}s")
            except (ValueError, TypeError):
                print(f"❌ Tipo de timeout inválido: {timeout_type_or_value}")
                print("💡 Use: 'quick' (60s), 'short' (120s), 'medium' (300s), 'long' (600s), 'extended' (1200s)")
                print("    ou um valor em segundos (ex: 450)")
    
    def get_current_timeout(self) -> int:
        """
        Retorna o timeout atual configurado.
        
        Returns:
            Timeout em segundos
        """
        return self.config.current_recovery_timeout
    
    def list_timeout_options(self):
        """Lista opções de timeout disponíveis."""
        print("⏱️ Opções de Timeout Disponíveis:")
        print(f"  quick: {self.config.recovery_timeout_quick}s (1 min) - Testes rápidos")
        print(f"  short: {self.config.recovery_timeout_short}s (2 min) - Casos rápidos")
        print(f"  medium: {self.config.recovery_timeout_medium}s (5 min) - Casos normais")
        print(f"  long: {self.config.recovery_timeout_long}s (10 min) - Casos complexos")
        print(f"  extended: {self.config.recovery_timeout_extended}s (20 min) - Casos críticos")
        print(f"  Personalizado: Qualquer valor em segundos")
        print(f"")
        print(f"📊 Timeout Atual: {self.config.current_recovery_timeout}s")
    
    def save_config(self, output_file: str):
        """
        Salva configurações atuais em arquivo.
        
        Args:
            output_file: Caminho para salvar configurações
        """
        try:
            import json
            from dataclasses import asdict
            
            config_dict = asdict(self.config)
            
            with open(output_file, 'w') as f:
                json.dump(config_dict, f, indent=2)
            
            print(f"✅ Configurações salvas em {output_file}")
            
        except Exception as e:
            print(f"❌ Erro ao salvar configurações: {e}")
    
    def print_config(self):
        """Imprime configurações atuais."""
        print("📋 Configurações atuais:")
        print("=" * 40)
        
        sections = {
            "Simulação": [
                ("time_acceleration", "Aceleração temporal"),
                ("default_mtbf_hours", "MTBF padrão (horas)"),
                ("default_mttr_minutes", "MTTR padrão (minutos)"),
            ],
            "Kubernetes": [
                ("namespace", "Namespace"),
                ("context", "Contexto kubectl"),
            ],
            "Monitoramento": [
                ("health_check_interval", "Intervalo de verificação (s)"),
                ("max_health_check_attempts", "Máximo de tentativas"),
                ("current_recovery_timeout", "⭐ Timeout atual (s)"),
            ],
            "Timeouts Disponíveis": [
                ("recovery_timeout_quick", "Timeout rápido (s)"),
                ("recovery_timeout_short", "Timeout curto (s)"),
                ("recovery_timeout_medium", "Timeout médio (s)"),
                ("recovery_timeout_long", "Timeout longo (s)"),
                ("recovery_timeout_extended", "Timeout estendido (s)"),
            ],
            "Relatórios": [
                ("enable_realtime_csv", "CSV em tempo real"),
                ("reports_dir", "Diretório de relatórios"),
                ("csv_filename_pattern", "Padrão de nome CSV"),
            ],
            "CLI": [
                ("default_iterations", "Iterações padrão"),
                ("default_interval", "Intervalo padrão (s)"),
                ("default_scenario", "Cenário padrão"),
            ]
        }
        
        for section_name, attributes in sections.items():
            print(f"\n🔧 {section_name}:")
            for attr_name, display_name in attributes:
                value = getattr(self.config, attr_name)
                if attr_name == "current_recovery_timeout":
                    print(f"  ⭐ {display_name}: {value}")
                else:
                    print(f"  {display_name}: {value}")


# ⭐ CONFIGURAÇÃO GLOBAL PADRÃO ⭐
# Esta é a instância global que pode ser acessada de qualquer lugar
DEFAULT_CONFIG = ConfigManager()

def get_config() -> ReliabilityConfig:
    """
    Retorna configuração global padrão.
    
    Returns:
        Configuração padrão
    """
    return DEFAULT_CONFIG.get_config()

def update_global_config(**kwargs):
    """
    Atualiza configuração global.
    
    Args:
        **kwargs: Configurações para atualizar
    """
    DEFAULT_CONFIG.update_config(**kwargs)

def set_global_recovery_timeout(timeout_type_or_value):
    """
    ⭐ FUNÇÃO GLOBAL PARA ALTERAR TIMEOUT ⭐
    
    Função conveniente para alterar o timeout globalmente.
    
    Args:
        timeout_type_or_value: Tipo ou valor do timeout
        
    Exemplos:
        set_global_recovery_timeout('short')  # 120s
        set_global_recovery_timeout(450)      # 450s
    """
    DEFAULT_CONFIG.set_recovery_timeout(timeout_type_or_value)

def get_current_recovery_timeout() -> int:
    """
    ⭐ FUNÇÃO GLOBAL PARA OBTER TIMEOUT ATUAL ⭐
    
    Returns:
        Timeout atual em segundos
    """
    return DEFAULT_CONFIG.get_current_timeout()

def list_timeout_options():
    """Lista opções de timeout disponíveis globalmente."""
    DEFAULT_CONFIG.list_timeout_options()