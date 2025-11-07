"""
Simulação Acelerada
==================

Módulo para simulação temporal acelerada de confiabilidade.
"""

import time
import numpy as np
import statistics
from datetime import datetime
from typing import Dict, List, Optional


class AcceleratedSimulation:
    """
    Classe para simulação temporal acelerada.
    
    Permite simular milhares de horas em minutos reais
    com distribuições estatísticas de falhas.
    """
    
    def __init__(self, time_acceleration: float = 10000.0, base_mttf_hours: float = 1.0):
        """
        Inicializa simulação acelerada.
        
        Args:
            time_acceleration: Fator de aceleração (1h real = X horas simuladas)
            base_mttf_hours: MTTF base em horas
        """
        self.time_acceleration = time_acceleration
        self.base_mttf_hours = base_mttf_hours
        self.simulation_start_real = None
        self.failure_intervals = []
        self.failure_distribution = "exponential"
    
    def start_simulation(self):
        """Inicia contador de tempo da simulação."""
        self.simulation_start_real = time.time()
    
    def get_simulation_time_hours(self) -> float:
        """
        Retorna tempo simulado atual em horas.
        
        Returns:
            Tempo simulado em horas
        """
        if not self.simulation_start_real:
            return 0.0
        
        real_elapsed = time.time() - self.simulation_start_real
        return (real_elapsed / 3600.0) * self.time_acceleration
    
    def calculate_next_failure_interval(self) -> float:
        """
        Calcula próximo intervalo de falha baseado na distribuição estatística.
        
        Returns:
            Intervalo até próxima falha em horas simuladas
        """
        current_mttf = self._calculate_current_mttf()
        
        if self.failure_distribution == "exponential":
            # Distribuição exponencial (mais comum para falhas de hardware/software)
            return np.random.exponential(current_mttf)
        
        elif self.failure_distribution == "weibull":
            # Distribuição Weibull (para desgaste progressivo)
            shape = 2.0  # β > 1 = taxa de falha crescente
            scale = current_mttf * np.power(np.log(2), 1.0/shape)
            return np.random.weibull(shape) * scale
        
        elif self.failure_distribution == "normal":
            # Distribuição normal (para falhas previsíveis)
            std_dev = current_mttf * 0.2  # 20% de variação
            return max(0.1, np.random.normal(current_mttf, std_dev))
        
        else:
            return current_mttf
    
    def _calculate_current_mttf(self) -> float:
        """
        Calcula MTTF atual baseado no histórico de falhas.
        
        Returns:
            MTTF atual em horas
        """
        if len(self.failure_intervals) < 2:
            return self.base_mttf_hours
        
        # Média dos intervalos recentes (últimas 10 falhas para suavizar)
        recent_intervals = self.failure_intervals[-10:]
        return float(np.mean(recent_intervals))
    
    def wait_for_next_failure_time(self, interval_hours: float) -> bool:
        """
        Aguarda o próximo tempo de falha na escala acelerada.
        
        Args:
            interval_hours: Intervalo em horas simuladas
            
        Returns:
            True se deve executar falha, False se simulação deve parar
        """
        # Converte horas simuladas para segundos reais
        real_wait_seconds = (interval_hours / self.time_acceleration) * 3600.0
        
        print(f"⏳ Aguardando próxima falha: {interval_hours:.2f}h simuladas "
              f"({real_wait_seconds:.1f}s reais)")
        
        # Aguarda o tempo real necessário
        time.sleep(real_wait_seconds)
        return True
    
    def register_failure_interval(self, interval_hours: float):
        """
        Registra intervalo entre falhas para cálculos futuros.
        
        Args:
            interval_hours: Intervalo entre falhas em horas
        """
        self.failure_intervals.append(interval_hours)
    
    def get_acceleration_stats(self) -> Dict:
        """
        Retorna estatísticas da aceleração temporal.
        
        Returns:
            Dicionário com estatísticas da simulação
        """
        sim_time = self.get_simulation_time_hours()
        real_time = time.time() - self.simulation_start_real if self.simulation_start_real else 0
        
        return {
            'time_acceleration': self.time_acceleration,
            'simulated_hours': sim_time,
            'real_seconds': real_time,
            'real_hours': real_time / 3600.0,
            'compression_ratio': f"1h real = {self.time_acceleration}h simuladas",
            'current_mttf_hours': self._calculate_current_mttf(),
            'total_failure_intervals': len(self.failure_intervals)
        }