#!/bin/bash
# Script para monitorar falhas em tempo real

echo "🔍 Monitoring Kubernetes cluster for chaos failures..."
echo "Press Ctrl+C to stop"
echo ""

# Função para mostrar timestamp
timestamp() {
  date '+%H:%M:%S'
}

# Monitor principal
while true; do
  clear
  echo "$(timestamp) - Cluster Status Monitoring"
  echo "========================================"
  
  echo ""
  echo "📊 PODS STATUS:"
  kubectl get pods --no-headers | while read line; do
    name=$(echo $line | awk '{print $1}')
    status=$(echo $line | awk '{print $3}')
    restarts=$(echo $line | awk '{print $4}')
    age=$(echo $line | awk '{print $5}')
    
    if [[ $restarts -gt 0 ]]; then
      echo "🔄 $name: $status (Restarts: $restarts, Age: $age)"
    else
      echo "✅ $name: $status (Age: $age)"
    fi
  done
  
  echo ""
  echo "🖥️  NODES STATUS:"
  kubectl get nodes --no-headers | while read line; do
    name=$(echo $line | awk '{print $1}')
    status=$(echo $line | awk '{print $2}')
    age=$(echo $line | awk '{print $5}')
    
    if [[ $status == "Ready" ]]; then
      echo "✅ $name: $status (Age: $age)"
    else
      echo "❌ $name: $status (Age: $age)"
    fi
  done
  
  echo ""
  echo "📋 RECENT EVENTS (last 5):"
  kubectl get events --sort-by='.lastTimestamp' | tail -5 | cut -c1-100
  
  sleep 3
done