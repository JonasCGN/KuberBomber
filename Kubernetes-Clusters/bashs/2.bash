#!/bin/bash

#become root!!!

CONTROLPLANE_NAME="kubemaster"
CONTROLPLANE_IP="192.168.0.200"
WORKERNODE01_NAME="kubenode01"
WORKERNODE01_IP="192.168.0.201"
WORKERNODE02_NAME="kubenode02"
WORKERNODE02_IP="192.168.0.202"


#set hostname
hostnamectl set-hostname ${WORKERNODE02_NAME}

#Maps hostnames to IP addresses
cat << EOF >> /etc/hosts
${CONTROLPLANE_IP} ${CONTROLPLANE_NAME}
${WORKERNODE01_IP} ${WORKERNODE01_NAME}
${WORKERNODE02_IP} ${WORKERNODE02_NAME}
EOF

#update server and install apt-transport-https and curl
apt-get update -y
apt install -y apt-transport-https curl qemu-guest-agent

#Install containerd 
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg |  gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" |  tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y containerd.io

#Configure containerd
mkdir -p /etc/containerd
containerd config default |  tee /etc/containerd/config.toml

#set SystemdCgroup = true within configs.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml

#Restart containerd daemon
systemctl restart containerd

#Enable containerd to start automatically at boot time
systemctl enable containerd

#install kubeadm, kubectl, kubelet,and kubernetes-cni 
curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg |  apt-key add
apt-add-repository -y "deb http://apt.kubernetes.io/ kubernetes-xenial main"
apt-get install -y kubeadm kubelet kubectl kubernetes-cni

#disable swap
swapoff -a

sed -e '/swap/ s/^#*/#/' -i /etc/fstab

#load the br_netfilter module in the Linux kernel
modprobe br_netfilter

echo 1 > /proc/sys/net/ipv4/ip_forward

#use o resultado do join do control plane