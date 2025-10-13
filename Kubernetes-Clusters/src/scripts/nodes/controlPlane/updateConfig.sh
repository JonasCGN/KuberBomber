#!/usr/bin/env bash
# updatekub.sh
# Uso:
#   sudo bash updatekub.sh [--fqdn api.seudominio.tld] [--public-ip X.X.X.X] [--persist-config]
# Ex.:
#   sudo bash updatekub.sh --persist-config
#   sudo bash updatekub.sh --fqdn api.exemplo.com --persist-config

set -euo pipefail

FQDN=""
PUBLIC_IP=""
PERSIST=false
KUBECONFIG_OUT="/home/ubuntu/kubeconfig.conf"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fqdn) FQDN="${2:-}"; shift 2;;
    --public-ip) PUBLIC_IP="${2:-}"; shift 2;;
    --persist-config) PERSIST=true; shift;;
    -h|--help)
      echo "Uso: $0 [--fqdn FQDN] [--public-ip X.X.X.X] [--persist-config]"
      exit 0;;
    *) echo "[!] Parâmetro desconhecido: $1"; exit 1;;
  esac
done

[[ $EUID -ne 0 ]] && { echo "[!] Rode como root (sudo)."; exit 1; }

# Caminhos do cert/clave do apiserver (kubeadm)
CRT="/etc/kubernetes/pki/apiserver.crt"
KEY="/etc/kubernetes/pki/apiserver.key"
[[ -f "$CRT" && -f "$KEY" ]] || { echo "[!] Não encontrei $CRT / $KEY. Este host é o control-plane com kubeadm?"; exit 1; }

# 1) Descobrir IP público via IMDSv2 se não informado
if [[ -z "$PUBLIC_IP" ]]; then
  echo "[*] Obtendo IP público via IMDSv2..."
  set +e
  TOKEN=$(curl -sS -m 3 -X PUT "http://169.254.169.254/latest/api/token" \
            -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
  PUBLIC_IP=$(curl -sS -m 3 -H "X-aws-ec2-metadata-token: ${TOKEN}" \
            "http://169.254.169.254/latest/meta-data/public-ipv4")
  set -e
  [[ -z "${PUBLIC_IP:-}" ]] && { echo "[!] Não consegui obter o IP público. Informe com --public-ip X.X.X.X"; exit 1; }
fi
echo "[OK] IP público detectado: ${PUBLIC_IP}"

# 2) Coletar SANs atuais do certificado
echo "[*] Lendo SANs atuais do apiserver..."
SAN_BLOCK=$(openssl x509 -in "$CRT" -noout -text | awk '/Subject Alternative Name/{flag=1;next}/X509v3/{flag=0}flag' || true)
readarray -t EXISTING_DNS < <(echo "$SAN_BLOCK" | grep -oE 'DNS:[^,]+' | sed 's/DNS://g;s/ //g' || true)
readarray -t EXISTING_IPS < <(echo "$SAN_BLOCK" | grep -oE 'IP Address:[^,]+' | sed 's/IP Address://g;s/ //g' || true)

# 3) Preparar lista final de SANs (sem duplicatas): todos os existentes + IP público + FQDN (se fornecido)
uniq_push() {
  local val="$1"; shift
  local -n arr="$1"
  [[ -z "$val" ]] && return 0
  for x in "${arr[@]:-}"; do [[ "$x" == "$val" ]] && return 0; done
  arr+=("$val")
}

uniq_push "$PUBLIC_IP" EXISTING_IPS
[[ -n "$FQDN" ]] && uniq_push "$FQDN" EXISTING_DNS

echo "[*] SANs finais que serão aplicados:"
for d in "${EXISTING_DNS[@]:-}"; do echo "    DNS: $d"; done
for i in "${EXISTING_IPS[@]:-}";  do echo "    IP:  $i"; done

# 4) Recriar o certificado do API Server com TODOS os SANs
TS=$(date +%F-%H%M%S)
cp -a "$CRT" "${CRT}.bak.${TS}" || true
cp -a "$KEY" "${KEY}.bak.${TS}" || true
rm -f "$CRT" "$KEY"

# Montar CSV para --apiserver-cert-extra-sans
SAN_CSV=""
for d in "${EXISTING_DNS[@]:-}"; do SAN_CSV+="${d},"; done
for i in "${EXISTING_IPS[@]:-}";  do SAN_CSV+="${i},"; done
SAN_CSV="${SAN_CSV%,}" # remove vírgula final

echo "[*] Recriando certificado do apiserver com SANs: ${SAN_CSV}"
kubeadm init phase certs apiserver --apiserver-cert-extra-sans "${SAN_CSV}"

# 5) Reiniciar o static pod do apiserver para carregar o novo cert
echo "[*] Reiniciando kube-apiserver (static pod)..."
if command -v crictl >/dev/null 2>&1; then
  POD_ID=$(crictl pods | awk '/kube-apiserver/{print $1; exit}' || true)
  if [[ -n "${POD_ID:-}" ]]; then
    crictl stopp "$POD_ID" || true
    crictl rmp "$POD_ID"   || true
  else
    # fallback: tocar o manifesto
    touch /etc/kubernetes/manifests/kube-apiserver.yaml
  fi
else
  # sem crictl: tocar o manifesto e reiniciar kubelet
  touch /etc/kubernetes/manifests/kube-apiserver.yaml
  systemctl restart kubelet || true
fi

echo "[*] Aguardando o apiserver subir (30s)..."
sleep 30

echo "[*] Conferindo SANs aplicados:"
openssl x509 -in "$CRT" -noout -text | sed -n '/Subject Alternative Name/,+1p' || true

# 6) (Opcional) Persistir ClusterConfiguration com certSANs para futuras renovações
if $PERSIST; then
  CFG="/root/kubeadm-cluster-sans.yaml"
  echo "[*] Persistindo certSANs no kubeadm-config..."
  {
    echo "apiVersion: kubeadm.k8s.io/v1beta3"
    echo "kind: ClusterConfiguration"
    echo "apiServer:"
    echo "  certSANs:"
    for d in "${EXISTING_DNS[@]:-}"; do echo "  - ${d}"; done
    for i in "${EXISTING_IPS[@]:-}";  do echo "  - ${i}"; done
  } > "$CFG"
  kubeadm init phase upload-config kubeadm --config "$CFG" || echo "[!] Aviso: não foi possível subir o kubeadm-config (ok continuar)."
fi

# 7) Exportar kubeconfig para /home/ubuntu/kubeconfig.conf e ajustar 'server:' para o IP público
echo "[*] Exportando kubeconfig para ${KUBECONFIG_OUT} ..."
cp /etc/kubernetes/admin.conf "$KUBECONFIG_OUT"
cp "$KUBECONFIG_OUT" "${KUBECONFIG_OUT}.bak.${TS}"

echo "[*] Ajustando 'server:' para https://${PUBLIC_IP}:6443 ..."
# Substitui o host preservando o prefixo e a porta
sed -E -i "s#^(\s*server:\s*https://)[^:/]+(:[0-9]+)?#\1${PUBLIC_IP}:6443#g" "$KUBECONFIG_OUT"

# Permissões conforme solicitado (atenção: 777 é inseguro)
chown ubuntu:ubuntu "$KUBECONFIG_OUT" || true
chmod 777 "$KUBECONFIG_OUT" || true
# (Recomendado em produção: chmod 600 "$KUBECONFIG_OUT")

echo "[OK] Concluído."
echo "    Kubeconfig atualizado: ${KUBECONFIG_OUT}"
echo "    Teste: KUBECONFIG=${KUBECONFIG_OUT} kubectl cluster-info && kubectl get nodes"
