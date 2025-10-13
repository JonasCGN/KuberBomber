#!/bin/bash

# Script para fazer deploy das aplicações no cluster Kubernetes local
# Autor: Sistema Híbrido AWS/Local
# Data: $(date)

set -e

# Configurações
AWS_ENABLED=${AWS_ENABLED:-false}
CLUSTER_NAME="local-k8s"
NAMESPACE="default"
KUBERNETES_DIR=${KUBERNETES_DIR:-"src/scripts/kubernetes"}

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

check_prerequisites() {
    log "Verificando pré-requisitos para deploy local..."
    
    if [ "$AWS_ENABLED" = "true" ]; then
        warn "AWS_ENABLED=true detectado. Este script é para deploy local."
        warn "Para deploy AWS, use: cd src/main/java && mvn compile exec:java"
        exit 1
    fi
    
    # Verificar se kubectl está instalado
    if ! command -v kubectl &> /dev/null; then
        error "kubectl não encontrado. Execute primeiro: bash src/scripts/local_setup.sh"
        exit 1
    fi
    
    # Verificar se cluster local existe e está ativo
    if ! kubectl cluster-info --context $CLUSTER_NAME &> /dev/null; then
        error "Cluster local não encontrado ou não está ativo."
        error "Execute primeiro: bash src/scripts/local_setup.sh"
        exit 1
    fi
    
    # Usar contexto do cluster local
    kubectl config use-context $CLUSTER_NAME
    
    # Configurar Docker para usar daemon do minikube
    if command -v minikube &> /dev/null && minikube status -p $CLUSTER_NAME &> /dev/null; then
        eval $(minikube docker-env -p $CLUSTER_NAME)
        log "Docker configurado para usar daemon do minikube"
    fi
    
    log "Pré-requisitos OK - usando cluster minikube $CLUSTER_NAME"
}

wait_for_pods() {
    local app_name=$1
    local timeout=${2:-300}
    
    info "Aguardando pods da aplicação $app_name estarem prontos..."
    
    kubectl wait --for=condition=ready pod -l app=$app_name --timeout=${timeout}s || {
        error "Timeout aguardando pods da aplicação $app_name"
        kubectl get pods -l app=$app_name
        kubectl describe pods -l app=$app_name
        return 1
    }
    
    log "Pods da aplicação $app_name estão prontos"
}

deploy_applications() {
    info "=== Fazendo deploy das aplicações ==="
    info "Usando configurações do diretório: $KUBERNETES_DIR"
    
    # Aplicar deployments
    info "Aplicando deployments..."
    kubectl apply -f $KUBERNETES_DIR/local_deployment.yaml
    
    # Aplicar services e ingress
    info "Aplicando services e ingress..."
    kubectl apply -f $KUBERNETES_DIR/local_services.yaml
    
    # Aguardar todos os deployments estarem prontos
    info "Aguardando deployments estarem prontos..."
    kubectl rollout status deployment/foo-app --timeout=450s
    kubectl rollout status deployment/bar-app --timeout=450s
    kubectl rollout status deployment/test-app --timeout=450s
    
    # Aplicar metrics-server se não estiver funcionando
    info "Aplicando metrics-server corrigido..."
    kubectl apply -f $KUBERNETES_DIR/metrics-server.yaml

    # Aguardar pods estarem prontos
    wait_for_pods "foo"
    wait_for_pods "bar"
    wait_for_pods "test"
    
    log "Deploy das aplicações concluído"
}

configure_monitoring() {
    info "=== Configurando monitoramento ==="
    
    # Verificar se prometheus está instalado
    if ! kubectl get namespace monitoring &> /dev/null; then
        warn "Namespace monitoring não encontrado. Pulando configuração de monitoramento."
        warn "Execute: bash src/scripts/local_setup.sh para instalar stack completa"
        return 0
    fi
    
    # Aplicar ServiceMonitor se existir
    if [ -f "src/scripts/nodes/controlPlane/kubernetes/kub_monitoring.yaml" ]; then
        info "Aplicando configurações de monitoramento..."
        kubectl apply -f src/scripts/nodes/controlPlane/kubernetes/kub_monitoring.yaml
    fi
    
    log "Monitoramento configurado"
}

test_applications() {
    info "=== Testando aplicações ==="
    
    # Aguardar ingress estar pronto
    info "Aguardando NGINX Ingress estar pronto..."
    kubectl wait --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=60s
    
    # Aguardar um pouco mais para garantir que tudo está funcionando
    sleep 30
    
    # Testar via localhost (NodePort)
    info "Testando endpoints via localhost..."
    
    echo "Testando /foo:"
    if curl -s -f http://localhost:30080/foo > /dev/null; then
        echo "✅ /foo OK"
    else
        echo "❌ /foo com problemas"
    fi
    
    echo "Testando /bar:"
    if curl -s -f http://localhost:30080/bar > /dev/null; then
        echo "✅ /bar OK"
    else
        echo "❌ /bar com problemas"
    fi
    
    echo "Testando /test:"
    if curl -s -f http://localhost:30080/test > /dev/null; then
        echo "✅ /test OK"
    else
        echo "❌ /test com problemas"
    fi
    
    # Testar LoadBalancer services (MetalLB)
    info "Verificando LoadBalancer services..."
    
    # Aguardar IPs externos serem atribuídos
    kubectl get svc -l type=LoadBalancer -o wide
    
    # Obter IPs dos LoadBalancers
    FOO_LB_IP=$(kubectl get svc foo-loadbalancer -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    BAR_LB_IP=$(kubectl get svc bar-loadbalancer -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    TEST_LB_IP=$(kubectl get svc test-loadbalancer -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    
    if [ -n "$FOO_LB_IP" ] && [ "$FOO_LB_IP" != "null" ]; then
        echo "✅ foo-loadbalancer: http://$FOO_LB_IP"
    else
        echo "⏳ foo-loadbalancer: Aguardando IP externo..."
    fi
    
    if [ -n "$BAR_LB_IP" ] && [ "$BAR_LB_IP" != "null" ]; then
        echo "✅ bar-loadbalancer: http://$BAR_LB_IP"
    else
        echo "⏳ bar-loadbalancer: Aguardando IP externo..."
    fi
    
    if [ -n "$TEST_LB_IP" ] && [ "$TEST_LB_IP" != "null" ]; then
        echo "✅ test-loadbalancer: http://$TEST_LB_IP"
    else
        echo "⏳ test-loadbalancer: Aguardando IP externo..."
    fi
}

show_cluster_status() {
    info "=== Status do Cluster ==="
    echo ""
    
    echo "📊 Nós do cluster:"
    kubectl get nodes -o wide
    echo ""
    
    echo "🚀 Deployments:"
    kubectl get deployments
    echo ""
    
    echo "🔄 Pods:"
    kubectl get pods -o wide
    echo ""
    
    echo "🌐 Services:"
    kubectl get svc
    echo ""
    
    echo "🚪 Ingress:"
    kubectl get ingress
    echo ""
    
    echo "📈 HPA:"
    kubectl get hpa
    echo ""
    
    if kubectl get namespace monitoring &> /dev/null; then
        echo "📊 Monitoramento:"
        kubectl get pods -n monitoring
        echo ""
    fi
}

show_access_info() {
    info "=== URLs de Acesso ==="
    echo ""
    
    # Obter IP do control-plane
    CONTROL_PLANE_IP=$(kubectl get node local-k8s-control-plane -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
    
    echo "🌐 Aplicações via Ingress:"
    echo "   • http://$CONTROL_PLANE_IP/foo"
    echo "   • http://$CONTROL_PLANE_IP/bar"
    echo "   • http://$CONTROL_PLANE_IP/test"
    echo "   • Ou via LoadBalancer IP: http://172.18.255.200/foo, /bar, /test"
    echo ""
    
    echo "🌐 Aplicações via LoadBalancer (MetalLB):"
    FOO_LB_IP=$(kubectl get svc foo-loadbalancer -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    BAR_LB_IP=$(kubectl get svc bar-loadbalancer -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    TEST_LB_IP=$(kubectl get svc test-loadbalancer -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    
    if [ -n "$FOO_LB_IP" ] && [ "$FOO_LB_IP" != "null" ]; then
        echo "   • foo: http://$FOO_LB_IP"
    fi
    if [ -n "$BAR_LB_IP" ] && [ "$BAR_LB_IP" != "null" ]; then
        echo "   • bar: http://$BAR_LB_IP"
    fi
    if [ -n "$TEST_LB_IP" ] && [ "$TEST_LB_IP" != "null" ]; then
        echo "   • test: http://$TEST_LB_IP"
    fi
    echo ""
    
    if kubectl get namespace monitoring &> /dev/null; then
        echo "📊 Monitoramento:"
        echo "   • Prometheus: http://$CONTROL_PLANE_IP:30082"
        echo "   • Grafana: http://$CONTROL_PLANE_IP:30081 (admin/admin123)"
        echo ""
        echo "💡 Alternativa (Port-forward):"
        echo "   • kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80"
        echo "   • kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090"
        echo "   • Acesse: http://localhost:3000 (Grafana), http://localhost:9090 (Prometheus)"
        echo ""
    fi
    
    echo "🔧 Comandos úteis:"
    echo "   • Ver logs: kubectl logs -l app=foo"
    echo "   • Escalar: kubectl scale deployment foo-app --replicas=3"
    echo "   • Status HPA: kubectl get hpa"
    echo "   • Métricas de pods: kubectl top pods"
    echo "   • Deletar tudo: kubectl delete -f src/scripts/kubernetes/"
    echo ""
}

generate_load_test_script() {
    info "Gerando script de teste de carga..."
    
    cat << 'EOF' > /tmp/load_test.sh
#!/bin/bash

echo "=== Teste de Carga para HPA ==="

# URLs para teste
URLS=(
    "http://localhost:30080/foo"
    "http://localhost:30080/bar"
    "http://localhost:30080/test"
)

# Função para gerar carga
generate_load() {
    local url=$1
    local duration=${2:-60}
    local concurrent=${3:-5}
    
    echo "Gerando carga para $url por ${duration}s com ${concurrent} conexões concorrentes..."
    
    for i in $(seq 1 $concurrent); do
        {
            end_time=$((SECONDS + duration))
            while [ $SECONDS -lt $end_time ]; do
                curl -s "$url" > /dev/null 2>&1
                sleep 0.1
            done
        } &
    done
    
    wait
    echo "Carga finalizada para $url"
}

# Mostrar HPA inicial
echo "Estado inicial do HPA:"
kubectl get hpa

echo ""
echo "Gerando carga nas aplicações..."

# Gerar carga em paralelo
for url in "${URLS[@]}"; do
    generate_load "$url" 120 3 &
done

# Monitorar HPA durante o teste
echo ""
echo "Monitorando HPA (pressione Ctrl+C para parar):"
while true; do
    sleep 10
    echo "$(date): "
    kubectl get hpa
    echo "Pods:"
    kubectl get pods -l 'app in (foo,bar,test)'
    echo "---"
done
EOF
    
    chmod +x /tmp/load_test.sh
    log "Script de teste de carga criado em: /tmp/load_test.sh"
    log "Execute: bash /tmp/load_test.sh para testar HPA"
}

cleanup_on_error() {
    error "Erro durante o deploy. Verificando status..."
    kubectl get pods -o wide
    kubectl get events --sort-by=.metadata.creationTimestamp
}

main() {
    # Configurar trap para limpeza em caso de erro
    trap cleanup_on_error ERR
    
    log "=== Iniciando Deploy Local das Aplicações ==="
    
    check_prerequisites
    deploy_applications
    configure_monitoring
    test_applications
    show_cluster_status
    show_access_info
    generate_load_test_script
    
    log "=== Deploy local concluído com sucesso! ==="
    log ""
    log "🎉 Suas aplicações estão rodando!"
    log "📝 Execute 'kubectl get all' para ver todos os recursos"
    log "🧪 Execute 'bash /tmp/load_test.sh' para testar HPA"
}

# Executar função principal
main "$@"