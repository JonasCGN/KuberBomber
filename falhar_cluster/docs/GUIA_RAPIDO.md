# 🚀 Guia de Execução Rápida - Chaos Engineering Framework

## ⚡ Start Imediato

### 1. Verificação Básica
```bash
# Verificar se está funcionando
python3 main.py --help

# Listar pods disponíveis
python3 main.py pod list

# Listar nodes disponíveis  
python3 main.py node list
```

### 2. Teste de Confiabilidade (PRINCIPAL)
```bash
# Executar simulação completa (RECOMENDADO)
python3 main.py reliability test
```
**O que acontece:**
- ⏱️ 500 horas simuladas em ~5 minutos reais
- 🎯 136+ falhas injetadas automaticamente  
- 📊 Métricas MTTF/MTBF/MTTR calculadas
- 📁 CSV gerado automaticamente

### 3. Comandos Essenciais

#### Falhas Manuais
```bash
# Matar um pod específico
python3 main.py pod kill test-app-76b795564c-8kwv6

# Drenar um node
python3 main.py node drain local-k8s-worker

# Estressar CPU (80% por 60s)
python3 main.py pod cpu-stress test-app-76b795564c-8kwv6 --cpu-percent 80 --duration 60
```

#### Análise de Resultados
```bash
# Gerar relatório de métricas
python3 main.py metrics report

# Analisar CSV específico
python3 main.py reliability analyze arquivo.csv

# Visualizações
python3 main.py metrics visualize
```

## 📊 Saídas Esperadas

### Teste de Confiabilidade
```
📊 Progresso: 500.1h simuladas, 136 falhas

📋 RESULTADOS FINAIS
==================
Total de Falhas: 136
MTTF: 3.37 horas
MTBF: 3.68 horas  
MTTR: 10.2 segundos

📁 Log CSV: reliability_test_standard_1759790248.csv
✅ Teste concluído com sucesso!
```

### Lista de Pods
```
                Available Pods in 'default'                
╭─────────────────────────────┬───────────────────────────┬─────────────╮
│ Pod Name                    │ Node                      │ Status      │
├─────────────────────────────┼───────────────────────────┼─────────────┤
│ bar-app-6b876c8456-7x2mj    │ local-k8s-worker2         │ ✅ Running  │
│ foo-app-7d978b489-sx29d     │ local-k8s-worker          │ ✅ Running  │
│ test-app-76b795564c-8kwv6   │ local-k8s-worker2         │ ✅ Running  │
╰─────────────────────────────┴───────────────────────────┴─────────────╯
```

## 🎯 Casos de Uso Rápidos

### Para Pesquisa Acadêmica
```bash
# Simulação de 24h (1 hora real)
python3 main.py reliability start --duration 1 --acceleration 24

# Simulação de 1 semana (aceleração 168x)  
python3 main.py reliability start --duration 1 --acceleration 168

# Análise customizada
python3 main.py reliability start --duration 2 --acceleration 500 --csv-path minha_pesquisa.csv
```

### Para Testes de Resiliência
```bash
# Testar recuperação de pods
python3 main.py pod kill <pod-name>

# Testar capacidade do cluster
python3 main.py node drain <node-name>

# Testar sob estresse
python3 main.py pod cpu-stress <pod-name> --cpu-percent 90 --duration 120
```

## 🔧 Resolução Rápida de Problemas

| Problema | Solução |
|----------|---------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| `No such command` | Use `python3 main.py --help` para ver comandos |
| `Failed to reboot node` | Normal - é simulação, não afeta cluster real |
| Cluster não acessível | Verificar `kubectl get nodes` |

## 📁 Arquivos Importantes

### Gerados Automaticamente
- `reliability_test_standard_*.csv` - Dados da simulação
- `metrics_report_all_*.json` - Relatório de métricas  
- `chaos_*.log` - Logs detalhados

### Estrutura do CSV
```csv
timestamp,failure_type,target,success,recovery_time,simulated_time
2025-10-06 19:38:59,pod_kill,foo-app-7d978b489-sx29d,true,10.2,125.5
2025-10-06 19:39:01,node_reboot,local-k8s-worker,false,0.0,138.9
```

---
**✅ Framework 100% Funcional e Pronto para Uso!**