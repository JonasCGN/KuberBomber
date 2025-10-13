#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prometheus logger (SPN metrics) -> CSVs (médias + pontos por step) [TEMPOS EM SEGUNDOS]
=====================================================================================

O que este script faz
---------------------
1) Gera um CSV de **médias** por deployment, incluindo médias e desvios (RT em segundos).
2) Gera um CSV secundário com **todos os pontos** retornados pelo Prometheus via /query_range
   (um registro por timestamp por métrica), com o **timestamp real** de cada ponto.

Métricas coletadas (por deployment):
- RT (latência média em **s**):
  sum(rate(..._ms_sum[W])) / sum(rate(..._ms_count[W])) / 1000
- Throughput (req/s):
  rate(..._count[W]) ou fallbacks por service (requests_total/requests)
- CPU (cores/s): sum(rate(container_cpu_usage_seconds_total{...}[W]))
- Mem (bytes):   sum(avg_over_time(container_memory_usage_bytes{...}[W]))
- Réplicas:      avg_over_time(kube_deployment_status_replicas_available{...}[W])

Onde [W] = janela da média móvel (window), configurável via --window-seconds.

Como usar (exemplo)
-------------------
python3 prometheus_logger_points.py \
  --address http://PROMETHEUS:9090 \
  --k8s-namespace default \
  --ingress-namespace nginx-ingress \
  --deployments auto \
  --out prometheus_means.csv \
  --steps-out prometheus_steps.csv \
  --window-seconds 300 \
  --collect-interval-seconds 30 \
  --step-seconds 30 \
  --max-workers 8 \
  --append \
  --debug
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

def base_query_range_url(base_addr: str) -> str:
    return f"{base_addr}/api/v1/query_range"

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

def prom_query_range(base_addr: str, promql: str, start_ts: float, end_ts: float, step_s: float, timeout: int = 10) -> Dict[str, Any]:
    params = {
        "query": promql,
        "start": f"{start_ts:.3f}",
        "end":   f"{end_ts:.3f}",
        "step":  f"{step_s:.3f}",
    }
    qs = urllib.parse.urlencode(params, safe="")
    url = f"{base_query_range_url(base_addr)}?{qs}"
    log.debug(f"PROMQL_RANGE: {promql} | start={params['start']} end={params['end']} step={params['step']}")
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except Exception as e:
        log.warning(f"Prometheus query_range error: {type(e).__name__}: {e}")
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

def extract_series_with_ts(prom_json: Dict[str, Any]) -> List[Tuple[float, float]]:
    """
    Retorna a primeira série encontrada como lista de pares (timestamp_epoch, valor_float),
    filtrando NaN/Inf. Timestamps em segundos (float).
    """
    out: List[Tuple[float, float]] = []
    try:
        if prom_json.get("status") != "success":
            return out
        result = prom_json.get("data", {}).get("result", [])
        if not result:
            return out
        values = result[0].get("values", [])
        for ts, sval in values:
            try:
                v = float(sval); t = float(ts)
                if math.isfinite(v) and math.isfinite(t):
                    out.append((t, v))
            except Exception:
                pass
    except Exception:
        pass
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

def first_non_empty_series_from_queries_range_with_ts(base_addr: str, queries: List[str],
                                                      start_ts: float, end_ts: float, step_s: float) -> List[Tuple[float, float]]:
    for q in queries:
        js = prom_query_range(base_addr, q, start_ts, end_ts, step_s)
        arr = extract_series_with_ts(js)
        if arr:
            log.debug(f"[MATCH_RANGE] {q} -> {len(arr)} pontos")
            return arr
        else:
            log.debug(f"[MISS_RANGE]  {q}")
    return []

# =========================
# Funções de labels/padrões
# =========================
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

def to_service_and_port(deployment: str) -> Tuple[str, str]:
    base = deployment.replace("-app", "")
    return f"{base}-service", "9898"

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
    seen, out = set(), []
    for x in cands:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

# =========================
# Métricas - séries com TS (query_range)
# =========================
def window_from_seconds(seconds: float) -> str:
    sec = max(1, int(round(float(seconds))))
    return f"[{sec//60}m]" if sec % 60 == 0 else f"[{sec}s]"

def get_response_time_series_ts(base_addr: str, deployment: str, window_seconds: float,
                                ingress_ns: str, ingress_host_prefix: str,
                                upstream_regex_override: Optional[str],
                                step_seconds: float) -> List[Tuple[float, float]]:
    w = window_from_seconds(window_seconds)
    patterns = [upstream_regex_override] if upstream_regex_override else upstream_candidates(
        deployment, ingress_ns if ingress_ns else "default", ingress_host_prefix
    )
    queries = [
        # média em segundos
        f'(sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_sum'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w})) / '
        f'sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w}))) / 1000'
        for pat in patterns
    ]
    end_ts = time.time()
    start_ts = end_ts - float(window_seconds)
    return first_non_empty_series_from_queries_range_with_ts(base_addr, queries, start_ts, end_ts, step_seconds)

def get_throughput_series_ts(base_addr: str, deployment: str, window_seconds: float,
                             ingress_ns: str, ingress_host_prefix: str,
                             upstream_regex_override: Optional[str],
                             step_seconds: float) -> List[Tuple[float, float]]:
    w = window_from_seconds(window_seconds)
    patterns = [upstream_regex_override] if upstream_regex_override else upstream_candidates(
        deployment, ingress_ns if ingress_ns else "default", ingress_host_prefix
    )
    q_latency_count = [
        f'sum(rate(nginx_ingress_controller_upstream_server_response_latency_ms_count'
        f'{{namespace="{ingress_ns}",upstream=~"{pat}"}}{w}))'
        for pat in patterns
    ]
    svc, port = to_service_and_port(deployment)
    svc_re = escape_regex_for_label(svc)
    q_requests = [
        f'sum(rate(nginx_ingress_controller_requests_total'
        f'{{namespace="{ingress_ns}",service=~".*{svc_re}(:{port})?"}}{w}))',
        f'sum(rate(nginx_ingress_controller_requests'
        f'{{namespace="{ingress_ns}",service=~".*{svc_re}(:{port})?"}}{w}))'
    ]
    end_ts = time.time(); start_ts = end_ts - float(window_seconds)
    return first_non_empty_series_from_queries_range_with_ts(base_addr, q_latency_count + q_requests, start_ts, end_ts, step_seconds)

def get_cpu_usage_series_ts(base_addr: str, deployment: str, window_seconds: float,
                            k8s_namespace: str, step_seconds: float) -> List[Tuple[float, float]]:
    w = window_from_seconds(window_seconds)
    dep_re = escape_regex_for_label(deployment)
    q = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{k8s_namespace}",pod=~"{dep_re}.*"}}{w}))'
    end_ts = time.time(); start_ts = end_ts - float(window_seconds)
    return first_non_empty_series_from_queries_range_with_ts(base_addr, [q], start_ts, end_ts, step_seconds)

def get_memory_usage_series_ts(base_addr: str, deployment: str, window_seconds: float,
                               k8s_namespace: str, step_seconds: float) -> List[Tuple[float, float]]:
    w = window_from_seconds(window_seconds)
    container = escape_label_value(deployment)
    dep_re = escape_regex_for_label(deployment)
    q = (f'sum(avg_over_time(container_memory_usage_bytes'
         f'{{namespace="{k8s_namespace}",pod=~"{dep_re}.*",container="{container}"}}{w}))')
    end_ts = time.time(); start_ts = end_ts - float(window_seconds)
    return first_non_empty_series_from_queries_range_with_ts(base_addr, [q], start_ts, end_ts, step_seconds)

def get_avg_replicas_series_ts(base_addr: str, deployment: str, window_seconds: float,
                               k8s_namespace: str, step_seconds: float) -> List[Tuple[float, float]]:
    w = window_from_seconds(window_seconds)
    dep = escape_label_value(deployment)
    q = (f'avg_over_time(kube_deployment_status_replicas_available'
         f'{{namespace="{k8s_namespace}",deployment="{dep}"}}{w})')
    end_ts = time.time(); start_ts = end_ts - float(window_seconds)
    return first_non_empty_series_from_queries_range_with_ts(base_addr, [q], start_ts, end_ts, step_seconds)

# =========================
# Utilidades estatísticas
# =========================
def finite_only(xs: List[float]) -> List[float]:
    return [x for x in xs if math.isfinite(x)]

def mean_or_nan(xs: List[float]) -> float:
    xs = finite_only(xs)
    try:
        import statistics
        return statistics.fmean(xs) if xs else float("nan")
    except Exception:
        return float("nan")

def std_or_nan(xs: List[float]) -> float:
    xs = finite_only(xs)
    try:
        import statistics
        return statistics.stdev(xs) if len(xs) >= 2 else (0.0 if len(xs) == 1 else float("nan"))
    except Exception:
        return float("nan")

def ts_list_to_values(ts_pairs: List[Tuple[float, float]]) -> List[float]:
    return [v for (_, v) in ts_pairs]

# =========================
# Cálculos auxiliares
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
    """Arredonda para o inteiro mais próximo (round to even em .5)."""
    if not math.isfinite(v):
        return 0
    r = round(v)
    if r > (2**31 - 1):
        return 2**31 - 1
    if r < -(2**31):
        return -(2**31)
    return r

# =========================
# Descoberta de deployments
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

# =========================
# Função principal por deployment (médias + steps)
# =========================
def compute_row_with_steps(base_addr: str, deployment: str, window_seconds: float, snapshot_str: str,
                           k8s_namespace: str, ingress_ns: str, ingress_host_prefix: str,
                           upstream_regex_override: Optional[str],
                           step_seconds: float):
    # --- Séries com timestamp real (query_range) ---
    rt_s_series_ts  = get_response_time_series_ts(base_addr, deployment, window_seconds,
                                                  ingress_ns, ingress_host_prefix, upstream_regex_override, step_seconds)
    tp_series_ts    = get_throughput_series_ts(base_addr, deployment, window_seconds,
                                               ingress_ns, ingress_host_prefix, upstream_regex_override, step_seconds)
    cpu_series_ts   = get_cpu_usage_series_ts(base_addr, deployment, window_seconds, k8s_namespace, step_seconds)
    mem_series_ts   = get_memory_usage_series_ts(base_addr, deployment, window_seconds, k8s_namespace, step_seconds)
    repl_series_ts  = get_avg_replicas_series_ts(base_addr, deployment, window_seconds, k8s_namespace, step_seconds)

    # --- Estatísticas (médias/desvios) a partir das séries ---
    rt_vals  = ts_list_to_values(rt_s_series_ts)
    tp_vals  = ts_list_to_values(tp_series_ts)
    cpu_vals = ts_list_to_values(cpu_series_ts)
    mem_vals = ts_list_to_values(mem_series_ts)
    rep_vals = ts_list_to_values(repl_series_ts)

    rt_s_mean = mean_or_nan(rt_vals);  rt_s_std = std_or_nan(rt_vals)
    tp_mean   = mean_or_nan(tp_vals);  tp_std   = std_or_nan(tp_vals)
    cpu_mean  = mean_or_nan(cpu_vals); cpu_std  = std_or_nan(cpu_vals)
    mem_mean  = mean_or_nan(mem_vals); mem_std  = std_or_nan(mem_vals)
    repl_mean = mean_or_nan(rep_vals); repl_std = std_or_nan(rep_vals)

    # Compatibilidade com cálculo de L = λ * W (W = RT em s)
    rt_s = rt_s_mean
    tp   = tp_mean
    cpu  = cpu_mean
    mem  = mem_mean
    repl = repl_mean

    number_of_jobs = (tp * rt_s) if (math.isfinite(tp) and math.isfinite(rt_s) and tp >= 0 and rt_s >= 0) else float("nan")

    row = {
        "DateTime": snapshot_str,
        "Deployment": deployment,
        "NumberOfJobsCeil": round_to_int(number_of_jobs),
        "TotalPodsCeil": ceil_to_int(repl),
        "NumberOfJobs": number_of_jobs if math.isfinite(number_of_jobs) else "",
        "TotalPods": repl if math.isfinite(repl) else "",
        "Moving Avg Window (s)": int(round(window_seconds)),
        "MA Arrival Rate (req/s)": tp if math.isfinite(tp) else "",
        "MA Throughput (req/s)": tp if math.isfinite(tp) else "",
        "MA Response Time (s)": rt_s if math.isfinite(rt_s) else "",
        "CPUUsage(cores/s)": cpu if math.isfinite(cpu) else "",
        "MemoryUsage(bytes)": mem if math.isfinite(mem) else "",
        # Estatística explícita da janela (em s e não ms)
        "RT Mean (s)": rt_s_mean if math.isfinite(rt_s_mean) else "",
        "RT Std (s)":  rt_s_std  if math.isfinite(rt_s_std)  else "",
        "TP Mean (req/s)": tp_mean if math.isfinite(tp_mean) else "",
        "TP Std (req/s)":  tp_std  if math.isfinite(tp_std)  else "",
        "CPU Mean (cores/s)": cpu_mean if math.isfinite(cpu_mean) else "",
        "CPU Std (cores/s)":  cpu_std  if math.isfinite(cpu_std)  else "",
        "Mem Mean (bytes)": mem_mean if math.isfinite(mem_mean) else "",
        "Mem Std (bytes)":  mem_std  if math.isfinite(mem_std)  else "",
        "Replicas Mean": repl_mean if math.isfinite(repl_mean) else "",
        "Replicas Std":  repl_std  if math.isfinite(repl_std)  else "",
    }

    # --- CSV de steps (timestamps reais de cada série) ---
    def ts_to_iso(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    step_rows = []
    def append_series_rows(metric_name: str, series_ts: List[Tuple[float, float]]):
        for (ts_epoch, val) in series_ts:
            step_rows.append({
                "SnapshotDateTime": snapshot_str,
                "Deployment": deployment,
                "Metric": metric_name,
                "WindowSeconds": int(round(window_seconds)),
                "StepSeconds": int(round(step_seconds)),
                "PointDateTime": ts_to_iso(ts_epoch),
                "Value": val
            })

    append_series_rows("RT_s",            rt_s_series_ts)
    append_series_rows("TP_req_per_s",    tp_series_ts)
    append_series_rows("CPU_cores_per_s", cpu_series_ts)
    append_series_rows("Mem_bytes",       mem_series_ts)
    append_series_rows("Replicas",        repl_series_ts)

    log.debug(f"[STEPS] {deployment}: {len(step_rows)} pontos gerados")
    return row, step_rows

# =========================
# Loop principal
# =========================
def main():
    parser = argparse.ArgumentParser(
        description="Prometheus logger (SPN metrics) -> CSVs (médias + pontos por step) — tempos em segundos",
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

    parser.add_argument("--out", default="prometheus_log.csv", help="CSV de saída (médias)")
    parser.add_argument("--steps-out", default="prometheus_steps.csv", help="CSV para pontos por step")
    parser.add_argument("--window-seconds", type=float, default=300.0,
                        help="Janela para média (range vector do PromQL), em segundos. Ex.: 300 = 5 min.")
    parser.add_argument("--collect-interval-seconds", type=float, default=30.0,
                        help="Intervalo entre coletas, em segundos. Ex.: 30 = coleta a cada 30s.")
    parser.add_argument("--step-seconds", type=float, default=None,
                        help="Step do query_range (default: usa --collect-interval-seconds).")
    parser.add_argument("--deployments", default="auto",
                        help='Lista de deployments separados por vírgula, ou "auto" para descobrir no Prometheus')
    parser.add_argument("--append", action="store_true", help="Anexar aos CSVs existentes (não recria cabeçalho)")
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
    collect_interval_sec = max(0.1, float(args.collect_interval_seconds))
    step_seconds = float(args.step_seconds) if args.step_seconds is not None else float(collect_interval_sec)
    step_seconds = max(1.0, step_seconds)

    # Cabeçalhos dos CSVs (RT em segundos)
    means_header = [
        "DateTime","Deployment",
        "NumberOfJobsCeil","TotalPodsCeil",
        "NumberOfJobs","TotalPods",
        "Moving Avg Window (s)","MA Arrival Rate (req/s)","MA Throughput (req/s)","MA Response Time (s)",
        "CPUUsage(cores/s)","MemoryUsage(bytes)",
        "RT Mean (s)","RT Std (s)","TP Mean (req/s)","TP Std (req/s)",
        "CPU Mean (cores/s)","CPU Std (cores/s)",
        "Mem Mean (bytes)","Mem Std (bytes)",
        "Replicas Mean","Replicas Std"
    ]
    steps_header = ["SnapshotDateTime","Deployment","Metric","WindowSeconds","StepSeconds","PointDateTime","Value"]

    file_exists_means = os.path.isfile(args.out)
    file_exists_steps = os.path.isfile(args.steps_out)
    mode_means = "a" if (args.append or file_exists_means) else "w"
    mode_steps = "a" if (args.append or file_exists_steps) else "w"

    with open(args.out, mode_means, newline="") as f_means, \
            open(args.steps_out, mode_steps, newline="") as f_steps:

        writer_means = csv.DictWriter(f_means, fieldnames=means_header)
        writer_steps = csv.DictWriter(f_steps, fieldnames=steps_header)

        if mode_means == "w":
            writer_means.writeheader()
        if mode_steps == "w":
            writer_steps.writeheader()

        while True:
            snapshot_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            max_workers = max(1, min(args.max_workers, len(deployments)))
            results: Dict[str, Tuple[Dict[str, Any], List[Dict[str, Any]]]] = {}

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                fut_map = {
                    ex.submit(
                        compute_row_with_steps,
                        base_addr, dep, window_seconds, snapshot_str,
                        args.k8s_namespace, args.ingress_namespace, args.ingress_host_prefix,
                        args.upstream_regex,
                        step_seconds
                    ): dep for dep in deployments
                }
                for fut in as_completed(fut_map):
                    dep = fut_map[fut]
                    try:
                        results[dep] = fut.result()
                    except Exception as e:
                        log.warning(f"Falha coletando {dep}: {e}")
                        empty_row = {
                            "DateTime": snapshot_str, "Deployment": dep,
                            "NumberOfJobsCeil": "", "TotalPodsCeil": "",
                            "NumberOfJobs": "", "TotalPods": "",
                            "Moving Avg Window (s)": int(round(window_seconds)),
                            "MA Arrival Rate (req/s)": "", "MA Throughput (req/s)": "", "MA Response Time (s)": "",
                            "CPUUsage(cores/s)": "", "MemoryUsage(bytes)": "",
                            "RT Mean (s)": "", "RT Std (s)": "", "TP Mean (req/s)": "", "TP Std (req/s)": "",
                            "CPU Mean (cores/s)": "", "CPU Std (cores/s)": "",
                            "Mem Mean (bytes)": "", "Mem Std (bytes)": "",
                            "Replicas Mean": "", "Replicas Std": ""
                        }
                        results[dep] = (empty_row, [])

            # Escreve nos CSVs
            for dep in deployments:
                row, step_rows = results[dep]
                writer_means.writerow(row)
                for r in step_rows:
                    writer_steps.writerow(r)

            f_means.flush(); f_steps.flush()
            time.sleep(collect_interval_sec)

if __name__ == "__main__":
    main()
