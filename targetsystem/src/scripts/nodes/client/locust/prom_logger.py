#!/usr/bin/env python3
"""
Prometheus logger (SPN metrics) -> CSV
--------------------------------------
Cada ciclo escreve 1 linha por deployment no MESMO timestamp.

Colunas (agora padronizadas em segundos para tempos):
 DateTime, Deployment, NumberOfJobsCeil, TotalPodsCeil,
 Moving Avg Window (s), MA Arrival Rate (req/s), MA Throughput (req/s), MA Response Time (s),
 CPUUsage(cores/s), MemoryUsage(bytes)

+ Novas colunas (std calculado pelo Prometheus na janela):
 - MA Arrival Rate Std (req/s)
 - MA Throughput Std (req/s)   [mesmo valor do Arrival quando derivado da mesma fonte]
 - MA Response Time Std (s)
 - CPUUsage Std (cores/s)
 - MemoryUsage Std (bytes)
 - Replicas Std (unidades)

Notas:
- O std é calculado com stddev_over_time sobre uma **subquery temporal** da expressão:
  stddev_over_time( (EXPR)[<window>:<subquery_step>] )
- Defina --subquery-step-seconds ~ igual ao seu scrape_interval (ex.: 15).
"""

import os
import csv
import time
import json
import math
import argparse
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================
# Logging
# =========================
log = logging.getLogger("prom_logger")

def setup_logging(debug: bool, log_file: Optional[str]):
    level = logging.DEBUG if debug else logging.INFO
    log.setLevel(level)
    fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(level)
    log.handlers.clear()
    log.addHandler(ch)
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setLevel(level)
        fh.setFormatter(fmt)
        log.addHandler(fh)

# =========================
# Config e normalização
# =========================
def normalize_address(address: Optional[str], port: Optional[str]) -> str:
    if not address:
        address = "http://localhost"
    addr = address.strip().rstrip("/")
    if "://" in addr:
        hostpart = addr.split("://", 1)[1]
        if ":" in hostpart.split("/")[0]:
            base = addr
        else:
            base = f"{addr}:{port}" if port else addr
    else:
        if port and (":" not in addr):
            base = f"http://{addr}:{port}"
        else:
            base = f"http://{addr}"
            if port and (":" not in addr):
                base = f"{base}:{port}"
    return base

def base_query_url(base_addr: str) -> str:
    return f"{base_addr}/api/v1/query"

# =========================
# Helpers Prometheus
# =========================
def prom_query(base_addr: str, promql: str, timeout: int = 10) -> Dict[str, Any]:
    url = base_query_url(base_addr) + "?query=" + urllib.parse.quote(promql, safe="")
    log.debug(f"PROMQL: {promql}")
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except Exception as e:
        log.warning(f"Prometheus query error: {type(e).__name__}: {e}")
        return {"status": "error", "error": type(e).__name__, "message": str(e)}

def extract_single_value(prom_json: Dict[str, Any]) -> float:
    try:
        if prom_json.get("status") != "success":
            return float("nan")
        data = prom_json.get("data", {})
        result = data.get("result", [])
        if not result:
            return float("nan")
        value = result[0].get("value", [])
        if len(value) < 2:
            return float("nan")
        s = str(value[1])
        if s in ("NaN", "Inf", "+Inf", "-Inf", ""):
            return float("nan")
        return float(s)
    except Exception:
        return float("nan")

def window_from_seconds(seconds: float) -> str:
    sec = max(1, int(round(float(seconds))))
    return f"[{sec//60}m]" if sec % 60 == 0 else f"[{sec}s]"

def subquery_window(window_seconds: float, sub_step_seconds: float) -> str:
    """Formata '[<window>:<step>]' sempre em segundos inteiros."""
    w = max(1, int(round(float(window_seconds))))
    s = max(1, int(round(float(sub_step_seconds))))
    return f"[{w}s:{s}s]"

def to_service_and_port(deployment: str) -> Tuple[str, str]:
    base = deployment.replace("-app", "")
    return f"{base}-service", "9898"

def escape_label_value(s: str) -> str:
    return s.replace('"', '\\"') if s else ""

def escape_regex_for_label(s: str) -> str:
    if s is None:
        return ""
    specials = '\\.*+?[]^$(){}=!<>|:'
    out = []
    for ch in s:
        if ch in specials:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)

def hostprefix_to_regex(prefix: str) -> str:
    if not prefix:
        return ""
    esc = escape_regex_for_label(prefix)
    return esc.replace("\\*", ".*")

# =========================
# Padrões de "upstream"
# =========================
def upstream_candidates(deployment: str, namespace: str, ingress_host_prefix: str) -> List[str]:
    svc, port = to_service_and_port(deployment)
    svc_re = escape_regex_for_label(svc)
    host_re = hostprefix_to_regex(ingress_host_prefix)

    cands = []
    if host_re:
        cands.append(f".*{host_re}-{svc_re}-{port}$")
    cands.append(f"k8s://{namespace}/{svc}:{port}")
    cands.append(f"{svc}.{namespace}.svc.cluster.local:{port}")
    cands.append(f"{svc}.{namespace}.svc:{port}")
    cands.append(f".*{svc}:{port}$")
    cands.append(f".*{svc}-{port}$")
    # Dedupe preservando ordem
    seen, out = set(), []
    for x in cands:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def first_non_nan_from_queries(base_addr: str, queries: List[str]) -> float:
    for q in queries:
        v = extract_single_value(prom_query(base_addr, q))
        if math.isfinite(v):
            log.debug(f"[MATCH] {q} -> {v}")
            return v
        else:
            log.debug(f"[MISS]  {q}")
    return float("nan")

# =========================
# Consultas (médias)
# =========================
def list_deployments_in_use(base_addr: str, k8s_namespace: str) -> List[str]:
    q = f'kube_deployment_status_replicas_available{{namespace="{k8s_namespace}"}}>0'
    raw = prom_query(base_addr, q)
    try:
        if raw.get("status") != "success":
            return []
        result = raw.get("data", {}).get("result", [])
        names = []
        for el in result:
            metric = el.get("metric", {})
            dep = metric.get("deployment")
            if dep:
                names.append(dep)
        unique_sorted = sorted(set(names))
        log.info(f"Deployments in use (auto): {unique_sorted}")
        return unique_sorted
    except Exception:
        return []

def get_cpu_usage(base_addr: str, deployment: str, window_seconds: float, k8s_namespace: str) -> float:
    w = window_from_seconds(window_seconds)
    dep_re = escape_regex_for_label(deployment)
    q = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{k8s_namespace}",pod=~"{dep_re}.*"}}{w}))'
    return extract_single_value(prom_query(base_addr, q))

def get_memory_usage(base_addr: str, deployment: str, window_seconds: float, k8s_namespace: str) -> float:
    w = window_from_seconds(window_seconds)
    container = escape_label_value(deployment)
    dep_re = escape_regex_for_label(deployment)
    q = (f'sum(avg_over_time(container_memory_usage_bytes'
         f'{{namespace="{k8s_namespace}",pod=~"{dep_re}.*",container="{container}"}}{w}))')
    return extract_single_value(prom_query(base_addr, q))

def get_response_time_seconds(base_addr: str, deployment: str, window_seconds: float,
                              ingress_ns: str, ingress_host_prefix: str,
                              upstream_regex_override: Optional[str]) -> float:
    """Retorna média do tempo de resposta em **segundos**."""
    w = window_from_seconds(window_seconds)
    patterns = [upstream_regex_override] if upstream_regex_override else upstream_candidates(
        deployment, ingress_ns if ingress_ns else "default", ingress_host_prefix
    )
    queries = [
        # (ms_sum/ms_count) -> ms ; /1000 -> s
        f'(sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w})) / '
        f'sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w}))) / 1000'
        for pat in patterns
    ]
    v = first_non_nan_from_queries(base_addr, queries)
    if not math.isfinite(v):
        log.warning(f"[RT] Nenhum upstream combinou para {deployment}. Use --upstream-regex se souber o valor.")
    return v

def get_throughput_rps(base_addr: str, deployment: str, window_seconds: float,
                       ingress_ns: str, ingress_host_prefix: str,
                       upstream_regex_override: Optional[str]) -> float:
    w = window_from_seconds(window_seconds)
    patterns = [upstream_regex_override] if upstream_regex_override else upstream_candidates(
        deployment, ingress_ns if ingress_ns else "default", ingress_host_prefix
    )
    q_latency_count = [
        f'sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w}))'
        for pat in patterns
    ]
    # Fallbacks por service (caso não reporte por upstream)
    svc, port = to_service_and_port(deployment)
    svc_re = escape_regex_for_label(svc)
    q_requests = [
        f'sum(rate(nginx_ingress_controller_requests_total'
        f'{{namespace="{ingress_ns}",service=~".*{svc_re}(:{port})?"}}{w}))',
        f'sum(rate(nginx_ingress_controller_requests'
        f'{{namespace="{ingress_ns}",service=~".*{svc_re}(:{port})?"}}{w}))'
    ]
    v = first_non_nan_from_queries(base_addr, q_latency_count + q_requests)
    if not math.isfinite(v):
        log.warning(f"[TP] Nenhum padrão funcionou para {deployment}. Tente --upstream-regex.")
    return v

def get_avg_replicas(base_addr: str, deployment: str, window_seconds: float, k8s_namespace: str) -> float:
    w = window_from_seconds(window_seconds)
    dep = escape_label_value(deployment)
    q = (f'avg_over_time(kube_deployment_status_replicas_available'
         f'{{namespace="{k8s_namespace}",deployment="{dep}"}}{w})')
    return extract_single_value(prom_query(base_addr, q))

# =========================
# Consultas (stddev na janela)
# =========================
def std_over_time_of_expr(base_addr: str, expr: str, window_seconds: float, sub_step_seconds: float) -> float:
    """
    Calcula stddev_over_time( (expr)[window:sub_step] ) em um query instantâneo.
    """
    subw = subquery_window(window_seconds, sub_step_seconds)
    q = f'stddev_over_time(({expr}){subw})'
    return extract_single_value(prom_query(base_addr, q))

def get_cpu_usage_std(base_addr: str, deployment: str, window_seconds: float, k8s_namespace: str,
                      sub_step_seconds: float) -> float:
    w = window_from_seconds(window_seconds)
    dep_re = escape_regex_for_label(deployment)
    expr = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{k8s_namespace}",pod=~"{dep_re}.*"}}{w}))'
    return std_over_time_of_expr(base_addr, expr, window_seconds, sub_step_seconds)

def get_memory_usage_std(base_addr: str, deployment: str, window_seconds: float, k8s_namespace: str,
                         sub_step_seconds: float) -> float:
    w = window_from_seconds(window_seconds)
    container = escape_label_value(deployment)
    dep_re = escape_regex_for_label(deployment)
    expr = (f'sum(avg_over_time(container_memory_usage_bytes'
            f'{{namespace="{k8s_namespace}",pod=~"{dep_re}.*",container="{container}"}}{w}))')
    return std_over_time_of_expr(base_addr, expr, window_seconds, sub_step_seconds)

def get_response_time_seconds_std(base_addr: str, deployment: str, window_seconds: float,
                                  ingress_ns: str, ingress_host_prefix: str,
                                  upstream_regex_override: Optional[str],
                                  sub_step_seconds: float) -> float:
    """Retorna o desvio-padrão do tempo de resposta em **segundos** (já divide por 1000 no PromQL)."""
    w = window_from_seconds(window_seconds)
    subw = subquery_window(window_seconds, sub_step_seconds)
    patterns = [upstream_regex_override] if upstream_regex_override else upstream_candidates(
        deployment, ingress_ns if ingress_ns else "default", ingress_host_prefix
    )
    queries = [
        # stddev_over_time( ( (ms_sum/ms_count)/1000 )[W:S] ) -> s
        f'stddev_over_time((( (sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w}))'
        f') / (sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w}))) ) / 1000){subw})'
        for pat in patterns
    ]
    return first_non_nan_from_queries(base_addr, queries)

def get_throughput_rps_std(base_addr: str, deployment: str, window_seconds: float,
                           ingress_ns: str, ingress_host_prefix: str,
                           upstream_regex_override: Optional[str],
                           sub_step_seconds: float) -> float:
    w = window_from_seconds(window_seconds)
    subw = subquery_window(window_seconds, sub_step_seconds)
    patterns = [upstream_regex_override] if upstream_regex_override else upstream_candidates(
        deployment, ingress_ns if ingress_ns else "default", ingress_host_prefix
    )
    q_latency_count_std = [
        f'stddev_over_time((sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w}))){subw})'
        for pat in patterns
    ]
    svc, port = to_service_and_port(deployment)
    svc_re = escape_regex_for_label(svc)
    q_requests_std = [
        f'stddev_over_time((sum(rate(nginx_ingress_controller_requests_total'
        f'{{namespace="{ingress_ns}",service=~".*{svc_re}(:{port})?"}}{w}))){subw})',
        f'stddev_over_time((sum(rate(nginx_ingress_controller_requests'
        f'{{namespace="{ingress_ns}",service=~".*{svc_re}(:{port})?"}}{w}))){subw})'
    ]
    return first_non_nan_from_queries(base_addr, q_latency_count_std + q_requests_std)

def get_avg_replicas_std(base_addr: str, deployment: str, window_seconds: float, k8s_namespace: str,
                         sub_step_seconds: float) -> float:
    w = window_from_seconds(window_seconds)
    expr = (f'avg_over_time(kube_deployment_status_replicas_available'
            f'{{namespace="{k8s_namespace}",deployment="{escape_label_value(deployment)}"}}{w})')
    return std_over_time_of_expr(base_addr, expr, window_seconds, sub_step_seconds)

# =========================
# Cálculos
# =========================
def ceil_to_int(v: float) -> int:
    if not (isinstance(v, float) or isinstance(v, int)):
        return 0
    if not math.isfinite(v):
        return 0
    c = math.ceil(v)
    if c > (2**31 - 1):
        return (2**31 - 1)
    if c < -(2**31):
        return -(2**31)
    return int(c)

def round_to_int(v: float) -> int:
    """Arredonda para o inteiro mais próximo (round)."""
    if not math.isfinite(v):
        return 0
    r = round(v)  # round half to even
    if r > (2**31 - 1):
        return 2**31 - 1
    if r < -(2**31):
        return -(2**31)
    return r

def compute_row(base_addr: str, deployment: str, window_seconds: float, snapshot_str: str,
                k8s_namespace: str, ingress_ns: str, ingress_host_prefix: str,
                upstream_regex_override: Optional[str],
                sub_step_seconds: float) -> Dict[str, Any]:
    # MÉDIAS
    rt_s  = get_response_time_seconds(base_addr, deployment, window_seconds, ingress_ns, ingress_host_prefix, upstream_regex_override)
    tp    = get_throughput_rps(base_addr, deployment, window_seconds, ingress_ns, ingress_host_prefix, upstream_regex_override)
    cpu   = get_cpu_usage(base_addr, deployment, window_seconds, k8s_namespace)
    mem   = get_memory_usage(base_addr, deployment, window_seconds, k8s_namespace)
    repl  = get_avg_replicas(base_addr, deployment, window_seconds, k8s_namespace)

    # DESVIOS-PADRÃO (na mesma janela, via subquery com step explícito)
    rt_s_std   = get_response_time_seconds_std(base_addr, deployment, window_seconds, ingress_ns, ingress_host_prefix, upstream_regex_override, sub_step_seconds)  # s
    tp_std     = get_throughput_rps_std(base_addr, deployment, window_seconds, ingress_ns, ingress_host_prefix, upstream_regex_override, sub_step_seconds)
    cpu_std    = get_cpu_usage_std(base_addr, deployment, window_seconds, k8s_namespace, sub_step_seconds)
    mem_std    = get_memory_usage_std(base_addr, deployment, window_seconds, k8s_namespace, sub_step_seconds)
    repl_std   = get_avg_replicas_std(base_addr, deployment, window_seconds, k8s_namespace, sub_step_seconds)

    number_of_jobs = (tp * rt_s) if (math.isfinite(tp) and math.isfinite(rt_s) and tp >= 0 and rt_s >= 0) else float("nan")

    row = {
        "DateTime": snapshot_str,
        "Deployment": deployment,

        # Contagens/legado
        "NumberOfJobsCeil": round_to_int(number_of_jobs),
        "TotalPodsCeil": ceil_to_int(repl),

        # Valores brutos
        "NumberOfJobs": number_of_jobs if math.isfinite(number_of_jobs) else "",
        "TotalPods": repl if math.isfinite(repl) else "",

        # Médias (agora RT em segundos)
        "Moving Avg Window (s)": int(round(window_seconds)),
        "MA Arrival Rate (req/s)": tp if math.isfinite(tp) else "",
        "MA Throughput (req/s)": tp if math.isfinite(tp) else "",
        "MA Response Time (s)": rt_s if math.isfinite(rt_s) else "",
        "CPUUsage(cores/s)": cpu if math.isfinite(cpu) else "",
        "MemoryUsage(bytes)": mem if math.isfinite(mem) else "",

        # Novas colunas: stddev na janela
        "MA Arrival Rate Std (req/s)": tp_std if math.isfinite(tp_std) else "",
        "MA Throughput Std (req/s)": tp_std if math.isfinite(tp_std) else "",
        "MA Response Time Std (s)": rt_s_std if math.isfinite(rt_s_std) else "",
        "CPUUsage Std (cores/s)": cpu_std if math.isfinite(cpu_std) else "",
        "MemoryUsage Std (bytes)": mem_std if math.isfinite(mem_std) else "",
        "Replicas Std": repl_std if math.isfinite(repl_std) else "",
    }
    log.info(f"ROW {deployment}: {row}")
    return row

# =========================
# Loop principal
# =========================
def main():
    parser = argparse.ArgumentParser(
        description="Prometheus logger (SPN metrics) -> CSV (janela e coleta separadas, RT em segundos).",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--address", default=os.getenv("PROMETHEUS_ADDRESS", "http://localhost"),
                        help='Endereço do Prometheus. Aceita "http://host:port" OU apenas "host" (o script adiciona http://).')
    parser.add_argument("--port", default=os.getenv("PROMETHEUS_PORT", "9090"),
                        help="Porta do Prometheus (ignorável se --address já tiver porta).")

    parser.add_argument("--k8s-namespace", default=os.getenv("KUBERNETES_NAMESPACE", "default"),
                        help="Namespace do Kubernetes para métricas de pods/deployments.")
    parser.add_argument("--ingress-namespace", default=os.getenv("INGRESS_NAMESPACE", "nginx-ingress"),
                        help="Namespace do Ingress (nginx).")
    parser.add_argument("--ingress-host-prefix", default=os.getenv("INGRESS_HOST_PREFIX", ""),
                        help="Prefixo do host do Ingress (opcional). Ex.: default-example-ingress-*.amazonaws.com")
    parser.add_argument("--upstream-regex", default=None,
                        help="Regex exato para o label 'upstream' (sobrepõe auto-detecção).")

    parser.add_argument("--out", default="prometheus_log.csv", help="CSV de saída")
    parser.add_argument("--window-seconds", type=float, default=300.0,
                        help="Janela para média (range vector do PromQL), em segundos. Ex.: 300 = 5 min.")
    parser.add_argument("--collect-interval-seconds", type=float, default=30.0,
                        help="Intervalo entre coletas, em segundos. Ex.: 30 = coleta a cada 30s.")
    parser.add_argument("--subquery-step-seconds", type=float, default=15.0,
                        help="Passo da subquery para stddev_over_time. Ideal ~ scrape_interval (ex.: 15).")
    parser.add_argument("--deployments", default="auto",
                        help='Lista de deployments separados por vírgula, ou "auto" para descobrir no Prometheus')
    parser.add_argument("--append", action="store_true", help="Anexar ao CSV existente (não recria cabeçalho)")
    parser.add_argument("--max-workers", type=int, default=8, help="Máximo de threads simultâneas para consultas")
    parser.add_argument("--debug", action="store_true", help="Habilita logs em nível DEBUG (PromQL e valores)")
    parser.add_argument("--log-file", default=None, help="Arquivo opcional para salvar o log")
    args = parser.parse_args()

    setup_logging(args.debug, args.log_file)

    base_addr = normalize_address(args.address, str(args.port) if args.port is not None else None)
    log.info(f"Prometheus base: {base_addr} (query URL: {base_query_url(base_addr)})")

    if args.deployments.strip().lower() == "auto":
        deployments = list_deployments_in_use(base_addr, args.k8s_namespace)
    else:
        deployments = [d.strip() for d in args.deployments.split(",") if d.strip()]
        log.info(f"Deployments (manual): {deployments}")

    if not deployments:
        log.error("Nenhum deployment encontrado. Defina --deployments ou verifique o Prometheus.")
        return

    window_seconds = max(1.0, float(args.window_seconds))
    collect_interval_sec = max(0.1, float(args.collect_interval_seconds))  # aceita frações
    sub_step_seconds = max(1.0, float(args.subquery_step_seconds))

    header = [
        "DateTime","Deployment",
        "NumberOfJobsCeil","TotalPodsCeil",
        "NumberOfJobs","TotalPods",
        "Moving Avg Window (s)","MA Arrival Rate (req/s)","MA Throughput (req/s)","MA Response Time (s)",
        "CPUUsage(cores/s)","MemoryUsage(bytes)",
        "MA Arrival Rate Std (req/s)","MA Throughput Std (req/s)","MA Response Time Std (s)",
        "CPUUsage Std (cores/s)","MemoryUsage Std (bytes)","Replicas Std"
    ]

    file_exists = os.path.isfile(args.out)
    mode = "a" if (args.append or file_exists) else "w"

    with open(args.out, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if mode == "w":
            writer.writeheader()

        while True:
            snapshot_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            max_workers = max(1, min(args.max_workers, len(deployments)))
            results: Dict[str, Dict[str, Any]] = {}

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                fut_map = {
                    ex.submit(
                        compute_row, base_addr, dep, window_seconds, snapshot_str,
                        args.k8s_namespace, args.ingress_namespace, args.ingress_host_prefix,
                        args.upstream_regex,
                        sub_step_seconds
                    ): dep for dep in deployments
                }
                for fut in as_completed(fut_map):
                    dep = fut_map[fut]
                    try:
                        results[dep] = fut.result()
                    except Exception as e:
                        log.warning(f"Falha coletando {dep}: {e}")
                        results[dep] = {
                            "DateTime": snapshot_str, "Deployment": dep,
                            "NumberOfJobsCeil": "", "TotalPodsCeil": "",
                            "NumberOfJobs": "", "TotalPods": "",
                            "Moving Avg Window (s)": int(round(window_seconds)),
                            "MA Arrival Rate (req/s)": "", "MA Throughput (req/s)": "", "MA Response Time (s)": "",
                            "CPUUsage(cores/s)": "", "MemoryUsage(bytes)": "",
                            "MA Arrival Rate Std (req/s)": "", "MA Throughput Std (req/s)": "", "MA Response Time Std (s)": "",
                            "CPUUsage Std (cores/s)": "", "MemoryUsage Std (bytes)": "", "Replicas Std": ""
                        }

            for dep in deployments:
                writer.writerow(results[dep])
            f.flush()

            time.sleep(collect_interval_sec)

if __name__ == "__main__":
    main()
