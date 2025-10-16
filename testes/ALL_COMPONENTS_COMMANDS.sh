#!/bin/bash
"""
COMANDOS PARA TESTES DE CONFIABILIDADE - TODOS OS COMPONENTES
============================================================

Baseado na tabela de componentes e métodos de falha do Kubernetes/Kind.
Execute estes comandos para testar a confiabilidade de cada camada.

ESTRUTURA DO COMANDO:
python3 reliability_tester.py --component <tipo> --failure-method <método> --target <alvo> --iterations <n> --interval <s>
"""

# ============================================================
# 📦 POD / CONTAINER FAILURES
# ============================================================

echo "=== TESTES DE PODS E CONTAINERS ==="

# 1. Container de aplicação - kill all processes
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target test-app-549846444f-pbsgl \
  --iterations 30 \
  --interval 60

# 2. Container de aplicação - kill init process (PID 1)
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_init \
  --target test-app-549846444f-pbsgl \
  --iterations 30 \
  --interval 60

# 4. Teste em outro pod (foo-app)
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target foo-app-6898f5b49f-76c97 \
  --iterations 30 \
  --interval 60

# 5. Teste em outro pod (bar-app)
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target bar-app-6495f959f6-wktz9 \
  --iterations 30 \
  --interval 60


# ============================================================
# 🖥️ WORKER NODE FAILURES
# ============================================================

echo "=== TESTES DE WORKER NODES ==="

# 6. Worker Node - restart completo (docker restart)
python3 reliability_tester.py \
  --component worker_node \
  --failure-method kill_worker_node_processes \
  --target local-k8s-worker \
  --iterations 10 \
  --interval 120

# 7. Worker Node 2 - restart completo
python3 reliability_tester.py \
  --component worker_node \
  --failure-method kill_worker_node_processes \
  --target local-k8s-worker2 \
  --iterations 10 \
  --interval 120

# 8. Kubelet - kill process (reinicia automaticamente)
python3 reliability_tester.py \
  --component worker_node \
  --failure-method kill_kubelet \
  --target local-k8s-worker \
  --iterations 15 \
  --interval 90

# 9. kube-proxy - delete pod (DaemonSet recria)
python3 reliability_tester.py \
  --component worker_node \
  --failure-method delete_kube_proxy \
  --target local-k8s-worker \
  --iterations 15 \
  --interval 90

# 10. Container Runtime (containerd) - restart nó inteiro
python3 reliability_tester.py \
  --component worker_node \
  --failure-method restart_containerd \
  --target local-k8s-worker \
  --iterations 10 \
  --interval 120


# ============================================================
# 🎛️ CONTROL PLANE FAILURES
# ============================================================

echo "=== TESTES DE CONTROL PLANE ==="

# 11. Control Plane - restart completo (todos processos)
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_control_plane_processes \
  --target local-k8s-control-plane \
  --iterations 10 \
  --interval 120

# 12. kube-apiserver - kill process (static pod reinicia)
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_apiserver \
  --target local-k8s-control-plane \
  --iterations 15 \
  --interval 90

# 13. kube-controller-manager - kill process (static pod reinicia)
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_controller_manager \
  --target local-k8s-control-plane \
  --iterations 15 \
  --interval 90

# 14. kube-scheduler - kill process (static pod reinicia)
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_scheduler \
  --target local-k8s-control-plane \
  --iterations 15 \
  --interval 90

# 15. etcd - kill process (static pod reinicia) ⚠️ CUIDADO: cluster fica indisponível
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_etcd \
  --target local-k8s-control-plane \
  --iterations 10 \
  --interval 120 \
  --timeout extended


# ============================================================
# 🚀 TESTES RÁPIDOS (5 iterações para validação)
# ============================================================

echo "=== TESTES RÁPIDOS DE VALIDAÇÃO ==="

# Pod test rápido
python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target test-app-549846444f-pbsgl \
  --iterations 5 \
  --interval 10

# Worker node test rápido
python3 reliability_tester.py \
  --component worker_node \
  --failure-method kill_kubelet \
  --target local-k8s-worker \
  --iterations 5 \
  --interval 30

# Control plane test rápido
python3 reliability_tester.py \
  --component control_plane \
  --failure-method kill_kube_apiserver \
  --target local-k8s-control-plane \
  --iterations 5 \
  --interval 30


# ============================================================
# 📊 COMANDOS AUXILIARES
# ============================================================

echo "=== COMANDOS AUXILIARES ==="

# Listar todos os alvos disponíveis
python3 reliability_tester.py --list-targets

# Ver opções de timeout
python3 reliability_tester.py --list-timeouts

# Configurar timeout para testes longos
python3 reliability_tester.py --set-timeout extended

# Ver configuração atual
python3 reliability_tester.py --show-config


# ============================================================
# 📋 TABELA DE REFERÊNCIA
# ============================================================

cat << 'EOF'

TABELA DE MÉTODOS DE FALHA DISPONÍVEIS:
========================================

| Camada          | Componente                       | --failure-method               | --component       | Self-healing |
|-----------------|----------------------------------|--------------------------------|-------------------|--------------|
| Worker Node     | Nó inteiro                       | kill_worker_node_processes     | worker_node       | ✅ Sim        |
| Worker Node     | kubelet                          | kill_kubelet                   | worker_node       | ✅ Sim        |
| Worker Node     | kube-proxy                       | delete_kube_proxy              | worker_node       | ✅ Sim        |
| Worker Node     | Container Runtime (containerd)   | restart_containerd             | worker_node       | ✅ Sim        |
| Control Plane   | Nó inteiro                       | kill_control_plane_processes   | control_plane     | ✅ Sim        |
| Control Plane   | kube-apiserver                   | kill_kube_apiserver            | control_plane     | ✅ Sim        |
| Control Plane   | kube-controller-manager          | kill_kube_controller_manager   | control_plane     | ✅ Sim        |
| Control Plane   | kube-scheduler                   | kill_kube_scheduler            | control_plane     | ✅ Sim        |
| Control Plane   | etcd                             | kill_etcd                      | control_plane     | ✅ Sim        |
| Pods/Containers | Container de aplicação (PID all) | kill_processes                 | pod               | ✅ Sim        |
| Pods/Containers | Container de aplicação (PID 1)   | kill_init                      | pod               | ✅ Sim        |
| Pods/Containers | Pod inteiro                      | delete_pod                     | pod               | ✅ Sim        |

ALVOS DISPONÍVEIS (obtidos com --list-targets):
================================================

Pods:
  - test-app-549846444f-pbsgl
  - foo-app-6898f5b49f-76c97
  - bar-app-6495f959f6-wktz9

Worker Nodes:
  - local-k8s-worker
  - local-k8s-worker2

Control Plane:
  - local-k8s-control-plane

OPÇÕES DE TIMEOUT:
==================

  quick: 60s (1 min)
  short: 120s (2 min)
  medium: 300s (5 min)
  long: 600s (10 min) [PADRÃO]
  extended: 1200s (20 min)

EXEMPLOS PRÁTICOS:
==================

# Teste completo de um pod (30 iterações)
python3 reliability_tester.py --component pod --failure-method kill_processes --target test-app-549846444f-pbsgl --iterations 30 --interval 60

# Teste de control plane com timeout estendido
python3 reliability_tester.py --component control_plane --failure-method kill_etcd --iterations 10 --interval 120 --timeout extended

# Teste rápido de worker node (5 iterações)
python3 reliability_tester.py --component worker_node --failure-method kill_kubelet --target local-k8s-worker --iterations 5 --interval 30

EOF
