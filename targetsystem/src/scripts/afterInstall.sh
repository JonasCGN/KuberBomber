#!/bin/bash


after_install(){

  bucketName=$1

  apt-get install -y zip

  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip awscliv2.zip
  ./aws/install

  echo '#!/bin/bash' > /root/start.sh
  tail -n 2 /root/addworkernode.txt >> /root/start.sh
  chmod +x /root/start.sh

  aws s3 cp /root/start.sh s3://"${bucketName}"/start.sh

  # Script para monitorar e adicionar roles aos workers automaticamente
  cat > /root/monitor_workers.sh << 'EOF'
#!/bin/bash
export KUBECONFIG=/etc/kubernetes/admin.conf

while true; do
    # Encontrar nodes sem role (que não são control-plane)
    nodes_without_role=$(kubectl get nodes --no-headers | grep -v control-plane | awk '$3 == "<none>" {print $1}')
    
    for node in $nodes_without_role; do
        echo "Adicionando role worker ao node: $node"
        kubectl label node $node node-role.kubernetes.io/worker=worker
    done
    
    sleep 30
done
EOF

  chmod +x /root/monitor_workers.sh
  
  # Executar o monitor em background
  nohup /root/monitor_workers.sh > /var/log/monitor_workers.log 2>&1 &

}




echo "install cp" >> /var/log/after_install.log
after_install $1 >> /var/log/after_install.log

