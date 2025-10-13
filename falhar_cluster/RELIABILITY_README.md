# 🎯 Sistema de Simulação de Confiabilidade - Kubernetes Chaos Engineering

## 📖 Visão Geral

Este sistema implementa simulação de confiabilidade acadêmica para clusters Kubernetes, permitindo análise de métricas críticas como **MTTF** (Mean Time To Failure), **MTBF** (Mean Time Between Failures) e **MTTR** (Mean Time To Recovery).

### 🚀 Como Usar

```bash
# Comando principal
python3 main.py reliability start [OPÇÕES]

# Exemplo básico
python3 main.py reliability start --duration 1.0 --acceleration 10000

# Exemplo avançado
python3 main.py reliability start \
    --duration 2.0 \
    --acceleration 50000 \
    --csv-path "teste_completo.csv" \
    --namespace "production"
```

## 🔧 Parâmetros de Configuração

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `--duration` | 1.0 | Duração da simulação em **horas reais** |
| `--acceleration` | 10000.0 | Fator de aceleração temporal (1h real = X horas simuladas) |
| `--csv-path` | `reliability_simulation.csv` | Arquivo CSV de saída com logs detalhados |
| `--namespace` | `default` | Namespace Kubernetes para testes |

### 📊 Aceleração Temporal

O sistema usa **aceleração temporal** para simular longos períodos em tempo reduzido:

- **Aceleração 10.000x**: 1 hora real = 10.000 horas simuladas (~1,14 anos)
- **Aceleração 50.000x**: 1 hora real = 50.000 horas simuladas (~5,7 anos)
- **Aceleração 100.000x**: 1 hora real = 100.000 horas simuladas (~11,4 anos)

## 💥 Tipos de Falha Implementados

### 1. 🔸 POD_KILL (`pod_kill`)
**Descrição**: Mata o processo principal (PID 1) dentro do container do pod.

**Comando Executado**:
```bash
kubectl exec <pod> -n <namespace> -- kill -9 1
```

**Impacto**:
- ✅ Mata apenas a aplicação
- ✅ Container pode reiniciar automaticamente
- ✅ Pod permanece "vivo" no Kubernetes
- ✅ Simula crash da aplicação

**Tempo de Recuperação**: 5-30 segundos (restart automático)

---

### 2. 🔄 POD_REBOOT (`pod_reboot`)
**Descrição**: Força delete completo do pod, simulando reboot total.

**Comando Executado**:
```bash
kubectl delete pod <pod> -n <namespace> --force --grace-period=0
```

**Impacto**:
- 🔥 Deleta pod completamente
- 🔄 Kubernetes recria automaticamente (se gerenciado por Deployment)
- 🔄 Novo IP, novo hostname
- 🔄 Simula reboot completo da máquina virtual

**Tempo de Recuperação**: 30-120 segundos (criação de novo pod)

---

### 3. 🖥️ NODE_REBOOT (`node_reboot`)
**Descrição**: Reinicia o nó worker completamente via reboot do sistema.

**Comando Executado**:
```bash
# Via node_injector usando SSH ou kubectl debug
sudo reboot
```

**Impacto**:
- 💥 Reinicia máquina física/virtual
- 💥 Todos os pods do nó são perdidos
- 💥 Kubernetes precisa reagendar pods
- 💥 Simula falha de hardware/sistema

**Tempo de Recuperação**: 2-10 minutos (boot + reagendamento)

---

### 4. ⚡ NODE_KILL_ALL (`node_kill_all`)
**Descrição**: Mata processos não-críticos do nó, preservando sistema base.

**Comandos Executados**:
```bash
kubectl debug node/<node> -it --image=busybox -- \
    chroot /host bash -c \
    "pkill -f -9 '(?!systemd|kubelet|dockerd|containerd).*'"
```

**Impacto**:
- ⚡ Mata aplicações e containers
- ⚡ Preserva kubelet, systemd, docker
- ⚡ Nó permanece "responsivo"
- ⚡ Simula sobrecarga de processos

**Tempo de Recuperação**: 1-5 minutos (restart de containers)

---

### 5. ☠️ NODE_KILL_CRITICAL (`node_kill_critical`)
**Descrição**: **MUITO DESTRUTIVO** - Mata processos críticos do Kubernetes.

**Processos Alvos**:
- `kubelet` - Agente Kubernetes no nó
- `containerd` - Runtime de containers  
- `dockerd` - Docker daemon
- `kube-proxy` - Proxy de rede
- `calico-node` - CNI (networking)
- `flannel` - CNI alternativo
- `coredns` - DNS interno
- `etcd` - Base de dados (se no worker)

**Comandos Executados**:
```bash
# Para cada processo crítico
kubectl debug node/<node> -it --image=busybox -- \
    chroot /host bash -c \
    "pkill -f -9 '<processo>'"

# Ataque final
kubectl debug node/<node> -it --image=busybox -- \
    chroot /host bash -c \
    "pkill -f -9 'containerd|docker|runc|kubelet|kube-proxy'"
```

**Impacto**:
- ☠️ **PODE QUEBRAR O NÓ PERMANENTEMENTE**
- ☠️ Perde comunicação com cluster
- ☠️ Pode exigir reboot manual
- ☠️ Simula falhas catastróficas

**Tempo de Recuperação**: 10+ minutos (ou manual)

## 📈 Métricas Calculadas

### 🎯 Métricas Principais

| Métrica | Descrição | Unidade |
|---------|-----------|---------|
| **MTTF** | Mean Time To Failure - Tempo médio até falha | Horas |
| **MTBF** | Mean Time Between Failures - Tempo médio entre falhas | Horas |
| **MTTR** | Mean Time To Recovery - Tempo médio de recuperação | Segundos |
| **Availability** | Disponibilidade do sistema | Percentual |
| **Reliability** | Confiabilidade em 1000h | Percentual |
| **Failure Rate** | Taxa de falha | Falhas/hora |

### 📊 Distribuições Estatísticas

O sistema suporta diferentes distribuições para intervalos de falha:

1. **Exponencial** (padrão): Falhas aleatórias uniformes
2. **Weibull**: Modelagem de desgaste/envelhecimento
3. **Normal**: Falhas previsíveis com variação

## 📋 Fluxo de Execução Detalhado

### 1. 🎬 Inicialização
```
[Início] → Carrega configurações → Conecta Kubernetes → Inicializa CSV
```

### 2. 🎯 Seleção de Alvo
```
[Scheduler] → Escolhe modo de falha aleatório → Seleciona alvo válido
```

### 3. 💥 Injeção de Falha
```
[Falha] → Mede saúde antes → Executa comando → Log evento → Inicia timer
```

### 4. 🔍 Monitoramento
```
[Monitor] → Detecta recuperação → Calcula MTTR → Atualiza métricas → Log recuperação
```

### 5. 📊 Cálculo de Métricas
```
[Métricas] → MTTF/MTBF/MTTR → Availability → Reliability → Salva CSV
```

### 6. 🔄 Loop Contínuo
```
[Loop] → Calcula próxima falha → Aguarda → Volta ao passo 2
```

## 📁 Arquivo CSV de Saída

O sistema gera um CSV detalhado com todas as informações:

```csv
timestamp,simulation_time_hours,real_time_seconds,event_type,failure_mode,target,target_type,failure_id,start_time,end_time,duration_seconds,duration_hours,mttf_hours,mtbf_hours,mttr_seconds,mttr_hours,next_failure_in_hours,cluster_health_before,cluster_health_after,additional_info
```

### 📋 Tipos de Eventos Logados

- `failure_initiated` - Falha iniciada
- `failure_detected` - Falha confirmada
- `recovery_started` - Recuperação iniciada
- `recovery_completed` - Recuperação concluída
- `simulation_started` - Simulação iniciada
- `simulation_stopped` - Simulação parada

## 🎮 Exemplos de Uso Prático

### 📊 Análise de Disponibilidade
```bash
# Simula 6 meses de operação em 30 minutos
python3 main.py reliability start \
    --duration 0.5 \
    --acceleration 8760 \
    --csv-path "analise_6meses.csv"
```

### 🔬 Teste de Stress Intenso
```bash
# Acelera muito para muitas falhas
python3 main.py reliability start \
    --duration 2.0 \
    --acceleration 100000 \
    --csv-path "stress_test.csv"
```

### 🏭 Simulação Produção
```bash
# Teste no namespace de produção
python3 main.py reliability start \
    --duration 1.0 \
    --acceleration 10000 \
    --csv-path "prod_reliability.csv" \
    --namespace "production"
```

## 📊 Análise dos Resultados

### 📈 Interpretação das Métricas

1. **MTTF Alto**: Sistema estável, falhas raras
2. **MTTR Baixo**: Recuperação rápida, boa resiliência
3. **Availability > 99%**: Sistema altamente disponível
4. **Reliability > 90%**: Confiável para 1000h operação

### 🎯 Benchmarks Típicos

| Tipo de Sistema | MTTF (horas) | MTTR (segundos) | Availability |
|-----------------|--------------|-----------------|--------------|
| **Crítico** | 8760+ | <60 | >99.9% |
| **Produção** | 720+ | <300 | >99% |
| **Desenvolvimento** | 168+ | <600 | >95% |

## ⚠️ Avisos Importantes

### 🚨 Modo NODE_KILL_CRITICAL
- **MUITO PERIGOSO** - pode quebrar nós permanentemente
- Use apenas em ambientes de teste
- Tenha plano de recuperação manual

### 🔒 Requisitos de Segurança
- Permissões administrativas no cluster
- Acesso via kubectl configurado
- Pods com privilégios para debug nodes

### 📋 Pré-requisitos
- Cluster Kubernetes funcional
- kubectl configurado
- Python 3.8+
- Dependências: kubernetes, numpy, rich, click

## 🎯 Conclusão

Este sistema oferece análise acadêmica robusta de confiabilidade para clusters Kubernetes, permitindo:

- ✅ Testes controlados de resiliência
- ✅ Análise quantitativa de disponibilidade  
- ✅ Métricas acadêmicas padrão (MTTF/MTBF/MTTR)
- ✅ Simulação acelerada de longos períodos
- ✅ Logging detalhado para análise posterior

**Use com responsabilidade e sempre em ambientes de teste!** 🛡️