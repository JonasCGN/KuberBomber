import os
import pandas as pd
import numpy as np
import argparse
from scipy.stats import t
import matplotlib.pyplot as plt



def process_metrics(input_path, confidence_level):
    results = []

    # Iterate over directories in the input path
    for subdir in os.listdir(input_path):
        subdir_path = os.path.join(input_path, subdir)

        # Check if the current path is a directory
        if os.path.isdir(subdir_path):
            # Paths to the files
            response_times_path = os.path.join(subdir_path, 'response_times.csv')
            k8s_metrics_path = os.path.join(subdir_path, 'k8s_metric.csv')

            if os.path.isfile(response_times_path) and os.path.isfile(k8s_metrics_path):
                # Read both files
                response_df = pd.read_csv(response_times_path)
                k8s_df = pd.read_csv(k8s_metrics_path)

                # Filter k8s_metric data to only include the first 10 minutes
                k8s_df['DateTime'] = pd.to_datetime(k8s_df['DateTime'])
                start_time = k8s_df['DateTime'].min()
                k8s_df = k8s_df[k8s_df['DateTime'] <= start_time + pd.Timedelta(minutes=10)]

                # Calculate tp (Throughput) from response_times.csv
                tp_mean = response_df['Response Time (ms)'].count() / response_df['Generated Wait Time (s)'].sum()
                tp_ci = 0  # No CI for tp as stated

                results.append({
                    "GROUP": "Real System",
                    "METRIC": "tp",
                    "X_VALUE": float(subdir),
                    "MEAN": tp_mean,
                    "MIN_CI": tp_mean,
                    "MAX_CI": tp_mean
                })

                # Calculate service_time from response_times.csv
                response_time_mean = response_df['Response Time (ms)'].mean() / 1000  # Convert to seconds
                response_time_std = response_df['Response Time (ms)'].std(ddof=1) / 1000  # Convert to seconds
                response_time_ci = t.ppf(1 - (1 - confidence_level) / 2, len(response_df) - 1) * (
                        response_time_std / np.sqrt(len(response_df))
                )

                results.append({
                    "GROUP": "Real System",
                    "METRIC": "service_time",
                    "X_VALUE": float(subdir),
                    "MEAN": response_time_mean,
                    "MIN_CI": response_time_mean - response_time_ci,
                    "MAX_CI": response_time_mean + response_time_ci
                })

                # Calculate npodstotal from k8s_metric.csv
                k8s_df['Custom Metric'] = k8s_df['foo-app_total_pod_cpu'] + k8s_df['bar-app-hpa_current_replicas'] + 3
                npodstotal_mean = k8s_df['Custom Metric'].mean() + 3  # Add 3 to all npodstotal results
                npodstotal_std = k8s_df['Custom Metric'].std(ddof=1)
                npodstotal_ci = t.ppf(1 - (1 - confidence_level) / 2, len(k8s_df['Custom Metric']) - 1) * (
                        npodstotal_std / np.sqrt(len(k8s_df['Custom Metric']))
                )


                results.append({
                    "GROUP": "Real System",
                    "METRIC": "npodstotal",
                    "X_VALUE": float(subdir),
                    "MEAN": npodstotal_mean,
                    "MIN_CI": npodstotal_mean - npodstotal_ci,
                    "MAX_CI": npodstotal_mean + npodstotal_ci
                })

    # Create a DataFrame from results and sort by X_VALUE
    results_df = pd.DataFrame(results)
    results_df.sort_values(by="X_VALUE", inplace=True)

    # Save the formatted data to a new CSV in the input path
    output_csv = os.path.join(input_path, 'formatted_aggregated_results.csv')
    results_df.to_csv(output_csv, index=False)
    print(f"Formatted aggregated results saved to {output_csv}")

    # Generate line graphs for each metric
    for metric in results_df['METRIC'].unique():
        metric_data = results_df[results_df['METRIC'] == metric]
        plt.figure(figsize=(12, 6))
        plt.plot(metric_data['X_VALUE'], metric_data['MEAN'], label=metric, marker='o')
        plt.fill_between(
            metric_data['X_VALUE'],
            metric_data['MIN_CI'],
            metric_data['MAX_CI'],
            alpha=0.2, label=f"{metric} CI"
        )
        plt.xlabel('X_VALUE')
        plt.ylabel('Metric Value')
        plt.title(f'{metric} Metric Over X_VALUE')
        plt.legend()
        plt.grid(True)
        output_graph = os.path.join(input_path, f"{metric.lower()}_metric_graph.png")
        plt.savefig(output_graph)
        print(f"{metric} metric graph saved to {output_graph}")
        plt.close()


# Example usage:
# process_metrics("/path/to/input/directory", 0.95)


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Process response times and compute metrics with graphs.")
    parser.add_argument("input_path", type=str, help="Path to the input directory containing arrival rate folders.")
    parser.add_argument("confidence_level", type=float, help="Confidence level for confidence intervals (e.g., 0.95 for 95%).")
    args = parser.parse_args()

    # Call the function with provided arguments
    process_metrics(args.input_path, args.confidence_level)
