#!/bin/bash

# Script principal para deploy híbrido AWS/Local
# Autor: Sistema Híbrido AWS/Local
# Data: $(date)

set -e

# Configurações padrão
AWS_ENABLED=${AWS_ENABLED:-false}
ENVIRONMENT=${ENVIRONMENT:-local}
USE_UBUNTU=${USE_UBUNTU:-false}

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

show_help() {
    echo "Uso: $0 [OPTIONS]"
    echo ""
    echo "Este script permite fazer deploy das aplicações tanto localmente quanto na AWS."
    echo ""
    echo "OPTIONS:"
    echo "  --aws              Habilita modo AWS (cria recursos na nuvem)"
    echo "  --local            Força modo local (usa minikube/Docker)"
    echo "  --ubuntu           Usa deployments da versão Ubuntu (kubernetes_ubuntu/)"
    echo "  --setup            Apenas configura ambiente (não faz deploy)"
    echo "  --deploy           Apenas faz deploy (assume ambiente já configurado)"
    echo "  --test             Executa testes após deploy"
    echo "  --clean            Remove recursos existentes antes do deploy"
    echo "  --help             Mostra esta ajuda"
    echo ""
    echo "Variáveis de ambiente:"
    echo "  AWS_ENABLED=true|false    - Controla se usa AWS ou local"
    echo "  ENVIRONMENT=local|aws     - Define o ambiente de deploy"
    echo "  USE_UBUNTU=true|false     - Controla se usa deployments Ubuntu"
    echo ""
    echo "Exemplos:"
    echo "  $0                        # Deploy local (padrão)"
    echo "  $0 --aws                  # Deploy na AWS"
    echo "  $0 --local --setup        # Apenas configura ambiente local"
    echo "  $0 --aws --deploy         # Apenas deploy AWS (CDK já configurado)"
    echo "  $0 --ubuntu               # Deploy local com versão Ubuntu"
    echo "  $0 --local --ubuntu --test # Deploy local Ubuntu com testes"
    echo "  AWS_ENABLED=true $0       # Deploy AWS via variável de ambiente"
    echo ""
    echo "Pré-requisitos:"
    echo "  Local: Docker, minikube, kubectl, helm"
    echo "  AWS: AWS CLI configurado, CDK, Maven, Java"
}

parse_args() {
    SETUP_ONLY=false
    DEPLOY_ONLY=false
    RUN_TESTS=false
    CLEAN_FIRST=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --aws)
                export AWS_ENABLED=true
                export ENVIRONMENT=aws
                shift
                ;;
            --local)
                export AWS_ENABLED=false
                export ENVIRONMENT=local
                shift
                ;;
            --ubuntu)
                export USE_UBUNTU=true
                shift
                ;;
            --setup)
                SETUP_ONLY=true
                shift
                ;;
            --deploy)
                DEPLOY_ONLY=true
                shift
                ;;
            --test)
                RUN_TESTS=true
                shift
                ;;
            --clean)
                CLEAN_FIRST=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                error "Opção desconhecida: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

check_prerequisites_aws() {
    log "Verificando pré-requisitos para AWS..."
    
    # Verificar AWS CLI
    if ! command -v aws &> /dev/null; then
        error "AWS CLI não encontrado. Instale: https://aws.amazon.com/cli/"
        exit 1
    fi
    
    # Verificar se AWS está configurado
    if ! aws sts get-caller-identity &> /dev/null; then
        error "AWS CLI não está configurado. Execute: aws configure"
        exit 1
    fi
    
    # Verificar CDK
    if ! command -v cdk &> /dev/null; then
        error "AWS CDK não encontrado. Instale: npm install -g aws-cdk"
        exit 1
    fi
    
    # Verificar Maven
    if ! command -v mvn &> /dev/null; then
        error "Maven não encontrado. Instale: apt install maven (como root)"
        exit 1
    fi
    
    # Verificar Java
    if ! command -v java &> /dev/null; then
        error "Java não encontrado. Instale: apt install openjdk-11-jdk (como root)"
        exit 1
    fi
    
    log "Pré-requisitos AWS OK"
}

ensure_kubectl_working() {
    # Função robusta para garantir que kubectl funcione
    
    # 1) Verificar se kubectl está instalado (path)
    if ! command -v kubectl &> /dev/null; then
        warn "kubectl não encontrado no PATH"
    else
        # se houver um kubeconfig em ~/.kube/config, exportar para consistência
        if [ -z "$KUBECONFIG" ] && [ -f "$HOME/.kube/config" ]; then
            export KUBECONFIG="$HOME/.kube/config"
        fi

        # Tentar obter nós (servidor) com timeout curto
        if kubectl get nodes --request-timeout='5s' &> /dev/null; then
            log "kubectl disponível e conectado ao cluster"
            return 0
        else
            warn "kubectl instalado, mas sem conexão com o servidor (cluster) ou timeout"
        fi
    fi

    warn "Tentando recuperar kubeconfig via minikube..."

    # Garantir que Docker funciona (necessário para minikube)
    if ! docker ps &> /dev/null; then
        warn "Docker não está acessível. Possíveis soluções:"
        warn "1. Iniciar Docker: systemctl start docker (como root)"
        warn "2. Adicionar usuário ao grupo: usermod -aG docker $USER (como root)"
        warn "3. Fazer logout/login para aplicar grupo docker"
        warn "4. Ou executar: newgrp docker"
        warn ""
        warn "Tentando continuar mesmo assim..."
    fi

    # Verificar se minikube está instalado
    if ! command -v minikube &> /dev/null; then
        error "minikube não está instalado"
        return 1
    fi

    # Obter clusters disponíveis via minikube
    clusters=$(minikube profile list -o json 2>/dev/null | grep -o '"name":"[^"]*"' | cut -d'"' -f4 || echo "")
    if [ -z "$clusters" ]; then
        warn "Nenhum cluster minikube encontrado"
        return 1
    fi

    cluster=$(echo "$clusters" | head -n1)

    mkdir -p "$HOME/.kube"

    # backup do config existente
    if [ -f "$HOME/.kube/config" ]; then
        cp "$HOME/.kube/config" "$HOME/.kube/config.backup.$(date +%s)" 2>/dev/null || true
    fi

    # recuperar kubeconfig do minikube
    if minikube kubectl --profile="$cluster" -- config view --raw > "$HOME/.kube/config" 2>/dev/null; then
        chmod 600 "$HOME/.kube/config" 2>/dev/null || true
        export KUBECONFIG="$HOME/.kube/config"

        if kubectl get nodes --request-timeout='5s' &> /dev/null; then
            log "✅ kubectl auto-recuperado com sucesso (minikube)"
            return 0
        fi
    fi

    error "❌ Não foi possível recuperar kubectl"
    return 1
}

check_prerequisites_local() {
    log "Verificando pré-requisitos para ambiente local..."
    
    # Verificar Docker
    if ! command -v docker &> /dev/null; then
        warn "Docker não encontrado. Será instalado automaticamente."
    elif ! docker ps &> /dev/null; then
        warn "Docker não está rodando ou usuário não tem permissões."
        warn "Execute manualmente: systemctl start docker (como root)"
        warn "E adicione seu usuário ao grupo docker: usermod -aG docker $USER (como root)"
    fi
    
    # SEMPRE garantir que kubectl funcione - NUNCA MAIS ERRO!
    ensure_kubectl_working || warn "kubectl pode precisar de configuração manual"
    
    log "Pré-requisitos locais verificados"
}

setup_aws_environment() {
    title "Configurando Ambiente AWS"
    
    info "Verificando se CDK está inicializado..."
    
    # Obter account ID e region
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    REGION=$(aws configure get region || echo "us-east-1")
    
    info "Account: $ACCOUNT_ID"
    info "Region: $REGION"
    
    # Verificar se CDK está inicializado
    if ! cdk ls &> /dev/null; then
        info "Inicializando CDK..."
        cdk bootstrap aws://$ACCOUNT_ID/$REGION
    fi
    
    log "Ambiente AWS configurado"
}

setup_local_environment() {
    title "Configurando Ambiente Local"
    
    if [ ! -f "src/scripts/local_setup.sh" ]; then
        error "Script de setup local não encontrado: src/scripts/local_setup.sh"
        exit 1
    fi
    
    info "Executando configuração local..."
    bash src/scripts/local_setup.sh
    
    log "Ambiente local configurado"
}

deploy_aws() {
    title "Fazendo Deploy na AWS"
    
    info "Compilando código Java..."
    cd src/main/java
    mvn compile
    
    info "Executando deploy CDK..."
    mvn exec:java -Dexec.mainClass="com.myorg.BaseInfrastructureApp"
    
    cd ../../..
    
    log "Deploy AWS concluído"
}

deploy_local() {
    title "Fazendo Deploy Local"
    
    # SEMPRE garantir kubectl funciona antes de qualquer operação
    ensure_kubectl_working || {
        error "kubectl não está funcionando. Execute primeiro: ./deploy.sh --local --setup"
        exit 1
    }
    
    if [ ! -f "src/scripts/local_deploy.sh" ]; then
        error "Script de deploy local não encontrado: src/scripts/local_deploy.sh"
        exit 1
    fi
    
    # Definir qual pasta de kubernetes usar
    if [ "$USE_UBUNTU" = "true" ]; then
        info "Executando deploy local com configurações Ubuntu..."
        export KUBERNETES_DIR="src/scripts/kubernetes_ubuntu"
    else
        info "Executando deploy local com configurações padrão..."
        export KUBERNETES_DIR="src/scripts/kubernetes"
    fi
    
    bash src/scripts/local_deploy.sh
    
    log "Deploy local concluído"
}

run_tests() {
    title "Executando Testes"
    
    if [ "$AWS_ENABLED" = "true" ]; then
        info "Executando testes AWS..."
        # Aqui você pode adicionar testes específicos para AWS
        warn "Testes AWS não implementados ainda"
    else
        info "Executando testes locais..."
        
        # Aguardar um pouco para garantir que tudo está funcionando
        sleep 10
        
        # Testar endpoints básicos
        echo "Testando endpoints..."
        
        if curl -s -f http://172.18.255.202:80/foo > /dev/null; then
            echo "✅ /foo OK"
        else
            echo "❌ /foo com problemas"
        fi
        
        if curl -s -f http://172.18.255.202:81/bar > /dev/null; then
            echo "✅ /bar OK"
        else
            echo "❌ /bar com problemas"
        fi
        
        if curl -s -f http://172.18.255.202:82/test > /dev/null; then
            echo "✅ /test OK"
        else
            echo "❌ /test com problemas"
        fi
        
        # Verificar HPA
        echo ""
        echo "Status do HPA:"
        kubectl get hpa
    fi
    
    log "Testes concluídos"
}

clean_aws() {
    title "Limpando Recursos AWS"
    
    warn "Isso irá destruir todos os recursos AWS criados pelo CDK!"
    read -p "Tem certeza? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Destruindo stack CDK..."
        cd src/main/java
        cdk destroy --force
        cd ../../..
        log "Recursos AWS limpos"
    else
        warn "Limpeza cancelada"
    fi
}

clean_local() {
    title "Limpando Recursos Locais"
    
    # Garantir kubectl funciona antes de limpar
    ensure_kubectl_working || true
    
    # Definir qual pasta usar para limpeza
    local kubernetes_dir="src/scripts/kubernetes"
    if [ "$USE_UBUNTU" = "true" ]; then
        kubernetes_dir="src/scripts/kubernetes_ubuntu"
        info "Removendo deployments Kubernetes Ubuntu..."
    else
        info "Removendo deployments Kubernetes padrão..."
    fi
    
    kubectl delete -f $kubernetes_dir/ --ignore-not-found=true 2>/dev/null || true
    
    info "Removendo cluster minikube..."
    if minikube profile list -o json 2>/dev/null | grep -q "local-k8s"; then
        minikube delete --profile local-k8s
    fi
    
    log "Recursos locais limpos"
}

show_status() {
    title "Status do Sistema"
    
    echo "Configuração atual:"
    echo "  AWS_ENABLED: $AWS_ENABLED"
    echo "  ENVIRONMENT: $ENVIRONMENT"
    echo "  USE_UBUNTU: $USE_UBUNTU"
    echo ""
    
    if [ "$AWS_ENABLED" = "true" ]; then
        echo "Modo AWS ativo"
        if command -v aws &> /dev/null; then
            echo "Account: $(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo 'N/A')"
            echo "Region: $(aws configure get region 2>/dev/null || echo 'N/A')"
        fi
    else
        if [ "$USE_UBUNTU" = "true" ]; then
            echo "Modo LOCAL ativo (versão Ubuntu)"
        else
            echo "Modo LOCAL ativo (versão padrão)"
        fi
        if command -v kubectl &> /dev/null; then
            echo "Contexto atual: $(kubectl config current-context 2>/dev/null || echo 'N/A')"
            if kubectl get nodes &> /dev/null; then
                echo "Nós do cluster: $(kubectl get nodes --no-headers | wc -l)"
            fi
        fi
    fi
}

main() {
    parse_args "$@"
    
    title "Deploy Híbrido Kubernetes - AWS/Local"
    echo "Modo: $ENVIRONMENT"
    echo "AWS_ENABLED: $AWS_ENABLED"
    echo ""
    
    # Limpar recursos se solicitado
    if [ "$CLEAN_FIRST" = "true" ]; then
        if [ "$AWS_ENABLED" = "true" ]; then
            clean_aws
        else
            clean_local
        fi
    fi
    
    # Verificar pré-requisitos
    if [ "$AWS_ENABLED" = "true" ]; then
        check_prerequisites_aws
    else
        check_prerequisites_local
    fi
    
    # Configurar ambiente se necessário
    if [ "$DEPLOY_ONLY" != "true" ]; then
        if [ "$AWS_ENABLED" = "true" ]; then
            setup_aws_environment
        else
            setup_local_environment
        fi
    fi
    
    # Fazer deploy se necessário
    if [ "$SETUP_ONLY" != "true" ]; then
        if [ "$AWS_ENABLED" = "true" ]; then
            deploy_aws
        else
            deploy_local
        fi
    fi
    
    # Executar testes se solicitado
    if [ "$RUN_TESTS" = "true" ]; then
        run_tests
    fi
    
    # Mostrar status final
    show_status
    
    title "Deploy Concluído!"
    
    if [ "$AWS_ENABLED" = "true" ]; then
        log "🌩️  Recursos criados na AWS"
        log "🔍 Verifique o console AWS para URLs e IPs"
        log "💰 Lembre-se de destruir recursos quando não precisar: $0 --aws --clean"
    else
        if [ "$USE_UBUNTU" = "true" ]; then
            log "🏠 Aplicações Ubuntu rodando localmente"
            log "🐧 Versão: Deployments Ubuntu (kubernetes_ubuntu/)"
        else
            log "� Aplicações rodando localmente"
            log "📦 Versão: Deployments padrão (kubernetes/)"
        fi
        log "�🌐 Acesse: http://localhost:30080/foo, /bar, /test"
        log "📊 Monitoramento: http://localhost:30081 (Grafana), http://localhost:30082 (Prometheus)"
        log "🧪 Teste HPA: bash /tmp/load_test.sh"
        if [ "$USE_UBUNTU" = "true" ]; then
            log "🗑️  Para limpar: $0 --local --ubuntu --clean"
        else
            log "🗑️  Para limpar: $0 --local --clean"
        fi
        echo ""
        log "💡 DICA: Se kubectl der erro, execute: $0 --fix-kubectl"
    fi
}

# Função especial para corrigir kubectl quando der erro
fix_kubectl() {
    echo "🔧 === CORREÇÃO AUTOMÁTICA DO KUBECTL ==="
    
    if ensure_kubectl_working; then
        echo "✅ kubectl corrigido com sucesso!"
        echo ""
        echo "Testando conexão:"
        kubectl get nodes 2>/dev/null || echo "❌ Ainda com problemas"
    else
        echo "❌ Não foi possível corrigir automaticamente"
        echo ""
        echo "Comandos manuais para tentar:"
        echo "1. minikube profile list"
        echo "2. minikube kubectl -- config view --raw > ~/.kube/config"
        echo "3. export KUBECONFIG=~/.kube/config"
        echo "4. kubectl get nodes"
    fi
    
    exit 0
}

# Verificar se foi chamado para corrigir kubectl
if [[ "$1" == "--fix-kubectl" ]]; then
    fix_kubectl
fi

# Executar função principal
main "$@"