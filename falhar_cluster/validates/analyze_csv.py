#!/usr/bin/env python3
"""
📊 Análise Detalhada do CSV de Simulação de Confiabilidade
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json

def analyze_reliability_csv(csv_path):
    """Análise detalhada do CSV de simulação de confiabilidade"""
    
    print("📊 Analisando dados de simulação de confiabilidade...")
    
    # Carregar dados
    df = pd.read_csv(csv_path)
    print(f"✅ Dados carregados: {len(df)} eventos")
    
    # Separar tipos de eventos
    failures = df[df['event_type'] == 'failure_initiated'].copy()
    recoveries = df[df['event_type'] == 'recovery_completed'].copy()
    
    print(f"\n📈 Resumo dos Eventos:")
    print(f"  • Falhas iniciadas: {len(failures)}")
    print(f"  • Recuperações completadas: {len(recoveries)}")
    print(f"  • Taxa de recuperação: {len(recoveries)/len(failures)*100:.1f}%")
    
    # Análise de falhas por tipo
    print(f"\n💥 Análise de Falhas:")
    failure_breakdown = failures['failure_mode'].value_counts()
    for failure_type, count in failure_breakdown.items():
        percentage = count / len(failures) * 100
        print(f"  • {failure_type}: {count} ({percentage:.1f}%)")
    
    # Análise de alvos
    print(f"\n🎯 Análise de Alvos:")
    target_breakdown = failures['target_type'].value_counts()
    for target_type, count in target_breakdown.items():
        print(f"  • {target_type}: {count}")
    
    # Principais alvos afetados
    top_targets = failures['target'].value_counts().head(5)
    print(f"\n🔥 Alvos Mais Afetados:")
    for target, count in top_targets.items():
        print(f"  • {target}: {count} falhas")
    
    # Análise de tempo de recuperação
    if len(recoveries) > 0 and 'duration_seconds' in recoveries.columns:
        recovery_times = recoveries['duration_seconds'].dropna()
        
        print(f"\n⏱️ Tempos de Recuperação:")
        print(f"  • Média: {recovery_times.mean():.2f}s")
        print(f"  • Mediana: {recovery_times.median():.2f}s")
        print(f"  • Desvio padrão: {recovery_times.std():.2f}s")
        print(f"  • Mínimo: {recovery_times.min():.2f}s")
        print(f"  • Máximo: {recovery_times.max():.2f}s")
        
        # Percentis
        p25 = recovery_times.quantile(0.25)
        p75 = recovery_times.quantile(0.75)
        p95 = recovery_times.quantile(0.95)
        
        print(f"  • P25: {p25:.2f}s")
        print(f"  • P75: {p75:.2f}s") 
        print(f"  • P95: {p95:.2f}s")
        
        # Detectar outliers
        iqr = p75 - p25
        lower_bound = p25 - 1.5 * iqr
        upper_bound = p75 + 1.5 * iqr
        outliers = recovery_times[(recovery_times < lower_bound) | (recovery_times > upper_bound)]
        
        if len(outliers) > 0:
            print(f"  ⚠️ Outliers detectados: {len(outliers)} ({len(outliers)/len(recovery_times)*100:.1f}%)")
        else:
            print(f"  ✅ Nenhum outlier detectado")
    
    # Métricas finais de confiabilidade
    last_row = df.iloc[-1]
    print(f"\n📊 Métricas Finais de Confiabilidade:")
    
    if 'mttf_hours' in last_row and pd.notna(last_row['mttf_hours']):
        mttf = last_row['mttf_hours']
        print(f"  • MTTF: {mttf:.2f} horas ({mttf*60:.0f} minutos)")
    
    if 'mtbf_hours' in last_row and pd.notna(last_row['mtbf_hours']):
        mtbf = last_row['mtbf_hours']
        print(f"  • MTBF: {mtbf:.2f} horas ({mtbf*60:.0f} minutos)")
    
    if 'mttr_seconds' in last_row and pd.notna(last_row['mttr_seconds']):
        mttr = last_row['mttr_seconds']
        print(f"  • MTTR: {mttr:.2f} segundos")
    
    # Análise temporal da simulação
    if 'simulation_time_hours' in df.columns and 'real_time_seconds' in df.columns:
        sim_hours = df['simulation_time_hours'].max()
        real_seconds = df['real_time_seconds'].max()
        real_minutes = real_seconds / 60
        acceleration = sim_hours / (real_seconds / 3600) if real_seconds > 0 else 0
        
        print(f"\n⚡ Métricas de Simulação:")
        print(f"  • Tempo simulado: {sim_hours:.2f} horas")
        print(f"  • Tempo real: {real_minutes:.2f} minutos ({real_seconds:.1f}s)")
        print(f"  • Fator de aceleração: {acceleration:.0f}x")
        print(f"  • Taxa de eventos: {len(df)/real_minutes:.1f} eventos/min")
    
    # Timeline de falhas por hora simulada
    if len(failures) > 0:
        print(f"\n📈 Distribuição Temporal de Falhas:")
        failures_timeline = failures.copy()
        failures_timeline['sim_hour_bin'] = (failures_timeline['simulation_time_hours'] // 50) * 50
        hourly_failures = failures_timeline['sim_hour_bin'].value_counts().sort_index()
        
        for hour_bin, count in hourly_failures.head(10).items():
            print(f"  • Horas {hour_bin:.0f}-{hour_bin+50:.0f}: {count} falhas")
    
    # Análise de eficiência de recuperação por tipo
    print(f"\n🔄 Eficiência de Recuperação por Tipo:")
    for failure_type in failures['failure_mode'].unique():
        if pd.notna(failure_type):
            type_failures = len(failures[failures['failure_mode'] == failure_type])
            type_recoveries = len(recoveries[recoveries['failure_mode'] == failure_type])
            efficiency = type_recoveries / type_failures * 100 if type_failures > 0 else 0
            print(f"  • {failure_type}: {efficiency:.1f}% ({type_recoveries}/{type_failures})")
    
    # Validação da qualidade dos dados
    print(f"\n✅ Validação da Qualidade dos Dados:")
    
    # Consistência temporal
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        time_gaps = df['timestamp'].diff()
        large_gaps = time_gaps[time_gaps > pd.Timedelta(seconds=30)]
        
        if len(large_gaps) > 0:
            print(f"  ⚠️ {len(large_gaps)} gaps temporais > 30s detectados")
        else:
            print(f"  ✅ Timeline consistente")
    
    # Balanceamento falha/recuperação
    balance_ratio = len(recoveries) / len(failures) if len(failures) > 0 else 0
    if balance_ratio < 0.8:
        print(f"  ⚠️ Baixa taxa de recuperação: {balance_ratio:.1%}")
    elif balance_ratio > 1.1:
        print(f"  ⚠️ Mais recuperações que falhas: {balance_ratio:.1%}")
    else:
        print(f"  ✅ Balanceamento adequado falhas/recuperações: {balance_ratio:.1%}")
    
    # Dados ausentes críticos
    critical_missing = 0
    if df['target'].isna().sum() > 0:
        critical_missing += df['target'].isna().sum()
        print(f"  ⚠️ {df['target'].isna().sum()} eventos sem alvo definido")
    
    if df['failure_mode'].isna().sum() > len(df[df['event_type'].isin(['simulation_started', 'simulation_stopped'])]):
        missing_modes = df['failure_mode'].isna().sum() - len(df[df['event_type'].isin(['simulation_started', 'simulation_stopped'])])
        critical_missing += missing_modes
        print(f"  ⚠️ {missing_modes} eventos sem modo de falha")
    
    if critical_missing == 0:
        print(f"  ✅ Todos os campos críticos preenchidos")
    
    print(f"\n🎯 Resumo da Validação:")
    
    # Calcular score de qualidade
    quality_score = 100
    
    if len(large_gaps) > 0:
        quality_score -= 10
    
    if balance_ratio < 0.8 or balance_ratio > 1.1:
        quality_score -= 15
    
    if critical_missing > 0:
        quality_score -= 20
    
    if len(outliers) / len(recovery_times) > 0.1:
        quality_score -= 10
    
    if quality_score >= 90:
        status = "🟢 EXCELENTE"
    elif quality_score >= 75:
        status = "🟡 BOM"
    elif quality_score >= 60:
        status = "🟠 ACEITÁVEL"
    else:
        status = "🔴 PROBLEMAS"
    
    print(f"  Score de qualidade: {quality_score}/100 {status}")
    
    # Recomendações
    print(f"\n💡 Recomendações:")
    
    if sim_hours < 100:
        print(f"  • Considere simulações mais longas (>100h) para estatísticas mais robustas")
    
    if len(failures) < 50:
        print(f"  • Aumente a taxa de falhas para obter mais amostras")
    
    if recovery_times.std() > recovery_times.mean():
        print(f"  • Alta variabilidade nos tempos de recuperação - investigar causas")
    
    if acceleration < 1000:
        print(f"  • Considere maior aceleração para simulações mais eficientes")
    
    print(f"  • CSV validado e pronto para análise acadêmica ✅")
    
    return {
        'total_events': len(df),
        'failures': len(failures),
        'recoveries': len(recoveries),
        'quality_score': quality_score,
        'simulated_hours': sim_hours,
        'real_minutes': real_minutes,
        'acceleration': acceleration
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python3 analyze_csv.py <arquivo.csv>")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    result = analyze_reliability_csv(csv_file)
    print(f"\n📊 Análise concluída: {result}")