#!/bin/bash

run_ssh_command(){
  remote_command="${1}"
  remote_address="${2}"
  echo "ssh -o StrictHostKeyChecking=no -i "${AWS_KEY_PEM}" ubuntu@${remote_address} ${remote_command}"
  ssh -o StrictHostKeyChecking=no -i "${AWS_KEY_PEM}" ubuntu@${remote_address} ${remote_command}
}

generate_data_CP(){
  remote_address="${1}"
  echo "ssh -o StrictHostKeyChecking=no -i ${AWS_KEY_PEM} ubuntu@${remote_address} nohup /home/ubuntu/get_k8s_metrics.sh 1 /home/ubuntu/$METRIC_DATA  &&"
  ssh -o StrictHostKeyChecking=no -i "${AWS_KEY_PEM}" ubuntu@${remote_address} "sudo nohup /home/ubuntu/get_k8s_metrics.sh 1 /home/ubuntu/$METRIC_DATA   &" &
}

stop_generate_data_CP(){
  remote_address="${1}"
  ssh -o StrictHostKeyChecking=no -i "${AWS_KEY_PEM}" ubuntu@${remote_address} "sudo pkill -f /home/ubuntu/$METRIC_DATA"
}

copy_files_from_CP(){
  remote_address="${1}"
  LOG_PATH="${2}"
  echo "scp -i ${AWS_KEY_PEM} ubuntu@${remote_address}:/home/ubuntu/$METRIC_DATA $LOG_PATH/"
  scp -i "${AWS_KEY_PEM}" ubuntu@${remote_address}:/home/ubuntu/$METRIC_DATA $LOG_PATH/
}

copy_log_files_from_CP(){
  remote_address="${1}"
  LOG_PATH="${2}"
  echo "scp -i ${AWS_KEY_PEM} ubuntu@${remote_address}:/home/ubuntu/after_install.log"
  scp -i "${AWS_KEY_PEM}" ubuntu@${remote_address}:/home/ubuntu/after_install.log $LOG_PATH/
}

copy_log_files_from_kb_conf(){
  remote_address="${1}"
  LOG_PATH="${2}"
  echo "scp -i ${AWS_KEY_PEM} ubuntu@${remote_address}:/home/ubuntu/kubernetes/kub_deployment.yaml"
  scp -i "${AWS_KEY_PEM}" ubuntu@${remote_address}:/home/ubuntu/kubernetes/kub_deployment.yaml $LOG_PATH/kub_deployment.yaml
  echo "scp -i ${AWS_KEY_PEM} ubuntu@${remote_address}:/home/ubuntu/kubernetesWS/kub_deployment_ws.yaml"
  scp -i "${AWS_KEY_PEM}" ubuntu@${remote_address}:/home/ubuntu/kubernetesWS/kub_deployment.yaml $LOG_PATH/kub_deployment_ws.yaml
}

run_experiment(){
  echo "--- begin run_experiment $(date +"%d-%m-%Y-%H-%M") ---"
  echo "./run_experiment.sh ${1} ${2} ${3} ${4}"

  export comment="uso apenas dos ultimos 15 segundos, reduçao do tempo para remoção para 10 segundo, sla novo=2"
  METRIC_DATA="k8s_metric.csv"
  export EXPERIMENT_TIME="70m"
  export DELAY_BETWEEN_RUN="1m"
  export CONFIDENCE_INTERVAL=0.95
  AWS_KEY_PEM=/home/ubuntu/awsacademy.pem


  export LABEL="teste-lat02"
  export LOW_EXPONENTIAL_MEAN_TIME=0.2
  export HIGH_EXPONENTIAL_MEAN_TIME=0.009
  export LOW_EXPONENTIAL_DURATION=190
  export HIGH_EXPONENTIAL_DURATION=190
  export MOVING_AVERAGE=60
  export TIME_STEP_INTERVAL=15



  BUCKET="${1}"
  LB_ADDR="${2}"
  GOOGLE_DRIVE_FOLDER_ID="${3}"
  CP_PUBLIC_ADDR=${4}

  export PROMETHEUS_PORT=30082
  export PROMETHEUS_ADDRESS="http://${CP_PUBLIC_ADDR}"
  export PROMETHEUS_MONITOR_INTERVAL=60


  while true; do
      status_code=$(curl -o /dev/null -s -w "%{http_code}\n" "http://${LB_ADDR}/test")
      if [ "$status_code" -eq 200 ]; then
          echo "Address is accessible!"
          break
      else
          echo "Waiting for http://${LB_ADDR}/test to be accessible..."
          sleep 30  # Wait for 5 seconds before retrying
      fi
  done

  sleep 5m

  ls -lha

  DIR_NAME=$(date +"%Y-%m-%d-%H-%M")
  BASE_DIR="/home/ubuntu/validation"
  mkdir -p "$BASE_DIR"
  LOG_DIR="$BASE_DIR/$DIR_NAME"
  echo "$LOG_DIR"
  mkdir -p "$LOG_DIR"

  # Shift the first 4 parameters and process the remaining ones
  shift 4
  echo "run the exponential times $@"
  echo "Processing additional parameters:"
  for expo in "$@"; do
      echo "run experiment with arrival rate: $expo"
      export EXPONENTIAL_MEAN=$expo


      export LOG_PATH="$LOG_DIR/$EXPONENTIAL_MEAN"
      mkdir -p $LOG_PATH

      echo "LOG_PATH is set to: $LOG_PATH"
      echo "arrival rate is set to: $EXPONENTIAL_MEAN"

      cd /home/ubuntu/

      generate_data_CP "${CP_PUBLIC_ADDR}"

      #window-seconds não inforior a 60
      python3 locust/prom_logger.py --deployments foo-app,bar-app \
      --window-seconds ${PROMETHEUS_MONITOR_INTERVAL} \
      --collect-interval-seconds ${PROMETHEUS_MONITOR_INTERVAL} \
        --out "${BASE_DIR}/${DIR_NAME}/$EXPONENTIAL_MEAN/prometheus_data_${expo}.csv" & PROM_PID=$!

      #teste um log COM RAW
      python3 locust/prom_logger_raw.py \
        --deployments foo-app,bar-app \
        --window-seconds 60 \
        --collect-interval-seconds 60 \
        --step-seconds 1 \
        --out "${BASE_DIR}/${DIR_NAME}/${EXPONENTIAL_MEAN}/prometheus_means_${expo}.csv" \
        --steps-out "${BASE_DIR}/${DIR_NAME}/${EXPONENTIAL_MEAN}/prometheus_steps_${expo}.csv" \
        & PROM_PID_RAW=$!

#      locust --locustfile locust/locust.py \
#      --csv "$LOG_PATH/locust_results" \
#      --logfile $LOG_PATH/locust_log \
#      --host "http://${LB_ADDR}" \
#      --run-time ${EXPERIMENT_TIME} \
#      --users 1 \
#      --spawn-rate 1 \
#      --headless

      #teste carga crescente para validar a
#      locust --locustfile locust/locust_test.py \
#      --csv "$LOG_PATH/locust_results" \
#      --logfile $LOG_PATH/locust_log \
#      --host "http://${LB_ADDR}" \
#      --run-time ${EXPERIMENT_TIME} \
#      --users 1 \
#      --spawn-rate 1 \
#      --headless

#      locust --locustfile locust/locust_steps.py \
#      --csv "$LOG_PATH/locust_results" \
#      --logfile $LOG_PATH/locust_log \
#      --host "http://${LB_ADDR}" \
#      --run-time ${EXPERIMENT_TIME} \
#      --users 1 \
#      --spawn-rate 1 \
#      --headless


      export LOW_EXPONENTIAL_MEAN_TIME=0.1
      export HIGH_EXPONENTIAL_MEAN_TIME=0.006
      export LOW_EXPONENTIAL_DURATION=150
      export HIGH_EXPONENTIAL_DURATION=250
#      TRACE_MODE=record \
#      TRACE_FILE="$LOG_PATH/arrival_trace.csv" \
      TRACE_MODE=replay \
      TRACE_FILE="/home/ubuntu/arrival_trace.csv" \
      locust --locustfile locust/locust_steps_random.py \
        --csv "$LOG_PATH/locust_results" \
        --logfile "$LOG_PATH/locust_log" \
        --host "http://$LB_ADDR" \
        --run-time "$EXPERIMENT_TIME" \
        --users 1 \
        --spawn-rate 1 \
        --headless


      echo " locust --locustfile locust/locust.py \
                  --csv "$LOG_PATH/locust_results" \
                  --logfile $LOG_PATH/locust_log \
                  --host "http://${LB_ADDR}" \
                  --run-time ${EXPERIMENT_TIME} \
                  --users 1 \
                  --spawn-rate 1 \
                  --headless"

      kill "$PROM_PID"
      kill "$PROM_PID_RAW"

      JSON_KEY_FILE_PATH=googleservices.json

      copy_files_from_CP "${CP_PUBLIC_ADDR}" "${LOG_PATH}"

      copy_log_files_from_CP "${CP_PUBLIC_ADDR}" "${LOG_PATH}"

      stop_generate_data_CP "${CP_PUBLIC_ADDR}"

      python3 locust/generategraph.py validation/$DIR_NAME/$EXPONENTIAL_MEAN/k8s_metric.csv  --ignore-begin-plot-time 60

      python3 locust/generate_locust_graph.py $LOG_PATH/response_times.csv --outdir ./graphs  --ignore-begin-plot-time 60

      mv graphs ${BASE_DIR}/${DIR_NAME}/$EXPONENTIAL_MEAN/

      python3 locust/resume_data.py ${BASE_DIR}/${DIR_NAME}/ ${CONFIDENCE_INTERVAL}

      echo "valores das variavis de LOW e HIGH são TAXAS e não TEMPO"
      env > validation/$DIR_NAME/$EXPONENTIAL_MEAN/env.log

      cp /var/log/run_experiment.log ${LOG_PATH}/
      cp /var/log/install_client.log ${LOG_PATH}/

      copy_log_files_from_kb_conf "${CP_PUBLIC_ADDR}" "${LOG_PATH}"

      cp /home/ubuntu/dockerkubedt.log ${LOG_PATH}/

      if [ -e $JSON_KEY_FILE_PATH  ]; then
        LOCAL_DIRECTORY_PATH=$BASE_DIR
        GOOGLE_DRIVE_FOLDER_ID=${GOOGLE_DRIVE_FOLDER_ID}
        INTERMEDIATE_FOLDER_NAME=digitaltwin
        echo "python3 locust/upload_to_drive.py $JSON_KEY_FILE_PATH $LOCAL_DIRECTORY_PATH $GOOGLE_DRIVE_FOLDER_ID $INTERMEDIATE_FOLDER_NAME"
        python3 locust/upload_to_drive.py "$JSON_KEY_FILE_PATH" "$LOCAL_DIRECTORY_PATH" "$GOOGLE_DRIVE_FOLDER_ID" "$INTERMEDIATE_FOLDER_NAME"
      fi

      echo "sleep ${DELAY_BETWEEN_RUN} the experiment to reduce the HPA to default value"
      sleep ${DELAY_BETWEEN_RUN}

      echo "finish experiment with arrival rate: $expo"
  done

  echo "--- end run_experiment $(date +"%d-%m-%Y-%H-%M") ---"

  aws cloudformation delete-stack --stack-name BaseInfrastructureStack

}

echo "run_experiment" >> /var/log/run_experiment.log
run_experiment "$@"  >> /var/log/run_experiment.log 2>&1