#!/bin/bash

# Script para parar os port-forwards das aplicações
# Autor: Sistema Híbrido AWS/Local

echo "=== Parando Port-forwards ==="

# Parar todos os port-forwards do kubectl
pkill -f "kubectl port-forward" 2>/dev/null

# Verificar se existem PIDs salvos
if [ -f "/tmp/portforward-pids.env" ]; then
    source /tmp/portforward-pids.env
    
    # Parar processos específicos se ainda estiverem rodando
    [ ! -z "$FOO_PF_PID" ] && kill $FOO_PF_PID 2>/dev/null
    [ ! -z "$BAR_PF_PID" ] && kill $BAR_PF_PID 2>/dev/null
    [ ! -z "$TEST_PF_PID" ] && kill $TEST_PF_PID 2>/dev/null
    
    # Remover arquivo de PIDs
    rm -f /tmp/portforward-pids.env
fi

# Limpar logs
rm -f /tmp/foo-portforward.log /tmp/bar-portforward.log /tmp/test-portforward.log

echo "✅ Port-forwards parados com sucesso!"
echo ""
echo "Para reiniciar, execute: bash src/scripts/local_deploy.sh"