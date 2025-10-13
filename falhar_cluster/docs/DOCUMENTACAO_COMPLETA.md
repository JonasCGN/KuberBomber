# 🔥 Documentação Completa - Kubernetes Chaos Engineering Framework

## 📋 Visão Geral

Este framework de Chaos Engineering para Kubernetes oferece capacidades completas de injeção de falhas para análise de confiabilidade e simulação de cenários de falha em clusters Kubernetes. É especialmente projetado para pesquisa acadêmica e análise de MTTF/MTBF/MTTR.

## 🚀 Início Rápido

### Pré-requisitos
- Python 3.8+
- Cluster Kubernetes funcional
- kubectl configurado
- Acesso ao cluster

### Instalação das Dependências
```bash
pip install -r requirements.txt
```

### Verificação de Ambiente
```bash
python3 main.py --help
```

## 📊 Comandos Principais

### 1. Gerenciamento de Pods

#### Listar Pods Disponíveis
```bash
python3 main.py pod list
```
**Saída esperada:**
```
                Available Pods in 'default'                
╭─────────────────────────────┬───────────────────────────┬─────────────╮
│ Pod Name                    │ Node                      │ Status      │
├─────────────────────────────┼───────────────────────────┼─────────────┤
│ bar-app-6b876c8456-7x2mj    │ local-k8s-worker2         │ ✅ Running  │
│ foo-app-7d978b489-sx29d     │ local-k8s-worker          │ ✅ Running  │
│ test-app-76b795564c-8kwv6   │ local-k8s-worker2         │ ✅ Running  │
│ test-app-76b795564c-j7wzp   │ local-k8s-worker          │ ✅ Running  │
│ test-app-76b795564c-l8gtx   │ local-k8s-worker2         │ ✅ Running  │
╰─────────────────────────────┴───────────────────────────┴─────────────╯
```

#### Matar Pod Específico
```bash
python3 main.py pod kill <nome-do-pod>
```

#### Reiniciar Pod
```bash
python3 main.py pod restart <nome-do-pod>
```

#### Consumir CPU do Pod
```bash
python3 main.py pod cpu-stress <nome-do-pod> --cpu-percent 80 --duration 60
```

#### Consumir Memória do Pod
```bash
python3 main.py pod memory-stress <nome-do-pod> --memory-mb 512 --duration 60
```

### 2. Gerenciamento de Nodes

#### Listar Nodes Disponíveis
```bash
python3 main.py node list
```
**Saída esperada:**
```
                Available Nodes                
╭─────────────────────────┬──────────┬────────╮
│ Node Name               │ Status   │ Role   │
├─────────────────────────┼──────────┼────────┤
│ local-k8s-control-plane │ ✅ Ready │ Master │
│ local-k8s-worker        │ ✅ Ready │ Worker │
│ local-k8s-worker2       │ ✅ Ready │ Worker │
╰─────────────────────────┴──────────┴────────╯
```

#### Drenar Node
```bash
python3 main.py node drain <nome-do-node>
```

### 3. Simulação de Confiabilidade

#### Teste Rápido de Confiabilidade (RECOMENDADO)
```bash
python3 main.py reliability test
```
**Características:**
- Duração: 500 horas simuladas
- Aceleração: 1000x (5 min reais = ~83h simuladas)
- Falhas automáticas: pods e nodes
- Métricas MTTF/MTBF/MTTR calculadas
- CSV automático gerado

**Saída esperada:**
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

#### Simulação Customizada
```bash
python3 main.py reliability start --duration 24 --acceleration 100 --csv-path minha_simulacao.csv
```

**Parâmetros:**
- `--duration`: Duração em horas reais
- `--acceleration`: Fator de aceleração temporal
- `--csv-path`: Arquivo CSV de saída
- `--namespace`: Namespace específico

#### Análise de Resultados CSV
```bash
python3 main.py reliability analyze minha_simulacao.csv
```

### 4. Métricas e Monitoramento

#### Gerar Relatório de Métricas
```bash
python3 main.py metrics report
```
**Saída:**
```
✅ Report generated: metrics_report_all_20251006_194419.json
```

#### Visualizações
```bash
python3 main.py metrics visualize
```

### 5. Cenários Pré-definidos

#### Executar Cenário de Chaos
```bash
python3 main.py scenario run <nome-do-cenario>
```

### 6. Configuração

#### Mostrar Configuração Atual
```bash
python3 main.py config show
```

#### Definir Configuração
```bash
python3 main.py config set <chave> <valor>
```

## 🔬 Análise de Confiabilidade para Pesquisa Acadêmica

### Métricas Calculadas

1. **MTTF (Mean Time To Failure)**: Tempo médio até falha
2. **MTBF (Mean Time Between Failures)**: Tempo médio entre falhas  
3. **MTTR (Mean Time To Recovery)**: Tempo médio de recuperação

### Aceleração Temporal

O framework implementa aceleração temporal para pesquisa:
- **Fator 1000x**: 1 hora real = 1000 horas simuladas
- **Logs detalhados**: Todas as falhas registradas com timestamps
- **CSV estruturado**: Formato adequado para análise estatística

### Tipos de Falhas Simuladas

1. **Pod Kill**: Terminação abrupta de pods
2. **Node Reboot**: Reinicialização de nodes (simulada)
3. **Process Kill**: Terminação de processos específicos
4. **Resource Stress**: Consumo intensivo de CPU/Memória

## 📁 Estrutura de Arquivos Gerados

### Relatórios CSV
```
reliability_test_standard_TIMESTAMP.csv
├── timestamp: Momento da falha
├── failure_type: Tipo de falha (pod_kill, node_reboot)
├── target: Alvo da falha (nome do pod/node)
├── success: Sucesso da injeção (true/false)
├── recovery_time: Tempo de recuperação
└── simulated_time: Tempo simulado
```

### Relatórios JSON
```
metrics_report_all_TIMESTAMP.json
├── summary: Resumo geral
├── failures: Lista de falhas
├── statistics: Estatísticas calculadas
└── recommendations: Recomendações
```

## 🛠️ Resolução de Problemas

### Erro: "No such command 'monitoring'"
✅ **Solução**: Use `python3 main.py monitor` (sem 'ing')

### Erro: "Failed to reboot node"
✅ **Normal**: O framework simula reinicializações sem afetar o cluster real

### Erro: "ModuleNotFoundError"
✅ **Solução**: Execute `pip install -r requirements.txt`

### Cluster não acessível
✅ **Verificação**: 
```bash
kubectl get nodes
kubectl get pods
```

## 📊 Exemplo de Uso Completo

### Cenário: Análise de Confiabilidade de 24h

```bash
# 1. Verificar cluster
python3 main.py pod list
python3 main.py node list

# 2. Executar simulação
python3 main.py reliability start --duration 1 --acceleration 24 --csv-path analise_24h.csv

# 3. Analisar resultados
python3 main.py reliability analyze analise_24h.csv

# 4. Gerar relatório
python3 main.py metrics report

# 5. Visualizações
python3 main.py metrics visualize
```

## 🎯 Casos de Uso Acadêmicos

### 1. Análise de Disponibilidade
- Execute simulações de 500h+ com aceleração 1000x
- Colete métricas MTTF/MTBF/MTTR
- Analise padrões de falha

### 2. Comparação de Arquiteturas
- Execute cenários em diferentes configurações
- Compare métricas entre setups
- Valide hipóteses de confiabilidade

### 3. Testes de Resiliência
- Injete falhas específicas
- Meça tempos de recuperação
- Avalie impacto de diferentes tipos de falha

## 📚 Referências e Próximos Passos

### Melhorias Futuras
- [ ] Integração com Prometheus
- [ ] Dashboard em tempo real
- [ ] Mais tipos de falha
- [ ] Análise preditiva

### Arquitetura
```
src/
├── core/           # Lógica principal
├── injectors/      # Injetores de falha
├── monitoring/     # Monitoramento e métricas
├── reliability/    # Simulação de confiabilidade
└── cli/           # Interface de linha de comando
```

---

**🔥 Framework 100% Funcional** - Pronto para uso em pesquisa acadêmica e análise de confiabilidade de sistemas Kubernetes.