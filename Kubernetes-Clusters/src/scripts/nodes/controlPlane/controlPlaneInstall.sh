#!/bin/bash


#tested in ubuntu server 22 kube  v1.28.2
#some kubernetes tutorials references
#https://medium.com/@the.nick.miller/setting-up-a-kubernetes-cluster-be0976170d8e
#https://milindasenaka96.medium.com/setup-your-k8s-cluster-with-aws-ec2-3768d78e7f05
#https://akyriako.medium.com/load-balancing-with-metallb-in-bare-metal-kubernetes-271aab751fb8
#https://www.youtube.com/watch?v=k8bxtsWe9qw
#https://mrmaheshrajput.medium.com/deploy-kubernetes-cluster-on-aws-ec2-instances-f3eeca9e95f1
#https://www.linkedin.com/pulse/4-ways-fine-tune-high-availability-kubernetes-nodes-mbong-ekwoge/
#https://mrmaheshrajput.medium.com/deploy-kubernetes-cluster-on-aws-ec2-instances-f3eeca9e95f1

install_cp(){
  apt-get update -y

  #install kubeadm, kubectl, kubelet,and kubernetes-cni
  curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
  echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list
  apt-get update -y
  apt-get install -y vim git curl wget kubelet=1.30.5-1.1 kubeadm=1.30.5-1.1 kubectl=1.30.5-1.1
  apt-mark hold kubelet kubeadm kubectl
  systemctl enable --now kubelet

  kubectl version --client && kubeadm version

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

  kubeadm config images pull --cri-socket unix:///run/containerd/containerd.sock

  PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)

  echo "my private IP ${PRIVATE_IP}"

  #initialize kubernetes cluster
  kubeadm init --pod-network-cidr=192.168.0.0/16 --apiserver-advertise-address=${PRIVATE_IP} | tee ~/addworkernode.txt

  export KUBECONFIG=/etc/kubernetes/admin.conf

  echo KUBECONFIG=/etc/kubernetes/admin.conf >> /etc/environment

#NETWORK
#  kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.25.0/manifests/tigera-operator.yaml
##
#  kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.25.0/manifests/custom-resources.yaml
  kubectl apply -f https://github.com/weaveworks/weave/releases/download/v2.8.1/weave-daemonset-k8s.yaml

  # COMENTADO: Usando versão corrigida do metrics-server no local_deploy.sh
  # wget https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
  # sed -i "/        - --metric-resolution=15s/a \        - --kubelet-insecure-tls" components.yaml
  # kubectl apply -f components.yaml
  echo "Metrics-server será aplicado via local_deploy.sh com configurações corrigidas"


#NETWORK

#INGRESS

  #install helm
#  curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | tee /usr/share/keyrings/helm.gpg > /dev/null
#  apt-get install apt-transport-https --yes
#  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | tee /etc/apt/sources.list.d/helm-stable-debian.list
#  apt-get update -y
#  apt-get install helm -y
  curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
  chmod 700 get_helm.sh
  ./get_helm.sh
  ln -s /usr/local/bin/helm /usr/sbin/helm
  #install helm

  #install nginx ingress
  #only one ingress improve
#  helm upgrade --install ingress-nginx ingress-nginx --repo https://kubernetes.github.io/ingress-nginx

#INGRESS


  kubectl get pods --all-namespaces

  echo "OPEN ~/addworkernode.txt to get join command"

  #set time to identify cluster changes

#  sed -i "s/pause:3.9 \"/pause:3.9 --node-status-update-frequency=4s\"/g" /var/lib/kubelet/kubeadm-flags.env
#
#  sed -i "/- --use-service-account-credentials=true/a \    - --node-monitor-period=3s" /etc/kubernetes/manifests/kube-controller-manager.yaml
#
#  sed -i "/- --node-monitor-period=3/a \    - --node-monitor-grace-period=16s" /etc/kubernetes/manifests/kube-controller-manager.yaml
#
#cat << EOF > /etc/kubernetes/manifests/kubeadm-apiserver-update.yaml
#apiVersion: kubeadm.k8s.io/v1beta3
#kind: ClusterConfiguration
#kubernetesVersion: v1.29.0
#apiServer:
#  extraArgs:
#    enable-admission-plugins: DefaultTolerationSeconds
#    default-not-ready-toleration-seconds: "20"
#    default-unreachable-toleration-seconds: "20"
#EOF
#
#  kubeadm init phase control-plane apiserver --config=/etc/kubernetes/manifests/kubeadm-apiserver-update.yaml
#
  systemctl restart kubelet

  systemctl restart containerd
}

file_path="/root/start.sh"

if [ -f "$file_path" ]; then
    echo "already installed" >> /var/log/install_cp.log
else
    echo "install cp" >> /var/log/install_cp.log
    install_cp >> /var/log/install_cp.log 2>&1
fi









