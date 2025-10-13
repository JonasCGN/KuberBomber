#!/bin/bash

# Define deployments in a list
DEPLOYMENTS=("bar-app" "foo-app")

# Resolve a label selector for a deployment.
# 1) Try .spec.selector.matchLabels.app
# 2) Fallback: strip "-app" suffix (bar-app -> app=bar)
# 3) Last resort: app=<deployment name>
get_pod_selector_for_deploy() {
  local deploy="$1"
  local app_val
  app_val=$(kubectl get deploy "$deploy" -o jsonpath='{.spec.selector.matchLabels.app}' 2>/dev/null)
  if [[ -n "$app_val" ]]; then
    echo "app=${app_val}"
    return
  fi
  # try to derive from name
  local guess="${deploy%-app}"
  if [[ -n "$guess" && "$guess" != "$deploy" ]]; then
    echo "app=${guess}"
  else
    echo "app=${deploy}"
  fi
}

# Function to collect metrics and write to CSV
collect_metrics() {
  # Delay time (in seconds) passed as the first argument
  DELAY=$1

  # Output CSV file
  OUTPUT_FILE="${2}"

  # Identify all nodes in the cluster
  NODES=$(kubectl get nodes -o jsonpath="{.items[*].metadata.name}")

  # Construct CSV header
  HEADER="DateTime"
  for DEPLOYMENT in "${DEPLOYMENTS[@]}"; do
    HPA_NAME="${DEPLOYMENT}-hpa"
    HEADER+=","${DEPLOYMENT}"_replicas,"${HPA_NAME}"_current_replicas,"${HPA_NAME}"_desired_replicas,"${HPA_NAME}"_max_replicas,"${HPA_NAME}"_cpu_utilization,"${HPA_NAME}"_cpu_value"
    HEADER+=","${DEPLOYMENT}"_total_pod_cpu,"${DEPLOYMENT}"_total_pod_memory,"${DEPLOYMENT}"_running_pods"
  done
  # Aggregated columns (bar+foo)
  HEADER+=",bar_foo_running_pods,bar_foo_total_pod_cpu,bar_foo_total_pod_memory"
  # Per-node metrics
  for NODE in $NODES; do
    HEADER+=",${NODE}_cpu_usage,${NODE}_mem_usage"
  done

  # Write header to the CSV file
  echo "$HEADER" > "$OUTPUT_FILE"

  # Infinite loop to collect metrics every DELAY seconds
  while true; do
    # Current date and time
    DATETIME=$(date +"%Y-%m-%d %H:%M:%S")

    # Initialize the metrics line with the datetime
    LINE="$DATETIME"

    # Combined accumulators
    COMBINED_POD_COUNT=0
    COMBINED_TOTAL_POD_CPU=0
    COMBINED_TOTAL_POD_MEMORY=0

    # Per-deployment metrics
    for DEPLOYMENT in "${DEPLOYMENTS[@]}"; do
      HPA_NAME="${DEPLOYMENT}-hpa"

      # Deployment replicas (default 0 if missing)
      DEPLOYMENT_REPLICAS=$(kubectl get deployment "$DEPLOYMENT" -o jsonpath="{.status.replicas}" 2>/dev/null)
      DEPLOYMENT_REPLICAS=${DEPLOYMENT_REPLICAS:-0}

      # HPA metrics (zeros if HPA doesn't exist)
      if kubectl get hpa "$HPA_NAME" >/dev/null 2>&1; then
        CURRENT_REPLICAS=$(kubectl get hpa "$HPA_NAME" -o jsonpath="{.status.currentReplicas}" 2>/dev/null)
        DESIRED_REPLICAS=$(kubectl get hpa "$HPA_NAME" -o jsonpath="{.status.desiredReplicas}" 2>/dev/null)
        MAX_REPLICAS=$(kubectl get hpa "$HPA_NAME" -o jsonpath="{.spec.maxReplicas}" 2>/dev/null)
        HPA_CPU_UTILIZATION=$(kubectl get hpa "$HPA_NAME" -o jsonpath="{.status.currentMetrics[0].resource.current.averageUtilization}" 2>/dev/null)
        HPA_CPU_VALUE=$(kubectl get hpa "$HPA_NAME" -o jsonpath="{.status.currentMetrics[0].resource.current.averageValue}" 2>/dev/null)
      else
        CURRENT_REPLICAS=0
        DESIRED_REPLICAS=0
        MAX_REPLICAS=0
        HPA_CPU_UTILIZATION=0
        HPA_CPU_VALUE=0
      fi

      # Default zeros if any field empty
      CURRENT_REPLICAS=${CURRENT_REPLICAS:-0}
      DESIRED_REPLICAS=${DESIRED_REPLICAS:-0}
      MAX_REPLICAS=${MAX_REPLICAS:-0}
      HPA_CPU_UTILIZATION=${HPA_CPU_UTILIZATION:-0}
      HPA_CPU_VALUE=${HPA_CPU_VALUE:-0}

      # Totals for pods in this deployment
      TOTAL_POD_CPU=0
      TOTAL_POD_MEMORY=0
      RUNNING_POD_COUNT=0

      # Build label selector from deployment
      SELECTOR=$(get_pod_selector_for_deploy "$DEPLOYMENT")

      # List only Running pods that match the selector
      PODS=$(kubectl get pods -l "$SELECTOR" --field-selector=status.phase=Running -o jsonpath="{.items[*].metadata.name}")
      for POD in $PODS; do
        # If 'kubectl top' has no metrics, default to 0
        POD_CPU=$(kubectl top pod "$POD" --no-headers 2>/dev/null | awk '{print $2}' | sed 's/m//')
        POD_CPU=${POD_CPU:-0}
        POD_MEMORY=$(kubectl top pod "$POD" --no-headers 2>/dev/null | awk '{print $3}' | sed 's/[^0-9]*//g')
        POD_MEMORY=${POD_MEMORY:-0}

        TOTAL_POD_CPU=$((TOTAL_POD_CPU + POD_CPU))
        TOTAL_POD_MEMORY=$((TOTAL_POD_MEMORY + POD_MEMORY))
        RUNNING_POD_COUNT=$((RUNNING_POD_COUNT + 1))
      done

      # Aggregate to combined bar+foo totals
      COMBINED_POD_COUNT=$((COMBINED_POD_COUNT + RUNNING_POD_COUNT))
      COMBINED_TOTAL_POD_CPU=$((COMBINED_TOTAL_POD_CPU + TOTAL_POD_CPU))
      COMBINED_TOTAL_POD_MEMORY=$((COMBINED_TOTAL_POD_MEMORY + TOTAL_POD_MEMORY))

      # Append per-deployment metrics
      LINE+=",$DEPLOYMENT_REPLICAS,$CURRENT_REPLICAS,$DESIRED_REPLICAS,$MAX_REPLICAS,$HPA_CPU_UTILIZATION,$HPA_CPU_VALUE,$TOTAL_POD_CPU,$TOTAL_POD_MEMORY,$RUNNING_POD_COUNT"
    done

    # Append combined (bar+foo)
    LINE+=",$COMBINED_POD_COUNT,$COMBINED_TOTAL_POD_CPU,$COMBINED_TOTAL_POD_MEMORY"

    # Per-node CPU/mem usage
    for NODE in $NODES; do
      CPU_USAGE=$(kubectl top node "$NODE" --no-headers 2>/dev/null | awk '{print $3}')
      MEM_USAGE=$(kubectl top node "$NODE" --no-headers 2>/dev/null | awk '{print $5}')
      CPU_USAGE=${CPU_USAGE:-0}
      MEM_USAGE=${MEM_USAGE:-0}
      LINE+=",$CPU_USAGE,$MEM_USAGE"
    done

    # Append the collected metrics to the CSV file
    echo "$LINE" >> "$OUTPUT_FILE"

    # Wait for the specified delay time before collecting the next set of metrics
    sleep "$DELAY"
  done
}

# Call the function with a delay time (in seconds)
collect_metrics "$@"
