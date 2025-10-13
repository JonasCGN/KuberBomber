#!/bin/bash


install_ingress(){
  numberOfNodes=$1
  echo "wait install ${numberOfNodes} ingress"


  /usr/sbin/helm version

  sleep 2m

  KUBECONFIG_PATH="/etc/kubernetes/admin.conf"

#  kubectl create namespace nginx-controller --kubeconfig /etc/kubernetes/admin.conf
  kubectl --kubeconfig "${KUBECONFIG_PATH}" create namespace nginx-ingress
#  openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout tls.key -out tls.crt -subj "/CN=default-server.local/O=Default Server"
#  kubectl --kubeconfig "${KUBECONFIG_PATH}" create secret tls default-server-secret --key tls.key --cert tls.crt -n nginx-ingress

  echo "install ingress"
  /usr/sbin/helm --kubeconfig "${KUBECONFIG_PATH}" repo add nginx-stable https://helm.nginx.com/stable --force-update
  /usr/sbin/helm --kubeconfig "${KUBECONFIG_PATH}" repo update
  /usr/sbin/helm install nginx-ingress nginx-stable/nginx-ingress \
              --version 2.2.1 \
              --namespace nginx-ingress \
              --set controller.replicaCount="${numberOfNodes}" \
              --set controller.service.type=NodePort \
              --set controller.service.httpNodePort=30081 \
              --set controller.service.httpsNodePort=30444 \
              --set controller.service.extraPorts[0].name=prometheus \
              --set controller.service.extraPorts[0].port=9113 \
              --set controller.service.extraPorts[0].targetPort=9113 \
              --set controller.ingressClass.create=true \
              --set controller.ingressClass.name=nginx \
              --set controller.ingressClass.setAsDefaultIngress=false \
              --set controller.nginxplus=false \
              --set controller.service.create=true \
              --set controller.appprotect.enable=false \
              --set controller.appprotectdos.enable=false \
              --set controller.serviceAccount.create=true \
              --set rbac.create=true \
              --set prometheus.create=true \
              --set prometheus.port=9113 \
              --set controller.enableSnippets=true \
              --set controller.enableLatencyMetrics=true \
              --kubeconfig "${KUBECONFIG_PATH}"
#
#  export HELM_EXPERIMENTAL_OCI=1
#
#  # Garante o namespace
#  kubectl --kubeconfig "${KUBECONFIG_PATH}" create namespace nginx-ingress \
#    --dry-run=client -o yaml | kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f -
#
#  # Instala/atualiza direto do GHCR (OCI)
#  # Observação: as chaves de NodePort aqui seguem o chart da NGINX (F5):
#  #   controller.service.httpPort.nodePort / controller.service.httpsPort.nodePort
#  # Portas extras via controller.service.customPorts
#  /usr/sbin/helm --kubeconfig "${KUBECONFIG_PATH}" upgrade --install nginx-ingress \
#    oci://ghcr.io/nginx/charts/nginx-ingress \
#    --namespace nginx-ingress \
#    --version 2.2.1 \
#    --set controller.replicaCount="${numberOfNodes}" \
#    --set controller.service.type=NodePort \
#    --set controller.service.httpPort.nodePort=30081 \
#    --set controller.service.httpsPort.nodePort=30444 \
#    --set controller.service.customPorts[0].name=prometheus \
#    --set controller.service.customPorts[0].port=9113 \
#    --set controller.service.customPorts[0].targetPort=9113 \
#    --set controller.ingressClass.create=true \
#    --set controller.ingressClass.name=nginx \
#    --set controller.ingressClass.setAsDefaultIngress=false \
#    --set controller.nginxplus=false \
#    --set controller.service.create=true \
#    --set controller.appprotect.enable=false \
#    --set controller.appprotectdos.enable=false \
#    --set controller.serviceAccount.create=true \
#    --set rbac.create=true \
#    --set prometheus.create=true \
#    --set prometheus.port=9113 \
#    --set controller.enableSnippets=true \
#    --set controller.enableLatencyMetrics=true \
#    --create-namespace


  sleep 1m

  kubectl --kubeconfig /etc/kubernetes/admin.conf patch svc nginx-ingress-controller -n nginx-ingress --type='json' -p='[{"op": "add", "path": "/spec/ports/-", "value": {"name": "prometheus", "port": 9113, "protocol": "TCP", "targetPort": 9113}}]'
  kubectl --kubeconfig /etc/kubernetes/admin.conf patch svc nginx-ingress-controller -n nginx-ingress --type='json' -p='[{"op": "replace", "path": "/spec/ports/0/nodePort", "value": 30080}, {"op": "replace", "path": "/spec/ports/1/nodePort", "value": 30443}]'
  kubectl --kubeconfig /etc/kubernetes/admin.conf patch deployment nginx-ingress-controller -n nginx-ingress --type='json' -p='[{"op": "add", "path": "/spec/template/spec/affinity", "value": {"podAntiAffinity": {"preferredDuringSchedulingIgnoredDuringExecution":[{"weight":100,"podAffinityTerm":{"labelSelector":{"matchLabels":{"app.kubernetes.io/name":"nginx-ingress","app.kubernetes.io/instance":"nginx-ingress"}},"topologyKey":"kubernetes.io/hostname"}}]}}}]'

  echo "end install ingress"

  sleep 1m

  echo "delete ingress-nginx-admission"

  kubectl delete -A ValidatingWebhookConfiguration ingress-nginx-admission --kubeconfig /etc/kubernetes/admin.conf

}

run_application(){
  use_autoscaling="$1"  # "true" para usar HPA (autoscaling) | "false" para sem autoscaling
  echo "run_application (autoscaling=${use_autoscaling})"

  sleep 3m

  if [ "${use_autoscaling}" = "true" ]; then
    # Com autoscaling (HPA)
    kubectl apply -f /home/ubuntu/kubernetes/kub_deployment.yaml --kubeconfig /etc/kubernetes/admin.conf
  else
    # Sem autoscaling
    kubectl apply -f /home/ubuntu/kubernetesWS/kub_deployment.yaml --kubeconfig /etc/kubernetes/admin.conf
  fi

  echo "run_application finish"
}

save_kub_config_in_s3() {
  # Parâmetro: nome do bucket S3
  bucketName="$1"

  echo "arquivo kubeconfig"
  cat /home/ubuntu/kubeconfig.conf

  echo "Enviando kubeconfig para o S3: s3://$bucketName/kubeconfig.conf"
  aws s3 cp "/home/ubuntu/kubeconfig.conf" s3://"$bucketName"/kubeconfig.conf
}


after_install(){

  bucketName=$1
  numberOfNodes=$2
  use_autoscaling="$3"   # novo parâmetro: "true" ou "false"
  bar_st="${4}"
  foo_st="${5}"

  apt-get install -y zip

  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip awscliv2.zip
  ./aws/install

  echo '#!/bin/bash' > /root/start.sh
  tail -n 2 /root/addworkernode.txt >> /root/start.sh
  chmod +x /root/start.sh

  aws s3 cp /root/start.sh s3://"${bucketName}"/start.sh

  install_ingress ${numberOfNodes}

  run_application "${use_autoscaling}"

  install_prometheus

  save_grafana_access_to_s3 "${bucketName}"

  set_applycation_env "${bar_st}" "${foo_st}"

  importar_dashboard_grafana

  echo "Some logs"

  kubectl get pods --kubeconfig /etc/kubernetes/admin.conf

  /home/ubuntu/updateConfig.sh --persist-config

  save_kub_config_in_s3 "${bucketName}"

  echo "Finish install"

}

set_applycation_env(){

  bar_st=$1
  foo_st=$2

  echo "set kubectl set env deployment/bar-app LOAD=1.0 MEAN=${bar_st}"

  kubectl set env deployment/bar-app LOAD=1.0 MEAN=${bar_st}

  echo "set kubectl set env deployment/foo-app LOAD=1.0 MEAN=${foo_st}"

  kubectl set env deployment/foo-app LOAD=1.0 MEAN=${foo_st}


}


save_grafana_access_to_s3() {
  # Parâmetro: nome do bucket S3
  bucketName="$1"

  # Nome do serviço e namespace
  serviceName="prometheus-grafana"
  namespace="monitoring"

  # Nome do arquivo JSON de saída
  outputFile="/root/grafana_access.json"

  echo "Obtendo IP do Node..."
  nodeIP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

  echo "Obtendo porta NodePort do Grafana..."
  nodePort=$(sudo kubectl get svc "$serviceName" -n "$namespace" -o jsonpath='{.spec.ports[0].nodePort}')

  echo "Obtendo senha do Grafana..."
  grafanaUser="admin"
  grafanaPassword=$(sudo kubectl get secret -n "$namespace" "$serviceName" -o jsonpath="{.data.admin-password}" | base64 --decode)

  echo "Gerando JSON em $outputFile..."
  cat <<EOF > "$outputFile"
{
  "ip": "$nodeIP",
  "port": "$nodePort",
  "username": "$grafanaUser",
  "password": "$grafanaPassword"
}
EOF

  echo "Enviando para o S3: s3://$bucketName/grafana_access.json"
  aws s3 cp "$outputFile" s3://"$bucketName"/grafana_access.json
}



install_prometheus() {
  sudo su
  export KUBECONFIG=/etc/kubernetes/admin.conf
  # Aguarda serviços críticos estarem prontos (opcional, mas ajuda em setups automatizados)
  sleep 10

  # Adiciona o repositório oficial da Prometheus Community
  /usr/sbin/helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
  sleep 10
  /usr/sbin/helm repo update
  sleep 10

  # Instala a stack completa no namespace 'monitoring'
  /usr/sbin/helm install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

  # Aguarda a instalação (pode aumentar esse tempo dependendo do cluster)
  sleep 60
  kubectl patch svc prometheus-grafana -n monitoring \
    -p '{"spec": {"type": "NodePort"}}'
  # Altera o serviço do Grafana para NodePort para permitir acesso externo
  kubectl patch svc prometheus-grafana -n monitoring   -p '{"spec": {"ports": [{"port":80, "targetPort":3000, "nodePort":30081}]}}'
  sleep 10
  #altera o prometheus para ser acessado externamente
  kubectl patch svc prometheus-kube-prometheus-prometheus -n monitoring \
    -p '{"spec": {"type": "NodePort"}}'
  kubectl patch svc prometheus-kube-prometheus-prometheus -n monitoring \
    -p '{"spec": {"ports": [{"port":9090, "targetPort":9090, "nodePort":30082}]}}'
  # Exibe o IP e a porta do serviço Grafana
  kubectl get svc prometheus-grafana -n monitoring

  kubectl apply -f /home/ubuntu/kubernetes/kub_monitoring.yaml --kubeconfig /etc/kubernetes/admin.conf

  # Exibe a senha de admin do Grafana (usuário: admin)
  echo -e "\nSenha do Grafana:"
  kubectl get secret -n monitoring prometheus-grafana \
    -o jsonpath="{.data.admin-password}" | base64 --decode && echo
}

configure_prometheus_metrics(){
  # COMENTADO: Usando versão corrigida do metrics-server no local_deploy.sh
  # kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
  echo "Metrics-server será aplicado via local_deploy.sh com configurações corrigidas"
}


importar_dashboard_grafana() {
  local configmap_name="grafana-dashboards"
  local dashboard_file="/home/ubuntu/grafana.json"
  local namespace="monitoring"

  ls -lha

  if [ ! -f "$dashboard_file" ]; then
    echo "❌ Arquivo '$dashboard_file' não encontrado."
    return 1
  fi

  echo "📦 Gerando ConfigMap '$configmap_name' com base em '$dashboard_file'..."
  kubectl create configmap "$configmap_name" \
    --from-file="$dashboard_file" \
    -n "$namespace" \
    --dry-run=client -o yaml > dashboards-cm.yaml

  echo "🏷️ Adicionando label 'grafana_dashboard=1' ao ConfigMap..."
  sed -i '/name: grafana-dashboards/a\  labels:\n    grafana_dashboard: "1"' dashboards-cm.yaml

  echo "🚀 Aplicando ConfigMap ao cluster..."
  kubectl apply -f dashboards-cm.yaml

  echo "♻️ Reiniciando pod do Grafana..."
  kubectl delete pod -n "$namespace" -l app.kubernetes.io/name=grafana

  echo "✅ Dashboard importado com sucesso para o Grafana!"
}



echo "install cp" >> /var/log/after_install.log
after_install "$@" >> /var/log/after_install.log 2>&1

cp /var/log/after_install.log /home/ubuntu/
chmod -R 777 /home/ubuntu/after_install.log

