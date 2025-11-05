#!/bin/bash


install_wn(){

  bucketName=$1

  #install kubeadm, kubectl, kubelet,and kubernetes-cni
  curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
  echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list
  apt-get update -y
  apt-get install -y kubelet=1.30.5-1.1 kubeadm=1.30.5-1.1 kubectl=1.30.5-1.1 kubernetes-cni=1.4.0-1.1

  ufw disable
  swapoff -a
  sudo sed -i "/swap/d" /etc/fstab

  modprobe br_netfilter
  modprobe overlay

  echo overlay >> /etc/modules-load.d/containerd.conf
  echo br_netfilter >> /etc/modules-load.d/containerd.conf

  echo "net.bridge.bridge-nf-call-ip6tables = 1" >> /etc/sysctl.d/kubernetes.conf
  echo "net.bridge.bridge-nf-call-iptables = 1" >> /etc/sysctl.d/kubernetes.conf
  echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.d/kubernetes.conf

  sysctl --system

  apt install -y apt-transport-https curl vim git software-properties-common ca-certificates gpg gnupg2
  #update server and install apt-transport-https and curl
  apt-get update -y
  apt install -y apt-transport-https curl qemu-guest-agent

  #Install containerd
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update -y
  apt-get install -y containerd.io=1.7.22-1

  mkdir -p /etc/containerd
  containerd config default > /etc/containerd/config.toml

  #set SystemdCgroup = true within config.toml
  sed -i "s/SystemdCgroup = false/SystemdCgroup = true/g" /etc/containerd/config.toml

  #Restart containerd daemon
  systemctl restart containerd
  #Enable containerd to start automatically at boot time
  systemctl enable containerd


}

start_kub_cluster(){

    bucketName=$1

    apt-get install -y zip

    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    ./aws/install | true

    #wait CP install finish
    sleep 6m

    echo "copy files"
    # Retry logic para download do start.sh
    for i in {1..5}; do
        if aws s3 cp s3://"${bucketName}"/start.sh /root/start.sh; then
            break
        fi
        echo "Tentativa $i falhou, tentando novamente em 30s..."
        sleep 30
    done
    ls /root/

    chmod +x /root/start.sh

    bash /root/start.sh

#    sed -i "s/pause:3.9\"/pause:3.9 --node-status-update-frequency=4s\"/g" /var/lib/kubelet/kubeadm-flags.env

    systemctl restart kubelet

}


file_path="/root/start.sh"

if [ -f "$file_path" ]; then
    echo "already installed" >> /var/log/install_wn.log
else
    echo "install cp" >> /var/log/install_wn.log
    install_wn >> /var/log/install_wn.log
    start_kub_cluster $1 >> /var/log/install_wn.log
fi