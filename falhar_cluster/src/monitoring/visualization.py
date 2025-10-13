#!/usr/bin/env python3
"""
Visualization and Graphing Module
=================================

Sistema para geração de gráficos e visualizações das métricas de resiliência.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.offline as pyo
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
from pathlib import Path
import sqlite3

from .metrics_collector import AdvancedMetricsCollector, MetricsAggregator
from ..core.base import FailureMetrics, RecoveryMetrics, logger


class ChaosVisualization:
    """Gerador de visualizações para métricas de chaos engineering"""
    
    def __init__(self, metrics_collector: AdvancedMetricsCollector):
        self.collector = metrics_collector
        self.aggregator = MetricsAggregator(metrics_collector)
        self.logger = logger.getChild("ChaosVisualization")
        
        # Configurações de estilo
        plt.style.use('seaborn-v0_8')
        self.colors = {
            'healthy': '#2E8B57',
            'degraded': '#FFD700', 
            'unhealthy': '#DC143C',
            'recovery': '#4169E1',
            'background': '#F5F5F5'
        }
    
    def plot_recovery_timeline(self, target: str, days: int = 7, 
                             save_path: Optional[str] = None) -> str:
        """
        Cria gráfico de timeline de recuperação para um target
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Busca dados do banco
        conn = sqlite3.connect(self.collector.db_path)
        query = '''
        SELECT start_time, end_time, recovery_time, failure_type, success
        FROM failures 
        WHERE target = ? AND start_time >= ? 
        ORDER BY start_time
        '''
        df = pd.read_sql_query(query, conn, params=(target, start_date))
        conn.close()
        
        if df.empty:
            self.logger.warning(f"No data found for target {target}")
            return ""
        
        # Converte timestamps
        df['start_time'] = pd.to_datetime(df['start_time'])
        df['end_time'] = pd.to_datetime(df['end_time'])
        
        # Cria figura
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
        fig.suptitle(f'Recovery Timeline - {target} (Last {days} days)', fontsize=16, fontweight='bold')
        
        # Gráfico 1: Timeline de falhas
        for idx, row in df.iterrows():
            if not pd.isna(row['end_time']):
                duration = (row['end_time'] - row['start_time']).total_seconds() / 60  # minutos
                color = self.colors['unhealthy'] if not bool(row['success']) else self.colors['degraded']
                
                ax1.barh(idx, duration, left=row['start_time'], height=0.6, 
                        color=color, alpha=0.7, label=row['failure_type'] if idx == 0 else "")
                
                # Adiciona texto com tempo de recuperação
                if not pd.isna(row['recovery_time']):
                    ax1.text(row['start_time'], idx, f"{row['recovery_time']:.1f}s", 
                            ha='left', va='center', fontsize=8)
        
        ax1.set_ylabel('Failure Events')
        ax1.set_title('Failure Duration Timeline')
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        ax1.xaxis.set_major_locator(mdates.DayLocator())
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
        # Gráfico 2: Tempo de recuperação por evento
        successful_failures = df[df['success'] == True].copy()
        if not successful_failures.empty:
            ax2.plot(successful_failures['start_time'], successful_failures['recovery_time'], 
                    marker='o', linestyle='-', color=self.colors['recovery'], linewidth=2, markersize=6)
            
            # Linha média
            mean_recovery = successful_failures['recovery_time'].mean()
            ax2.axhline(y=mean_recovery, color=self.colors['unhealthy'], 
                       linestyle='--', alpha=0.7, label=f'Average: {mean_recovery:.1f}s')
            
            ax2.set_ylabel('Recovery Time (seconds)')
            ax2.set_title('Recovery Time Trend')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
        
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        ax2.xaxis.set_major_locator(mdates.DayLocator())
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        
        # Salva gráfico
        if save_path is None:
            save_path = f"recovery_timeline_{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Recovery timeline saved to {save_path}")
        return save_path
    
    def plot_availability_heatmap(self, targets: List[str], days: int = 30,
                                save_path: Optional[str] = None) -> str:
        """
        Cria heatmap de disponibilidade por target e dia
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Coleta dados de disponibilidade
        availability_data = []
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        for target in targets:
            for date in date_range:
                # Calcula disponibilidade para cada dia
                day_start = date
                day_end = date + timedelta(days=1)
                
                conn = sqlite3.connect(self.collector.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                SELECT SUM(COALESCE(downtime, 0)) FROM failures 
                WHERE target = ? AND start_time >= ? AND start_time < ?
                ''', (target, day_start, day_end))
                
                result = cursor.fetchone()
                downtime = result[0] if result[0] is not None else 0
                
                availability = ((24 * 3600 - downtime) / (24 * 3600)) * 100
                availability_data.append({
                    'target': target,
                    'date': date.strftime('%Y-%m-%d'),
                    'availability': availability
                })
                
                conn.close()
        
        # Cria DataFrame
        df = pd.DataFrame(availability_data)
        
        if df.empty:
            self.logger.warning("No availability data found")
            return ""
        
        # Pivota dados para heatmap
        heatmap_data = df.pivot(index='target', columns='date', values='availability')
        
        # Cria figura
        fig, ax = plt.subplots(figsize=(16, max(6, len(targets) * 0.8)))
        
        # Cria heatmap
        im = ax.imshow(heatmap_data.values, cmap='RdYlGn', aspect='auto', vmin=90, vmax=100)
        
        # Configurações dos eixos
        ax.set_xticks(range(len(heatmap_data.columns)))
        ax.set_xticklabels([pd.to_datetime(d).strftime('%m/%d') for d in heatmap_data.columns], rotation=45)
        ax.set_yticks(range(len(heatmap_data.index)))
        ax.set_yticklabels(heatmap_data.index)
        
        # Adiciona valores nas células
        for i in range(len(heatmap_data.index)):
            for j in range(len(heatmap_data.columns)):
                value = heatmap_data.iloc[i, j]
                if not np.isnan(value):
                    color = 'white' if float(value) < 95 else 'black'
                    ax.text(j, i, f'{value:.1f}%', ha='center', va='center', color=color, fontsize=8)
        
        # Colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Availability (%)', rotation=270, labelpad=15)
        
        ax.set_title(f'Availability Heatmap - Last {days} days', fontsize=14, fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Target')
        
        plt.tight_layout()
        
        # Salva gráfico
        if save_path is None:
            save_path = f"availability_heatmap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Availability heatmap saved to {save_path}")
        return save_path
    
    def plot_failure_type_distribution(self, days: int = 30, 
                                     save_path: Optional[str] = None) -> str:
        """
        Cria gráfico de distribuição de tipos de falha
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Busca dados
        conn = sqlite3.connect(self.collector.db_path)
        query = '''
        SELECT failure_type, COUNT(*) as count, AVG(recovery_time) as avg_recovery
        FROM failures 
        WHERE start_time >= ? 
        GROUP BY failure_type
        ORDER BY count DESC
        '''
        df = pd.read_sql_query(query, conn, params=(start_date,))
        conn.close()
        
        if df.empty:
            self.logger.warning("No failure data found")
            return ""
        
        # Cria figura com subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'Failure Analysis - Last {days} days', fontsize=16, fontweight='bold')
        
        # 1. Gráfico de pizza - distribuição de tipos
        import matplotlib.cm as cm
        colors = cm.Set3(np.linspace(0, 1, len(df)))
        ax1.pie(df['count'], labels=df['failure_type'], autopct='%1.1f%%', colors=colors)
        ax1.set_title('Failure Type Distribution')
        
        # 2. Gráfico de barras - contagem por tipo
        bars = ax2.bar(df['failure_type'], df['count'], color=colors)
        ax2.set_title('Failure Count by Type')
        ax2.set_ylabel('Number of Failures')
        ax2.tick_params(axis='x', rotation=45)
        
        # Adiciona valores nas barras
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'{int(height)}', ha='center', va='bottom')
        
        # 3. Tempo médio de recuperação por tipo
        recovery_data = df[df['avg_recovery'].notna()]
        if not recovery_data.empty:
            bars = ax3.bar(recovery_data['failure_type'], recovery_data['avg_recovery'], 
                          color=colors[:len(recovery_data)])
            ax3.set_title('Average Recovery Time by Type')
            ax3.set_ylabel('Recovery Time (seconds)')
            ax3.tick_params(axis='x', rotation=45)
            
            # Adiciona valores nas barras
            for bar in bars:
                height = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                        f'{height:.1f}s', ha='center', va='bottom')
        else:
            ax3.text(0.5, 0.5, 'No recovery data available', ha='center', va='center',
                    transform=ax3.transAxes, fontsize=12)
            ax3.set_title('Average Recovery Time by Type')
        
        # 4. Timeline de falhas por tipo
        conn = sqlite3.connect(self.collector.db_path)
        query = '''
        SELECT DATE(start_time) as date, failure_type, COUNT(*) as count
        FROM failures 
        WHERE start_time >= ? 
        GROUP BY DATE(start_time), failure_type
        ORDER BY date
        '''
        timeline_df = pd.read_sql_query(query, conn, params=(start_date,))
        conn.close()
        
        if not timeline_df.empty:
            timeline_pivot = timeline_df.pivot(index='date', columns='failure_type', values='count').fillna(0)
            timeline_pivot.plot(kind='area', stacked=True, ax=ax4, alpha=0.7)
            ax4.set_title('Failure Timeline by Type')
            ax4.set_ylabel('Number of Failures')
            ax4.tick_params(axis='x', rotation=45)
            ax4.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        else:
            ax4.text(0.5, 0.5, 'No timeline data available', ha='center', va='center',
                    transform=ax4.transAxes, fontsize=12)
            ax4.set_title('Failure Timeline by Type')
        
        plt.tight_layout()
        
        # Salva gráfico
        if save_path is None:
            save_path = f"failure_distribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Failure distribution plot saved to {save_path}")
        return save_path
    
    def create_interactive_dashboard(self, targets: Optional[List[str]] = None, 
                                   days: int = 30) -> str:
        """
        Cria dashboard interativo usando Plotly
        """
        if targets is None:
            # Busca todos os targets únicos
            conn = sqlite3.connect(self.collector.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT target FROM failures LIMIT 10')
            targets = [row[0] for row in cursor.fetchall()]
            conn.close()
        
        if not targets:
            self.logger.warning("No targets found for dashboard")
            return ""
        
        # Cria subplots
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                'Recovery Time Trends',
                'Availability by Target', 
                'Failure Type Distribution',
                'MTTR Comparison',
                'Incident Timeline',
                'Resilience Scores'
            ),
            specs=[
                [{"secondary_y": False}, {"secondary_y": False}],
                [{"secondary_y": False}, {"secondary_y": False}],
                [{"colspan": 2}, None]
            ]
        )
        
        # 1. Recovery Time Trends
        for target in targets[:5]:  # Limita a 5 targets para visibilidade
            conn = sqlite3.connect(self.collector.db_path)
            query = '''
            SELECT start_time, recovery_time FROM failures 
            WHERE target = ? AND recovery_time IS NOT NULL 
            ORDER BY start_time
            '''
            df = pd.read_sql_query(query, conn, params=(target,))
            conn.close()
            
            if not df.empty:
                df['start_time'] = pd.to_datetime(df['start_time'])
                fig.add_trace(
                    go.Scatter(
                        x=df['start_time'],
                        y=df['recovery_time'],
                        mode='lines+markers',
                        name=f'{target}',
                        line=dict(width=2)
                    ),
                    row=1, col=1
                )
        
        # 2. Availability by Target
        availability_data = []
        for target in targets:
            availability = self.collector.calculate_availability_metrics(target, period_hours=24*days)
            availability_data.append({
                'target': target,
                'availability': availability.availability_percentage
            })
        
        if availability_data:
            availability_df = pd.DataFrame(availability_data)
            fig.add_trace(
                go.Bar(
                    x=availability_df['target'],
                    y=availability_df['availability'],
                    name='Availability %',
                    marker_color='lightblue'
                ),
                row=1, col=2
            )
        
        # 3. Failure Type Distribution
        benchmarks = self.aggregator.benchmark_failure_types()
        if benchmarks:
            failure_types = list(benchmarks.keys())
            counts = [benchmarks[ft]['count'] for ft in failure_types]
            
            fig.add_trace(
                go.Pie(
                    labels=failure_types,
                    values=counts,
                    name="Failure Types"
                ),
                row=2, col=1
            )
        
        # 4. MTTR Comparison
        failure_types = []
        if benchmarks:
            failure_types = list(benchmarks.keys())
            mttr_values = [benchmarks[ft]['avg_recovery_time'] for ft in failure_types]
            
            fig.add_trace(
                go.Bar(
                    x=failure_types,
                    y=mttr_values,
                    name='MTTR (seconds)',
                    marker_color='orange'
                ),
                row=2, col=2
            )
        
        # 5. Resilience Scores
        scores_data = []
        for target in targets:
            score = self.collector.calculate_resilience_score(target)
            scores_data.append({
                'target': target,
                'score': score.overall_score,
                'grade': score.grade
            })
        
        if scores_data:
            scores_df = pd.DataFrame(scores_data)
            
            # Cria gráfico de radar para scores de resiliência
            fig.add_trace(
                go.Bar(
                    x=scores_df['target'],
                    y=scores_df['score'],
                    name='Resilience Score',
                    text=scores_df['grade'],
                    textposition='auto',
                    marker_color='green'
                ),
                row=3, col=1
            )
        
        # Configurações do layout
        fig.update_layout(
            height=1200,
            showlegend=True,
            title_text=f"Chaos Engineering Dashboard - Last {days} days",
            title_x=0.5
        )
        
        # Configurações dos eixos
        fig.update_xaxes(title_text="Time", row=1, col=1)
        fig.update_yaxes(title_text="Recovery Time (s)", row=1, col=1)
        
        fig.update_xaxes(title_text="Target", row=1, col=2)
        fig.update_yaxes(title_text="Availability (%)", row=1, col=2)
        
        fig.update_xaxes(title_text="Failure Type", row=2, col=2)
        fig.update_yaxes(title_text="MTTR (seconds)", row=2, col=2)
        
        fig.update_xaxes(title_text="Target", row=3, col=1)
        fig.update_yaxes(title_text="Score (0-100)", row=3, col=1)
        
        # Salva dashboard
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_file = f"chaos_dashboard_{timestamp}.html"
        
        pyo.plot(fig, filename=html_file, auto_open=False)
        
        self.logger.info(f"Interactive dashboard saved to {html_file}")
        return html_file
    
    def plot_resilience_radar(self, targets: List[str], 
                            save_path: Optional[str] = None) -> str:
        """
        Cria gráfico radar de scores de resiliência
        """
        if len(targets) > 6:
            targets = targets[:6]  # Limita para visibilidade
        
        # Coleta dados de resiliência
        scores_data = []
        for target in targets:
            score = self.collector.calculate_resilience_score(target)
            scores_data.append({
                'target': target,
                'recovery_speed': score.recovery_speed_score,
                'availability': score.availability_score,
                'consistency': score.consistency_score,
                'overall': score.overall_score
            })
        
        if not scores_data:
            self.logger.warning("No resilience data found")
            return ""
        
        # Cria figura Plotly
        fig = go.Figure()
        
        categories = ['Recovery Speed', 'Availability', 'Consistency', 'Overall Score']
        
        for data in scores_data:
            values = [
                data['recovery_speed'],
                data['availability'],
                data['consistency'],
                data['overall']
            ]
            
            fig.add_trace(go.Scatterpolar(
                r=values,
                theta=categories,
                fill='toself',
                name=data['target'],
                line=dict(width=2)
            ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100]
                )
            ),
            showlegend=True,
            title="Resilience Score Comparison",
            width=800,
            height=600
        )
        
        # Salva gráfico
        if save_path is None:
            save_path = f"resilience_radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        pyo.plot(fig, filename=save_path, auto_open=False)
        
        self.logger.info(f"Resilience radar chart saved to {save_path}")
        return save_path
    
    def generate_summary_report(self, target: Optional[str] = None,
                              days: int = 30) -> Dict[str, str]:
        """
        Gera conjunto completo de visualizações
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        files_generated = {}
        
        try:
            # Timeline de recuperação
            if target:
                recovery_file = self.plot_recovery_timeline(target, days)
                files_generated['recovery_timeline'] = recovery_file
            
            # Heatmap de disponibilidade
            conn = sqlite3.connect(self.collector.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT target FROM failures LIMIT 10')
            targets = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            if targets:
                heatmap_file = self.plot_availability_heatmap(targets, days)
                files_generated['availability_heatmap'] = heatmap_file
            
            # Distribuição de tipos de falha
            distribution_file = self.plot_failure_type_distribution(days)
            files_generated['failure_distribution'] = distribution_file
            
            # Dashboard interativo
            dashboard_file = self.create_interactive_dashboard(targets, days)
            files_generated['interactive_dashboard'] = dashboard_file
            
            # Radar de resiliência
            if len(targets) >= 2:
                radar_file = self.plot_resilience_radar(targets)
                files_generated['resilience_radar'] = radar_file
            
            self.logger.info(f"Generated {len(files_generated)} visualization files")
            
        except Exception as e:
            self.logger.error(f"Error generating visualizations: {e}")
        
        return files_generated


# Funções utilitárias
def quick_visualization(db_path: str = "chaos_metrics.db", target: Optional[str] = None):
    """Gera visualizações rápidas para análise"""
    collector = AdvancedMetricsCollector(db_path)
    viz = ChaosVisualization(collector)
    
    print("Generating chaos engineering visualizations...")
    
    files = viz.generate_summary_report(target=target, days=7)
    
    print("\nGenerated files:")
    for viz_type, filename in files.items():
        print(f"  {viz_type}: {filename}")
    
    return files


if __name__ == "__main__":
    # Exemplo de uso
    print("Chaos Visualization - Example Usage")
    
    # Cria dados de exemplo se não existirem
    collector = AdvancedMetricsCollector()
    viz = ChaosVisualization(collector)
    
    # Gera visualizações de exemplo
    files = quick_visualization()
    
    print(f"\nVisualization files generated: {len(files)}")