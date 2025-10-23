# Sistema de Simulação de Disponibilidade Kubernetes

## 🎯 Visão Geral

Sistema completo de simulação de disponibilidade para infraestrutura Kubernetes, implementando:

- **Distribuição Exponencial**: Falhas baseadas em MTTF (Mean Time To Failure)
- **Timing Híbrido**: 1 minuto real entre falhas + tempo real de recuperação
- **Integração Kubernetes**: Uso de `kubectl` para falhas e monitoramento reais
- **Relatórios Detalhados**: CSV com eventos, estatísticas e métricas de disponibilidade

## 🏗️ Arquitetura

```
kuber_bomber/
├── simulation/
│   └── availability_simulator.py    # Motor principal de simulação
├── cli/
│   └── availability_cli.py          # Interface de linha de comando
├── monitoring/
│   └── health_checker.py            # Monitoramento de saúde dos componentes
├── reports/
│   └── csv_reporter.py              # Geração de relatórios CSV
└── failure_injectors/
    ├── pod_injector.py              # Injeção de falhas em pods
    ├── node_injector.py             # Injeção de falhas em nodes
    └── control_plane_injector.py    # Injeção de falhas no control plane
```

## ⚙️ Componentes Configurados

| Componente | Tipo | MTTF | Descrição |
|------------|------|------|-----------|
| `foo-app` | pod | 100h | Aplicação foo |
| `bar-app` | pod | 120h | Aplicação bar |
| `test-app` | pod | 80h | Aplicação de teste |
| `local-k8s-worker` | node | 500h | Worker node 1 |
| `local-k8s-worker2` | node | 500h | Worker node 2 |
| `local-k8s-control-plane` | control_plane | 800h | Control plane |

## 🚀 Como Usar

### 1. Pré-requisitos

- Cluster Kubernetes funcionando (kind/minikube/etc)
- `kubectl` configurado
- Python 3.8+
- Dependências: `numpy`, `pandas`, `matplotlib`

### 2. Execução via CLI

```bash
cd /home/jonascgn/Documentos/1_Artigo/testes

# Simulação básica (24h fictícias, 1 iteração)
python -m kuber_bomber.cli.availability_cli

# Simulação personalizada (48h fictícias, 5 iterações)
python -m kuber_bomber.cli.availability_cli --duration 48 --iterations 5

# Simulação de 1 semana (168h fictícias) com delay customizado
python -m kuber_bomber.cli.availability_cli --duration 168 --iterations 10 --delay 30
```

**⚠️ IMPORTANTE - Duração:**
- `--duration` é em **HORAS FICTÍCIAS** (simuladas), não tempo real
- Exemplo: `--duration 168` simula 1 semana de operação em minutos reais
- O tempo real depende do número de falhas e tempo de recuperação

### 3. Parâmetros

- `--duration`: Duração da simulação em **HORAS FICTÍCIAS** (padrão: 24)
- `--iterations`: Número de iterações (padrão: 1)  
- `--delay`: Delay entre falhas em segundos **REAIS** (padrão: 60)

### 4. Critérios de Disponibilidade Interativos

O CLI pergunta para cada aplicação quantos pods precisam estar funcionando:

```
📦 foo-app:
   Quantos pods de foo-app precisam estar Ready? (mín: 1): 2
   ✅ foo-app: mínimo 2 pod(s)

📦 bar-app:
   Quantos pods de bar-app precisam estar Ready? (mín: 1): 1
   ✅ bar-app: mínimo 1 pod(s)

📦 test-app:
   Quantos pods de test-app precisam estar Ready? (mín: 1): 3
   ✅ test-app: mínimo 3 pod(s)
```

**Sistema está disponível quando:**
- `foo-app`: ≥ 2 pods Ready
- `bar-app`: ≥ 1 pod Ready  
- `test-app`: ≥ 3 pods Ready
- **E** todos os nodes estão funcionais
- **E** control plane está operacional

### 4. Uso Programático

```python
from kuber_bomber.simulation.availability_simulator import AvailabilitySimulator, Component

# Criar componentes customizados
components = [
    Component("my-app", "pod", mttf_hours=50.0),
    Component("worker-1", "node", mttf_hours=300.0)
]

# Criar simulador
simulator = AvailabilitySimulator(components=components, min_pods_required=1)

# Configurar critérios específicos de disponibilidade
simulator.availability_criteria = {
    "my-app": 2,      # Precisa de pelo menos 2 pods da my-app
    "other-app": 1    # Precisa de pelo menos 1 pod da other-app
}

# Executar simulação (12 horas fictícias, 3 iterações)
simulator.run_simulation(duration_hours=12.0, iterations=3)
```

## 📊 Relatórios

Os relatórios são salvos automaticamente em:

```
ano/mes/dia/component/availability_simulation/mttf_based/
├── availability_simulation_YYYYMMDD_HHMMSS.csv    # Eventos detalhados
└── simulation_stats_YYYYMMDD_HHMMSS.csv           # Estatísticas agregadas
```

### Formato dos Eventos

```csv
event_time_hours,real_time_seconds,component_type,component_name,
failure_type,recovery_time_seconds,system_available,available_pods,
required_pods,availability_percentage,downtime_duration,cumulative_downtime
```

### Formato das Estatísticas

```csv
metric,value,unit,description
simulation_duration_hours,24.0,hours,Duração total da simulação
total_failures,15,count,Total de falhas simuladas
system_availability,99.2,percentage,Disponibilidade geral do sistema
mean_recovery_time,45.3,seconds,Tempo médio de recuperação
total_downtime,0.8,hours,Tempo total de indisponibilidade
iterations_executed,1,count,Número de iterações executadas
```

## 🔧 Lógica de Funcionamento

### 1. Inicialização
- Define componentes com seus MTTFs
- Cria fila de eventos ordenada por tempo
- Gera primeiro evento de falha para cada componente

### 2. Loop Principal
```python
while current_time < duration:
    event = heapq.heappop(event_queue)
    inject_failure(event.component)
    wait_for_recovery()  # Tempo real
    schedule_next_failure()  # +1min + exponential
    monitor_availability()
```

### 3. Timing Híbrido
- **Entre falhas**: 1 minuto fixo + intervalo exponencial
- **Recuperação**: Tempo real até pods ficarem Ready
- **Monitoramento**: Verificação contínua de disponibilidade

### 4. Critério de Disponibilidade e Cálculo de Indisponibilidade

**Sistema está disponível quando TODOS os critérios são atendidos simultaneamente:**

**Pods por aplicação (configurável):**
- `foo-app`: ≥ X pods Ready (usuário define X)
- `bar-app`: ≥ Y pods Ready (usuário define Y)  
- `test-app`: ≥ Z pods Ready (usuário define Z)

**Infraestrutura:**
- Nodes worker funcionais
- Control plane operacional

**⏰ Cálculo do Tempo de Indisponibilidade:**

O sistema calcula indisponibilidade baseado nos critérios específicos:

```
Exemplo: foo≥2, bar≥1, test≥3

🟢 DISPONÍVEL:    foo=3, bar=2, test=4  (todos critérios OK)
🔴 INDISPONÍVEL:  foo=1, bar=2, test=4  (foo abaixo do mínimo)
🔴 INDISPONÍVEL:  foo=2, bar=0, test=4  (bar abaixo do mínimo)  
🔴 INDISPONÍVEL:  foo=1, bar=0, test=2  (todos abaixo do mínimo)
```

**Algoritmo de cálculo:**
1. A cada evento, verifica disponibilidade atual
2. Calcula tempo desde última verificação
3. Se sistema estava disponível → adiciona ao tempo_disponível
4. Se sistema estava indisponível → adiciona ao tempo_indisponível  
5. Disponibilidade% = (tempo_disponível / tempo_total) × 100

**Exemplo prático:**
- 10:00-10:30: todos OK → 30min disponível
- 10:30-10:35: foo cai para 1 → 5min **indisponível**
- 10:35-11:00: foo volta para 2 → 25min disponível  
- 11:00-11:10: test cai para 2 → 10min **indisponível**
- **Resultado:** 15min indisponível de 70min total = 78.6% disponibilidade

## 📈 Métricas Coletadas

- **Disponibilidade do Sistema**: % de tempo que o sistema está disponível
- **MTTR (Mean Time To Recovery)**: Tempo médio de recuperação
- **Downtime Total**: Tempo total de indisponibilidade
- **Falhas por Componente**: Distribuição de falhas
- **Estatísticas de Recuperação**: Min, max, média, desvio padrão

## 🎯 Casos de Uso

1. **Análise de Confiabilidade**: Avaliar disponibilidade esperada da infraestrutura
2. **Planejamento de Capacidade**: Determinar número mínimo de réplicas
3. **Teste de Resiliência**: Validar comportamento sob falhas
4. **Otimização de MTTF**: Encontrar pontos críticos de falha
5. **Compliance SLA**: Verificar se sistema atende requisitos de disponibilidade

## 🔍 Limitações e Considerações

- Simulação assume distribuição exponencial (memoryless)
- Falhas são independentes entre componentes
- Tempo de recuperação é medido em ambiente real
- Requer cluster Kubernetes funcional para testes completos
- Simulação é determinística com seed fixo para reprodutibilidade

## 🚀 Extensões Futuras

- Suporte a correlação entre falhas
- Distribuições alternativas (Weibull, Normal)
- Interface web para visualização
- Integração com Prometheus/Grafana
- Simulação de falhas de rede e armazenamento
- Modo "dry-run" para testes sem cluster real