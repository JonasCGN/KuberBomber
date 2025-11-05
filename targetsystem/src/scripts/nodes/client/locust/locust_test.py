import os
import csv
import random
from locust import HttpUser, task, events
import gevent
from gevent.lock import Semaphore
from datetime import datetime
from requests.adapters import HTTPAdapter
from collections import deque
import time

# -------------------------
# Configurações via ambiente
# -------------------------

# Legado (lambda único) – mantido para compatibilidade, não usado diretamente
exponential_mean = float(os.getenv("EXPONENTIAL_MEAN", 10))

# Tempos médios (em segundos) para a exponencial (definem as taxas de início/fim da rampa)
LOW_EXPONENTIAL_MEAN_TIME  = float(os.getenv("LOW_EXPONENTIAL_MEAN_TIME", 4))
HIGH_EXPONENTIAL_MEAN_TIME = float(os.getenv("HIGH_EXPONENTIAL_MEAN_TIME", 30))

# Durações de cada passo e idle entre passos (segundos)
STEP_DURATION       = float(os.getenv("STEP_DURATION", 180))          # duração de cada patamar da rampa (s)
IDLE_BETWEEN_STEPS  = float(os.getenv("IDLE_BETWEEN_STEPS", 180))     # pausa entre passos (s) — agora com baixa carga
RAMP_STEPS          = int(os.getenv("RAMP_STEPS", "10"))              # número de passos da rampa (>=1)

# Janela (segundos) para médias móveis de chegada, throughput e response time
MOVING_AVERAGE = float(os.getenv("MOVING_AVERAGE", 30))

# Rótulo para identificar o experimento/log
LABEL = os.getenv("LABEL", "Conf A")

# Caminhos de log
log_path = os.getenv("LOG_PATH", ".")
response_log_file = os.path.join(log_path, "response_times.csv")
error_log_file    = os.path.join(log_path, "error_log.csv")

# Limite opcional de requisições simultâneas por usuário (0 ou vazio = sem limite)
MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "0"))

# -------------------------
# Estado global de logs
# -------------------------
response_file = None
error_file    = None
response_writer = None
error_writer    = None
mean_response_time_s = 0.0   # média global em segundos
total_requests = 0

# Estruturas para médias móveis (guardam apenas dados dentro da janela corrente)
ma_arrivals       = deque()  # timestamps de criação/envio
ma_timestamps     = deque()  # timestamps de conclusão
ma_response_times = deque()  # pares (timestamp, rt_s)

# Duração total do teste (padrão 10 minutos, pode ser sobrescrita por --run-time)
run_time_seconds = 600

# -------------------------
# Hooks de início/fim de teste
# -------------------------

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    global response_file, error_file, response_writer, error_writer, run_time_seconds

    # Interpretar --run-time (ex.: "10m", "1h", "30s")
    run_time = environment.parsed_options.run_time
    if run_time:
        run_time_seconds = convert_run_time_to_seconds(run_time)
    else:
        print("No --run-time specified, using default of 600 seconds")

    print(f"Test will run for: {run_time_seconds} seconds")
    if LABEL:
        print(f"Test LABEL: {LABEL}")

    # Abre CSVs
    os.makedirs(log_path, exist_ok=True)
    response_file = open(response_log_file, mode="w", newline="")
    response_writer = csv.writer(response_file)
    response_writer.writerow([
        "Request Type",
        "Name",
        "Request Created At",
        "Response Time (s)",          # agora em segundos
        "Generated Wait Time (s)",
        "Mean Response Time (s)",     # agora em segundos
        "HTTP Status Code",
        "Moving Avg Window (s)",
        "MA Arrival Rate (req/s)",
        "MA Throughput (req/s)",
        "MA Response Time (s)",       # agora em segundos
        "Label"
    ])

    error_file = open(error_log_file, mode="w", newline="")
    error_writer = csv.writer(error_file)
    error_writer.writerow([
        "Request Type",
        "Name",
        "Request Created At",
        "Response Time (s)",          # segundos (0.0 se erro antes de medir)
        "Exception",
        "Label"
    ])

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    global response_file, error_file
    if response_file:
        response_file.close()
    if error_file:
        error_file.close()

# -------------------------
# Utilitário
# -------------------------

def convert_run_time_to_seconds(run_time_str):
    """Convert the run-time (e.g., '10m', '1h', '30s') to seconds."""
    if isinstance(run_time_str, int):
        return run_time_str
    time_value = int(run_time_str[:-1])  # parte numérica
    time_unit  = run_time_str[-1]        # sufixo (m, h, s)
    if time_unit == 'm':
        return time_value * 60
    elif time_unit == 'h':
        return time_value * 60 * 60
    elif time_unit == 's':
        return time_value
    else:
        raise ValueError(f"Unknown time unit: {time_unit}")

def linspace_inclusive(start, end, n):
    """Gera n pontos igualmente espaçados de start até end (inclusive)."""
    if n <= 1:
        return [start]
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]

# -------------------------
# Usuário Locust
# -------------------------

class MyUser(HttpUser):
    _spawned_scheduler = False  # garante spawn único do agendador por usuário

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Aumenta o pool para evitar "Connection pool is full"
        adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.client.mount("http://", adapter)
        self.client.mount("https://", adapter)

        # Controle temporal
        self.elapsed_wall = 0.0  # tempo de parede acumulado para terminar o teste

        # Endpoints e pesos
        self.endpoints = ["/bar", "/foo"]
        self.endpoint_probabilities = [0.5, 0.5]

        # Limite opcional de requisições em voo por usuário
        self._sem = Semaphore(MAX_INFLIGHT) if MAX_INFLIGHT > 0 else None

        # ---------- Configuração da RAMPA (em taxas, convertidas para média exponencial) ----------
        # Carga baixa/alta como taxas (req/s)
        self.low_rate  = (1.0 / LOW_EXPONENTIAL_MEAN_TIME)  if LOW_EXPONENTIAL_MEAN_TIME  > 0 else 0.0
        self.high_rate = (1.0 / HIGH_EXPONENTIAL_MEAN_TIME) if HIGH_EXPONENTIAL_MEAN_TIME > 0 else 0.0

        # n valores igualmente espaçados (inclusive) de low_rate até high_rate
        steps = max(1, RAMP_STEPS)
        self.rate_steps = linspace_inclusive(self.low_rate, self.high_rate, steps)

        # Pré-calcula as médias exponenciais de cada passo (1/λ)
        self.mean_times_per_step = [(1.0 / r if r > 0 else float("inf")) for r in self.rate_steps]

    # ----- Espera (Exponencial) -----

    def exponential_wait(self, mean_time):
        """
        Gera tempo de espera a partir de uma exponencial com média 'mean_time' (segundos).
        random.expovariate espera λ = 1/mean.
        """
        if mean_time == float("inf"):
            # Sem chegadas (λ=0): só "dorme" até trocar de passo
            return float("inf")
        return random.expovariate(1.0 / mean_time) if mean_time > 0 else 0.0

    # ----- Logging -----

    def log_response(self, name, response, request_created_at, wait_time):
        """Helper para logar resposta com o horário de criação (tudo em segundos)."""
        global response_writer, mean_response_time_s, total_requests
        global ma_arrivals, ma_timestamps, ma_response_times, MOVING_AVERAGE

        # Tempo desta resposta (s)
        rt_s = response.elapsed.total_seconds()

        # Média global incremental (em s)
        total_requests += 1
        mean_response_time_s = ((mean_response_time_s * (total_requests - 1)) + rt_s) / total_requests

        # ----- Médias móveis (throughput e RT) com base na conclusão -----
        now_ts = time.time()
        cutoff = now_ts - MOVING_AVERAGE

        # Throughput (respostas concluídas) em req/s
        ma_timestamps.append(now_ts)
        while ma_timestamps and ma_timestamps[0] < cutoff:
            ma_timestamps.popleft()
        ma_throughput = (len(ma_timestamps) / MOVING_AVERAGE) if MOVING_AVERAGE > 0 else 0.0

        # Response time médio na janela (s)
        ma_response_times.append((now_ts, rt_s))
        while ma_response_times and ma_response_times[0][0] < cutoff:
            ma_response_times.popleft()
        ma_rt_s = (sum(item[1] for item in ma_response_times) / len(ma_response_times)) if ma_response_times else 0.0

        # ----- Taxa de chegada (envio/criação) em req/s -----
        while ma_arrivals and ma_arrivals[0] < cutoff:
            ma_arrivals.popleft()
        ma_arrival_rate = (len(ma_arrivals) / MOVING_AVERAGE) if MOVING_AVERAGE > 0 else 0.0

        # ----- Escrita no CSV -----
        if response_writer:  # Ensure the file is still open
            response_writer.writerow([
                "GET",
                name,
                request_created_at,           # quando a request foi criada
                rt_s,                         # response time em s
                wait_time,                    # tempo de espera gerado nesta iteração (s)
                mean_response_time_s,         # média global de RT em s
                response.status_code,         # HTTP status
                MOVING_AVERAGE,               # janela da média móvel em s
                ma_arrival_rate,              # chegada média (req/s) na janela
                ma_throughput,                # throughput médio (req/s) na janela
                ma_rt_s,                      # RT médio (s) na janela
                LABEL
            ])

    def send_request(self, endpoint, wait_time):
        """Envia request e loga a resposta (executa em greenlet separado)."""
        global error_writer, ma_arrivals, MOVING_AVERAGE
        request_created_at = datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")
        try:
            # Semáforo opcional para limitar requisições simultâneas por usuário
            if self._sem is not None:
                self._sem.acquire()

            try:
                # Marca a CRIAÇÃO/ENVIO da requisição (taxa de chegada)
                created_ts_epoch = time.time()
                request_created_at = datetime.fromtimestamp(created_ts_epoch).strftime("%Y-%m-%d %H:%M:%S")

                # Atualiza a janela de chegadas (req/s de chegada)
                ma_arrivals.append(created_ts_epoch)
                cutoff = created_ts_epoch - MOVING_AVERAGE
                while ma_arrivals and ma_arrivals[0] < cutoff:
                    ma_arrivals.popleft()

                # Envia a requisição
                response = self.client.get(endpoint)

                # Loga a resposta (com o horário de criação capturado acima)
                self.log_response(endpoint, response, request_created_at, wait_time)
            finally:
                if self._sem is not None:
                    self._sem.release()

        except Exception as e:
            if error_writer:
                error_writer.writerow(["GET", endpoint, request_created_at, 0.0, str(e), LABEL])

    # ----- Agendamento (rampa por passos) -----

    def schedule_requests_ramp(self):
        """
        Executa uma rampa de carga usando chegadas Poisson (exponencial),
        com RAMP_STEPS patamares. Em cada patamar:
          - usa taxa constante (λ) -> inter-arrivals ~ Exp(λ)
          - dura STEP_DURATION segundos
          - em seguida, pausa IDLE_BETWEEN_STEPS segundos com BAIXA CARGA (λ_low)
        O teto global de execução é run_time_seconds (se configurado por --run-time).
        """
        start_wall = time.time()

        for step_idx, mean_time in enumerate(self.mean_times_per_step):
            # Encerrar se atingiu o teto global
            if (time.time() - start_wall) >= run_time_seconds:
                break

            # ----- Fase ativa (STEP_DURATION) -----
            step_start = time.time()
            next_ts = step_start  # agenda pelo relógio
            while True:
                now = time.time()
                if (now - start_wall) >= run_time_seconds:
                    break

                # Verifica fim do passo
                if (now - step_start) >= STEP_DURATION:
                    break

                # Sorteia próximo intervalo
                wait_time = self.exponential_wait(mean_time)
                if wait_time == float("inf"):
                    # λ=0 => sem chegadas neste passo; apenas espera até o fim do passo
                    gevent.sleep(0.1)
                    continue

                next_ts += wait_time

                # Dorme até o horário agendado (sono relativo)
                sleep_for = max(0.0, next_ts - time.time())
                if sleep_for > 0:
                    gevent.sleep(sleep_for)

                # Escolhe endpoint conforme as probabilidades
                current_endpoint = random.choices(self.endpoints, weights=self.endpoint_probabilities)[0]

                # Dispara em greenlet separado (não bloqueia o agendador)
                gevent.spawn(self.send_request, current_endpoint, wait_time)

            # Encerrar se atingiu o teto global
            if (time.time() - start_wall) >= run_time_seconds:
                break

            # ----- Idle COM BAIXA CARGA entre passos (MUDANÇA SOLICITADA) -----
            idle_start = time.time()
            next_idle_ts = idle_start

            # média dos inter-arrivals durante o idle (em s)
            mean_time_idle = LOW_EXPONENTIAL_MEAN_TIME if LOW_EXPONENTIAL_MEAN_TIME > 0 else float("inf")

            while (time.time() - idle_start) < IDLE_BETWEEN_STEPS:
                if (time.time() - start_wall) >= run_time_seconds:
                    break

                wait_time_idle = self.exponential_wait(mean_time_idle)
                if wait_time_idle == float("inf"):
                    # Sem chegadas durante o idle: dorme curto para não travar o loop
                    gevent.sleep(0.1)
                    continue

                next_idle_ts += wait_time_idle
                sleep_for_idle = max(0.0, next_idle_ts - time.time())
                if sleep_for_idle > 0:
                    gevent.sleep(sleep_for_idle)

                current_endpoint = random.choices(self.endpoints, weights=self.endpoint_probabilities)[0]
                gevent.spawn(self.send_request, current_endpoint, wait_time_idle)

            if (time.time() - start_wall) >= run_time_seconds:
                break

    # ----- Spawn único -----

    def on_start(self):
        # Garantir que apenas um greenlet de agendamento seja criado por usuário
        if not self._spawned_scheduler:
            self._spawned_scheduler = True
            gevent.spawn(self.schedule_requests_ramp)

    # Mantém o @task para o Locust não reclamar, mas não cria novos greenlets
    @task
    def noop(self):
        gevent.sleep(0.1)
