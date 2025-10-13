#!/usr/bin/env python3
"""
Metrics Collection and Analysis Module
======================================

Sistema avançado para coleta, armazenamento e análise de métricas de recuperação
e resiliência de sistemas.
"""

import time
import csv
import sqlite3
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import json

from ..core.base import FailureMetrics, RecoveryMetrics, FailureType, logger


@dataclass
class AvailabilityMetrics:
    """Métricas de disponibilidade"""
    target: str
    uptime_seconds: float
    downtime_seconds: float
    total_period_seconds: float
    availability_percentage: float
    mtbf: float  # Mean Time Between Failures
    mttr: float  # Mean Time To Repair
    incident_count: int


@dataclass
class PerformanceMetrics:
    """Métricas de performance durante falhas"""
    target: str
    failure_type: FailureType
    response_time_before: Optional[float] = None
    response_time_during: Optional[float] = None
    response_time_after: Optional[float] = None
    throughput_before: Optional[float] = None
    throughput_during: Optional[float] = None
    throughput_after: Optional[float] = None
    error_rate_before: Optional[float] = None
    error_rate_during: Optional[float] = None
    error_rate_after: Optional[float] = None


@dataclass
class ResilienceScore:
    """Score de resiliência calculado"""
    target: str
    recovery_speed_score: float  # 0-100
    availability_score: float   # 0-100
    consistency_score: float    # 0-100
    overall_score: float        # 0-100
    grade: str                  # A, B, C, D, F


class AdvancedMetricsCollector:
    """Coletor avançado de métricas com persistência e análise"""
    
    def __init__(self, db_path: str = "chaos_metrics.db"):
        self.db_path = db_path
        self.logger = logger
        self.init_database()
        
    def init_database(self):
        """Inicializa banco de dados SQLite para persistência"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de falhas
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS failures (
            id TEXT PRIMARY KEY,
            failure_type TEXT NOT NULL,
            target TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            recovery_time REAL,
            downtime REAL,
            success BOOLEAN,
            error_message TEXT,
            additional_metrics TEXT
        )
        ''')
        
        # Tabela de métricas de disponibilidade
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS availability_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            measurement_date DATETIME NOT NULL,
            uptime_seconds REAL NOT NULL,
            downtime_seconds REAL NOT NULL,
            total_period_seconds REAL NOT NULL,
            availability_percentage REAL NOT NULL,
            mtbf REAL,
            mttr REAL,
            incident_count INTEGER
        )
        ''')
        
        # Tabela de métricas de performance
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            failure_type TEXT NOT NULL,
            measurement_time DATETIME NOT NULL,
            response_time_before REAL,
            response_time_during REAL,
            response_time_after REAL,
            throughput_before REAL,
            throughput_during REAL,
            throughput_after REAL,
            error_rate_before REAL,
            error_rate_during REAL,
            error_rate_after REAL
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def _store_failure_metrics(self, metrics: FailureMetrics):
        """Método auxiliar para armazenar métricas de falha"""
        # Este método é chamado internamente e pode ser expandido conforme necessário
        pass
    
    def record_failure(self, metrics: FailureMetrics):
        """Registra métricas de falha no banco"""
        # Armazena métricas básicas no banco de dados
        self._store_failure_metrics(metrics)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT OR REPLACE INTO failures 
        (id, failure_type, target, start_time, end_time, recovery_time, downtime, 
         success, error_message, additional_metrics)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            metrics.failure_id,
            metrics.failure_type.value,
            metrics.target,
            metrics.start_time,
            metrics.end_time,
            metrics.recovery_time,
            metrics.downtime,
            metrics.success,
            metrics.error_message,
            json.dumps(metrics.additional_metrics) if metrics.additional_metrics else None
        ))
        
        conn.commit()
        conn.close()
    
    def record_availability_metrics(self, metrics: AvailabilityMetrics):
        """Registra métricas de disponibilidade"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO availability_metrics 
        (target, measurement_date, uptime_seconds, downtime_seconds, 
         total_period_seconds, availability_percentage, mtbf, mttr, incident_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            metrics.target,
            datetime.now(),
            metrics.uptime_seconds,
            metrics.downtime_seconds,
            metrics.total_period_seconds,
            metrics.availability_percentage,
            metrics.mtbf,
            metrics.mttr,
            metrics.incident_count
        ))
        
        conn.commit()
        conn.close()
    
    def record_performance_metrics(self, metrics: PerformanceMetrics):
        """Registra métricas de performance"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO performance_metrics 
        (target, failure_type, measurement_time, response_time_before, response_time_during,
         response_time_after, throughput_before, throughput_during, throughput_after,
         error_rate_before, error_rate_during, error_rate_after)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            metrics.target,
            metrics.failure_type.value,
            datetime.now(),
            metrics.response_time_before,
            metrics.response_time_during,
            metrics.response_time_after,
            metrics.throughput_before,
            metrics.throughput_during,
            metrics.throughput_after,
            metrics.error_rate_before,
            metrics.error_rate_during,
            metrics.error_rate_after
        ))
        
        conn.commit()
        conn.close()
    
    def calculate_availability_metrics(self, target: str, 
                                     period_hours: int = 24) -> AvailabilityMetrics:
        """Calcula métricas de disponibilidade para um target"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=period_hours)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Busca falhas no período
        cursor.execute('''
        SELECT recovery_time, downtime FROM failures 
        WHERE target = ? AND start_time >= ? AND start_time <= ?
        AND success = 1
        ''', (target, start_time, end_time))
        
        failures = cursor.fetchall()
        conn.close()
        
        total_period = period_hours * 3600  # segundos
        total_downtime = sum(f[1] for f in failures if f[1] is not None)
        uptime = total_period - total_downtime
        
        availability_percentage = (uptime / total_period) * 100
        
        # Calcula MTBF e MTTR
        incident_count = len(failures)
        if incident_count > 0:
            mtbf = uptime / incident_count if incident_count > 0 else 0
            recovery_times = [f[0] for f in failures if f[0] is not None]
            mttr = sum(recovery_times) / len(recovery_times) if recovery_times else 0
        else:
            mtbf = total_period
            mttr = 0
        
        return AvailabilityMetrics(
            target=target,
            uptime_seconds=uptime,
            downtime_seconds=total_downtime,
            total_period_seconds=total_period,
            availability_percentage=availability_percentage,
            mtbf=mtbf,
            mttr=mttr,
            incident_count=incident_count
        )
    
    def calculate_resilience_score(self, target: str) -> ResilienceScore:
        """Calcula score de resiliência para um target"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Busca dados de falhas dos últimos 30 dias
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        cursor.execute('''
        SELECT recovery_time, failure_type FROM failures 
        WHERE target = ? AND start_time >= ? 
        AND success = 1 AND recovery_time IS NOT NULL
        ''', (target, thirty_days_ago))
        
        failures = cursor.fetchall()
        conn.close()
        
        if not failures:
            # Se não há dados, assume score neutro
            return ResilienceScore(
                target=target,
                recovery_speed_score=50.0,
                availability_score=50.0,
                consistency_score=50.0,
                overall_score=50.0,
                grade="C"
            )
        
        # 1. Recovery Speed Score (baseado na velocidade de recuperação)
        recovery_times = [f[0] for f in failures]
        avg_recovery_time = statistics.mean(recovery_times)
        
        # Score inversamente proporcional ao tempo (menor tempo = maior score)
        # Assume que 60s é tempo ideal (100 pontos), 300s é ruim (20 pontos)
        recovery_speed_score = max(20, min(100, 100 - (avg_recovery_time - 60) * 80 / 240))
        
        # 2. Availability Score
        availability = self.calculate_availability_metrics(target, period_hours=24*7)  # 7 dias
        availability_score = availability.availability_percentage
        
        # 3. Consistency Score (baseado na variabilidade dos tempos de recuperação)
        if len(recovery_times) > 1:
            recovery_stddev = statistics.stdev(recovery_times)
            # Menor desvio padrão = maior consistência
            consistency_score = max(0, min(100, 100 - (recovery_stddev / avg_recovery_time) * 100))
        else:
            consistency_score = 100.0  # Único ponto = perfeitamente consistente
        
        # Score geral (média ponderada)
        overall_score = (
            recovery_speed_score * 0.4 +
            availability_score * 0.4 +
            consistency_score * 0.2
        )
        
        # Determina nota
        if overall_score >= 90:
            grade = "A"
        elif overall_score >= 80:
            grade = "B"
        elif overall_score >= 70:
            grade = "C"
        elif overall_score >= 60:
            grade = "D"
        else:
            grade = "F"
        
        return ResilienceScore(
            target=target,
            recovery_speed_score=round(recovery_speed_score, 2),
            availability_score=round(availability_score, 2),
            consistency_score=round(consistency_score, 2),
            overall_score=round(overall_score, 2),
            grade=grade
        )
    
    def get_failure_trends(self, target: Optional[str] = None, 
                          days: int = 30) -> Dict[str, Any]:
        """Analisa tendências de falhas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Constrói query baseada nos parâmetros
        start_date = datetime.now() - timedelta(days=days)
        
        if target:
            cursor.execute('''
            SELECT failure_type, DATE(start_time) as failure_date, 
                   COUNT(*) as count, AVG(recovery_time) as avg_recovery
            FROM failures 
            WHERE target = ? AND start_time >= ?
            GROUP BY failure_type, DATE(start_time)
            ORDER BY failure_date DESC
            ''', (target, start_date))
        else:
            cursor.execute('''
            SELECT failure_type, DATE(start_time) as failure_date, 
                   COUNT(*) as count, AVG(recovery_time) as avg_recovery
            FROM failures 
            WHERE start_time >= ?
            GROUP BY failure_type, DATE(start_time)
            ORDER BY failure_date DESC
            ''', (start_date,))
        
        results = cursor.fetchall()
        conn.close()
        
        # Organiza dados por tipo de falha
        trends = {}
        daily_totals = {}
        
        for failure_type, date, count, avg_recovery in results:
            if failure_type not in trends:
                trends[failure_type] = {
                    'dates': [],
                    'counts': [],
                    'avg_recovery_times': []
                }
            
            trends[failure_type]['dates'].append(date)
            trends[failure_type]['counts'].append(count)
            trends[failure_type]['avg_recovery_times'].append(avg_recovery or 0)
            
            if date not in daily_totals:
                daily_totals[date] = 0
            daily_totals[date] += count
        
        return {
            'target': target or 'all',
            'period_days': days,
            'trends_by_failure_type': trends,
            'daily_totals': daily_totals,
            'total_failures': sum(daily_totals.values()),
            'analysis_date': datetime.now().isoformat()
        }
    
    def export_metrics_report(self, target: Optional[str] = None, 
                            format_type: str = 'json') -> str:
        """Exporta relatório completo de métricas"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        target_suffix = f"_{target}" if target else "_all"
        filename = f"metrics_report{target_suffix}_{timestamp}.{format_type}"
        
        # Coleta dados
        availability = self.calculate_availability_metrics(target) if target else None
        resilience = self.calculate_resilience_score(target) if target else None
        trends = self.get_failure_trends(target, days=30)
        
        # Dados de falhas recentes
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if target:
            cursor.execute('''
            SELECT * FROM failures WHERE target = ? 
            ORDER BY start_time DESC LIMIT 100
            ''', (target,))
        else:
            cursor.execute('''
            SELECT * FROM failures 
            ORDER BY start_time DESC LIMIT 100
            ''')
        
        recent_failures = cursor.fetchall()
        conn.close()
        
        # Monta relatório
        report = {
            'metadata': {
                'target': target or 'all_targets',
                'generated_at': datetime.now().isoformat(),
                'report_type': 'comprehensive_metrics'
            },
            'availability_metrics': asdict(availability) if availability else None,
            'resilience_score': asdict(resilience) if resilience else None,
            'failure_trends': trends,
            'recent_failures_count': len(recent_failures),
            'summary': {
                'total_incidents': len(recent_failures),
                'avg_recovery_time': statistics.mean([
                    f[5] for f in recent_failures if f[5] is not None
                ]) if any(f[5] for f in recent_failures) else 0,
                'success_rate': len([f for f in recent_failures if f[7]]) / len(recent_failures) * 100 if recent_failures else 0
            }
        }
        
        # Exporta no formato solicitado
        if format_type == 'json':
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
        elif format_type == 'csv':
            # Exporta falhas em CSV
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'failure_id', 'failure_type', 'target', 'start_time', 
                    'end_time', 'recovery_time', 'downtime', 'success',
                    'error_message', 'additional_metrics'
                ])
                writer.writerows(recent_failures)
        
        self.logger.info(f"Metrics report exported to {filename}")
        return filename
    
    def cleanup_old_data(self, days_to_keep: int = 90):
        """Remove dados antigos do banco"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Remove falhas antigas
        cursor.execute('DELETE FROM failures WHERE start_time < ?', (cutoff_date,))
        failures_deleted = cursor.rowcount
        
        # Remove métricas antigas
        cursor.execute('DELETE FROM availability_metrics WHERE measurement_date < ?', (cutoff_date,))
        availability_deleted = cursor.rowcount
        
        cursor.execute('DELETE FROM performance_metrics WHERE measurement_time < ?', (cutoff_date,))
        performance_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"Cleaned up old data: {failures_deleted} failures, "
                        f"{availability_deleted} availability metrics, "
                        f"{performance_deleted} performance metrics")


class MetricsAggregator:
    """Agregador de métricas para análises comparativas"""
    
    def __init__(self, collector: AdvancedMetricsCollector):
        self.collector = collector
        self.logger = logger.getChild("MetricsAggregator")
    
    def compare_targets(self, targets: List[str]) -> Dict[str, ResilienceScore]:
        """Compara scores de resiliência entre múltiplos targets"""
        scores = {}
        for target in targets:
            scores[target] = self.collector.calculate_resilience_score(target)
        
        return scores
    
    def benchmark_failure_types(self, failure_types: Optional[List[FailureType]] = None) -> Dict[str, Dict[str, float]]:
        """Analisa performance de diferentes tipos de falha"""
        if failure_types is None:
            failure_types = list(FailureType)
        
        conn = sqlite3.connect(self.collector.db_path)
        cursor = conn.cursor()
        
        benchmarks = {}
        
        for failure_type in failure_types:
            cursor.execute('''
            SELECT recovery_time, downtime FROM failures 
            WHERE failure_type = ? AND success = 1 
            AND recovery_time IS NOT NULL
            ''', (failure_type.value,))
            
            results = cursor.fetchall()
            
            if results:
                recovery_times = [r[0] for r in results]
                downtimes = [r[1] for r in results if r[1] is not None]
                
                benchmarks[failure_type.value] = {
                    'count': len(results),
                    'avg_recovery_time': statistics.mean(recovery_times),
                    'median_recovery_time': statistics.median(recovery_times),
                    'min_recovery_time': min(recovery_times),
                    'max_recovery_time': max(recovery_times),
                    'stddev_recovery_time': statistics.stdev(recovery_times) if len(recovery_times) > 1 else 0,
                    'avg_downtime': statistics.mean(downtimes) if downtimes else 0
                }
            else:
                benchmarks[failure_type.value] = {
                    'count': 0,
                    'avg_recovery_time': 0,
                    'median_recovery_time': 0,
                    'min_recovery_time': 0,
                    'max_recovery_time': 0,
                    'stddev_recovery_time': 0,
                    'avg_downtime': 0
                }
        
        conn.close()
        return benchmarks
    
    def generate_sla_report(self, target: str, sla_availability: float = 99.9,
                           sla_recovery_time: float = 300) -> Dict[str, Any]:
        """Gera relatório de aderência a SLA"""
        availability = self.collector.calculate_availability_metrics(target, period_hours=24*30)  # 30 dias
        resilience = self.collector.calculate_resilience_score(target)
        
        # Verifica aderência
        availability_met = availability.availability_percentage >= sla_availability
        recovery_time_met = availability.mttr <= sla_recovery_time
        
        return {
            'target': target,
            'sla_period': '30_days',
            'sla_requirements': {
                'availability_target': sla_availability,
                'recovery_time_target': sla_recovery_time
            },
            'actual_performance': {
                'availability_actual': availability.availability_percentage,
                'recovery_time_actual': availability.mttr
            },
            'sla_compliance': {
                'availability_met': availability_met,
                'recovery_time_met': recovery_time_met,
                'overall_met': availability_met and recovery_time_met
            },
            'metrics_summary': {
                'total_incidents': availability.incident_count,
                'total_downtime_hours': availability.downtime_seconds / 3600,
                'mtbf_hours': availability.mtbf / 3600,
                'resilience_score': resilience.overall_score,
                'resilience_grade': resilience.grade
            },
            'generated_at': datetime.now().isoformat()
        }


# Funções utilitárias
def analyze_recovery_patterns(db_path: str = "chaos_metrics.db") -> Dict[str, Any]:
    """Analisa padrões de recuperação"""
    collector = AdvancedMetricsCollector(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Busca dados de recuperação por hora do dia
    cursor.execute('''
    SELECT strftime('%H', start_time) as hour, 
           AVG(recovery_time) as avg_recovery,
           COUNT(*) as count
    FROM failures 
    WHERE recovery_time IS NOT NULL AND success = 1
    GROUP BY strftime('%H', start_time)
    ORDER BY hour
    ''')
    
    hourly_patterns = cursor.fetchall()
    
    # Busca dados por dia da semana
    cursor.execute('''
    SELECT strftime('%w', start_time) as weekday,
           AVG(recovery_time) as avg_recovery,
           COUNT(*) as count
    FROM failures 
    WHERE recovery_time IS NOT NULL AND success = 1
    GROUP BY strftime('%w', start_time)
    ORDER BY weekday
    ''')
    
    weekly_patterns = cursor.fetchall()
    
    conn.close()
    
    return {
        'hourly_patterns': [
            {'hour': int(h), 'avg_recovery_time': avg, 'incident_count': count}
            for h, avg, count in hourly_patterns
        ],
        'weekly_patterns': [
            {'weekday': int(w), 'avg_recovery_time': avg, 'incident_count': count}
            for w, avg, count in weekly_patterns
        ],
        'analysis_date': datetime.now().isoformat()
    }


if __name__ == "__main__":
    # Exemplo de uso
    collector = AdvancedMetricsCollector()
    
    print("Advanced Metrics Collector - Example Usage")
    
    # Simula algumas métricas
    from ..core.base import FailureType, generate_failure_id
    
    # Exemplo de falha simulada
    test_metrics = FailureMetrics(
        failure_id=generate_failure_id(FailureType.POD_DELETE, "test-pod"),
        failure_type=FailureType.POD_DELETE,
        target="test-pod",
        start_time=datetime.now() - timedelta(minutes=5),
        end_time=datetime.now(),
        recovery_time=45.0,
        downtime=45.0,
        success=True
    )
    
    collector.record_failure(test_metrics)
    
    # Calcula métricas de disponibilidade
    availability = collector.calculate_availability_metrics("test-pod")
    print(f"Availability: {availability.availability_percentage:.2f}%")
    
    # Calcula score de resiliência
    score = collector.calculate_resilience_score("test-pod")
    print(f"Resilience Score: {score.overall_score}/100 (Grade: {score.grade})")
    
    # Exporta relatório
    report_file = collector.export_metrics_report("test-pod")
    print(f"Report exported to: {report_file}")