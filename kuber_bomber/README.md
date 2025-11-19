# 🎯 Testes de Confiabilidade - Todos os Componentes Kubernetes

## 📋 Visão Geral

Este framework modular permite testar a confiabilidade de **TODOS** os componentes de um cluster Kubernetes (Kind), incluindo:

- ✅ **Pods e Containers** (aplicações)
- ✅ **Worker Nodes** (nós de trabalho)
- ✅ **Control Plane** (API Server, Scheduler, Controller Manager, etcd)
- ✅ **Componentes de Rede** (kube-proxy, containerd)

## 🚀 Comandos Básicos

### Estrutura do Comando

```bash
python3 reliability_tester.py \
  --component <tipo> \
  --failure-method <método> \
  --target <alvo> \
  --iterations <número> \
  --interval <segundos>
```

### Exemplo (seu comando original)

````markdown
# Kuber Bomber - Framework de Testes de Confiabilidade para Kubernetes

![Kubernetes](https://img.shields.io/badge/Kubernetes-1.24%2B-blue)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## 📋 Índice

1. [Sobre o Projeto](#sobre-o-projeto)
2. [Instalação e Configuração Inicial](#instalação-e-configuração-inicial)
3. [Conceitos Principais](#conceitos-principais)
4. [Como Usar](#como-usar)
5. [Exemplos de Comandos](#exemplos-de-comandos)
6. [Componentes Testáveis](#componentes-testáveis)
7. [Valores Padrão](#valores-padrão)
8. [Troubleshooting](#troubleshooting)

---

## 📖 Sobre o Projeto

**Kuber Bomber** é um framework completo para testes de confiabilidade e disponibilidade em clusters Kubernetes. Ele permite:

- 🎯 **Injetar falhas** controladas em componentes do Kubernetes
- 📊 **Medir disponibilidade** do sistema antes, durante e após falhas
- ⏱️ **Calcular MTTR** (Mean Time To Recovery) automaticamente
- 📈 **Analisar resiliência** em ambiente local (Kind) ou AWS
- 🔄 **Executar simulações** aceleradas de falhas ao longo do tempo

### Componentes Testáveis

- **Pods de Aplicação**: Processos, containers
- **Worker Nodes**: Shutdown, kill de processos, kubelet
- **Control Plane**: API Server, Scheduler, Controller Manager, etcd, **NOVO: Shutdown Completo**
- **Runtime**: Containerd, kube-proxy
- **Network**: Partições de rede

---

## 🚀 Instalação e Configuração Inicial

### Pré-requisitos

```bash
# Python 3.9+
python3 --version

# Docker (para Kind local)
docker --version

# kubectl
kubectl version --client

# aws-cli (apenas se usar AWS)
aws --version
```

### Instalação

```bash
# 1. Clone o repositório
cd /seu/caminho/kuber_bomber

# 2. Instale dependências
pip install -r requirements.txt

# 3. Configure variáveis de ambiente (opcional)
export KUBER_BOMBER_CONFIG_PATH="/seu/caminho/kuber_bomber/configs"
```

### Verificar Instalação

```bash
# Verificar que pode ser importado
python3 -c "import kuber_bomber; print('✅ Kuber Bomber instalado')"

# Listar principais módulos
ls -la kuber_bomber/
```

---

## 📚 Conceitos Principais

### MTTF (Mean Time To Failure)

Tempo médio entre falhas. Padrão: varia por componente
- **Pod**: 1h
- **Worker Node**: 72h
- **Control Plane**: 168h (1 semana)

### MTTR (Mean Time To Recovery)

Tempo médio para recuperação após falha. Calculado automaticamente:
- Via **health checker** em tempo real
- Via **sleep configurado** para simulações

### Métodos de Falha Disponíveis

#### Worker Node
```
- kill_worker_node_processes    # Mata todos os processos
- shutdown_worker_node          # Desliga o node (self-healing automático) ⭐
- kill_kubelet                  # Mata kubelet específico
- restart_containerd            # Reinicia container runtime
```

#### Control Plane (NOVO - Shutdown Completo)
```
- kill_control_plane_processes  # Mata todos os processos
- shutdown_control_plane        # Desliga completo (self-healing automático) ⭐ NOVO
- kill_kube_apiserver           # Mata API Server
- kill_kube_controller_manager  # Mata Controller Manager
- kill_kube_scheduler           # Mata Scheduler
- kill_etcd                     # Mata etcd
```

#### Pod
```
- kill_processes                # Mata todos os processos do pod
- kill_init                     # Mata init do pod
```

---

## 🎮 Como Usar

### 1. Configuração Rápida (Descoberta Automática)

```bash
# Gerar configuração com descoberta automática
python3 -m kuber_bomber.cli.availability_cli --get-config

# Gerar com análise MTTR completa (10-20 minutos)
python3 -m kuber_bomber.cli.availability_cli --get-config-all
```

### 2. Teste de Confiabilidade Simples

```bash
# Teste em control plane com shutdown (NOVO)
cd kuber_bomber && python3 reliability_tester.py \
  --component control_plane \
  --failure-method shutdown_control_plane \
  --target local-k8s-control-plane \
  --iterations 5 \
  --interval 10

# Teste em worker node
python3 reliability_tester.py \
  --component worker_node \
  --failure-method shutdown_worker_node \
  --target ip-10-0-0-241 \
  --iterations 3 \
  --interval 10 \
  --aws
```

### 3. Simulação de Disponibilidade

```bash
# Simulação local (Kind) com configuração padrão
python3 -m kuber_bomber.cli.availability_cli --use-config-simples

# Simulação AWS com força completa
python3 -m kuber_bomber.cli.availability_cli \
  --use-config-simples \
  --force-aws

# Simulação customizada
python3 -m kuber_bomber.cli.availability_cli \
  --use-config-simples \
  --duration 2000 \
  --iterations 10 \
  --delay 60
```

### 4. Usar Classe de Exemplo (Recomendado)

```python
from kuber_bomber.core.exemplo_uso import ExemploUso

# Criar instância
exemplo = ExemploUso(use_aws=False)  # False para Kind, True para AWS

# Fluxo completo recomendado
exemplo.executar_fluxo_completo()

# Ou usar métodos individuais
config = exemplo.get_config(run_mttr_analysis=True)
disponibilidade = exemplo.check_availability()
resultados = exemplo.run_test(
    component_type='control_plane',
    failure_method='shutdown_control_plane',
    iterations=5
)
```

---

## 💡 Exemplos de Comandos

### Exemplo 1: Testar Control Plane com Shutdown (NOVO ⭐)

```bash
# Local (Kind)
cd kuber_bomber && python3 reliability_tester.py \
  --component control_plane \
  --failure-method shutdown_control_plane \
  --iterations 3 \
  --interval 10

# AWS
cd kuber_bomber && python3 reliability_tester.py \
  --component control_plane \
  --failure-method shutdown_control_plane \
  --target local-k8s-control-plane \
  --iterations 40 \
  --interval 10 \
  --aws
```

### Exemplo 2: Descoberta + Teste Completo

```bash
# Etapa 1: Descobrir infraestrutura e calcular MTTR
python3 -m kuber_bomber.cli.availability_cli --get-config-all

# Etapa 2: Executar simulação com config gerada
python3 -m kuber_bomber.cli.availability_cli --use-config-simples
```

### Exemplo 3: Teste em Pod

```bash
# Seu comando original de exemplo
cd kuber_bomber && python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target test-app-549846444f-pbsgl \
  --iterations 30 \
  --interval 60
```

### Exemplo 4: Script Python Automatizado

```python
#!/usr/bin/env python3
from kuber_bomber.core.reliability_tester import ReliabilityTester

# Criar testador
tester = ReliabilityTester()

# Executar teste de control plane
resultados = tester.run_reliability_test(
    component_type='control_plane',
    failure_method='shutdown_control_plane',
    target='local-k8s-control-plane',
    iterations=5,
    interval=10
)

# Analisar resultados
for r in resultados:
    print(f"Iteração {r['iteration']}: MTTR={r['recovery_time_seconds']:.2f}s, Recuperado={r['recovered']}")
```

---

## 🔧 Componentes Testáveis

### Tabela Completa de Métodos

| Componente                  | `--failure-method`             | `--component`   | Descrição | Self-healing |
|-----------------------------|--------------------------------|-----------------|-----------|----------|
| **Pod (all PIDs)**          | `kill_processes`               | `pod`           | `kill -9 -1` | ✅ |
| **Pod (PID 1)**             | `kill_init`                    | `pod`           | `kill -9 1` | ✅ |
| **Worker Node**             | `kill_worker_node_processes`   | `worker_node`   | `docker restart <node>` | ✅ |
| **Worker Node (shutdown)**  | `shutdown_worker_node`         | `worker_node`   | `docker stop + delay + start` | ✅ |
| **kubelet**                 | `kill_kubelet`                 | `worker_node`   | `pkill kubelet` | ✅ |
| **kube-proxy**              | `delete_kube_proxy`            | `worker_node`   | Delete pod DaemonSet | ✅ |
| **containerd**              | `restart_containerd`           | `worker_node`   | `docker restart <node>` | ✅ |
| **Control Plane**           | `kill_control_plane_processes` | `control_plane` | `docker restart` | ✅ |
| **Control Plane (shutdown)** | `shutdown_control_plane` ⭐     | `control_plane` | `docker stop + delay + start` | ✅ |
| **kube-apiserver**          | `kill_kube_apiserver`          | `control_plane` | `pkill kube-apiserver` | ✅ |
| **kube-controller-manager** | `kill_kube_controller_manager` | `control_plane` | `pkill kube-controller` | ✅ |
| **kube-scheduler**          | `kill_kube_scheduler`          | `control_plane` | `pkill kube-scheduler` | ✅ |
| **etcd**                    | `kill_etcd`                    | `control_plane` | `pkill etcd` | ✅ |

---

## 📊 Configuração Avançada

### Estrutura de Arquivos de Configuração

```
kuber_bomber/configs/
├── aws_config.json              # Config AWS (SSH, host, user)
├── aws_config_exemplo.json      # Exemplo de configuração AWS
├── config_simples_used.json     # Configuração atual de simulação
└── config_simples_used_exemplo.json
```

### aws_config.json

```json
{
  "ssh_host": "54.123.45.67",
  "ssh_key": "/home/user/.ssh/id_rsa",
  "ssh_user": "ubuntu",
  "applications": {
    "foo-service": "http://54.123.45.67:30001",
    "bar-service": "http://54.123.45.67:30002",
    "test-service": "http://54.123.45.67:30003"
  }
}
```

### Variáveis de Ambiente

```bash
# Configurar timeout de recuperação (segundos)
export KUBER_BOMBER_RECOVERY_TIMEOUT=300

# Modo verboso
export KUBER_BOMBER_VERBOSE=1
```

---

## 📊 Valores Padrão

### MTTF Padrão (Mean Time To Failure)

| Componente | MTTF Padrão | Descrição |
|------------|----------|-----------|
| Pod | 1h | Falha em aplicações |
| Worker Node | 72h | Falha em nó worker |
| Control Plane | 168h | Falha em control plane |
| Kubelet | 168h | Processo kubelet |
| API Server | 168h | Kubernetes API |
| Etcd | 240h | Banco de dados |

### MTTR Padrão (Mean Time To Recovery)

| Componente | MTTR Padrão | Método |
|------------|----------|--------|
| Pod | 30-60s | Restart automático |
| Worker Node | 5-10min | Shutdown + reboot |
| Control Plane | 1-2min | Shutdown + reboot |

### Timeouts Padrão

```python
DEFAULT_RECOVERY_TIMEOUT = 300  # 5 minutos
HEALTH_CHECK_TIMEOUT = 10       # 10 segundos por check
HEALTH_CHECK_INTERVAL = 2       # 2 segundos
DEFAULT_INTERVAL = 60           # 60 segundos entre iterações
```

---

## 🔍 Troubleshooting

### Problema: "Control plane não recupera após shutdown"

```bash
# Para Kind: Verificar se container está realmente reiniciando
docker ps -a | grep control-plane

# Verificar logs do Kind
kind get logs --name=local-k8s

# Para AWS: Verificar status da instância
aws ec2 describe-instances --filters "Name=tag:Name,Values=ControlPlane"
```

### Problema: "Não consegue descobrir pods"

```bash
# Verificar conectividade kubectl
kubectl get pods -A

# Verificar context
kubectl config current-context

# Listar targets disponíveis
python3 reliability_tester.py --list-targets
```

### Problema: "AWS Command not found"

```bash
# Instalar AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

### Problema: "Connection timeout no SSH"

```bash
# Verificar conectividade SSH
ssh -i /seu/path/id_rsa ubuntu@seu-ip

# Testar SSH com verbose
ssh -v -i /seu/path/id_rsa ubuntu@seu-ip
```

---

## 📈 Estrutura de Saída

### Diretório de Resultados

```
simulation/
└── 2025/11/18/
    └── 153045/  # Timestamp (HHMMSS)
        ├── statistics.csv
        ├── availability_report.json
        └── detailed_results.csv
```

---

## 🎓 Roteiro Recomendado para Iniciantes

### Passo 1: Verificar Instalação
```bash
python3 -c "import kuber_bomber; print('✅ OK')"
```

### Passo 2: Teste Local Simples (Pod)
```bash
cd kuber_bomber && python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --iterations 3 \
  --interval 5
```

### Passo 3: Teste Control Plane Shutdown ⭐ NOVO
```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method shutdown_control_plane \
  --iterations 3 \
  --interval 10
```

### Passo 4: Simulação Completa
```bash
python3 -m kuber_bomber.cli.availability_cli --get-config-all
python3 -m kuber_bomber.cli.availability_cli --use-config-simples
```

### Passo 5: Automação em Python
```python
from kuber_bomber.core.exemplo_uso import ExemploUso
exemplo = ExemploUso()
exemplo.executar_fluxo_completo()
```

---

## 🚨 Alertas Importantes

### ⚠️ Control Plane Shutdown (NOVO)

O novo método `shutdown_control_plane`:
- Desliga a instância completamente (Kind: docker stop, AWS: EC2 stop)
- Aguarda delay configurado (padrão: 10s)
- Religa automaticamente (self-healing)
- Mede tempo real até aplicações ficarem prontas

**Impacto**: Cluster inteiro fica indisponível durante o shutdown!

---

## 📄 Licença

MIT License - Use livremente em ambientes de teste e aprendizado.

---

**Última atualização**: 18 de Novembro de 2025

**Versão**: 2.1.0 (com suporte a shutdown_control_plane)
````

## 📦 1. Testes de Pods e Containers

### 1.1 Kill All Processes (kill -9 -1)

```bash
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target test-app-549846444f-pbsgl \
  --iterations 2 \
  --interval 60
```

**Self-healing:** ✅ Kubernetes reinicia automaticamente (restartPolicy: Always)

### 1.2 Kill Init Process (PID 1)

```bash
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_init \
  --target test-app-549846444f-pbsgl \
  --iterations 2 \
  --interval 60
```

**Self-healing:** ✅ ReplicaSet/Deployment cria novo pod automaticamente

## 🖥️ 2. Testes de Worker Nodes

### 2.1 Restart Node Completo (docker restart)

```bash
python3 reliability_tester.py \
  --component worker_node \
  --failure-method kill_worker_node_processes \
  --target local-k8s-worker2 \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ Container do nó volta, pods reiniciam
**Observação:** Todos os pods do nó param temporariamente

### 2.2 Kill Kubelet

```bash
python3 reliability_tester.py \
  --component worker_node \
  --failure-method kill_kubelet \
  --target local-k8s-worker2 \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ Container reinicia kubelet automaticamente
**Observação:** Não afeta outros nós

### 2.3 Delete kube-proxy Pod

```bash
python3 reliability_tester.py \
  --component worker_node \
  --failure-method delete_kube_proxy \
  --target local-k8s-worker2 \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ DaemonSet recria o pod automaticamente
**Observação:** Pode causar falhas temporárias de rede

### 2.4 Restart Container Runtime (containerd)

```bash
python3 reliability_tester.py \
  --component worker_node \
  --failure-method restart_containerd \
  --target local-k8s-worker2 \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ Nó inteiro reinicia
**Observação:** Em Kind, equivale a `docker restart <node>`

## 🎛️ 3. Testes de Control Plane

### 3.1 Restart Control Plane Completo

```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_control_plane_processes \
  --target local-k8s-control-plane \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ Container reinicia com todos os componentes
**Observação:** Cluster fica indisponível temporariamente

### 3.2 Kill kube-apiserver

```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_apiserver \
  --target local-k8s-control-plane \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ Static Pod reinicia automaticamente
**Observação:** API fica indisponível durante restart

### 3.3 Kill kube-controller-manager

```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_controller_manager \
  --target local-k8s-control-plane \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ Static Pod reinicia automaticamente
**Observação:** Recursos não são reconciliados enquanto estiver down

### 3.4 Kill kube-scheduler

```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_scheduler \
  --target local-k8s-control-plane \
  --iterations 2 \
  --interval 10
```

**Self-healing:** ✅ Static Pod reinicia automaticamente
**Observação:** Novos pods não são agendados até voltar

### 3.5 Kill etcd ⚠️

```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_etcd \
  --target local-k8s-control-plane \
  --iterations 2 \
  --interval 10 \
  --timeout extended
```

**Self-healing:** ✅ Static Pod reinicia automaticamente
**⚠️ ATENÇÃO:** Cluster fica "mudo" temporariamente, não aceita alterações
**Recomendação:** Use timeout `extended` (20 min)

## 📊 Tabela Completa de Métodos

| Componente                        | `--failure-method`             | `--component`   | Comando Sugerido                             | Self-healing |
| --------------------------------- | -------------------------------- | ----------------- | -------------------------------------------- | ------------ |
| **Container (all PIDs)**    | `kill_processes`               | `pod`           | `kill -9 -1`                               | ✅           |
| **Container (PID 1)**       | `kill_init`                    | `pod`           | `kill -9 1`                                | ✅           |
| **Worker Node**             | `kill_worker_node_processes`   | `worker_node`   | `docker restart <node>`                    | ✅           |
| **kubelet**                 | `kill_kubelet`                 | `worker_node`   | `pkill kubelet`                            | ✅           |
| **kube-proxy**              | `delete_kube_proxy`            | `worker_node`   | `kubectl delete pod -l k8s-app=kube-proxy` | ✅           |
| **containerd**              | `restart_containerd`           | `worker_node`   | `docker restart <node>`                    | ✅           |
| **Control Plane (todos)**   | `kill_control_plane_processes` | `control_plane` | `docker restart control-plane`             | ✅           |
| **kube-apiserver**          | `kill_kube_apiserver`          | `control_plane` | `pkill kube-apiserver`                     | ✅           |
| **kube-controller-manager** | `kill_kube_controller_manager` | `control_plane` | `pkill kube-controller`                    | ✅           |
| **kube-scheduler**          | `kill_kube_scheduler`          | `control_plane` | `pkill kube-scheduler`                     | ✅           |
| **etcd**                    | `kill_etcd`                    | `control_plane` | `pkill etcd`                               | ✅           |

## 🎯 Alvos Disponíveis

### Listar todos os alvos

```bash
python3 reliability_tester.py --list-targets
```

### Alvos típicos:

**Pods:**

- `test-app-549846444f-pbsgl`
- `foo-app-6898f5b49f-76c97`
- `bar-app-6495f959f6-wktz9`

**Worker Nodes:**

- `local-k8s-worker`
- `local-k8s-worker2`

**Control Plane:**

- `local-k8s-control-plane`

## ⏰ Configuração de Timeout

### Ver opções disponíveis

```bash
python3 reliability_tester.py --list-timeouts
```

### Opções:

- `quick`: 60s (1 min) - Testes rápidos
- `short`: 120s (2 min) - Casos rápidos
- `medium`: 300s (5 min) - Casos normais
- `long`: 600s (10 min) - **PADRÃO**
- `extended`: 1200s (20 min) - Casos críticos (etcd, control plane completo)

### Configurar globalmente

```bash
python3 reliability_tester.py --set-timeout extended
```

### Usar em comando específico

```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_etcd \
  --iterations 10 \
  --timeout extended
```

## 🧪 Testes Rápidos de Validação

### Pod (5 iterações)

```bash
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target test-app-549846444f-pbsgl \
  --iterations 5 \
  --interval 10
```

### Worker Node (5 iterações)

```bash
python3 reliability_tester.py \
  --component worker_node \
  --failure-method kill_kubelet \
  --target local-k8s-worker \
  --iterations 5 \
  --interval 30
```

### Control Plane (5 iterações)

```bash
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_apiserver \
  --target local-k8s-control-plane \
  --iterations 5 \
  --interval 30
```

## 📊 Resultados

### Localização dos CSVs

```
testes/2025/10/15/
├── realtime_reliability_test_pod_kill_processes_20251015_175500.csv
├── component_metrics_pod_kill_processes_20251015_180115.csv
└── ...
```

### CSV em Tempo Real ⭐

- Cada iteração é salva **imediatamente** após completar
- Não perde dados se interromper o teste
- Progressão visível durante a execução

### Métricas Incluídas

- **MTTR** (Mean Time To Recovery)
- **Taxa de sucesso**
- **Disponibilidade**
- **Desvio padrão**
- **Mediana, mínimo, máximo**

## 🔧 Comandos Auxiliares

```bash
# Ver configuração atual
python3 reliability_tester.py --show-config

# Listar timeouts
python3 reliability_tester.py --list-timeouts

# Listar alvos
python3 reliability_tester.py --list-targets

# Configurar timeout
python3 reliability_tester.py --set-timeout long
```

## 📁 Estrutura Modular

```
reliability_framework/
├── cli/                    # Interface de linha de comando
├── core/                   # Orquestrador principal
├── failure_injectors/      # Injetores de falha
│   ├── pod_injector.py
│   ├── node_injector.py
│   └── control_plane_injector.py  # ⭐ NOVO
├── monitoring/             # Monitoramento de saúde
├── reports/                # Geração de relatórios CSV
├── simulation/             # Simulação acelerada
└── utils/                  # Configuração e utilidades
```

## 🎓 Exemplos Práticos

### Suite Completa de Testes de Pod

```bash
# Teste 1: Kill all processes
python3 reliability_tester.py --component pod --failure-method kill_processes --target test-app-549846444f-pbsgl --iterations 30 --interval 60

# Teste 2: Kill init
python3 reliability_tester.py --component pod --failure-method kill_init --target test-app-549846444f-pbsgl --iterations 30 --interval 60

# Teste 3: Delete pod
python3 reliability_tester.py --component pod --failure-method delete_pod --target test-app-549846444f-pbsgl --iterations 30 --interval 60
```

### Suite Completa de Control Plane

```bash
# API Server
python3 reliability_tester.py --component control_plane --failure-method kill_kube_apiserver --iterations 15 --interval 90

# Controller Manager
python3 reliability_tester.py --component control_plane --failure-method kill_kube_controller_manager --iterations 15 --interval 90

# Scheduler
python3 reliability_tester.py --component control_plane --failure-method kill_kube_scheduler --iterations 15 --interval 90

# etcd (com timeout estendido)
python3 reliability_tester.py --component control_plane --failure-method kill_etcd --iterations 10 --interval 120 --timeout extended
```

## 📚 Recursos Adicionais

- `ALL_COMPONENTS_COMMANDS.sh` - Script bash com todos os comandos
- `COMMANDS_GUIDE.md` - Guia detalhado de comandos (no diretório do framework)
- `README.md` - Documentação completa do framework

## ✅ Funcionalidades Principais

1. ✅ **Modularização completa** - Código organizado e reutilizável
2. ✅ **CSV em tempo real** - Dados salvos durante execução
3. ✅ **Timeout configurável** - Ajuste para diferentes cenários
4. ✅ **Todos componentes** - Pod, Worker Node, Control Plane
5. ✅ **Self-healing** - Todos os métodos têm recuperação automática
6. ✅ **Flags originais mantidas** - Compatibilidade total

---

**Criado em:** 15 de Outubro de 2025
**Framework:** Reliability Testing for Kubernetes (Kind)
