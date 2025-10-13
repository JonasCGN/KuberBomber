#!/bin/bash

# Script para NUNCA MAIS ter erro no kubectl
# Uso: ./fix-kubectl.sh

echo "🔧 Corrigindo kubectl definitivamente..."

# 1. Garantir Docker funcionando
if ! docker ps &> /dev/null; then
    echo "📦 Configurando Docker..."
    sudo systemctl start docker
    sudo usermod -aG docker $USER
    sudo chown root:docker /var/run/docker.sock
    sudo chmod 660 /var/run/docker.sock
    
    # Aplicar grupo na sessão
    newgrp docker << 'EOF'
exit
EOF
fi

# 2. Verificar se há cluster kind
clusters=$(kind get clusters 2>/dev/null || echo "")
if [ -z "$clusters" ]; then
    echo "❌ Nenhum cluster kind encontrado"
    echo "Execute: ./deploy.sh --local --setup"
    exit 1
fi

# 3. Obter primeiro cluster
cluster=$(echo "$clusters" | head -n1)
echo "📡 Usando cluster: $cluster"

# 4. Configurar kubeconfig PERMANENTE
mkdir -p ~/.kube

# Backup do config atual
if [ -f ~/.kube/config ]; then
    cp ~/.kube/config ~/.kube/config.backup.$(date +%s)
    echo "💾 Backup criado"
fi

# Obter kubeconfig do kind
if kind get kubeconfig --name "$cluster" > ~/.kube/config; then
    chmod 600 ~/.kube/config
    echo "✅ Kubeconfig criado"
else
    echo "❌ Erro ao obter kubeconfig"
    exit 1
fi

# 5. Configurar variáveis de ambiente
export KUBECONFIG=~/.kube/config

# 6. Testar
if kubectl version --short &> /dev/null; then
    echo "🎉 SUCCESS! kubectl funcionando!"
    echo ""
    echo "Cluster info:"
    kubectl get nodes
    echo ""
    echo "Para garantir em futuras sessões, adicione ao seu ~/.bashrc:"
    echo "export KUBECONFIG=~/.kube/config"
else
    echo "❌ Ainda com problemas"
    echo "Tente executar manualmente:"
    echo "export KUBECONFIG=~/.kube/config"
    echo "kubectl get nodes"
fi