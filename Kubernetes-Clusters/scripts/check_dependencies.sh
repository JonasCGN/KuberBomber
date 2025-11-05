#!/bin/bash

# Script para verificar e instalar dependências para Minikube

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

info() {
    echo -e "${BLUE}[CHECK]${NC} $1"
}

check_and_install_minikube() {
    info "Verificando Minikube..."
    
    if command -v minikube &> /dev/null; then
        log "✅ Minikube já instalado: $(minikube version --short)"
        return 0
    fi
    
    warn "Minikube não encontrado. Instalando..."
    
    # Download e instalação do Minikube
    curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
    sudo install minikube-linux-amd64 /usr/local/bin/minikube
    rm minikube-linux-amd64
    
    if command -v minikube &> /dev/null; then
        log "✅ Minikube instalado com sucesso: $(minikube version --short)"
    else
        error "❌ Falha na instalação do Minikube"
        exit 1
    fi
}

check_docker() {
    info "Verificando Docker..."
    
    if command -v docker &> /dev/null; then
        if docker ps &> /dev/null; then
            log "✅ Docker funcionando corretamente"
        else
            error "❌ Docker não está rodando. Execute: sudo systemctl start docker"
            exit 1
        fi
    else
        error "❌ Docker não está instalado"
        exit 1
    fi
}

check_kubectl() {
    info "Verificando kubectl..."
    
    if command -v kubectl &> /dev/null; then
        log "✅ kubectl já instalado: $(kubectl version --client --short)"
    else
        warn "kubectl não encontrado. Instalando..."
        
        # Download e instalação do kubectl
        curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
        sudo install kubectl /usr/local/bin/kubectl
        rm kubectl
        
        log "✅ kubectl instalado com sucesso"
    fi
}

main() {
    echo "🔍 Verificando dependências para Minikube..."
    echo ""
    
    check_docker
    check_kubectl
    check_and_install_minikube
    
    echo ""
    log "✅ Todas as dependências verificadas!"
    echo ""
    echo "Para usar Minikube, execute:"
    echo "  make run_minikube_full    # Setup completo"
    echo "  make run_minikube_setup   # Apenas criar cluster"
    echo "  make run_minikube_clean   # Limpar ambiente"
}

main "$@"