#!/bin/bash

# Script para monitorar e reiniciar port-forwards automaticamente
# Executar em background: nohup bash port-forward-monitor.sh > /tmp/pf-monitor.log 2>&1 &

echo "🚀 Iniciando monitor de port-forwards..."

# Função para verificar se port-forward está ativo
check_portforward() {
    local port=$1
    local pid_file="/tmp/pf-${port}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Ativo
        fi
    fi
    return 1  # Inativo
}

# Função para iniciar port-forward
start_portforward() {
    local service=$1
    local port=$2
    local pid_file="/tmp/pf-${port}.pid"
    
    echo "📡 Iniciando port-forward para ${service} na porta ${port}"
    kubectl port-forward svc/${service} ${port}:9898 > /tmp/pf-${service}.log 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    echo "✅ Port-forward para ${service} iniciado (PID: $pid)"
}

# Função para parar todos os port-forwards
stop_all_portforwards() {
    echo "🛑 Parando todos os port-forwards..."
    pkill -f "kubectl port-forward" 2>/dev/null
    rm -f /tmp/pf-*.pid
    echo "✅ Port-forwards parados"
}

# Trap para limpeza ao receber SIGTERM
trap 'stop_all_portforwards; exit 0' SIGTERM SIGINT

echo "📋 Configurações:"
echo "  - foo-service: localhost:8080"
echo "  - bar-service: localhost:8081" 
echo "  - test-service: localhost:8082"
echo ""

# Loop principal
while true; do
    echo "🔍 Verificando port-forwards $(date)"
    
    # Verificar foo-service (porta 8080)
    if ! check_portforward "8080"; then
        echo "⚠️ Port-forward foo-service inativo, reiniciando..."
        start_portforward "foo-service" "8080"
        sleep 5
    fi
    
    # Verificar bar-service (porta 8081)
    if ! check_portforward "8081"; then
        echo "⚠️ Port-forward bar-service inativo, reiniciando..."
        start_portforward "bar-service" "8081"
        sleep 5
    fi
    
    # Verificar test-service (porta 8082)
    if ! check_portforward "8082"; then
        echo "⚠️ Port-forward test-service inativo, reiniciando..."
        start_portforward "test-service" "8082"
        sleep 5
    fi
    
    # Aguardar antes da próxima verificação
    sleep 30
done