"""
Analisador de Métricas
====================

Módulo para análise e cálculo de métricas de confiabilidade.
"""

import statistics
from datetime import datetime
from typing import Dict, List
from ..utils.config import get_config


class MetricsAnalyzer:
    """
    Analisador de métricas de confiabilidade.
    
    Calcula MTTF, MTTR, disponibilidade e outras métricas
    por componente individual.
    """
    
    def __init__(self):
        """Inicializa o analisador de métricas."""
        self.config = get_config()
        self.component_metrics = {}
    
    def update_component_metrics(self, component_id: str, component_type: str, 
                               recovery_time: float, recovered: bool):
        """
        Atualiza métricas individuais de um componente específico.
        
        Args:
            component_id: ID único do componente
            component_type: Tipo do componente (pod, worker_node, etc.)
            recovery_time: Tempo de recuperação em segundos
            recovered: Se a recuperação foi bem-sucedida
        """
        if component_id not in self.component_metrics:
            self.component_metrics[component_id] = {
                'component_type': component_type,
                'total_failures': 0,
                'successful_recoveries': 0,
                'recovery_times': [],
                'failure_timestamps': [],
                'mttr_current': 0.0,
                'availability': 0.0
            }
        
        metrics = self.component_metrics[component_id]
        metrics['total_failures'] += 1
        metrics['failure_timestamps'].append(datetime.now().isoformat())
        
        if recovered:
            metrics['successful_recoveries'] += 1
            metrics['recovery_times'].append(recovery_time)
            metrics['mttr_current'] = statistics.mean(metrics['recovery_times'])
        
        # Calcular disponibilidade (% de recuperações bem-sucedidas)
        metrics['availability'] = (metrics['successful_recoveries'] / metrics['total_failures']) * 100
    
    def get_component_statistics(self, component_id: str) -> Dict:
        """
        Retorna estatísticas detalhadas de um componente específico.
        
        Args:
            component_id: ID do componente
            
        Returns:
            Dicionário com estatísticas calculadas
        """
        if component_id not in self.component_metrics:
            return {}
        
        metrics = self.component_metrics[component_id]
        recovery_times = metrics['recovery_times']
        
        stats = {
            'component_id': component_id,
            'component_type': metrics['component_type'],
            'total_failures': metrics['total_failures'],
            'successful_recoveries': metrics['successful_recoveries'],
            'availability_percent': metrics['availability'],
            'mttr_mean': statistics.mean(recovery_times) if recovery_times else 0,
            'mttr_median': statistics.median(recovery_times) if recovery_times else 0,
            'mttr_min': min(recovery_times) if recovery_times else 0,
            'mttr_max': max(recovery_times) if recovery_times else 0,
            'mttr_std_dev': statistics.stdev(recovery_times) if len(recovery_times) > 1 else 0
        }
        
        return stats
    
    def calculate_and_print_statistics(self, results: List[Dict]):
        """
        Calcula e exibe estatísticas do teste.
        
        Args:
            results: Lista com resultados de iterações
        """
        if not results:
            return
        
        recovery_times = [r['recovery_time_seconds'] for r in results if r['recovered']]
        success_rate = len(recovery_times) / len(results) * 100
        
        print(f"\n📊 === ESTATÍSTICAS DO TESTE ===")
        print(f"🔢 Total de iterações: {len(results)}")
        print(f"✅ Taxa de sucesso: {success_rate:.1f}% ({len(recovery_times)}/{len(results)})")
        
        if recovery_times:
            print(f"⏱️ MTTR Médio: {statistics.mean(recovery_times):.2f}s")
            print(f"📈 MTTR Máximo: {max(recovery_times):.2f}s")
            print(f"📉 MTTR Mínimo: {min(recovery_times):.2f}s")
            if len(recovery_times) > 1:
                print(f"📊 Desvio Padrão: {statistics.stdev(recovery_times):.2f}s")
                print(f"📏 Mediana: {statistics.median(recovery_times):.2f}s")
        else:
            print("❌ Nenhuma recuperação bem-sucedida para calcular MTTR")
        
        print("="*50)
    
    def print_individual_component_stats(self):
        """Imprime estatísticas individuais de cada componente testado."""
        if not self.component_metrics:
            print("📊 Nenhuma métrica de componente individual disponível")
            return
        
        print(f"\n📊 === MÉTRICAS INDIVIDUAIS POR COMPONENTE ===")
        
        for component_id, metrics in self.component_metrics.items():
            stats = self.get_component_statistics(component_id)
            
            print(f"\n🔧 Componente: {component_id}")
            print(f"   📝 Tipo: {stats['component_type']}")
            print(f"   💥 Total de falhas: {stats['total_failures']}")
            print(f"   ✅ Recuperações bem-sucedidas: {stats['successful_recoveries']}")
            print(f"   📈 Disponibilidade: {stats['availability_percent']:.2f}%")
            
            if stats['mttr_mean'] > 0:
                print(f"   ⏱️ MTTR Médio: {stats['mttr_mean']:.2f}s")
                print(f"   📊 MTTR Mediano: {stats['mttr_median']:.2f}s")
                print(f"   📉 MTTR Mínimo: {stats['mttr_min']:.2f}s")
                print(f"   📈 MTTR Máximo: {stats['mttr_max']:.2f}s")
                if stats['mttr_std_dev'] > 0:
                    print(f"   📏 Desvio Padrão: {stats['mttr_std_dev']:.2f}s")
            else:
                print(f"   ❌ Nenhuma recuperação bem-sucedida para calcular MTTR")
        
        print("="*60)