#!/bin/bash
# Script para criar e fazer push de uma imagem enhanced com ferramentas de debug

IMAGE_NAME="iuresf/apprunner-enhanced"
TAG="latest"

echo "🔧 Construindo imagem enhanced com ferramentas de debug..."
docker build -f Dockerfile.enhanced -t ${IMAGE_NAME}:${TAG} .

echo "📤 Fazendo push da imagem para Docker Hub..."
docker push ${IMAGE_NAME}:${TAG}

echo "✅ Imagem ${IMAGE_NAME}:${TAG} criada e publicada com sucesso!"
echo "📋 Ferramentas incluídas:"
echo "   - ps, kill, pgrep, pkill (procps)"
echo "   - killall, fuser (psmisc)" 
echo "   - curl, wget (networking)"
echo "   - ping, netstat (net-tools)"
echo ""
echo "🔄 Para atualizar os deployments, execute:"
echo "   sed -i 's|iuresf/apprunner|iuresf/apprunner-enhanced|g' src/scripts/nodes/controlPlane/kubernetes/kub_deployment.yaml"