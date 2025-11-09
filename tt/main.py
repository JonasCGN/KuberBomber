import os
import glob
import pandas as pd

metrics = glob.glob(os.path.join(os.getcwd(), "**/metrics.csv"), recursive=True)

print("Métricas coletadas:")
for metric_file in metrics:
    print(f" - {metric_file}")
    df = pd.read_csv(metric_file)
    print(df.head())
    # Print MTTR metrics if columns exist
    for col, label, emoji in [
        ("mttr_mean", "MTTR Médio", "⏱️"),
        ("mttr_median", "MTTR Mediano", "📊"),
        ("mttr_min", "MTTR Mínimo", "📉"),
        ("mttr_max", "MTTR Máximo", "📈"),
        ("mttr_std_dev", "Desvio Padrão", "📏"),
    ]:
        if col in df.columns:
            print(f"{emoji} {label}: {df.at[0, col]:.2f}s")