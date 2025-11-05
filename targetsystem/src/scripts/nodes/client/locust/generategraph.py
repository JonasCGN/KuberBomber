import traceback
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import os
import argparse

def clean_column(col: pd.Series) -> pd.Series:
    """
    Remove units/symbols (%, m, etc.) and convert to float when column is object.
    Otherwise, coerce to numeric.
    """
    if col.dtype == "object":
        return col.astype(str).str.replace(r"[^\d\.\-eE+]", "", regex=True).replace({"": None}).astype(float)
    return pd.to_numeric(col, errors="coerce")

def clean_and_plot_csv(file_path: str, ignore_begin_plot_time: float = 0.0):
    """
    Reads a CSV file, cleans the data, and plots each numeric column against
    time since start (seconds). Optionally ignores the first N seconds
    (ignore_begin_plot_time) and re-bases X to start at 0 after the cut.
    Saves graphs in the 'graphs' directory.
    """
    try:
        # Load the CSV file
        df = pd.read_csv(file_path)

        # Strip column names and print available columns for debugging
        df.columns = df.columns.str.strip()
        print("Columns in the DataFrame:", df.columns)

        # Ensure the DateTime column exists and parse it
        if 'DateTime' not in df.columns:
            print("The file must have a 'DateTime' column.")
            return
        df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')

        # Drop rows with invalid DateTime values and index by DateTime
        df.dropna(subset=['DateTime'], inplace=True)
        df.set_index('DateTime', inplace=True)

        # Clean numeric-like columns
        df = df.apply(clean_column)

        # Drop completely empty columns
        df.dropna(axis=1, how='all', inplace=True)

        # Select only numeric columns
        numeric_df = df.select_dtypes(include=['number']).copy()
        if numeric_df.empty:
            print("No numeric columns to plot.")
            return

        # === X axis as time since start (seconds) ===
        # 1) Ensure chronological order to define a real "start"
        numeric_df = numeric_df.sort_index()

        # 2) Baseline at the earliest timestamp (idx.min())
        idx = numeric_df.index
        delta = (idx - idx.min())  # TimedeltaIndex
        # Make it a Series aligned to the index (not an Index)
        x_seconds = pd.Series(delta.total_seconds(), index=idx, name="t")

        # --- IGNORE BEGIN PLOT TIME: remove the FIRST 'cut' seconds ---
        cut = float(ignore_begin_plot_time or 0.0)
        if cut > 0:
            mask = x_seconds >= cut
            numeric_df_plot = numeric_df.loc[mask].copy()
            if numeric_df_plot.empty:
                print("All points were filtered out by ignore_begin_plot_time.")
                return
            # Rebase X so it starts exactly at 0 after the requested cut
            x_plot = x_seconds.loc[mask] - cut
        else:
            numeric_df_plot = numeric_df
            x_plot = x_seconds

        # Create a directory to save the graphs
        output_dir = 'graphs'
        os.makedirs(output_dir, exist_ok=True)

        # Plot each column (Y) versus elapsed seconds (X)
        for column in numeric_df_plot.columns:
            plt.figure()
            plt.plot(x_plot.values, numeric_df_plot[column].values, label=column)

            ax = plt.gca()
            # X axis visible, start at zero, integer ticks
            ax.set_xlim(left=0)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))

            plt.xlabel('Time since start (s)')
            plt.ylabel(column)
            title_suffix = f" [ignored {cut}s]" if cut > 0 else ""
            plt.title(f"Line Graph of {column}{title_suffix}")
            plt.legend()
            plt.grid(True)
            plt.tight_layout()

            safe_col = "".join(ch if ch.isalnum() else "_" for ch in column).strip("_")
            plt.savefig(os.path.join(output_dir, f"{safe_col}_line_graph.png"), dpi=120)
            plt.close()

        print(f"Graphs have been created and saved in the '{output_dir}' directory.")

    except Exception as e:
        print("An error occurred:")
        traceback.print_exc()

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Generate line graphs from a CSV file (X = seconds since start).")
    parser.add_argument("file", type=str, help="Path to the CSV file")
    parser.add_argument(
        "--ignore-begin-plot-time",
        type=float,
        default=0.0,
        help="Seconds to ignore at the beginning of the plot (default: 0.0)."
    )
    args = parser.parse_args()

    # Call the function with the provided file name
    clean_and_plot_csv(args.file, ignore_begin_plot_time=args.ignore_begin_plot_time)
