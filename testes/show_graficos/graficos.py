import pandas as pd
import os
import glob
# matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np

# Se True, gera o ZIP dos gráficos
zipar = False

# 1. Buscar todos os interactions.csv no database
base_dir = r'show_graficos/database'
output_dir = r'show_graficos/plots'
os.makedirs(output_dir, exist_ok=True)
csv_files = glob.glob(os.path.join(base_dir, '**/statistics.csv'), recursive=True)

saved_plots = []
disponibilidade = []

for arquivo_csv in csv_files:
    arquivo = pd.read_csv(arquivo_csv)
    print(arquivo)
    if arquivo.iat[2,0] != "current_time_hours":
        ativo = float(str(arquivo.iat[1,1])) - float(str(arquivo.iat[4,1]));
        total_duration = float(str(arquivo.iat[1,1]))
        disponibilidade.append(ativo / total_duration);
        
if len(disponibilidade) == 0:
    print("Nenhum dado em 'disponibilidade' para plotar.")
else:
    arr = np.array(disponibilidade, dtype=float)
    media = np.mean(arr)
    desvio = np.std(arr)
    print("Média do Tempo de Disponiliblidade: ", media)
    print("Desvio do Tempo de Disponiliblidade: ", desvio)

    plt.figure(figsize=(8,4))
    plt.plot(arr, marker='o', linestyle='-', label='Disponibilidade')
        # mostrar valores acima dos pontos
    for i, v in enumerate(arr):
        plt.text(i, v, f"{v:.7f}", ha='center', va='bottom', fontsize=8)
    plt.xlabel('Amostra')
    plt.ylabel('Disponibilidade (fração)')
    plt.title('Tempo de Disponibilidade por amostra')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    out_file = os.path.join(output_dir, 'disponibilidade.png')
    plt.savefig(out_file)
    print(f'Gráfico salvo em: {out_file}')
    plt.show()