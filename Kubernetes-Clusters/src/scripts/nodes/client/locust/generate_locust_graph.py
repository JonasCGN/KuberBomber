import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

def compute_x_axis_seconds(df: pd.DataFrame) -> pd.Series:
    """
    Retorna eixo X em segundos desde t0.
    Preferência: soma cumulativa de 'Generated Wait Time (s)'.
    Fallback: delta de 'Request Created At' (s).
    Último fallback: índice (0..N-1).
    """
    # 1) Soma cumulativa do tempo de espera gerado
    if "Generated Wait Time (s)" in df.columns:
        try:
            waits = pd.to_numeric(df["Generated Wait Time (s)"], errors="coerce").fillna(0).clip(lower=0)
            x = waits.cumsum()
            return x
        except Exception:
            pass

    # 2) Diferença de timestamp desde o primeiro
    if "Request Created At" in df.columns:
        try:
            ts = pd.to_datetime(df["Request Created At"], errors="coerce")
            if ts.notna().any():
                t0 = ts.iloc[0]
                x = (ts - t0).dt.total_seconds().fillna(0)
                return x
        except Exception:
            pass

    # 3) Índice
    return pd.Series(range(len(df)), dtype="float64")

def clean_numeric(col: pd.Series) -> pd.Series:
    """
    Remove caracteres não numéricos típicos (%, unidades) e converte para float.
    Só aplica se dtype == object.
    """
    if col.dtype == "object":
        return col.astype(str).str.replace(r"[^\d\.\-eE+]", "", regex=True).replace({"": None}).astype(float)
    return pd.to_numeric(col, errors="coerce")

def clean_and_plot_csv(
        file_path: str,
        outdir: str = "graphs",
        label_filter: str = None,
        prefix: str = "",
        ignore_begin_plot_time: float = 0.0,
):
    """
    Lê o CSV, prepara eixo X (tempo desde o início em segundos), e plota
    cada métrica média em gráficos separados no diretório 'graphs'.

    Exemplo:
      python plot_locust_metrics.py response_times.csv --ignore-begin-plot-time 120
      python plot_locust_metrics.py response_times.csv --label "Conf A" --outdir ./graphs_confA --ignore-begin-plot-time 60
    """
    # Carrega CSV
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    print("Columns in the DataFrame:", list(df.columns))

    # Converte timestamp se presente e ordena temporalmente
    if "Request Created At" in df.columns:
        df["Request Created At"] = pd.to_datetime(df["Request Created At"], errors="coerce")
        df = df.sort_values("Request Created At").reset_index(drop=True)

    # Filtro opcional por Label
    if label_filter is not None and "Label" in df.columns:
        df = df[df["Label"] == label_filter].reset_index(drop=True)

    if df.empty:
        print("No data to plot after applying filters.")
        return

    # Limpa colunas potencialmente textuais para numéricas (todas em segundos)
    for col in [
        "Generated Wait Time (s)",
        "MA Arrival Rate (req/s)",
        "MA Throughput (req/s)",
        "MA Response Time (s)",     # <-- ajustado
        "Mean Response Time (s)",   # <-- ajustado
        "Moving Avg Window (s)",
        "Response Time (s)",        # robustez (ex.: arquivo de erros)
    ]:
        if col in df.columns:
            df[col] = clean_numeric(df[col])

    # Eixo X base: tempo desde o início (s)
    x_full = compute_x_axis_seconds(df)

    # Ignorar primeiros N segundos do gráfico, se configurado
    if ignore_begin_plot_time and ignore_begin_plot_time > 0:
        mask = x_full >= ignore_begin_plot_time
        df_plot = df.loc[mask].copy()
        x_plot = x_full.loc[mask]
        if not df_plot.empty:
            x_plot = x_plot - x_plot.iloc[0]  # rebase para começar em 0
        else:
            print("All points were filtered out by ignore_begin_plot_time.")
            return
    else:
        df_plot = df
        x_plot = x_full

    # Descobre janela da média para título
    ma_window = None
    if "Moving Avg Window (s)" in df_plot.columns and not df_plot["Moving Avg Window (s)"].isna().all():
        try:
            ma_window = int(df_plot["Moving Avg Window (s)"].mode(dropna=True)[0])
        except Exception:
            ma_window = None

    # Define o rótulo da legenda com base na coluna Label
    legend_label = None
    if "Label" in df_plot.columns:
        if label_filter:
            legend_label = label_filter
        else:
            try:
                legend_label = df_plot["Label"].mode(dropna=True)[0]
            except Exception:
                legend_label = "Label"
    else:
        legend_label = "Series"

    window_suffix = f" (Window={ma_window}s)" if ma_window is not None else ""
    ignore_suffix = f" [ignored {ignore_begin_plot_time}s]" if ignore_begin_plot_time and ignore_begin_plot_time > 0 else ""

    # Métricas a plotar (todas em segundos, exceto taxas em req/s)
    metrics = [
        ("MA Arrival Rate (req/s)", "MA Arrival Rate (req/s)"),
        ("MA Throughput (req/s)", "MA Throughput (req/s)"),
        ("MA Response Time (s)", "MA Response Time (s)"),
        ("Mean Response Time (s)", "Mean Response Time (s)"),
    ]

    os.makedirs(outdir, exist_ok=True)

    for col, ylabel in metrics:
        if col in df_plot.columns and not df_plot[col].dropna().empty:
            y = df_plot[col]

            plt.figure()
            plt.plot(x_plot, y, label=legend_label)

            ax = plt.gca()
            ax.set_xlim(left=0)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))

            ax.set_xlabel("Time since start (s)")
            ax.set_ylabel(ylabel)
            ax.set_title(f"Line Graph of {col}{window_suffix}{ignore_suffix}")
            plt.legend()
            plt.grid(True)
            plt.tight_layout()

            # Nome do arquivo
            safe_col = "".join(ch if ch.isalnum() else "_" for ch in col).strip("_").lower()
            fname = f"{prefix}{safe_col}"
            if legend_label and legend_label != "Series":
                safe_lab = "".join(ch if ch.isalnum() else "_" for ch in str(legend_label)).strip("_").lower()
                fname += f"_{safe_lab}"
            outpath = os.path.join(outdir, f"{fname}_line_graph.png")

            plt.savefig(outpath, dpi=120)
            plt.close()
            print(f"Saved: {outpath}")
        else:
            print(f"Column not found or empty after filtering, skipping: {col}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate line graphs from Locust CSV (time axis starts at 0s).")
    parser.add_argument("file", type=str, help="Path to the CSV file (e.g., response_times.csv)")
    parser.add_argument("--outdir", type=str, default="graphs", help="Output directory for graphs")
    parser.add_argument("--label", type=str, default=None, help="Optional Label filter (exact match)")
    parser.add_argument("--prefix", type=str, default="", help="Optional output filename prefix")
    parser.add_argument(
        "--ignore-begin-plot-time",
        type=float,
        default=0.0,
        help="Seconds to ignore at the beginning of the plot (default: 0).",
    )
    args = parser.parse_args()

    IGNORE_BEGIN_PLOT_TIME = args.ignore_begin_plot_time

    clean_and_plot_csv(
        file_path=args.file,
        outdir=args.outdir,
        label_filter=args.label,
        prefix=args.prefix,
        ignore_begin_plot_time=IGNORE_BEGIN_PLOT_TIME,
    )
