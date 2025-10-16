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

```bash
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target test-app-549846444f-pbsgl \
  --iterations 30 \
  --interval 60
```

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

| Componente                  | `--failure-method`             | `--component`   | Comando Sugerido                           | Self-healing |
| --------------------------- | ------------------------------ | --------------- | ------------------------------------------ | ------------ |
| **Container (all PIDs)**    | `kill_processes`               | `pod`           | `kill -9 -1`                               | ✅            |
| **Container (PID 1)**       | `kill_init`                    | `pod`           | `kill -9 1`                                | ✅            |
| **Pod inteiro**             | `delete_pod`                   | `pod`           | `kubectl delete pod`                       | ✅            |
| **Worker Node**             | `kill_worker_node_processes`   | `worker_node`   | `docker restart <node>`                    | ✅            |
| **kubelet**                 | `kill_kubelet`                 | `worker_node`   | `pkill kubelet`                            | ✅            |
| **kube-proxy**              | `delete_kube_proxy`            | `worker_node`   | `kubectl delete pod -l k8s-app=kube-proxy` | ✅            |
| **containerd**              | `restart_containerd`           | `worker_node`   | `docker restart <node>`                    | ✅            |
| **Control Plane (todos)**   | `kill_control_plane_processes` | `control_plane` | `docker restart control-plane`             | ✅            |
| **kube-apiserver**          | `kill_kube_apiserver`          | `control_plane` | `pkill kube-apiserver`                     | ✅            |
| **kube-controller-manager** | `kill_kube_controller_manager` | `control_plane` | `pkill kube-controller`                    | ✅            |
| **kube-scheduler**          | `kill_kube_scheduler`          | `control_plane` | `pkill kube-scheduler`                     | ✅            |
| **etcd**                    | `kill_etcd`                    | `control_plane` | `pkill etcd`                               | ✅            |

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
