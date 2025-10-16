import pandas as pd

import matplotlib
matplotlib.use('TkAgg')  # ou 'Qt5Agg'
import matplotlib.pyplot as plt

# 1. Nome do arquivo CSV (mude se tiver outro nome)
arquivo_csv = r'/home/jonascgn/Programas_Curso/1_Artigo/show_graficos/database/pod/realtime_reliability_test_pod_kill_processes_20251015_180733.csv'

# 2. Ler o arquivo CSV
df = pd.read_csv(arquivo_csv)

# 3. Ignorar a linha RESUMO (transforma em número e remove os que não são)
df = df[pd.to_numeric(df['iteration'], errors='coerce').notnull()]
df['iteration'] = df['iteration'].astype(int)

# 4. Plotar gráfico de linha
plt.figure(figsize=(12, 6))
plt.plot(df['iteration'], df['recovery_time_seconds'], marker='o', linestyle='-', color='b')

# 5. Personalizar o gráfico
plt.title('Tempo de Recuperação do POD por Iteração', fontsize=16)
plt.xlabel('Iteração', fontsize=12)
plt.ylabel('Tempo de Recuperação (s)', fontsize=12)
plt.grid(True, linestyle='--', alpha=0.5)
plt.xticks(df['iteration'])  # mostra todas as iterações no eixo X
plt.tight_layout()

# 6. Mostrar o gráfico
plt.show()
