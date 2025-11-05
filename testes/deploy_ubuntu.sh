#!/bin/bash
"""
Deploy Ubuntu Pods
==================

Script para aplicar deployment com containers Ubuntu de debug.
"""

echo "🚀 === APLICANDO DEPLOYMENT UBUNTU ==="

# Verificar se estamos no diretório correto
if [[ ! -f "kub_deployment_ubuntu.yaml" ]]; then
    echo "❌ Arquivo kub_deployment_ubuntu.yaml não encontrado!"
    echo "Execute este script do diretório testes/"
    exit 1
fi

# Verificar chave SSH
SSH_KEY="$HOME/.ssh/vockey.pem"
if [[ ! -f "$SSH_KEY" ]]; then
    echo "❌ Chave SSH não encontrada em $SSH_KEY"
    exit 1
fi

# Carregar configuração
if [[ ! -f "aws_config.json" ]]; then
    echo "❌ Arquivo aws_config.json não encontrado!"
    echo "Execute primeiro: python3 aws_setup.py"
    exit 1
fi

SSH_HOST=$(python3 -c "import json; print(json.load(open('aws_config.json'))['ssh_host'])")

echo "📡 Conectando ao cluster AWS: $SSH_HOST"

# Aplicar deployment
echo "📦 Aplicando deployment com containers Ubuntu..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SSH_HOST" 'sudo kubectl apply -f -' < kub_deployment_ubuntu.yaml

if [[ $? -eq 0 ]]; then
    echo "✅ Deployment aplicado com sucesso!"
    
    echo "⏳ Aguardando pods reiniciarem..."
    sleep 10
    
    echo "📋 Status dos pods:"
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SSH_HOST" 'sudo kubectl get pods'
    
    echo ""
    echo "🎯 === PRÓXIMOS PASSOS ==="
    echo "1. Aguarde todos os pods ficarem Running (pode levar alguns minutos)"
    echo "2. Execute: python3 aws_reliability_tester.py"
    echo "3. Use os comandos de teste exemplo mostrados"
    echo ""
    echo "📋 Verificar status: ssh -i ~/.ssh/vockey.pem ubuntu@$SSH_HOST 'sudo kubectl get pods'"
else
    echo "❌ Erro ao aplicar deployment!"
    exit 1
fi