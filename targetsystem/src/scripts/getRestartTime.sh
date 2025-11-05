#!/bin/bash
#start a pod with two nodes and shut down the node with the node
dc_a_number=1

dc_b_number=2

stop_dc=$dc_a_number

wait_start_dc=$dc_b_number


experiment_begin=$(date '+%Y%m%d%H%M%S')

echo "experiment begin ${experiment_begin}" >> restartTimes.txt

for i in {1..30} ; do

  disaster_time=$(date +%s%3N)
  echo "stop instance in DC ${stop_dc}"
  stop_instance_is=$(aws ec2 describe-instances --filters "Name=tag:DC,Values=${stop_dc}" "Name=instance-state-name,Values=running"  --query "Reservations[*].Instances[*].InstanceId" --output text)
  echo "stoping - ${stop_instance_is}"
  aws ec2 stop-instances --instance-ids ${stop_instance_is}

  while ! kubectl get pods -o wide | grep "ip-10-0-${wait_start_dc}-*" | grep -q "Running"; do
      echo "wait start instance DC ${wait_start_dc}"
      sleep 1  # Optional: Adjust the sleep duration as needed
  done

  echo "stop restarted"
  restartTime=$(date +%s%3N)
  restartTime=$((restartTime - disaster_time))
  time_difference_hours=$(bc <<< "scale=4; $restartTime / (1000 * 60 * 60)")
  echo ${time_difference_hours} >> restartTimes.txt

  aws ec2 start-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=${stop_dc}" "Name=instance-state-name,Values=stopped" --query "Reservations[*].Instances[*].InstanceId" --output text)

  sleep 3m

  change_dc=$stop_dc

  stop_dc=$wait_start_dc

  wait_start_dc=$change_dc

done

#shutdown all environment
aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=${wait_start_dc}"  --query "Reservations[*].Instances[*].InstanceId" --output text)
aws ec2 stop-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:DC,Values=${stop_dc}"  --query "Reservations[*].Instances[*].InstanceId" --output text)
sleep 3m
shutdown -h now