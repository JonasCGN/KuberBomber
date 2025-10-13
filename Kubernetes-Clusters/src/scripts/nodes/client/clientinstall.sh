#!/bin/bash

install_docker(){
  echo "install docker"
  apt-get remove -y docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc || true

  # 1) Pré-requisitos e chave do repositório oficial
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  # 2) Recria o arquivo /etc/apt/sources.list.d/docker.list CORRETAMENTE (1 linha só!)
  rm -f /etc/apt/sources.list.d/docker.list
  ARCH="$(dpkg --print-architecture)"
  CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list

  # 3) Instala Docker Engine + CLI + containerd + buildx + compose plugin
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # 4) Sobe serviço e valida
  systemctl enable --now docker
  docker --version
  echo "installed docker"
}

wait_copy_from_s3() {
  local bucket="${1:?informe o bucket}"
  local key="${2:?informe a key (ex: kubeconfig.conf)}"
  local dest="${3:?informe o destino local}"

  if ! command -v aws >/dev/null 2>&1; then
    echo "[erro] aws CLI não encontrado no PATH" >&2
    return 127
  fi

  # Respeita AWS_PROFILE/AWS_REGION se definidos
  local args=()
  [[ -n "${AWS_PROFILE:-}" ]] && args+=(--profile "$AWS_PROFILE")
  [[ -n "${AWS_REGION:-}"  ]] && args+=(--region  "$AWS_REGION")

  echo "[info] aguardando s3://${bucket}/${key} (checando a cada 1s)..."
  while :; do
    if aws s3api head-object --bucket "$bucket" --key "$key" "${args[@]}" >/dev/null 2>&1; then
      echo "[info] encontrado, copiando para ${dest}..."
      mkdir -p -- "$(dirname -- "$dest")"
      aws s3 cp "s3://${bucket}/${key}" "$dest" --no-progress "${args[@]}"
      echo "[ok] copiado: ${dest}"
      return 0
    fi
    echo "[info] aguardando s3://${bucket}/${key} (checando a cada 1s)..."
    sleep 1
  done
}

run_dt_container(){

  CP_PUBLIC_ADDR="${1}"
  RABBITMQ_HOST="${2}"
  RABBITMQ_PASS="${3}"

  export WINDOW_SECONDS=60
  export DATA_TIME_FILTER_LAST=60
  export STEP_SECONDS=1
  export SLA=10.0
  export DELAY_BETWEEN_RUN=15

  echo "docker run --rm -dt --name kubedt \
    -e PROMETHEUS_BASE=\"http://${CP_PUBLIC_ADDR}:30082\" \
    -e WINDOW_SECONDS=${WINDOW_SECONDS} \
    -e DATA_TIME_FILTER_LAST=${DATA_TIME_FILTER_LAST} \
    -e STEP_SECONDS=${STEP_SECONDS} \
    -e SLA=${SLA} \
    -e DELAY_BETWEEN_RUN=${DELAY_BETWEEN_RUN} \
    -e KUBECONFIG=\"/app/kubeconfig.conf\" \
    -e RABBITMQ_HOST=\"${RABBITMQ_HOST}\" \
    -e RABBITMQ_USER=user \
    -e RABBITMQ_PASS=\"${RABBITMQ_PASS}\" \
    -e RABBITMQ_PORT=5672 \
    -v /home/ubuntu/kubeconfig.conf:/app/kubeconfig.conf:ro \
    iuresf/kubernetes-dt:latest"

  docker run --rm \
    -dt \
    --name kubedt \
    -e PROMETHEUS_BASE="http://${CP_PUBLIC_ADDR}:30082" \
    -e WINDOW_SECONDS=${WINDOW_SECONDS} \
    -e DATA_TIME_FILTER_LAST=${DATA_TIME_FILTER_LAST} \
    -e STEP_SECONDS=${STEP_SECONDS} \
    -e SLA=${SLA} \
    -e DELAY_BETWEEN_RUN=${DELAY_BETWEEN_RUN} \
    -e KUBECONFIG="/app/kubeconfig.conf" \
    -e RABBITMQ_HOST="${RABBITMQ_HOST}" \
    -e RABBITMQ_USER=user \
    -e RABBITMQ_PASS="${RABBITMQ_PASS}" \
    -e RABBITMQ_PORT=5672 \
    -v /home/ubuntu/kubeconfig.conf:/app/kubeconfig.conf:ro \
    iuresf/kubernetes-dt:latest

    nohup docker logs -f kubedt >> /home/ubuntu/dockerkubedt.log 2>&1 &
    disown

}

install_client(){
  echo "begin install_client"
  echo "install ${1} ${2} ${3} ${4}"

  BUCKET="${1}"
  LB_ADDR="${2}"
  GOOGLE_DRIVE_FOLDER_ID="${3}"
  CP_PUBLIC_ADDR=${4}
  RABBITMQ_HOST="${5}"
  RABBITMQ_PASS="${6}"

  ls -lha

  echo "${4} $CP_PUBLIC_ADDR"

  apt-get update

  apt-get install python3-pip -y

  pip install locust pandas matplotlib scipy

  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

  apt-get install -y python3-zope.event

  echo "finish install_client"

  echo "copy kubernetes files"

  install_docker

  wait_copy_from_s3 "$BUCKET" "kubeconfig.conf" "/home/ubuntu/kubeconfig.conf"

  run_dt_container "$CP_PUBLIC_ADDR" "$RABBITMQ_HOST" "$RABBITMQ_PASS"

  echo "run experiment"

  echo "/home/ubuntu/run_experiment.sh ${BUCKET} ${LB_ADDR} ${GOOGLE_DRIVE_FOLDER_ID} ${CP_PUBLIC_ADDR} 1"

#  /home/ubuntu/run_experiment.sh ${BUCKET} ${LB_ADDR} ${GOOGLE_DRIVE_FOLDER_ID} ${CP_PUBLIC_ADDR} "0.05" "0.075" "0.1" "0.125" "0.15" "0.175" "0.2" "0.225" "0.25" "0.275" "0.3" "0.325" "0.35" "0.375" "0.4" "0.425" "0.45" "0.475" "0.5"
  /home/ubuntu/run_experiment.sh ${BUCKET} ${LB_ADDR} ${GOOGLE_DRIVE_FOLDER_ID} ${CP_PUBLIC_ADDR} "1"

  echo "finish experiment"

}

echo "install_client" >> /var/log/install_client.log
install_client "$@"  >> /var/log/install_client.log 2>&1