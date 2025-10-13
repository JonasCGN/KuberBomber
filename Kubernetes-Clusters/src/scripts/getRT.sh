#!/bin/bash

experiment_begin=$(date '+%Y%m%d%H%M%S')
echo "experiment begin ${experiment_begin}" >> repaiTimes.txt

#set the de that will fail
failedDC=2
numberOffailedNodes=2

kubectl apply -f kub_deployment.yaml

mindc=11
totalPods=12
totalNodes=6

for i in {1..30} ; do

  disaster_time=$(date +%s%3N)
  echo "stop instance ${stop_dc} - ${stop_name}"
  stop_instance_is=$(aws ec2 describe-instances --filters "Name=tag:DC,Values=${failedDC}" "Name=instance-state-name,Values=running"  --query "Reservations[*].Instances[*].InstanceId" --output text)
  echo "stoping - ${stop_instance_is}"
  aws ec2 stop-instances --instance-ids ${stop_instance_is}

  echo "->>after fail:"
  kubectl get pods -o wide
  while [ $(kubectl get pods -o wide| grep "nginx-deployment" | grep "Running" | grep -v "ip-10-0-${failedDC}-*" | wc -l) -lt "$mindc" ]; do
      echo "Wait POds recovery.."
      sleep 1
  done
  echo "->>after wait fail"
  kubectl get pods -o wide


  restartTime=$(date +%s%3N)
  echo "raw times:${disaster_time};${restartTime};"
  restartTime=$((restartTime - disaster_time))
  echo ${restartTime} >> repaiTimesInMS.txt
  time_difference_hours=$(bc <<< "scale=4; $restartTime / (1000 * 60 * 60)")
  echo ${time_difference_hours} >> repaiTimes.txt
  echo "${restartTime}ms;${time_difference_hours}h;"

  echo "start restarted"
  aws ec2 start-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=${failedDC}" "Name=instance-state-name,Values=stopped" --query "Reservations[*].Instances[*].InstanceId" --output text)

  echo "on nodes:"
  kubectl get nodes | grep "ip-10-0-${failedDC}-*" | grep "Ready"
  echo "->>after star node:"
 #wait node return
 kubectl get nodes -o wide
  while [ $(kubectl get nodes -o wide| grep "ip-10-0-${failedDC}-*" | grep "Ready" | grep -v "NotReady" | wc -l) -lt "$numberOffailedNodes" ]; do
      echo "Wait node ${failedDC} return.."
      sleep 1
  done
  echo "->>after wait star node:"
  kubectl get nodes -o wide
  sleep 1m

  kubectl delete -f kub_deployment.yaml
  #wait shutdown pods
  echo "->>after delete kub:"
  kubectl get pods -o wide
  while [ $(kubectl get pods -o wide| grep "nginx-deployment"  | wc -l) -ge "1" ]; do
      echo "wait deployment deletion."
      sleep 1
  done
  echo "->>after wait delete kub:"
  kubectl get pods -o wide
  sleep 1m


  aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=0" --query "Reservations[*].Instances[*].InstanceId" --output text)
  aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=1" --query "Reservations[*].Instances[*].InstanceId" --output text)
  aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=2" --query "Reservations[*].Instances[*].InstanceId" --output text)

  sleep 5m

  aws ec2 start-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=0" --query "Reservations[*].Instances[*].InstanceId" --output text)
  aws ec2 start-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=1" --query "Reservations[*].Instances[*].InstanceId" --output text)
  aws ec2 start-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=2" --query "Reservations[*].Instances[*].InstanceId" --output text)


  echo "on nodes:"
  kubectl get nodes | grep "Ready"
  echo "->>after star node:"
 #wait node return
 kubectl get nodes -o wide
  while [ $(kubectl get nodes -o wide| grep "Ready" | grep -v "NotReady"| wc -l) -lt "$totalNodes" ]; do
      echo "Wait nodes return.."
      sleep 1
  done
  echo "->>after wait star node:"
  kubectl get nodes -o wide
  sleep 5m

  #wait all pods restart
  kubectl apply -f kub_deployment.yaml
  #wait start pods
  echo "->>after apply kub:"
  kubectl get pods -o wide
  while [ $(kubectl get pods -o wide| grep "nginx-deployment" | grep "Running"  | wc -l) -lt "$totalPods" ]; do
      echo "Wait all pods start."
      sleep 1
  done
  echo "->>after wait apply kub:"
  kubectl get pods -o wide
  sleep 1m

done

sleep 3m
#shutdown all environment
aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=0"  --query "Reservations[*].Instances[*].InstanceId" --output text)
aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=1"  --query "Reservations[*].Instances[*].InstanceId" --output text)
aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=2"  --query "Reservations[*].Instances[*].InstanceId" --output text)
sleep 3m
shutdown -h now
