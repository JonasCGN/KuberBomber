# Chaos Engineering Framework para Kubernetes

Um framework completo de Chaos Engineering em Python para testes de resiliência em clusters Kubernetes, incluindo **Simulador de Confiabilidade** para pesquisa acadêmica.

## 🎯 Visão Geral

Este framework implementa técnicas avançadas de chaos engineering, permitindo testar a resiliência de aplicações Kubernetes através de:

- **Falhas em Pods**: Delete, kill, limitação de recursos, crashloop
- **Falhas em Processos**: Kill, stress de CPU/memória/I/O  
- **Falhas em Nós**: Drain, cordon, reboot, partição de rede, preenchimento de disco
- **Cenários Avançados**: Falhas em cascata, rolling restart, testes de blast radius
- **🔬 Simulador de Confiabilidade**: Métricas MTTF/MTBF/MTTR para análise acadêmica
- **Monitoramento**: Coleta de métricas de recuperação e saúde do sistema
- **Visualização**: Gráficos interativos de tempo de recuperação e dashboards

## 🆕 **NOVO: Simulador de Confiabilidade**

**Funcionalidade específica para pesquisa acadêmica** com:

- ⏱️ **Escala temporal acelerada**: 1h real = 10.000h simuladas
- 📊 **Métricas padrão**: MTTF, MTBF, MTTR conforme literatura
- 📋 **Logging CSV**: Dados estruturados para análise estatística
- 🔬 **Kill específico**: Mata aplicações em pods (não delete)
- 🔄 **Scheduler automático**: Falhas baseadas em distribuições estatísticas
- 📈 **Análise integrada**: Relatórios e visualizações automáticas

### Uso Rápido do Simulador

```bash
# Teste rápido (3 minutos reais = 1000h simuladas)
python chaos_cli.py reliability test --preset quick

# Simulação customizada
python chaos_cli.py reliability start --duration 1.0 --acceleration 10000.0

# Análise de resultados
python chaos_cli.py reliability analyze --csv-path simulation.csv
```

📖 **[Guia Completo do Simulador](RELIABILITY_SIMULATOR_GUIDE.md)**

## 🏗️ Arquitetura

O framework segue uma arquitetura modular e desacoplada:

```
├── base.py                           # Classes abstratas e tipos base
├── pod_injector.py                  # Injeção de falhas em pods
├── process_injector.py              # Injeção de falhas em processos
├── node_injector.py                 # Injeção de falhas em nós
├── system_monitor.py                # Monitoramento do sistema
├── metrics_collector.py             # Coleta e persistência de métricas
├── visualization.py                 # Geração de gráficos e dashboards
├── advanced_scenarios.py            # Cenários complexos de chaos
├── simple_reliability_simulator.py  # 🔬 Simulador de confiabilidade para pesquisa
├── chaos_cli.py                     # Interface de linha de comando
├── main.py                          # Ponto de entrada principal
├── requirements.txt                 # Dependências
├── README.md                        # Documentação principal
└── RELIABILITY_SIMULATOR_GUIDE.md   # 📖 Guia do simulador acadêmico
```

## 📋 Pré-requisitos

- Python 3.8+
- Acesso a cluster Kubernetes (kubeconfig configurado)
- Dependências listadas em `requirements.txt`

### Para AWS (opcional):
- Credenciais AWS configuradas
- Permissões EC2 para reboot/shutdown de instâncias

### Para SSH (opcional):
- Acesso SSH aos nós do cluster
- Chaves SSH configuradas

## 🚀 Instalação

1. **Clone ou baixe os arquivos do framework**

2. **Instale as dependências:**
```bash
pip install -r requirements.txt
```

3. **Configure o acesso ao Kubernetes:**
```bash
# Verifique se kubectl está configurado
kubectl get nodes

# Ou configure o kubeconfig explicitamente
export KUBECONFIG=/path/to/your/kubeconfig
```

4. **Configure credenciais AWS (opcional):**
```bash
aws configure
# OU
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-west-2
```

## 💻 Uso Básico

### CLI Interativo

```bash
# Executa interface CLI completa
python main.py

# Ou usando o CLI diretamente
python chaos_cli.py --help
```

### Exemplos de Comandos

```bash
# Falhas em Pods
python chaos_cli.py pod delete my-app-pod --namespace default
python chaos_cli.py pod limit my-app-pod --cpu 100m --memory 128Mi

# Falhas em Nós  
python chaos_cli.py node drain worker-node-1
python chaos_cli.py node reboot worker-node-1 --confirm

# Falhas em Processos
python chaos_cli.py process kill 1234
python chaos_cli.py process stress-cpu 1 --duration 300 --percent 80

# Monitoramento
python chaos_cli.py monitor cluster-health
python chaos_cli.py monitor list-pods --all-namespaces

# Métricas
python chaos_cli.py metrics summary --days 7
python chaos_cli.py metrics export-csv chaos_report.csv

# Cenários Avançados
python chaos_cli.py scenarios cascade-failure --app test-app --intensity medium
python chaos_cli.py scenarios blast-radius --max-failures 3

# 🔬 Simulação de Confiabilidade (NOVO!)
python chaos_cli.py reliability test --preset standard
python chaos_cli.py reliability start --duration 0.5 --acceleration 10000.0
python chaos_cli.py reliability analyze --csv-path simulation.csv
```

### API Programática

```python
from pod_injector import PodFailureInjector
from node_injector import NodeFailureInjector
from advanced_scenarios import AdvancedChaosScenarios

# Falha simples em pod
pod_injector = PodFailureInjector(namespace="default")
metrics = pod_injector.inject_failure("my-app-pod", failure_type="delete")
print(f"Recovery time: {metrics.recovery_time}s")

# Cenário avançado
scenarios = AdvancedChaosScenarios()
result = scenarios.cascade_failure_scenario(app_label="my-app", intensity="medium")
print(f"Scenario success: {result.success}")
```

## 📊 Funcionalidades

### 1. Injeção de Falhas em Pods

- **Delete**: Remove pod e monitora recriação
- **Kill**: Mata processo principal do container
- **Resource Limit**: Aplica limites de CPU/memória
- **Crashloop**: Induz loop de crashes

```python
from pod_injector import PodFailureInjector

injector = PodFailureInjector(namespace="default")

# Delete pod
metrics = injector.inject_failure("my-pod", failure_type="delete")

# Limita recursos
metrics = injector.inject_failure("my-pod", failure_type="limit", 
                                cpu_limit="100m", memory_limit="128Mi")
```

### 2. Injeção de Falhas em Processos

- **Kill**: Mata processos por PID ou nome
- **CPU Stress**: Gera carga de CPU
- **Memory Stress**: Consome memória
- **I/O Stress**: Gera carga de disco

```python
from process_injector import ProcessFailureInjector

injector = ProcessFailureInjector()

# Kill processo
metrics = injector.inject_failure("1234", failure_type="kill")

# Stress CPU
metrics = injector.inject_failure("1", failure_type="cpu_stress", 
                                duration=300, cpu_percent=80)
```

### 3. Injeção de Falhas em Nós

- **Drain**: Remove pods do nó
- **Cordon**: Impede scheduling no nó  
- **Reboot**: Reinicia nó (AWS)
- **Network Partition**: Bloqueia comunicação
- **Disk Fill**: Preenche disco

```python
from node_injector import NodeFailureInjector

injector = NodeFailureInjector()

# Drain nó
metrics = injector.inject_failure("worker-1", failure_type="drain")

# Reboot nó AWS
metrics = injector.inject_failure("worker-1", failure_type="reboot")
```

### 4. Cenários Avançados

- **Cascade Failure**: Falhas em cascata
- **Rolling Restart**: Restart controlado
- **Network Partition**: Isolamento de nós
- **Resource Exhaustion**: Esgotamento de recursos
- **Blast Radius**: Teste de limite de falhas

```python
from advanced_scenarios import AdvancedChaosScenarios

scenarios = AdvancedChaosScenarios()

# Falha em cascata
result = scenarios.cascade_failure_scenario(
    app_label="my-app", 
    intensity="medium"
)

# Teste de blast radius
result = scenarios.blast_radius_test(max_concurrent_failures=3)
```

### 5. Monitoramento e Métricas

```python
from system_monitor import SystemMonitor
from metrics_collector import AdvancedMetricsCollector

# Monitoramento
monitor = SystemMonitor()
health = monitor.get_cluster_health()
print(f"Cluster score: {health.cluster_score}")

# Métricas
collector = AdvancedMetricsCollector()
summary = collector.get_metrics_summary(days=7)
print(f"Total failures: {summary['total_failures']}")
```

### 6. Visualização

```python
from visualization import ChaosVisualization

viz = ChaosVisualization()

# Timeline de recuperação
viz.plot_recovery_timeline(metrics_list, save_path="recovery.png")

# Dashboard interativo
viz.create_interactive_dashboard(save_path="dashboard.html")

# Radar de resiliência
viz.plot_resilience_radar(failure_types, save_path="radar.png")
```

## 🎛️ Configuração

### Variáveis de Ambiente

```bash
# Kubernetes
export KUBECONFIG=/path/to/kubeconfig

# AWS (opcional)
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-west-2

# SSH (opcional)
export SSH_PRIVATE_KEY_PATH=/path/to/private_key
export SSH_USERNAME=ubuntu

# Database
export CHAOS_DB_PATH=/path/to/chaos_metrics.db

# Logging
export CHAOS_LOG_LEVEL=INFO
```

### Arquivo de Configuração

Crie `chaos_config.yaml`:

```yaml
chaos_config:
  # Configurações globais
  default_namespace: "default"
  max_concurrent_failures: 3
  default_timeout: 300
  
  # AWS
  aws:
    region: "us-west-2"
    auto_tag_instances: true
  
  # SSH
  ssh:
    username: "ubuntu"
    private_key_path: "~/.ssh/id_rsa"
    port: 22
  
  # Métricas
  metrics:
    database_path: "chaos_metrics.db"
    retention_days: 90
    
  # Segurança
  safety:
    enable_production_guard: true
    allowed_namespaces: ["default", "test", "staging"]
    forbidden_labels: ["production", "critical"]
```

## 🛡️ Segurança

### Proteções Implementadas

1. **Namespace Isolation**: Limita ações a namespaces específicos
2. **Label Filtering**: Evita recursos marcados como críticos
3. **Confirmation Prompts**: Requer confirmação para ações destrutivas
4. **Timeout Protection**: Limites automáticos de tempo
5. **Recovery Automation**: Recuperação automática quando possível

### Boas Práticas

- Sempre teste em ambiente não-produtivo primeiro
- Use namespaces dedicados para testes
- Configure timeouts adequados
- Monitore métricas durante testes
- Tenha planos de rollback preparados

## 📈 Métricas e Relatórios

### Métricas Coletadas

- **Tempo de Recuperação**: Quanto tempo para o sistema se recuperar
- **Disponibilidade**: Percentual de uptime durante falhas
- **Score de Resiliência**: Pontuação baseada em múltiplos fatores
- **Impacto no Sistema**: Degradação de performance
- **Efetividade de Falhas**: Taxa de sucesso das injeções

### Tipos de Relatórios

```python
# Resumo de métricas
summary = collector.get_metrics_summary(days=7)

# Métricas de disponibilidade  
availability = collector.calculate_availability_metrics(start_date, end_date)

# Benchmark de tipos de falha
benchmark = collector.benchmark_failure_types()

# Exportar para CSV
collector.export_metrics_csv("report.csv")
```

## 🔧 Desenvolvimento

### Estrutura de Classes

```python
# Classes base
class BaseFailureInjector(ABC):
    @abstractmethod
    def inject_failure(self, target: str, failure_type: str, **kwargs) -> FailureMetrics
    
    @abstractmethod  
    def recover_failure(self, failure_id: str) -> bool

# Classes especializadas
class PodFailureInjector(BaseFailureInjector):
    def inject_failure(self, target: str, failure_type: str, **kwargs) -> FailureMetrics:
        # Implementação específica para pods

class NodeFailureInjector(BaseFailureInjector):  
    def inject_failure(self, target: str, failure_type: str, **kwargs) -> FailureMetrics:
        # Implementação específica para nós
```

### Adicionando Novos Injetores

1. Herde de `BaseFailureInjector`
2. Implemente métodos obrigatórios
3. Registre no `ChaosOrchestrator`
4. Adicione comandos CLI correspondentes

### Executando Testes

```bash
# Testes unitários
python -m pytest tests/

# Validação de sintaxe
python -m py_compile *.py

# Verificar dependências
python -c "import requirements_checker; requirements_checker.check()"
```

## 📋 Exemplo Completo

```python
#!/usr/bin/env python3
"""
Exemplo completo de uso do framework
"""

from datetime import datetime
from pod_injector import PodFailureInjector, PodMonitor
from node_injector import NodeFailureInjector
from advanced_scenarios import AdvancedChaosScenarios
from visualization import ChaosVisualization
from metrics_collector import AdvancedMetricsCollector

def run_complete_chaos_test():
    """Executa um teste completo de chaos engineering"""
    
    print("🚀 Iniciando teste completo de Chaos Engineering")
    
    # Inicialização
    pod_injector = PodFailureInjector(namespace="default")
    node_injector = NodeFailureInjector()
    scenarios = AdvancedChaosScenarios()
    viz = ChaosVisualization()
    collector = AdvancedMetricsCollector()
    
    all_metrics = []
    
    # 1. Teste básico de pod
    print("\n📦 Testando falhas em pods...")
    pods = pod_injector.list_targets()
    if pods:
        target_pod = pods[0]
        metrics = pod_injector.inject_failure(target_pod, failure_type="delete")
        all_metrics.append(metrics)
        print(f"   Pod {target_pod} - Recovery time: {metrics.recovery_time:.2f}s")
    
    # 2. Teste de nó
    print("\n🖥️  Testando falhas em nós...")
    nodes = node_injector.list_targets()
    worker_nodes = [n for n in nodes if "master" not in n.lower()]
    if worker_nodes:
        target_node = worker_nodes[0]
        metrics = node_injector.inject_failure(target_node, failure_type="cordon")
        all_metrics.append(metrics)
        print(f"   Node {target_node} - Recovery time: {metrics.recovery_time:.2f}s")
    
    # 3. Cenário avançado
    print("\n🌊 Executando cenário de falha em cascata...")
    result = scenarios.cascade_failure_scenario(intensity="low")
    all_metrics.extend(result.recovery_metrics)
    print(f"   Cascade scenario - Success: {result.success}, "
          f"Recovery time: {result.total_recovery_time:.2f}s")
    
    # 4. Gerar visualizações
    print("\n📊 Gerando visualizações...")
    if all_metrics:
        viz.plot_recovery_timeline(all_metrics, save_path="test_recovery_timeline.png")
        viz.create_interactive_dashboard(save_path="test_dashboard.html")
        print("   Gráficos salvos: test_recovery_timeline.png, test_dashboard.html")
    
    # 5. Salvar métricas
    print("\n💾 Salvando métricas...")
    for metrics in all_metrics:
        collector.record_failure(metrics)
    
    # 6. Gerar relatório
    print("\n📋 Gerando relatório...")
    summary = collector.get_metrics_summary(days=1)
    
    print(f"""
📊 RELATÓRIO FINAL
================
Total de falhas: {summary.get('total_failures', 0)}
Tempo médio de recuperação: {summary.get('avg_recovery_time', 0):.2f}s
Taxa de sucesso: {summary.get('success_rate', 0)*100:.1f}%
Score de resiliência: {summary.get('resilience_score', 0):.1f}/100

Teste concluído com sucesso! 🎉
""")

if __name__ == "__main__":
    run_complete_chaos_test()
```

## 🆘 Solução de Problemas

### Problemas Comuns

1. **Erro de conectividade Kubernetes**
   ```bash
   # Verifique kubeconfig
   kubectl get nodes
   export KUBECONFIG=/path/to/correct/kubeconfig
   ```

2. **Dependências em falta**
   ```bash
   pip install -r requirements.txt
   ```

3. **Problemas de permissão AWS**
   ```bash
   aws sts get-caller-identity
   ```

4. **SSH não funciona**
   ```bash
   ssh -i ~/.ssh/private_key ubuntu@node-ip
   ```

### Logs e Debug

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Recovery Manual

```python
# Recovery manual de falhas
from base import ChaosOrchestrator

orchestrator = ChaosOrchestrator()
orchestrator.emergency_recovery_all()
```

## 🤝 Contribuição

1. Faça fork do projeto
2. Crie branch para feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para branch (`git push origin feature/nova-funcionalidade`)
5. Abra Pull Request

## 📄 Licença

Este projeto está sob licença MIT. Veja arquivo LICENSE para detalhes.

## 🔗 Referências

- [Chaos Engineering Principles](https://principlesofchaos.org/)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
- [AWS Fault Injection Simulator](https://aws.amazon.com/fis/)
- [Gremlin Chaos Engineering](https://www.gremlin.com/chaos-engineering/)

---

**⚠️ AVISO**: Este framework pode causar interrupções no sistema. Use apenas em ambientes de teste ou com extrema cautela em produção. Sempre tenha planos de backup e recovery preparados.