#!/bin/bash

# Script de deploy Minikube seguindo padrão exato do deploy.sh original
# Replica todas as funcionalidades: setup, deploy, metallb, nginx, monitoring

set -e

# Configurações padrão
USE_UBUNTU=${USE_UBUNTU:-true}
KUBERNETES_DIR="src/scripts/kubernetes_ubuntu"
CLUSTER_NAME="minikube"
NAMESPACE="default"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

info() {
    echo -e "${BLUE}[DEPLOY]${NC} $1"
}

title() {
    echo -e "${CYAN}=== $1 ===${NC}"
}

# Verificar se Minikube está instalado
check_minikube() {
    if ! command -v minikube &> /dev/null; then
        error "Minikube não está instalado!"
        echo "Para instalar:"
        echo "  curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64"
        echo "  sudo install minikube-linux-amd64 /usr/local/bin/minikube"
        exit 1
    fi
    
    log "✅ Minikube encontrado: $(minikube version --short)"
}

# Garantir que kubectl funciona (similar ao ensure_kubectl_working original)
ensure_kubectl_working() {
    log "Verificando kubectl..."
    
    if ! command -v kubectl &> /dev/null; then
        error "kubectl não está instalado"
        return 1
    fi
    
    # Tentar usar kubectl
    if kubectl cluster-info &> /dev/null; then
        log "✅ kubectl funcionando corretamente"
        return 0
    fi
    
    # Se não funcionar, tentar configurar com Minikube
    if minikube status &> /dev/null; then
        log "Configurando kubectl para usar Minikube..."
        kubectl config use-context minikube
        
        if kubectl cluster-info &> /dev/null; then
            log "✅ kubectl configurado com sucesso"
            return 0
        fi
    fi
    
    error "kubectl não está funcionando"
    return 1
}

# Setup ambiente Minikube (equivale ao setup_local_environment)
setup_minikube_environment() {
    title "Configurando Ambiente Minikube"
    
    check_minikube
    
    # Verificar se já existe um cluster
    if minikube status &> /dev/null; then
        warn "Cluster Minikube já existe, recriando para garantir configuração limpa..."
        minikube delete
    fi
    
    log "🚀 Criando cluster Minikube..."
    
    # Criar cluster com configurações similares ao Kind
    minikube start \
        --driver=docker \
        --nodes=4 \
        --cpus=4 \
        --memory=8192 \
        --disk-size=40g \
        --kubernetes-version=v1.28.0 \
        --addons=ingress,dns,dashboard,metrics-server \
        --network-plugin=cni \
        --cni=calico \
        || {
            error "Falha ao criar cluster Minikube"
            exit 1
        }
    
    log "✅ Cluster Minikube criado com sucesso!"
    
    # Configurar kubectl context
    kubectl config use-context minikube
    
    # Verificar nodes
    log "📋 Verificando nodes do cluster..."
    kubectl get nodes -o wide
    
    # Habilitar registry add-on para multi-node
    log "🐳 Habilitando registry add-on..."
    minikube addons enable registry
    
    ensure_kubectl_working || {
        error "kubectl não está funcionando após setup"
        exit 1
    }
    
    log "✅ Ambiente Minikube configurado com sucesso!"
}

# Instalar MetalLB no Minikube
install_minikube_metallb() {
    title "Instalando MetalLB no Minikube"
    
    # Verificar se já está instalado
    if kubectl get namespace metallb-system &> /dev/null; then
        log "✅ MetalLB já está instalado"
        return 0
    fi
    
    log "📦 Instalando MetalLB..."
    kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.13.12/config/manifests/metallb-native.yaml
    
    # Aguardar MetalLB estar pronto
    log "⏳ Aguardando MetalLB estar pronto..."
    kubectl wait --namespace metallb-system \
        --for=condition=ready pod \
        --selector=app=metallb \
        --timeout=120s
    
    # Configurar pool de IPs para Minikube
    log "🌐 Configurando pool de IPs para MetalLB..."
    
    # Descobrir subnet do Minikube para configurar MetalLB
    MINIKUBE_IP=$(minikube ip)
    SUBNET_BASE=$(echo $MINIKUBE_IP | cut -d'.' -f1-3)
    
    cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: minikube-pool
  namespace: metallb-system
spec:
  addresses:
  - ${SUBNET_BASE}.200-${SUBNET_BASE}.250
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: minikube-l2
  namespace: metallb-system
EOF
    
    log "✅ MetalLB configurado com pool ${SUBNET_BASE}.200-250"
}

# Instalar NGINX Ingress no Minikube
install_minikube_nginx() {
    title "Configurando NGINX Ingress no Minikube"
    
    # Habilitar addon ingress do Minikube (já foi habilitado no start)
    log "✅ NGINX Ingress já habilitado via addon do Minikube"
    
    # Aguardar estar pronto
    log "⏳ Aguardando NGINX Ingress estar pronto..."
    kubectl wait --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=120s
    
    log "✅ NGINX Ingress configurado"
}

# Instalar stack de monitoramento
install_minikube_monitoring() {
    title "Instalando Stack de Monitoramento"
    
    # Verificar se já está instalado
    if kubectl get namespace monitoring &> /dev/null; then
        log "✅ Stack de monitoramento já está instalado"
        return 0
    fi
    
    # Verificar se Helm está instalado
    if ! command -v helm &> /dev/null; then
        log "📦 Instalando Helm..."
        curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    fi
    
    log "📊 Instalando Prometheus + Grafana..."
    
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
        --timeout=5m
    
    log "✅ Stack de monitoramento instalado"
}

# Deploy aplicações no Minikube (equivale ao deploy_local)
deploy_minikube_applications() {
    title "Fazendo Deploy das Aplicações no Minikube"
    
    ensure_kubectl_working || {
        error "kubectl não está funcionando. Execute primeiro: --minikube-setup"
        exit 1
    }
    
    # Instalar infraestrutura necessária
    install_minikube_metallb
    install_minikube_nginx
    install_minikube_monitoring
    
    # Deploy das aplicações
    info "📦 Aplicando deployments das aplicações..."
    kubectl apply -f src/scripts/kubernetes_ubuntu/local_deployment.yaml
    
    info "🌐 Aplicando services e ingress..."
    kubectl apply -f src/scripts/kubernetes_ubuntu/local_services.yaml
    
    # Aplicar metrics-server
    info "📊 Aplicando metrics-server..."
    kubectl apply -f src/scripts/kubernetes_ubuntu/metrics-server.yaml
    
    # Aguardar deployments estarem prontos
    info "⏳ Aguardando deployments estarem prontos..."
    kubectl rollout status deployment/foo-app --timeout=300s
    kubectl rollout status deployment/bar-app --timeout=300s
    kubectl rollout status deployment/test-app --timeout=300s
    
    # Aguardar pods estarem prontos
    log "⏳ Aguardando pods estarem prontos..."
    kubectl wait --for=condition=ready pod -l app=foo --timeout=180s
    kubectl wait --for=condition=ready pod -l app=bar --timeout=180s
    kubectl wait --for=condition=ready pod -l app=test --timeout=180s
    
    # Configurar port-forwards (similar ao original)
    setup_minikube_port_forwards
    
    log "✅ Deploy das aplicações concluído no Minikube!"
}

# Setup port-forwards para Minikube (similar ao setup_port_forwards)
setup_minikube_port_forwards() {
    title "Configurando Port-forwards para Minikube"
    
    log "Configurando port-forwards para acesso local..."
    
    # Parar port-forwards existentes
    stop_port_forwards
    
    # Aguardar um pouco para pods ficarem prontos
    sleep 5
    
    # Configurar port-forwards em background
    log "Iniciando port-forwards..."
    
    # Port-forward para foo-app
    if kubectl get service foo-loadbalancer &> /dev/null; then
        kubectl port-forward service/foo-loadbalancer 8080:80 > /dev/null 2>&1 &
        echo "FOO_PF_PID=$!" >> /tmp/portforward-pids.env
        log "✅ foo-app: http://localhost:8080/foo"
    fi
    
    # Port-forward para bar-app
    if kubectl get service bar-loadbalancer &> /dev/null; then
        kubectl port-forward service/bar-loadbalancer 8081:81 > /dev/null 2>&1 &
        echo "BAR_PF_PID=$!" >> /tmp/portforward-pids.env
        log "✅ bar-app: http://localhost:8081/bar"
    fi
    
    # Port-forward para test-app
    if kubectl get service test-loadbalancer &> /dev/null; then
        kubectl port-forward service/test-loadbalancer 8082:82 > /dev/null 2>&1 &
        echo "TEST_PF_PID=$!" >> /tmp/portforward-pids.env
        log "✅ test-app: http://localhost:8082/test"
    fi
    
    # Port-forwards para monitoramento (se existirem)
    if kubectl get service prometheus-server -n monitoring &> /dev/null; then
        kubectl port-forward service/prometheus-server 30082:80 -n monitoring > /dev/null 2>&1 &
        echo "PROM_PF_PID=$!" >> /tmp/portforward-pids.env
        log "✅ Prometheus: http://localhost:30082"
    fi
    
    if kubectl get service grafana -n monitoring &> /dev/null; then
        kubectl port-forward service/grafana 30081:80 -n monitoring > /dev/null 2>&1 &
        echo "GRAFANA_PF_PID=$!" >> /tmp/portforward-pids.env
        log "✅ Grafana: http://localhost:30081"
    fi
    
    log "Port-forwards configurados. PIDs salvos em /tmp/portforward-pids.env"
}

# Parar port-forwards
stop_port_forwards() {
    info "Parando port-forwards existentes..."
    
    # Parar port-forwards pelo PID se disponível
    if [ -f "/tmp/portforward-pids.env" ]; then
        source /tmp/portforward-pids.env
        [ -n "$FOO_PF_PID" ] && kill $FOO_PF_PID 2>/dev/null || true
        [ -n "$BAR_PF_PID" ] && kill $BAR_PF_PID 2>/dev/null || true
        [ -n "$TEST_PF_PID" ] && kill $TEST_PF_PID 2>/dev/null || true
        [ -n "$PROM_PF_PID" ] && kill $PROM_PF_PID 2>/dev/null || true
        [ -n "$GRAFANA_PF_PID" ] && kill $GRAFANA_PF_PID 2>/dev/null || true
        rm -f /tmp/portforward-pids.env
    fi
    
    # Parar todos os port-forwards kubectl como backup
    pkill -f "kubectl port-forward" 2>/dev/null || true
    
    log "Port-forwards parados"
}

# Limpar ambiente Minikube (equivale ao clean)
clean_minikube() {
    title "Limpando Ambiente Minikube"
    
    # Parar port-forwards
    stop_port_forwards
    
    if minikube status &> /dev/null; then
        log "🧹 Parando e removendo cluster Minikube..."
        minikube delete
        log "✅ Cluster Minikube removido"
    else
        log "ℹ️ Nenhum cluster Minikube ativo encontrado"
    fi
    
    # Limpar contextos kubectl
    kubectl config delete-context minikube 2>/dev/null || true
    kubectl config delete-cluster minikube 2>/dev/null || true
    kubectl config delete-user minikube 2>/dev/null || true
    
    log "✅ Ambiente Minikube limpo"
}

# Testar aplicações (similar ao run_tests)
test_minikube_applications() {
    title "Testando Aplicações no Minikube"
    
    ensure_kubectl_working || {
        error "kubectl não está funcionando"
        exit 1
    }
    
    log "� Verificando pods em execução..."
    kubectl get pods -o wide
    
    log "🌐 Verificando serviços..."
    kubectl get services
    
    # Aguardar um pouco para garantir que tudo está funcionando
    sleep 10
    
    # Testar endpoints via Minikube service
    log "🧪 Testando conectividade via Minikube..."
    
    # Usar minikube service para obter URLs
    minikube service list
    
    # Testar endpoints se port-forwards estão rodando
    if pgrep -f "kubectl port-forward" > /dev/null; then
        log "🧪 Testando endpoints locais..."
        
        if curl -s -f http://localhost:8080/foo > /dev/null 2>&1; then
            log "✅ /foo OK"
        else
            warn "⚠️ /foo com problemas (pode estar inicializando)"
        fi
        
        if curl -s -f http://localhost:8081/bar > /dev/null 2>&1; then
            log "✅ /bar OK"
        else
            warn "⚠️ /bar com problemas (pode estar inicializando)"
        fi
        
        if curl -s -f http://localhost:8082/test > /dev/null 2>&1; then
            log "✅ /test OK"
        else
            warn "⚠️ /test com problemas (pode estar inicializando)"
        fi
    else
        warn "Port-forwards não estão rodando. Execute --port-forwards"
    fi
    
    # Verificar HPA
    log "📊 Status do HPA:"
    kubectl get hpa 2>/dev/null || log "HPA não configurado"
    
    log "✅ Testes concluídos"
}

# Mostrar status (similar ao show_status)
show_minikube_status() {
    title "Status do Ambiente Minikube"
    
    if minikube status &> /dev/null; then
        log "🏠 Aplicações Ubuntu rodando no Minikube"
        log "🐧 Versão: Deployments Ubuntu (kubernetes_ubuntu/)"
        log "🌐 Acesso via localhost (port-forward):"
        log "   • foo: http://localhost:8080/foo"
        log "   • bar: http://localhost:8081/bar"
        log "   • test: http://localhost:8082/test"
        log "📊 Monitoramento: http://localhost:30081 (Grafana), http://localhost:30082 (Prometheus)"
        log "🧪 Teste HPA: bash /tmp/load_test.sh"
        log "🔄 Parar port-forwards: pkill -f 'kubectl port-forward'"
        
        # Mostrar informações do cluster
        log "📋 Informações do cluster:"
        kubectl get nodes
        kubectl get pods --all-namespaces | head -10
    else
        warn "Cluster Minikube não está rodando"
    fi
}

# Função principal
main() {
    case "${1:-help}" in
        --minikube-setup)
            setup_minikube_environment
            ;;
        --minikube-deploy)
            deploy_minikube_applications
            ;;
        --minikube-clean)
            clean_minikube
            ;;
        --minikube-test)
            test_minikube_applications
            ;;
        --minikube-status)
            show_minikube_status
            ;;
        --port-forwards)
            setup_minikube_port_forwards
            ;;
        --stop-port-forwards)
            stop_port_forwards
            ;;
        --minikube-full)
            log "🚀 Executando setup completo Minikube (setup + deploy + port-forwards)"
            setup_minikube_environment
            deploy_minikube_applications
            show_minikube_status
            log "✅ Setup completo concluído!"
            ;;
        help|--help)
            echo "Uso: $0 [OPTION]"
            echo ""
            echo "Opções Minikube (replica funcionalidades do deploy.sh):"
            echo "  --minikube-setup      Configura cluster Minikube (equivale a --local --setup)"
            echo "  --minikube-deploy     Deploy aplicações (equivale a --local --deploy --ubuntu)"
            echo "  --minikube-clean      Remove cluster (equivale a --clean)"
            echo "  --minikube-test       Testa aplicações (equivale a --test)"
            echo "  --minikube-status     Mostra status do ambiente"
            echo "  --port-forwards       Configura port-forwards"
            echo "  --stop-port-forwards  Para port-forwards"
            echo "  --minikube-full       Setup completo (setup + deploy + status)"
            echo ""
            echo "Exemplos:"
            echo "  $0 --minikube-setup     # Apenas configura cluster"
            echo "  $0 --minikube-deploy    # Apenas faz deploy"
            echo "  $0 --minikube-full      # Setup + deploy completo"
            echo "  $0 --minikube-clean     # Remove tudo"
            ;;
        *)
            error "Opção inválida: $1"
            $0 --help
            exit 1
            ;;
    esac
}

main "$@"