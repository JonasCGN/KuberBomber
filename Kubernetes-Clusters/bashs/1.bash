#!/bin/bash

#become root!!!
#funcionou em ubuntu server 22 kube  v1.28.2
#https://medium.com/@the.nick.miller/setting-up-a-kubernetes-cluster-be0976170d8e                 -- base
#https://akyriako.medium.com/load-balancing-with-metallb-in-bare-metal-kubernetes-271aab751fb8    --metalb
#https://www.youtube.com/watch?v=k8bxtsWe9qw                                                      --ingress


CONTROLPLANE_NAME="kubemaster"
CONTROLPLANE_IP="192.168.0.200"
WORKERNODE01_NAME="kubenode01"
WORKERNODE01_IP="192.168.0.201"
WORKERNODE02_NAME="kubenode02"
WORKERNODE02_IP="192.168.0.202"


#set hostname
hostnamectl set-hostname ${CONTROLPLANE_NAME}

#Maps hostnames to IP addresses
cat << EOF >> /etc/hosts
${CONTROLPLANE_IP} ${CONTROLPLANE_NAME}
${WORKERNODE01_IP} ${WORKERNODE01_NAME}
${WORKERNODE02_IP} ${WORKERNODE02_NAME}
EOF

apt-get update -y
apt install -y apt-transport-https curl vim git


#Install containerd
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y containerd.io

mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml


#set SystemdCgroup = true within config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml

#Restart containerd daemon
systemctl restart containerd

#Enable containerd to start automatically at boot time
systemctl enable containerd


#install kubeadm, kubectl, kubelet,and kubernetes-cni
curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add
apt-add-repository -y "deb http://apt.kubernetes.io/ kubernetes-xenial main"
apt -y install kubeadm kubelet kubectl kubernetes-cni

#disable swap
swapoff -a

#check if a swap entry exists and remove it if it does
sed -e '/swap/ s/^#*/#/' -i /etc/fstab

#Load the br_netfilter module in the Linux kernel
modprobe br_netfilter

echo 1 > /proc/sys/net/ipv4/ip_forward

#initialize kubernetes cluster
kubeadm init --pod-network-cidr=10.244.0.0/16 | tee ~/addworkernode.txt

echo "OPEN ~/addworkernode.txt to get join command"

#kubeadm join 192.168.0.200:6443 --token nbjxmm.7720097kl2n8wcye \
#	--discovery-token-ca-cert-hash sha256:c63b79d16efb7ee17c1d4becdf8da0f5be421014dd767b29ba59a8feaa4d2d49

#  mkdir -p $HOME/.kube
#  sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
#  sudo chown $(id -u):$(id -g) $HOME/.kube/config

export KUBECONFIG=/etc/kubernetes/admin.conf

kubectl apply -f https://raw.githubusercontent.com/flannel-io/flannel/v0.20.2/Documentation/kube-flannel.yml