# Explicação Completa da Arquitetura Kubernetes neste Projeto

## 1. O que é Kind e para que serve

**Kind (Kubernetes IN Docker)** = ferramenta que cria clusters Kubernetes usando containers Docker como "nós".

- Cada nó (control-plane, worker, worker2) é um **container Docker**.
- Roda Kubernetes completo localmente sem precisar de VMs.
- Perfeito para desenvolvimento, testes e CI/CD.

```bash
# No seu caso, kind cria 3 containers:
# - local-k8s-control-plane (master)
# - local-k8s-worker (worker 1)
# - local-k8s-worker2 (worker 2)
```

## 2. Estrutura dos Nós (Nodes)

### Control Plane (Master Node)
**Container**: `local-k8s-control-plane`

Componentes que rodam nele:
- **kube-apiserver**: API REST que recebe todos os comandos kubectl
- **etcd**: banco de dados distribuído que guarda estado do cluster
- **kube-scheduler**: decide em qual worker agendar novos pods
- **kube-controller-manager**: garante estado desejado (replicas, endpoints, etc)
- **cloud-controller-manager**: integração com provedor cloud (AWS no seu caso)

### Worker Nodes
**Containers**: `local-k8s-worker`, `local-k8s-worker2`

Componentes que rodam neles:
- **kubelet**: agente que executa pods e reporta status ao control plane
- **kube-proxy**: gerencia regras de rede (iptables) para Services
- **Container Runtime**: containerd/Docker que executa os containers dos pods

## 3. Fluxo de Deploy Local (./deploy.sh --local)

### Passo 1: Setup (`src/scripts/local_setup.sh`)
```bash
# 1. Instala dependências (Docker, kind, kubectl, helm)
# 2. Cria cluster kind com 1 control-plane + 2 workers
kind create cluster --name local-k8s --config kind-config.yaml

# 3. Instala MetalLB (Load Balancer para bare metal)
kubectl apply -f https://raw.githubusercontent.com/.../metallb-native.yaml

# 4. Configura pool de IPs (ex: 172.18.255.200-172.18.255.250)
kubectl apply -f src/scripts/kubernetes/metallb-config.yaml

# 5. Instala Metrics Server (para HPA funcionar)
kubectl apply -f https://github.com/.../metrics-server.yaml

# 6. Instala Prometheus + Grafana (monitoramento)
helm install prometheus prometheus-community/kube-prometheus-stack
```

### Passo 2: Deploy (`src/scripts/local_deploy.sh`)
```bash
# 1. Build da imagem Docker da aplicação
docker build -t testapp:latest src/scripts/testapp/

# 2. Carrega imagem no kind (containers precisam ter acesso)
kind load docker-image testapp:latest --name local-k8s

# 3. Aplica manifestos Kubernetes
kubectl apply -f src/scripts/kubernetes/local_deployment.yaml
kubectl apply -f src/scripts/kubernetes/local_services.yaml
```

## 4. Estrutura dos Manifestos Kubernetes

### Deployment (`src/scripts/kubernetes/local_deployment.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: foo-app
spec:
  replicas: 2  # 2 pods iniciais
  template:
    spec:
      containers:
      - name: foo
        image: testapp:latest
        ports:
        - containerPort: 5000
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
---
# Similar para bar-app e test-app
```

**O que acontece**:
1. Scheduler vê que precisa criar 2 réplicas de `foo-app`
2. Escolhe workers com recursos disponíveis
3. kubelet em cada worker puxa a imagem `testapp:latest`
4. Cria containers e inicia processo `python server.py`

### Service (`src/scripts/kubernetes/local_services.yaml`)
```yaml
apiVersion: v1
kind: Service
metadata:
  name: foo-service
spec:
  type: LoadBalancer  # MetalLB vai alocar IP externo
  selector:
    app: foo  # Seleciona pods com label app=foo
  ports:
  - port: 80
    targetPort: 5000  # Porta do container
---
# Similar para bar-service (porta 81) e test-service (porta 82)
```

**O que acontece**:
1. MetalLB aloca IP do pool (ex: 172.18.255.202)
2. kube-proxy configura iptables em todos os nodes
3. Tráfego em `172.18.255.202:80` → encaminhado para pods `foo-app:5000`
4. Load balancing automático entre as réplicas

## 5. Comunicação entre Componentes

### Fluxo de Requisição HTTP

```
Cliente (você)
    ↓ curl http://172.18.255.202:80/foo
MetalLB (IP externo 172.18.255.202)
    ↓ iptables redirect
kube-proxy (worker node)
    ↓ round-robin
Pod foo-app-xxxxx (container testapp:5000)
    ↓ python server.py
Resposta HTTP 200 OK
```

### Comunicação Interna do Cluster

```
kubectl (seu terminal)
    ↓ HTTPS
kube-apiserver (control-plane)
    ↓ gRPC
kubelet (worker)
    ↓ CRI (Container Runtime Interface)
containerd
    ↓ runc
Container Linux (processo isolado)
```

### Monitoramento

```
Prometheus (scrape)
    ↓ HTTP :8080/metrics
kubelet (cAdvisor embutido)
    ↓ lê cgroups
Métricas CPU/Mem dos containers
    ↓
Grafana Dashboard
```

## 6. Horizontal Pod Autoscaler (HPA)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: foo-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: foo-app
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50  # 50% CPU
```

**Como funciona**:
1. Metrics Server coleta uso de CPU a cada 15s
2. HPA Controller verifica se CPU > 50%
3. Se sim, calcula: `réplicas_novas = réplicas_atuais × (uso_atual / target)`
4. Atualiza Deployment para escalar
5. Scheduler agenda novos pods em workers disponíveis

## 7. Rede no Kind

### Rede Docker (kind)
```
docker network inspect kind
# Nome: kind
# Subnet: 172.18.0.0/16
# Gateway: 172.18.0.1

# Containers:
# - local-k8s-control-plane: 172.18.0.2
# - local-k8s-worker: 172.18.0.3
# - local-k8s-worker2: 172.18.0.4
```

### Rede Kubernetes (CNI - kindnet)
```
# Pod Network (interno): 10.244.0.0/16
# - Pods no worker1: 10.244.1.0/24
# - Pods no worker2: 10.244.2.0/24

# Service Network: 10.96.0.0/12
# - ClusterIP Services recebem IPs deste range
# - kube-dns: 10.96.0.10
```

### MetalLB (IPs externos)
```
# Pool configurado: 172.18.255.200-172.18.255.250
# Services tipo LoadBalancer recebem IPs deste pool
# Exemplo:
# - foo-service: 172.18.255.202:80
# - bar-service: 172.18.255.202:81
# - test-service: 172.18.255.202:82
```

## 8. Comparação Local vs AWS

### Modo Local (kind)
```bash
./deploy.sh --local

# Infraestrutura:
# - Nodes: containers Docker
# - Networking: Docker network + kindnet CNI
# - Load Balancer: MetalLB
# - Storage: emptyDir / hostPath
# - Custo: $0

# Acesso:
# - http://172.18.255.202:80/foo
# - http://172.18.255.202:81/bar
```

### Modo AWS (CDK)
```bash
./deploy.sh --aws

# Infraestrutura:
# - Nodes: EC2 instances (t3.medium)
# - Networking: VPC + Subnets + Security Groups
# - Load Balancer: AWS ELB/ALB
# - Storage: EBS volumes
# - Custo: ~$50-100/mês

# Stack CDK cria:
# - VPC com subnets públicas/privadas
# - Auto Scaling Groups para workers
# - NAT Gateway para acesso internet
# - Route53 para DNS (opcional)
```

## 9. Teste de Carga (HPA)

Script gerado: load_test.sh

```bash
#!/bin/bash
# Gera requisições para testar HPA

for i in {1..1000}; do
  curl -s http://172.18.255.202:80/foo > /dev/null &
done

# Watch HPA escalar:
kubectl get hpa -w

# Resultado esperado:
# foo-hpa  Deployment/foo-app  50%/50%  2  10  2  0s
# foo-hpa  Deployment/foo-app  87%/50%  2  10  2  15s
# foo-hpa  Deployment/foo-app  87%/50%  2  10  4  30s  # Escalou!
```

## 10. Comandos Úteis de Debug

```bash
# Ver todos os recursos
kubectl get all -A

# Logs de um pod
kubectl logs -f <pod-name>

# Entrar em um pod
kubectl exec -it <pod-name> -- /bin/bash

# Ver eventos do cluster
kubectl get events --sort-by='.lastTimestamp'

# Ver uso de recursos
kubectl top nodes
kubectl top pods

# Verificar endpoints dos services
kubectl get endpoints

# Ver configuração do MetalLB
kubectl get ipaddresspool -n metallb-system

# Inspecionar iptables (dentro de um node)
docker exec local-k8s-worker iptables -t nat -L -n -v
```

## Resumo da Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Host (seu PC)                 │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │                 Docker Network (kind)             │  │
│  │                    172.18.0.0/16                  │  │
│  │                                                   │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │   Control Plane (container)                  │ │  │
│  │  │   - kube-apiserver                           │ │  │
│  │  │   - etcd                                     │ │  │
│  │  │   - scheduler                                │ │  │
│  │  │   - controller-manager                       │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                   │  │
│  │  ┌──────────────────┐        ┌──────────────────┐ │  │
│  │  │  Worker 1        │        │  Worker 2        │ │  │
│  │  │  - kubelet       │        │  - kubelet       │ │  │
│  │  │  - kube-proxy    │        │  - kube-proxy    │ │  │
│  │  │  - containerd    │        │  - containerd    │ │  │
│  │  │                  │        │                  │ │  │
│  │  │  Pods:           │        │  Pods:           │ │  │
│  │  │  • foo-app-xxx   │        │  • bar-app-yyy   │ │  │
│  │  │  • test-app-zzz  │        │  • prometheus    │ │  │
│  │  └──────────────────┘        └──────────────────┘ │  │
│  │                                                   │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │  MetalLB (Load Balancer)                     │ │  │
│  │  │  IP Pool: 172.18.255.200-250                 │ │  │
│  │  │  Services:                                   │ │  │
│  │  │  • foo-service → 172.18.255.201:80           │ │  │
│  │  │  • bar-service → 172.18.255.202:81           │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Você (navegador/curl) → http://172.18.255.201:80/foo   │
└─────────────────────────────────────────────────────────┘
```