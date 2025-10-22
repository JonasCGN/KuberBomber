


import pandas as pd
import matplotlib
import os
import glob
import zipfile
# matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

# Se True, gera o ZIP dos gráficos
zipar = False

# 1. Buscar todos os interactions.csv no database
base_dir = r'show_graficos/database'
output_dir = r'show_graficos/plots'
os.makedirs(output_dir, exist_ok=True)
csv_files = glob.glob(os.path.join(base_dir, '**/interactions.csv'), recursive=True)

saved_plots = []

for arquivo_csv in csv_files:
    # Extrair componente, método e timestamp do caminho
    partes = arquivo_csv.split(os.sep)
    try:
        idx = partes.index('database')
        componente = partes[idx+1] if len(partes) > idx+1 else 'unknown'
        metodo = partes[idx+2] if len(partes) > idx+2 else 'unknown'
        timestamp = partes[idx+3] if len(partes) > idx+3 else 'notime'
    except ValueError:
        componente = 'unknown'
        metodo = 'unknown'
        timestamp = 'notime'

    print(f"\nProcessando: {componente} - {metodo} - {arquivo_csv}")
    df = pd.read_csv(arquivo_csv)

    # Ignorar a linha RESUMO (transforma em número e remove os que não são)
    df = df[pd.to_numeric(df['iteration'], errors='coerce').notnull()]
    df['iteration'] = df['iteration'].astype(int)

    df = df.iloc[10:]
    df['iteration'] = range(1, len(df) + 1)

    plt.figure(figsize=(12, 6))
    plt.plot(df['iteration'], df['recovery_time_seconds'], marker='o', linestyle='-', color='b')
    plt.title(f'Tempo de Recuperação por Iteração\nComponente: {componente} | Método: {metodo}', fontsize=16)
    plt.xlabel('Iteração', fontsize=12)
    plt.ylabel('Tempo de Recuperação (s)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.xticks(df['iteration'])
    plt.tight_layout()

    # Salvar figura
    plot_filename = f"{componente}__{metodo}__{timestamp}.png"
    plot_path = os.path.join(output_dir, plot_filename)
    plt.savefig(plot_path)
    saved_plots.append(plot_path)
    plt.close()

if zipar:
    zip_path = os.path.join(output_dir, 'graficos_plots.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for plot_file in saved_plots:
            arcname = os.path.basename(plot_file)
            zipf.write(plot_file, arcname)
    print(f"\n✅ Todos os gráficos salvos em {output_dir} e compactados em {zip_path}")
else:
    print(f"\n✅ Todos os gráficos salvos em {output_dir}")
