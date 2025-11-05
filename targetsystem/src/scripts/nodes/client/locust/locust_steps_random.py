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

# =========================
# Configurações via ambiente
# =========================

# Legado (lambda único) – mantido para compatibilidade, não usado diretamente
exponential_mean = float(os.getenv("EXPONENTIAL_MEAN", 8))

# Número de degraus por época (quanto maior, mais suave a transição)
TIME_STEP_INTERVAL = int(os.getenv("TIME_STEP_INTERVAL", "10"))

# Limites para tempo médio da exponencial (em segundos)
LOW_EXPONENTIAL_MEAN_TIME  = float(os.getenv("LOW_EXPONENTIAL_MEAN_TIME", 4))
HIGH_EXPONENTIAL_MEAN_TIME = float(os.getenv("HIGH_EXPONENTIAL_MEAN_TIME", 30))

# Limites para duração de cada época (em segundos)
LOW_EXPONENTIAL_DURATION  = float(os.getenv("LOW_EXPONENTIAL_DURATION", 120))
HIGH_EXPONENTIAL_DURATION = float(os.getenv("HIGH_EXPONENTIAL_DURATION", 120))

# Janela (segundos) para médias móveis de chegada, throughput e response time
MOVING_AVERAGE = float(os.getenv("MOVING_AVERAGE", 30))

# Rótulo para identificar o experimento/log
LABEL = os.getenv("LABEL", "Conf A")

# Caminhos de log
log_path = os.getenv("LOG_PATH", ".")
response_log_file = os.path.join(log_path, "response_times.csv")
error_log_file = os.path.join(log_path, "error_log.csv")

# Limite opcional de requisições simultâneas por usuário (0 = sem limite)
MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "0"))

# (Opcional) Semente para reprodutibilidade dos sorteios (quando não estiver em TRACE replay)
SEED = os.getenv("SEED")
if SEED is not None:
    try:
        random.seed(int(SEED))
    except ValueError:
        random.seed(SEED)

# ================
# TRACE / REPLAY
# ================
TRACE_MODE = os.getenv("TRACE_MODE", "off").lower()  # off | record | replay
TRACE_FILE = os.getenv("TRACE_FILE", os.path.join(log_path, "arrival_trace.csv"))
REPLAY_LOOP = os.getenv("REPLAY_LOOP", "1").lower() in {"1", "true", "yes"}

_trace_writer = None      # (file_handle, csv_writer)
_trace_rows = []          # lista de tuplas (wait_time_s, endpoint)
_trace_idx = 0            # índice de leitura durante replay


def _trace_open_for_record():
    """Abre arquivo de trace para gravação de (wait_time_s, endpoint)."""
    global _trace_writer
    os.makedirs(os.path.dirname(TRACE_FILE) or ".", exist_ok=True)
    f = open(TRACE_FILE, "w", newline="")
    w = csv.writer(f)
    w.writerow(["wait_time_s", "endpoint"])
    _trace_writer = (f, w)


def _trace_close():
    """Fecha arquivo de trace se aberto para escrita."""
    global _trace_writer
    if _trace_writer:
        _trace_writer[0].close()
        _trace_writer = None


def _trace_record(wait_time, endpoint):
    """Registra uma chegada no trace quando em modo record."""
    if TRACE_MODE == "record" and _trace_writer:
        _trace_writer[1].writerow([f"{float(wait_time):.9f}", endpoint])


def _trace_load_for_replay():
    """Carrega o arquivo de trace para lista de eventos em memória."""
    global _trace_rows
    _trace_rows.clear()
    with open(TRACE_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wt = float(row["wait_time_s"])
            ep = row.get("endpoint", "/")
            _trace_rows.append((wt, ep))
    if not _trace_rows:
        raise RuntimeError("TRACE_MODE=replay, mas o arquivo de trace está vazio.")


def _trace_next():
    """Entrega o próximo (wait_time_s, endpoint) do trace; None se acabou e não deve repetir."""
    global _trace_idx
    if not _trace_rows:
        raise RuntimeError("TRACE_MODE=replay, mas não há eventos carregados.")
    if _trace_idx >= len(_trace_rows):
        if not REPLAY_LOOP:
            return None
        _trace_idx = 0
    v = _trace_rows[_trace_idx]
    _trace_idx += 1
    return v


# =========================
# Estado global de logs
# =========================
response_file = None
error_file = None
response_writer = None
error_writer = None
mean_response_time_s = 0.0  # média global em segundos
total_requests = 0

# Estruturas para médias móveis (guardam apenas dados dentro da janela corrente)
ma_arrivals = deque()        # timestamps de criação/envio
ma_timestamps = deque()      # timestamps de conclusão
ma_response_times = deque()  # pares (timestamp, rt_s)

# Duração total do teste (padrão 10 minutos)
run_time_seconds = 600


# =========================
# Hooks de início/fim de teste
# =========================
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    global response_file, error_file, response_writer, error_writer, run_time_seconds

    # Interpretar --run-time (ex.: "10m", "1h", "30s")
    run_time = getattr(environment, "parsed_options", None)
    run_time = run_time.run_time if run_time else None
    if run_time:
        run_time_seconds = convert_run_time_to_seconds(run_time)
    else:
        print("No --run-time specified, using default of 600 seconds")

    print(f"Test will run for: {run_time_seconds} seconds")
    if LABEL:
        print(f"Test LABEL: {LABEL}")

    # LOGs
    os.makedirs(log_path, exist_ok=True)
    response_file = open(response_log_file, mode="w", newline="")
    response_writer = csv.writer(response_file)
    response_writer.writerow([
        "Request Type",
        "Name",
        "Request Created At",
        "Response Time (s)",
        "Generated Wait Time (s)",
        "Mean Response Time (s)",
        "HTTP Status Code",
        "Moving Avg Window (s)",
        "MA Arrival Rate (req/s)",
        "MA Throughput (req/s)",
        "MA Response Time (s)",
        "Label"
    ])

    error_file = open(error_log_file, mode="w", newline="")
    error_writer = csv.writer(error_file)
    error_writer.writerow([
        "Request Type",
        "Name",
        "Request Created At",
        "Response Time (s)",
        "Exception",
        "Label"
    ])

    # TRACE
    if TRACE_MODE == "record":
        print(f"[TRACE] Gravando chegadas em: {TRACE_FILE}")
        _trace_open_for_record()
    elif TRACE_MODE == "replay":
        print(f"[TRACE] Reproduzindo chegadas de: {TRACE_FILE} (loop={REPLAY_LOOP})")
        _trace_load_for_replay()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    global response_file, error_file
    if response_file:
        response_file.close()
    if error_file:
        error_file.close()
    _trace_close()


# ===========
# Utilitário
# ===========
def convert_run_time_to_seconds(run_time_str):
    """Converte '10m', '1h', '30s' para segundos."""
    if isinstance(run_time_str, int):
        return run_time_str
    time_value = int(run_time_str[:-1])  # parte numérica
    time_unit = run_time_str[-1]         # sufixo (m, h, s)
    if time_unit == 'm':
        return time_value * 60
    elif time_unit == 'h':
        return time_value * 60 * 60
    elif time_unit == 's':
        return time_value
    else:
        raise ValueError(f"Unknown time unit: {time_unit}")


# =================
# Usuário do Locust
# =================
class MyUser(HttpUser):
    # garante spawn único do agendador por usuário
    _spawned_scheduler = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.client.mount("http://", adapter)
        self.client.mount("https://", adapter)

        self.elapsed_wall = 0.0

        # Ajuste aqui os endpoints e probabilidades conforme seu cenário
        self.endpoints = ["/bar", "/foo"]
        self.endpoint_probabilities = [0.5, 0.5]

        self._sem = Semaphore(MAX_INFLIGHT) if MAX_INFLIGHT > 0 else None

        # -------------------------------------------------------------
        # ÉPOCAS (random: duração + média-alvo) com interpolação em degraus
        # -------------------------------------------------------------
        self.epoch_elapsed_wall = 0.0               # tempo decorrido na época atual
        self.epoch_duration = None                  # duração da época (s) – sorteada
        self.epoch_steps = max(1, TIME_STEP_INTERVAL)
        self.epoch_start_mean = None                # média inicial desta época (s)
        self.epoch_target_mean = None               # média alvo desta época (s)
        self._init_first_epoch()                    # inicializa a primeira época

    # ---- Helpers de ÉPOCA ----
    def _rand_duration(self):
        low = min(LOW_EXPONENTIAL_DURATION, HIGH_EXPONENTIAL_DURATION)
        high = max(LOW_EXPONENTIAL_DURATION, HIGH_EXPONENTIAL_DURATION)
        return random.uniform(low, high)

    def _rand_mean(self):
        low = min(LOW_EXPONENTIAL_MEAN_TIME, HIGH_EXPONENTIAL_MEAN_TIME)
        high = max(LOW_EXPONENTIAL_MEAN_TIME, HIGH_EXPONENTIAL_MEAN_TIME)
        return random.uniform(low, high)

    def _init_first_epoch(self):
        """Inicializa a primeira época com start e target aleatórios nos limites."""
        self.epoch_duration = self._rand_duration()
        self.epoch_start_mean = self._rand_mean()
        self.epoch_target_mean = self._rand_mean()
        if abs(self.epoch_target_mean - self.epoch_start_mean) < 1e-6:
            # força uma diferença mínima
            self.epoch_target_mean = min(
                max(self.epoch_start_mean * 1.05, LOW_EXPONENTIAL_MEAN_TIME),
                HIGH_EXPONENTIAL_MEAN_TIME
            )
        self.epoch_elapsed_wall = 0.0

    def _roll_epoch_if_needed(self, delta_wall):
        """Avança tempo de época e, se necessário, inicia uma nova época."""
        self.epoch_elapsed_wall += delta_wall
        if self.epoch_elapsed_wall >= self.epoch_duration:
            # Média final desta época (para continuidade suave)
            final_mean = self._interpolated_mean_time()
            self.epoch_start_mean = float(final_mean)
            self.epoch_target_mean = self._rand_mean()
            if abs(self.epoch_target_mean - self.epoch_start_mean) < 1e-6:
                self.epoch_target_mean = min(
                    max(self.epoch_start_mean * 1.05, LOW_EXPONENTIAL_MEAN_TIME),
                    HIGH_EXPONENTIAL_MEAN_TIME
                )
            self.epoch_duration = self._rand_duration()
            self.epoch_elapsed_wall = 0.0

    def _interpolated_mean_time(self):
        """
        Retorna a média exponencial corrente (em s) interpolando em degraus
        de epoch_start_mean -> epoch_target_mean ao longo de epoch_duration.
        """
        duration = max(1e-9, float(self.epoch_duration))
        ratio = min(1.0, max(0.0, self.epoch_elapsed_wall / duration))
        step_index = int(ratio * self.epoch_steps)          # 0..epoch_steps
        frac = step_index / self.epoch_steps                # 0.0..1.0
        mean = self.epoch_start_mean + (self.epoch_target_mean - self.epoch_start_mean) * frac
        # proteção contra limites
        floor = min(LOW_EXPONENTIAL_MEAN_TIME, HIGH_EXPONENTIAL_MEAN_TIME)
        ceil  = max(LOW_EXPONENTIAL_MEAN_TIME, HIGH_EXPONENTIAL_MEAN_TIME)
        return max(floor, min(ceil, float(mean)))

    # ---- Espera (Exponencial) ----
    def exponential_wait(self):
        """
        Gera inter-arrival exponencial com mean variável por degraus (época corrente).
        random.expovariate usa λ = 1/mean.
        """
        mean_time = self._interpolated_mean_time()
        return random.expovariate(1.0 / mean_time) if mean_time > 0 else 0.0

    # ---- Logging ----
    def log_response(self, name, response, request_created_at, wait_time):
        """Escreve no CSV de respostas; calcula médias móveis e global."""
        global response_writer, mean_response_time_s, total_requests
        global ma_arrivals, ma_timestamps, ma_response_times, MOVING_AVERAGE

        rt_s = response.elapsed.total_seconds()

        # Média global incremental (em s)
        total_requests += 1
        mean_response_time_s = ((mean_response_time_s * (total_requests - 1)) + rt_s) / total_requests

        # Throughput (respostas concluídas) em req/s
        now_ts = time.time()
        cutoff = now_ts - MOVING_AVERAGE

        ma_timestamps.append(now_ts)
        while ma_timestamps and ma_timestamps[0] < cutoff:
            ma_timestamps.popleft()
        ma_throughput = (len(ma_timestamps) / MOVING_AVERAGE) if MOVING_AVERAGE > 0 else 0.0

        # Response time médio na janela (em s)
        ma_response_times.append((now_ts, rt_s))
        while ma_response_times and ma_response_times[0][0] < cutoff:
            ma_response_times.popleft()
        ma_rt_s = (sum(item[1] for item in ma_response_times) / len(ma_response_times)) if ma_response_times else 0.0

        # Taxa de chegada (envio/criação) em req/s
        while ma_arrivals and ma_arrivals[0] < cutoff:
            ma_arrivals.popleft()
        ma_arrival_rate = (len(ma_arrivals) / MOVING_AVERAGE) if MOVING_AVERAGE > 0 else 0.0

        if response_writer:
            response_writer.writerow([
                "GET",
                name,
                request_created_at,
                rt_s,
                wait_time,
                mean_response_time_s,
                response.status_code,
                MOVING_AVERAGE,
                ma_arrival_rate,
                ma_throughput,
                ma_rt_s,
                LABEL
            ])

    def send_request(self, endpoint, wait_time):
        """Envia a requisição e registra o resultado/erro."""
        global error_writer, ma_arrivals, MOVING_AVERAGE
        request_created_at = datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")
        try:
            if self._sem is not None:
                self._sem.acquire()
            try:
                # Marca CRIAÇÃO/ENVIO (para taxa de chegada)
                created_ts_epoch = time.time()
                request_created_at = datetime.fromtimestamp(created_ts_epoch).strftime("%Y-%m-%d %H:%M:%S")

                ma_arrivals.append(created_ts_epoch)
                cutoff = created_ts_epoch - MOVING_AVERAGE
                while ma_arrivals and ma_arrivals[0] < cutoff:
                    ma_arrivals.popleft()

                # Envia a requisição
                response = self.client.get(endpoint)

                # Loga a resposta
                self.log_response(endpoint, response, request_created_at, wait_time)
            finally:
                if self._sem is not None:
                    self._sem.release()

        except Exception as e:
            if error_writer:
                error_writer.writerow(["GET", endpoint, request_created_at, 0.0, str(e), LABEL])

    # ---- Agendamento (pacing por relógio) ----
    def schedule_requests(self):
        """
        Agenda chegadas Poisson (expovariate) por relógio: inter-arrivals independem do tempo de resposta.
        Usa tempo de parede para rolar épocas e encerrar o teste.
        """
        start_wall = time.time()
        next_ts = start_wall
        last_tick = start_wall

        while True:
            now = time.time()
            delta = now - last_tick
            last_tick = now

            self.elapsed_wall = now - start_wall
            if self.elapsed_wall >= run_time_seconds:
                break

            # Avança época (e rola para a próxima quando necessário)
            self._roll_epoch_if_needed(delta)

            # Determina o próximo inter-arrival + endpoint (replay ou geração)
            if TRACE_MODE == "replay":
                nxt = _trace_next()
                if nxt is None:
                    break  # acabou o trace e não vamos dar loop
                wait_time, current_endpoint = nxt
            else:
                wait_time = self.exponential_wait()
                current_endpoint = random.choices(self.endpoints, weights=self.endpoint_probabilities)[0]
                _trace_record(wait_time, current_endpoint)

            # Agenda horário absoluto do próximo envio (minimiza drift)
            next_ts += wait_time

            # Dorme até o horário agendado
            sleep_for = max(0.0, next_ts - time.time())
            if sleep_for > 0:
                gevent.sleep(sleep_for)

            # Dispara a request em greenlet separado
            gevent.spawn(self.send_request, current_endpoint, wait_time)

    # ---- Spawn único ----
    def on_start(self):
        # Garante que apenas um greenlet de agendamento seja criado por usuário
        if not self._spawned_scheduler:
            self._spawned_scheduler = True
            gevent.spawn(self.schedule_requests)

    # Mantém o @task para o Locust não reclamar, mas não cria novos greenlets
    @task
    def noop(self):
        gevent.sleep(0.1)

# TRACE_MODE=record \
# TRACE_FILE="$LOG_PATH/arrival_trace.csv" \
# locust --locustfile locust/locust_steps_random.py \
#   --csv "$LOG_PATH/locust_results" \
#   --logfile "$LOG_PATH/locust_log" \
#   --host "http://$LB_ADDR" \
#   --run-time "$EXPERIMENT_TIME" \
#   --users 1 \
#   --spawn-rate 1 \
#   --headless

# TRACE_MODE=replay \
# TRACE_FILE="$LOG_PATH/arrival_trace.csv" \
# REPLAY_LOOP=1 \
# locust --locustfile locust/locust_steps_random.py \
#   --csv "$LOG_PATH/locust_results" \
#   --logfile "$LOG_PATH/locust_log" \
#   --host "http://$LB_ADDR" \
#   --run-time "$EXPERIMENT_TIME" \
#   --users 1 \
#   --spawn-rate 1 \
#   --headless