#!/usr/bin/env python3
import time
import socket
import os
import random
from flask import Flask, jsonify

app = Flask(__name__)

# ---------------- Config via ambiente ----------------
# MEAN = tempo MÉDIO de CPU por requisição (em segundos)
# LOAD em (0, 1]: fração média de uso (1 = sempre ocupado; <1 = intercala busy/sleep)
MEAN = float(os.getenv('MEAN', '2.0'))     # padrão 2.0 para demonstrar o caso pedido
LOAD = float(os.getenv('LOAD', '1.0'))     # padrão 1.0 (100% de 1 vCPU)

# Saneamento de valores
if MEAN <= 0:
    MEAN = 0.001
if LOAD <= 0:
    LOAD = 0.01
elif LOAD > 1:
    LOAD = 1.0

# Duração do passo de CPU-alvo por ciclo (em segundos de CPU)
CPU_STEP = float(os.getenv('CPU_STEP', '0.01'))  # ajustar se quiser ciclos mais longos/curtos

def simulate_processing():
    """
    Consome aproximadamente 'cpu_budget' segundos de CPU por requisição.
    - Se LOAD = 1.0: apenas busy loop medido por tempo de CPU.
    - Se LOAD < 1.0: alterna busy (CPU_STEP de CPU) com sleep proporcional,
      de forma que o uso médio de CPU tende a LOAD, e o tempo de relógio ~ cpu_budget / LOAD.
    """
    cpu_budget = random.expovariate(1.0 / MEAN)  # segundos de CPU desejados
    start_wall = time.time()
    start_cpu = time.process_time()
    cpu_used = 0.0

    while cpu_used < cpu_budget:
        # Quanto de CPU ainda falta neste ciclo
        remaining = cpu_budget - cpu_used
        step_target = CPU_STEP if remaining > CPU_STEP else remaining

        # Busy-loop até consumir 'step_target' segundos de CPU
        seg_start = time.process_time()
        while (time.process_time() - seg_start) < step_target:
            pass

        # CPU usada até agora
        cpu_used = time.process_time() - start_cpu

        # Se LOAD < 1, dorme uma fração para reduzir uso médio
        if LOAD < 1.0 and step_target > 0:
            idle_wall = step_target * (1.0 - LOAD) / LOAD
            time.sleep(idle_wall)

    end_wall = time.time()
    wall_time = end_wall - start_wall
    return cpu_budget, cpu_used, wall_time

def handle_request():
    cpu_budget, cpu_used, wall_time = simulate_processing()

    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)

    return jsonify({
        "cpu_time_budget_s": cpu_budget,      # alvo (distribuição exponencial, média = MEAN)
        "cpu_time_used_s": cpu_used,          # CPU efetivamente consumida
        "processing_time_wall_s": wall_time,  # tempo de relógio decorrido
        "mean_env": MEAN,
        "load_env": LOAD,
        "hostname": hostname,
        "ip_address": ip_address
    })

# --- Rota dinâmica via env ---
DYNAMIC_ROUTE_PATH = os.getenv('ROUTE_PATH', '/').rstrip('/') or '/'
app.add_url_rule(DYNAMIC_ROUTE_PATH, 'handle_request', handle_request)
# -----------------------------

if __name__ == '__main__':
    # threaded=True permite concorrência no dev server do Flask.
    # Em produção, prefira gunicorn (ex.: -w 2 -k gthread --threads 2).
    app.run(host='0.0.0.0', port=9898, threaded=True)
