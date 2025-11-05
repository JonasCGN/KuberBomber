#!/bin/bash

# Lista de IPs das instâncias (acesso via NodePort)
# Substitua pelos IPs públicos reais dos seus nós onde o NGINX Ingress Controller está rodando.
# Se você tiver múltiplos nós com IPs públicos e o Ingress Controller rodar em todos, liste-os aqui.
# Exemplo: NODEPORT_IPS=("3.90.109.177" "SEU_OUTRO_IP_AQUI")
NODEPORT_IPS=("107.22.79.91"  "34.230.17.19")

# Porta NodePort do Ingress NGINX para HTTP (confirmada como 31584)
NODEPORT=30080

# URL do Load Balancer AWS (acesso via DNS)
# Certifique-se de que este é o DNS do seu Load Balancer provisionado pelo Kubernetes.
# Se for HTTPS, mude para https:// e considere o uso de certificados.
LOADBALANCER_BASE_URL="http://hpalb-1246113748.us-east-1.elb.amazonaws.com"

# Número de requisições por endpoint
REQUESTS=200000

echo "➡️ Enviando requisições para os IPs via NodePort (com cabeçalho Host)..."
#for ip in "${NODEPORT_IPS[@]}"; do
#  echo "➡️ IP: $ip"
#  for i in $(seq 1 $REQUESTS); do
#    # Requisição para /foo com Host: foo.local
#    curl -s -o /dev/null -w "[$ip] /foo -> %{http_code}\n" -H "Host: absd.amazonaws.com" "http://$ip:$NODEPORT/foo"
#    # Requisição para /bar com Host: bar.local
#    curl -s -o /dev/null -w "[$ip] /bar -> %{http_code}\n" -H "Host: absd.amazonaws.com" "http://$ip:$NODEPORT/bar"
#    # Requisição para /test com Host: test.local
#    curl -s -o /dev/null -w "[$ip] /test -> %{http_code}\n" -H "Host: absd.amazonaws.com" "http://$ip:$NODEPORT/test"
#  done
#done

echo "➡️ Enviando requisições via Load Balancer ($LOADBALANCER_BASE_URL) (com cabeçalho Host)..."
for i in $(seq 1 $REQUESTS); do
  # Requisição para /foo via Load Balancer com Host: foo.local
  # Removido -k, pois geralmente não é necessário para HTTP. Se for HTTPS e certificado autoassinado, adicione -k novamente.
  curl -s -o /dev/null -w "[LB] /foo -> %{http_code}\n" -H "Host: foo.amazonaws.com" "$LOADBALANCER_BASE_URL/foo"
  # Requisição para /bar via Load Balancer com Host: bar.local
  curl -s -o /dev/null -w "[LB] /bar -> %{http_code}\n" -H "Host: bar.amazonaws.com" "$LOADBALANCER_BASE_URL/bar"
  # Requisição para /test via Load Balancer com Host: test.local
#  curl -s -o /dev/null -w "[LB] /test -> %{http_code}\n" -H "Host: test.amazonaws.com" "$LOADBALANCER_BASE_URL/test"
done

echo "✅ Tráfego simulado concluído."
