### lista deployments
http://54.86.240.39:30082/api/v1/query?query=kube_deployment_status_replicas_available{namespace="default"}>0
### CPU utilization:
# Bar service
http://3.84.224.31:30082/api/v1/query?query=sum(rate(container_cpu_usage_seconds_total{namespace="default", pod=~"bar-app.*"}[5m]))
# Foo service
http://3.84.224.31:30082/api/v1/query?query=sum(rate(container_cpu_usage_seconds_total{namespace="default", pod=~"foo-app.*"}[5m]))

### Memory utilization
# Bar service
http://3.84.224.31:30082/api/v1/query?query=sum(avg_over_time(container_memory_usage_bytes{namespace="default",%20pod=~"bar-app.*",%20container="bar-app"}[5m]))
# Foo service
http://3.84.224.31:30082/api/v1/query?query=sum(avg_over_time(container_memory_usage_bytes{namespace="default",%20pod=~"foo-app.*",%20container="foo-app"}[5m]))

### response time
# bar service
http://3.84.224.31:30082/api/v1/query?query=(sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-bar-service-9898"}[5m])) / sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-bar-service-9898"}[5m]))) / 1000
# foo service
http://3.84.224.31:30082/api/v1/query?query=(sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-foo-service-9898"}[5m])) / sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-foo-service-9898"}[5m]))) / 1000
# foo e bar
http://3.84.224.31:30082/api/v1/query?query=(sum by (upstream) (rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[5m])) / sum by (upstream) (rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[5m]))) / 1000

### TP - vazao
# bar service
http://3.84.224.31:30082/api/v1/query?query=sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-bar-service-9898"}[${QUERY_INTERVAL}]))
# foo service
http://3.84.224.31:30082/api/v1/query?query=sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-foo-service-9898"}[${QUERY_INTERVAL}]))
# foo e bar
http://3.84.224.31:30082/api/v1/query?query=sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[${QUERY_INTERVAL}]))

# ingress input
http://3.84.224.31:30082/api/v1/query?query=sum(rate(nginx_ingress_controller_requests_total{namespace="nginx-ingress"}[5m]))


### qt media de pods
# bar service
http://3.84.224.31:30082/api/v1/query?query=avg_over_time(kube_deployment_status_replicas_available{namespace="default", deployment="bar-app"}[5m])
# foo service
http://3.84.224.31:30082/api/v1/query?query=avg_over_time(kube_deployment_status_replicas_available{namespace="default", deployment="foo-app"}[5m])

### qt media de worker nodes
http://3.84.224.31:30082/api/v1/query?query=sum(avg_over_time(kube_node_status_condition{condition="Ready", status="true"}[5m])) - 1

## qt medida de trabalhos -TODO
http://3.84.224.31:30082/api/v1/query?query=avg_over_time(sum(kube_job_status_active{namespace="default"})[5m])


#!/bin/bash

# --- Variáveis de Configuração ---
# Endereço IP ou hostname do seu servidor Prometheus
PROMETHEUS_ADD="3.84.224.31"
# Porta do seu servidor Prometheus
PROMETHEUS_PORT="30082"
# Intervalo de tempo para as consultas PromQL (ex: '5m', '1h')
QUERY_INTERVAL="5m" # Pode ser alterado conforme sua necessidade

# URL base do Prometheus
PROMETHEUS_BASE_URL="http://${PROMETHEUS_ADD}:${PROMETHEUS_PORT}/api/v1/query"

# --- Consultas PromQL ---
# As consultas são definidas como strings para facilitar a leitura.
# Quando usadas com curl, o shell ou o próprio curl farão a codificação de URL necessária.

# --- Utilização de CPU ---
# Bar service
QUERY_CPU_BAR='sum(rate(container_cpu_usage_seconds_total{namespace="default", pod=~"bar-app.*"}[${QUERY_INTERVAL}]))'
# Foo service
QUERY_CPU_FOO='sum(rate(container_cpu_usage_seconds_total{namespace="default", pod=~"foo-app.*"}[${QUERY_INTERVAL}]))'

# --- Utilização de Memória ---
# Bar service (agora média ao longo do tempo para o container 'bar-app')
QUERY_MEMORY_BAR='sum(avg_over_time(container_memory_usage_bytes{namespace="default", pod=~"bar-app.*", container="bar-app"}[${QUERY_INTERVAL}]))'
# Foo service (agora média ao longo do tempo para o container 'foo-app')
QUERY_MEMORY_FOO='sum(avg_over_time(container_memory_usage_bytes{namespace="default", pod=~"foo-app.*", container="foo-app"}[${QUERY_INTERVAL}]))'

# --- Tempo de Resposta (em segundos) ---
# Bar service
QUERY_RESPONSE_TIME_BAR='(sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-bar-service-9898"}[${QUERY_INTERVAL}])) / sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-bar-service-9898"}[${QUERY_INTERVAL}]))) / 1000'
# Foo service
QUERY_RESPONSE_TIME_FOO='(sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-foo-service-9898"}[${QUERY_INTERVAL}])) / sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-foo-service-9898"}[${QUERY_INTERVAL}]))) / 1000'
# Foo e Bar (agrupado por upstream)
QUERY_RESPONSE_TIME_FOO_BAR_GROUPED='(sum by (upstream) (rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[${QUERY_INTERVAL}])) / sum by (upstream) (rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[${QUERY_INTERVAL}]))) / 1000'
# Foo e Bar (valor único combinado)
QUERY_RESPONSE_TIME_FOO_BAR_COMBINED='(sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[${QUERY_INTERVAL}])) / sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[${QUERY_INTERVAL}]))) / 1000'

# --- response time (RPS) ---
# Bar service
QUERY_ARRIVAL_RATE_BAR='sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-bar-service-9898"}[${QUERY_INTERVAL}]))'
# Foo service
QUERY_ARRIVAL_RATE_FOO='sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream="default-example-ingress-*.amazonaws.com-foo-service-9898"}[${QUERY_INTERVAL}]))'
# Foo e Bar (valor único combinado)
QUERY_ARRIVAL_RATE_FOO_BAR_COMBINED='sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count{namespace="nginx-ingress", upstream=~"default-example-ingress-.*-(bar|foo)-service-9898"}[${QUERY_INTERVAL}]))'

# --- Quantidade Média de Pods ---
# Bar service
QUERY_AVG_REPLICAS_BAR='avg_over_time(kube_deployment_status_replicas_available{namespace="default", deployment="bar-app"}[${QUERY_INTERVAL}])'
# Foo service
QUERY_AVG_REPLICAS_FOO='avg_over_time(kube_deployment_status_replicas_available{namespace="default", deployment="foo-app"}[${QUERY_INTERVAL}])'

# --- Quantidade Média de Worker Nodes ---
# Esta consulta calcula a média da quantidade de nós "Ready" (incluindo o control plane) e subtrai 1.
QUERY_AVG_WORKER_NODES='sum(avg_over_time(kube_node_status_condition{condition="Ready", status="true"}[${QUERY_INTERVAL}])) - 1'

# --- Quantidade Média de Trabalhos (Jobs) Ativos ---
# Média do número TOTAL de trabalhos ativos no namespace 'default' ao longo do tempo
# Devido a limitações na versão do Prometheus, esta consulta retorna a contagem INSTANTÂNEA
# de Jobs ativos. Para a média ao longo do tempo, use uma ferramenta de visualização como o Grafana.
QUERY_AVG_ACTIVE_JOBS='sum(kube_job_status_active{namespace="default"})'

# --- Vazão de Dados (Bytes por Segundo) ---
# Vazão total de bytes enviados pelo NGINX Ingress Controller
QUERY_THROUGHPUT_BYTES='sum(rate(nginx_ingress_controller_bytes_sent_total{namespace="nginx-ingress"}[${QUERY_INTERVAL}]))'

# --- Taxa de Entrada (Requisições por Segundo - RPS Total do Ingress Controller) ---
# Quantidade de requisições que entram no sistema por segundo, agregando todas as instâncias do Ingress Controller.
QUERY_INGRESS_RPS_TOTAL='sum(rate(nginx_ingress_controller_requests_total{namespace="nginx-ingress"}[${QUERY_INTERVAL}]))'


# --- Exemplos de como usar as variáveis em comandos curl ---
echo "--- Exemplos de uso ---"
echo "CPU - Bar service:"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_CPU_BAR}\""
echo ""

echo "Memory - Foo service:"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_MEMORY_FOO}\""
echo ""

echo "Response Time - Foo e Bar (grouped by upstream):"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_RESPONSE_TIME_FOO_BAR_GROUPED}\""
echo ""

echo "Arrival Rate - Foo e Bar (combined single value):"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_ARRIVAL_RATE_FOO_BAR_COMBINED}\""
echo ""

echo "Average Worker Nodes:"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_AVG_WORKER_NODES}\""
echo ""

echo "Average Active Jobs:"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_AVG_ACTIVE_JOBS}\""
echo ""

echo "Throughput (Bytes/Sec):"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_THROUGHPUT_BYTES}\""
echo ""

echo "Ingress RPS Total:"
echo "curl \"${PROMETHEUS_BASE_URL}?query=${QUERY_INGRESS_RPS_TOTAL}\""
echo ""