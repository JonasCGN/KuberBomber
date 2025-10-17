
import pandas as pd
import matplotlib
import os
import glob
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

# 1. Buscar todos os interactions.csv no database
base_dir = r'show_graficos/database'
csv_files = glob.glob(os.path.join(base_dir, '**/interactions.csv'), recursive=True)

for arquivo_csv in csv_files:
    # Extrair componente e método de falha do caminho
    # Exemplo: .../database/control_plane/kill_kube_scheduler/20251016_112014/interactions.csv
    partes = arquivo_csv.split(os.sep)
    # Esperado: .../<database>/<componente>/<metodo>/<timestamp>/interactions.csv
    try:
        idx = partes.index('database')
        componente = partes[idx+1] if len(partes) > idx+1 else 'unknown'
        metodo = partes[idx+2] if len(partes) > idx+2 else 'unknown'
    except ValueError:
        componente = 'unknown'
        metodo = 'unknown'

    print(f"\nProcessando: {componente} - {metodo} - {arquivo_csv}")
    df = pd.read_csv(arquivo_csv)
    # Ignorar a linha RESUMO (transforma em número e remove os que não são)
    df = df[pd.to_numeric(df['iteration'], errors='coerce').notnull()]
    df['iteration'] = df['iteration'].astype(int)

    plt.figure(figsize=(12, 6))
    plt.plot(df['iteration'], df['recovery_time_seconds'], marker='o', linestyle='-', color='b')
    plt.title(f'Tempo de Recuperação por Iteração\nComponente: {componente} | Método: {metodo}', fontsize=16)
    plt.xlabel('Iteração', fontsize=12)
    plt.ylabel('Tempo de Recuperação (s)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.xticks(df['iteration'])
    plt.tight_layout()
    plt.show()
