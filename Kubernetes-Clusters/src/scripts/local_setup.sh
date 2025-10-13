#!/bin/bash

# Script para configurar ambiente Kubernetes local
# Autor: Sistema Híbrido AWS/Local
# Data: $(date)

set -e

# Configurações
AWS_ENABLED=${AWS_ENABLED:-false}
LOCAL_MODE=${LOCAL_MODE:-true}
CLUSTER_NAME="local-k8s"

echo "=== Configuração de Ambiente Kubernetes Local ==="
echo "AWS_ENABLED: $AWS_ENABLED"
echo "LOCAL_MODE: $LOCAL_MODE"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log "Verificando pré-requisitos..."
    
    # Verificar se está rodando no Ubuntu
    if [[ ! -f /etc/os-release ]] || ! grep -q "Ubuntu" /etc/os-release; then
        warn "Este script foi testado no Ubuntu. Outros sistemas podem ter problemas."
    fi
    
    # Verificar se tem privilégios sudo
    if ! sudo -n true 2>/dev/null; then
        error "Este script precisa de privilégios sudo. Execute: sudo -v"
        exit 1
    fi
    
    log "Pré-requisitos OK"
}

install_docker() {
    if command -v docker &> /dev/null; then
        log "Docker já está instalado"
        return 0
    fi
    
    log "Instalando Docker..."
    
    # Atualizar repositórios
    sudo apt-get update -y
    
    # Instalar dependências
    sudo apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # Adicionar chave GPG do Docker
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    
    # Adicionar repositório do Docker
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Instalar Docker
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Adicionar usuário ao grupo docker
    sudo usermod -aG docker $USER
    
    # Iniciar e habilitar Docker
    sudo systemctl start docker
    sudo systemctl enable docker
    
    log "Docker instalado com sucesso"
    warn "IMPORTANTE: Faça logout e login novamente para usar Docker sem sudo"
}

install_kind() {
    if command -v kind &> /dev/null; then
        log "kind já está instalado"
        return 0
    fi
    
    log "Instalando kind (Kubernetes in Docker)..."
    
    # Download kind
    curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
    chmod +x ./kind
    sudo mv ./kind /usr/local/bin/kind
    
    log "kind instalado com sucesso"
}

install_kubectl() {
    if command -v kubectl &> /dev/null; then
        log "kubectl já está instalado"
        return 0
    fi
    
    log "Instalando kubectl..."
    
    # Download kubectl
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    chmod +x kubectl
    sudo mv kubectl /usr/local/bin/
    
    # Configurar autocompletar
    echo 'source <(kubectl completion bash)' >> ~/.bashrc
    echo 'alias k=kubectl' >> ~/.bashrc
    echo 'complete -o default -F __start_kubectl k' >> ~/.bashrc
    
    log "kubectl instalado com sucesso"
}

install_helm() {
    if command -v helm &> /dev/null; then
        log "Helm já está instalado"
        return 0
    fi
    
    log "Instalando Helm..."
    
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    
    log "Helm instalado com sucesso"
}

create_kind_cluster() {
    # Verificar se cluster já existe
    if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
        log "Cluster ${CLUSTER_NAME} já existe"
        return 0
    fi
    
    log "Criando cluster Kubernetes local com kind..."
    
    # Criar arquivo de configuração do cluster
    cat <<EOF > /tmp/kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 30080
    protocol: TCP
  - containerPort: 443
    hostPort: 30443
    protocol: TCP
  - containerPort: 9090
    hostPort: 30082
    protocol: TCP
  - containerPort: 3000
    hostPort: 30081
    protocol: TCP
- role: worker
  labels:
    node-type: worker
- role: worker
  labels:
    node-type: worker
EOF

    # Criar cluster
    kind create cluster --config=/tmp/kind-config.yaml --name $CLUSTER_NAME
    
    # Configurar kubectl para usar o cluster
    kubectl cluster-info --context kind-$CLUSTER_NAME
    
    log "Cluster criado com sucesso"
}

install_metallb() {
    log "Instalando MetalLB (Load Balancer)..."
    
    # Verificar se já está instalado
    if kubectl get namespace metallb-system &> /dev/null; then
        log "MetalLB já está instalado"
        return 0
    fi
    
    # Instalar MetalLB
    kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.13.12/config/manifests/metallb-native.yaml
    
    # Aguardar MetalLB estar pronto
    log "Aguardando MetalLB estar pronto..."
    kubectl wait --namespace metallb-system \
        --for=condition=ready pod \
        --selector=app=metallb \
        --timeout=60s
    
    log "Configurando pool de IPs para MetalLB (172.18.255.200-172.18.255.250)..."
    
    # Aplicar configuração do MetalLB
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    kubectl apply -f "$SCRIPT_DIR/kubernetes/metallb-config.yaml"
    
    log "MetalLB configurado com sucesso"
}

install_nginx_ingress() {
    log "Instalando NGINX Ingress Controller..."
    
    # Verificar se já está instalado
    if kubectl get namespace ingress-nginx &> /dev/null; then
        log "NGINX Ingress já está instalado"
        return 0
    fi
    
    # Instalar NGINX Ingress Controller para kind
    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
    
    # Aguardar estar pronto
    log "Aguardando NGINX Ingress estar pronto..."
    kubectl wait --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=60s
    
    log "NGINX Ingress configurado com sucesso"
}

install_monitoring_stack() {
    log "Instalando stack de monitoramento (Prometheus + Grafana)..."
    
    # Verificar se já está instalado
    if kubectl get namespace monitoring &> /dev/null; then
        log "Stack de monitoramento já está instalado"
        return 0
    fi
    
    # Adicionar repositório do Prometheus
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo update
    
    # Instalar stack Prometheus
    helm install prometheus prometheus-community/kube-prometheus-stack \
        --namespace monitoring \
        --create-namespace \
        --set prometheus.service.type=NodePort \
        --set prometheus.service.nodePort=30082 \
        --set grafana.service.type=NodePort \
        --set grafana.service.nodePort=30081 \
        --set grafana.adminPassword=admin123 \
        --wait \
        --timeout=3m
    
    log "Stack de monitoramento instalado com sucesso"
}

show_cluster_info() {
    log "=== Informações do Cluster ==="
    echo ""
    
    echo "Contexto atual:"
    kubectl config current-context
    echo ""
    
    echo "Nós do cluster:"
    kubectl get nodes -o wide
    echo ""
    
    echo "Namespaces:"
    kubectl get namespaces
    echo ""
    
    echo "=== URLs de Acesso ==="
    echo "- Aplicações via Ingress: http://172.18.255.200 (use Header 'Host: localhost')"  
    echo "- Aplicações via LoadBalancer: IPs serão atribuídos pelo MetalLB"
    echo "- Prometheus: http://172.18.0.2:30082"
    echo "- Grafana: http://172.18.0.2:30081 (admin/admin123)"
    echo ""
    
    echo "=== Comandos Úteis ==="
    echo "- Ver todos os recursos: kubectl get all --all-namespaces"
    echo "- Logs do ingress: kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller"
    echo "- Testar conectividade: curl -H 'Host: localhost' http://172.18.255.200/foo"
    echo ""
}

cleanup_on_error() {
    error "Erro durante a instalação. Limpando recursos..."
    if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
        kind delete cluster --name $CLUSTER_NAME
    fi
    exit 1
}

main() {
    # Configurar trap para limpeza em caso de erro
    trap cleanup_on_error ERR
    
    if [ "$AWS_ENABLED" = "true" ]; then
        log "AWS_ENABLED=true - Pulando configuração local"
        return 0
    fi
    
    log "Iniciando configuração do ambiente Kubernetes local..."
    
    check_prerequisites
    install_docker
    install_kind
    install_kubectl
    install_helm
    create_kind_cluster
    install_metallb
    install_nginx_ingress
    install_monitoring_stack
    
    show_cluster_info
    
    log "=== Configuração concluída com sucesso! ==="
    log "Agora você pode executar: bash src/scripts/local_deploy.sh"
}

# Executar função principal
main "$@"