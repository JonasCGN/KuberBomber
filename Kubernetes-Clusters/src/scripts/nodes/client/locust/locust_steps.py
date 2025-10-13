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
exponential_mean = float(os.getenv("EXPONENTIAL_MEAN", 8))

TIME_STEP_INTERVAL = int(os.getenv("TIME_STEP_INTERVAL", "10"))  # nº de degraus por fase (subida/descida)


# Tempos médios (em segundos) para a exponencial
LOW_EXPONENTIAL_MEAN_TIME  = float(os.getenv("LOW_EXPONENTIAL_MEAN_TIME", 4))
HIGH_EXPONENTIAL_MEAN_TIME = float(os.getenv("HIGH_EXPONENTIAL_MEAN_TIME", 30))

# Durações de cada fase (segundos)
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

# Limite opcional de requisições simultâneas por usuário (0 ou vazio = sem limite)
MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "0"))

# -------------------------
# Estado global de logs
# -------------------------
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
        "Response Time (s)",          # <-- agora em segundos
        "Generated Wait Time (s)",
        "Mean Response Time (s)",     # <-- agora em segundos
        "HTTP Status Code",
        "Moving Avg Window (s)",
        "MA Arrival Rate (req/s)",
        "MA Throughput (req/s)",
        "MA Response Time (s)",       # <-- agora em segundos
        "Label"
    ])

    error_file = open(error_log_file, mode="w", newline="")
    error_writer = csv.writer(error_file)
    error_writer.writerow([
        "Request Type",
        "Name",
        "Request Created At",
        "Response Time (s)",          # <-- agora em segundos (0 se erro antes de medir)
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
    time_unit = run_time_str[-1]         # sufixo (m, h, s)
    if time_unit == 'm':
        return time_value * 60
    elif time_unit == 'h':
        return time_value * 60 * 60
    elif time_unit == 's':
        return time_value
    else:
        raise ValueError(f"Unknown time unit: {time_unit}")

# -------------------------
# Usuário Locust
# -------------------------

class MyUser(HttpUser):
    # garante spawn único do agendador por usuário
    _spawned_scheduler = False


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.client.mount("http://", adapter)
        self.client.mount("https://", adapter)

        self.elapsed_wall = 0.0
        self.endpoints = ["/bar", "/foo"]
        self.endpoint_probabilities = [0.5, 0.5]

        self.current_phase = "low"        # "low" (subindo) ou "high" (descendo)
        self.phase_elapsed_wall = 0.0

        self._sem = Semaphore(MAX_INFLIGHT) if MAX_INFLIGHT > 0 else None

    # ----- Alternância -----

    def _current_mean_time(self):
        """Retorna o tempo médio da fase atual (em segundos)."""
        return LOW_EXPONENTIAL_MEAN_TIME if self.current_phase == "low" else HIGH_EXPONENTIAL_MEAN_TIME

    def _current_duration(self):
        return LOW_EXPONENTIAL_DURATION if self.current_phase == "low" else HIGH_EXPONENTIAL_DURATION

    def _interpolated_mean_time(self):
        """
        Retorna o mean_time (em segundos) da exponencial, variando em degraus lineares.
        - Na fase 'low': sobe de LOW até HIGH ao longo de LOW_EXPONENTIAL_DURATION.
        - Na fase 'high': desce de HIGH até LOW ao longo de HIGH_EXPONENTIAL_DURATION.
        O total de degraus por fase é TIME_STEP_INTERVAL.
        """
        # Segurança
        steps = max(1, TIME_STEP_INTERVAL)
        duration = max(1e-9, self._current_duration())  # evita div/0

        # Qual fração da fase já se passou (0.0 .. 1.0)
        ratio = min(1.0, max(0.0, self.phase_elapsed_wall / duration))

        # Índice do degrau atual (0 .. steps)
        step_index = int(ratio * steps)

        low, high = LOW_EXPONENTIAL_MEAN_TIME, HIGH_EXPONENTIAL_MEAN_TIME

        if self.current_phase == "low":
            # subindo: low -> high
            mean = low + (high - low) * (step_index / steps)
        else:
            # descendo: high -> low
            mean = high - (high - low) * (step_index / steps)

        # Evita valores não positivos por segurança
        return max(1e-9, float(mean))

    def _maybe_switch_phase(self):
        if self.phase_elapsed_wall >= self._current_duration():
            self.current_phase = "high" if self.current_phase == "low" else "low"
            self.phase_elapsed_wall = 0.0

    # ----- Espera (Exponencial) -----

    def exponential_wait(self):
        """
        Gera tempo de espera exponencial com mean variável por degraus.
        random.expovariate usa λ = 1/mean.
        """
        mean_time = self._interpolated_mean_time()
        return random.expovariate(1.0 / mean_time) if mean_time > 0 else 0.0

    # ----- Logging -----

    def log_response(self, name, response, request_created_at, wait_time):
        """Helper function to log response with request creation time (tudo em segundos)."""
        global response_writer, mean_response_time_s, total_requests
        global ma_arrivals, ma_timestamps, ma_response_times, MOVING_AVERAGE

        # Tempo desta resposta (segundos)
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

        # Response time médio na janela (em s)
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
                request_created_at,                 # quando a request foi criada
                rt_s,                               # response time em s
                wait_time,                          # tempo de espera gerado nesta iteração (s)
                mean_response_time_s,               # média global de RT em s
                response.status_code,               # HTTP status
                MOVING_AVERAGE,                     # janela da média móvel em s
                ma_arrival_rate,                    # chegada média (req/s) na janela
                ma_throughput,                      # throughput médio (req/s) na janela
                ma_rt_s,                            # RT médio (s) na janela
                LABEL
            ])

    def send_request(self, endpoint, wait_time):
        """Send request and log the response (executa em greenlet separado)."""
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

    # ----- Agendamento (pacing por relógio) -----

    def schedule_requests(self):
        """
        Agenda chegadas Poisson (expovariate) por relógio: inter-arrivals independem do tempo de resposta.
        Usa tempo de parede para alternância de fase e término do teste.
        """
        start_wall = time.time()
        next_ts = start_wall
        last_tick = start_wall

        while True:
            now = time.time()
            self.elapsed_wall = now - start_wall
            self.phase_elapsed_wall += (now - last_tick)
            last_tick = now

            # Encerrar pelo tempo de parede global
            if self.elapsed_wall >= run_time_seconds:
                break

            # Alterna fase se necessário
            self._maybe_switch_phase()

            # Sorteia próximo intervalo e agenda horário do próximo envio
            wait_time = self.exponential_wait()
            next_ts += wait_time

            # Dorme até o horário agendado (sono relativo)
            sleep_for = max(0.0, next_ts - time.time())
            if sleep_for > 0:
                gevent.sleep(sleep_for)

            # Escolhe endpoint conforme as probabilidades
            current_endpoint = random.choices(self.endpoints, weights=self.endpoint_probabilities)[0]

            # Dispara em greenlet separado (não bloqueia o agendador)
            gevent.spawn(self.send_request, current_endpoint, wait_time)

    # ----- Spawn único -----

    def on_start(self):
        # Garantir que apenas um greenlet de agendamento seja criado por usuário
        if not self._spawned_scheduler:
            self._spawned_scheduler = True
            gevent.spawn(self.schedule_requests)

    # Mantém o @task para o Locust não reclamar, mas não cria novos greenlets
    @task
    def noop(self):
        gevent.sleep(0.1)
