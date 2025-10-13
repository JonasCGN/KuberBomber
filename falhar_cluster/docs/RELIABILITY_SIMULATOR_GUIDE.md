# Simulador de Confiabilidade para Pesquisa Acadêmica

## 📖 Visão Geral

O **Simulador de Confiabilidade** é um módulo especializado do framework de Chaos Engineering projetado especificamente para análise acadêmica e pesquisa científica. Ele implementa simulações aceleradas com métricas padrão da indústria **MTTF**, **MTBF** e **MTTR** para avaliar a confiabilidade de clusters Kubernetes.

### 🎯 Objetivo Acadêmico

- **Análise de Artigos**: Coleta de dados para publicações científicas
- **Simulação Temporal**: Compressão de tempo (1h real = 10.000h simuladas)
- **Métricas Padronizadas**: MTTF, MTBF, MTTR conforme literatura
- **Logging Detalhado**: CSV estruturado para análise estatística
- **Reproducibilidade**: Configurações controláveis e determinísticas

## 🔬 Métricas Implementadas

### **MTTF - Mean Time To Failure**
- **Definição**: Tempo médio até a próxima falha
- **Unidade**: Horas
- **Cálculo**: Média dos intervalos entre falhas consecutivas
- **Uso no Artigo**: Previsibilidade de falhas do sistema

### **MTBF - Mean Time Between Failures**
- **Definição**: Tempo médio entre falhas (incluindo recuperação)
- **Unidade**: Horas  
- **Cálculo**: Tempo total de operação ÷ número de falhas
- **Uso no Artigo**: Confiabilidade geral do sistema

### **MTTR - Mean Time To Recovery**
- **Definição**: Tempo médio para recuperação após falha
- **Unidade**: Segundos
- **Cálculo**: Média dos tempos de recuperação individuais
- **Uso no Artigo**: Resiliência e capacidade de auto-recuperação

## ⚡ Escala Temporal Acelerada

### Conceito
O simulador implementa **compressão temporal** para simular longos períodos operacionais em tempo reduzido:

```
1 hora real = 10.000 horas simuladas (padrão)
6 minutos reais = 1.000 horas simuladas
1 minuto real = 166 horas simuladas
```

### Configurações Disponíveis
- **Aceleração 1000x**: Para testes rápidos
- **Aceleração 5000x**: Para simulações padrão  
- **Aceleração 10000x**: Para análises estendidas
- **Aceleração customizada**: Qualquer valor positivo

## 🛠️ Tipos de Falha Específicos

### **POD_KILL**: Kill de Aplicação
- **Método**: `kill -9 1` (PID 1 do container)
- **Comportamento**: Mata processo principal sem deletar pod
- **Recuperação**: Kubernetes reinicia automaticamente
- **Realismo**: Simula falhas de software/aplicação

### **NODE_REBOOT**: Reinicialização de Nó  
- **Método**: Reboot completo da instância
- **Comportamento**: Nó fica indisponível temporariamente
- **Recuperação**: Boot do sistema + rejoining cluster
- **Realismo**: Simula falhas de hardware/infraestrutura

## 📊 Estrutura do Log CSV

O simulador gera logs CSV estruturados para análise acadêmica:

```csv
timestamp,simulation_time_hours,real_time_seconds,event_type,failure_mode,target,target_type,failure_id,start_time,end_time,duration_seconds,mttf_hours,mtbf_hours,mttr_seconds,next_failure_in_hours,cluster_health_before,cluster_health_after,notes
```

### Eventos Registrados
- **simulation_started**: Início da simulação
- **failure_initiated**: Falha foi injetada
- **recovery_completed**: Sistema se recuperou
- **simulation_stopped**: Fim da simulação

### Campos Principais
- **simulation_time_hours**: Tempo na escala acelerada
- **real_time_seconds**: Tempo real decorrido
- **duration_seconds**: Tempo de recuperação específico
- **mttf_hours/mtbf_hours/mttr_seconds**: Métricas calculadas
- **cluster_health_before/after**: Score de saúde do cluster

## 🚀 Guia de Uso

### 1. Instalação e Dependências

```bash
# Navegue para o diretório do framework
cd falhar_cluster/

# Instale dependências
pip install -r requirements.txt

# Verifique conectividade Kubernetes
kubectl get nodes
```

### 2. Execução Básica

```bash
# Teste rápido (3 minutos reais)
python chaos_cli.py reliability test --preset quick

# Simulação padrão (6 minutos reais)  
python chaos_cli.py reliability test --preset standard

# Simulação estendida (15 minutos reais)
python chaos_cli.py reliability test --preset extended
```

### 3. Simulação Personalizada

```bash
# Simulação de 1 hora real com aceleração 10000x
python chaos_cli.py reliability start \
    --duration 1.0 \
    --acceleration 10000.0 \
    --csv-path minha_simulacao.csv \
    --namespace default
```

### 4. Análise de Resultados

```bash
# Análise estatística dos dados CSV
python chaos_cli.py reliability analyze \
    --csv-path minha_simulacao.csv \
    --output analise_resultados.json
```

## 📈 Exemplo de Uso para Artigo

### Cenário: Análise de Confiabilidade de 1 Ano

```bash
# Simula 1 ano (8760h) em 52 minutos reais
python chaos_cli.py reliability start \
    --duration 0.87 \
    --acceleration 10000.0 \
    --csv-path estudo_anual.csv

# Analisa resultados
python chaos_cli.py reliability analyze \
    --csv-path estudo_anual.csv \
    --output metricas_anuais.json
```

### Dados Obtidos
- **MTTF**: Tempo médio entre falhas (ex: 45.2 horas)
- **MTBF**: Intervalo médio incluindo recuperação (ex: 48.7 horas)  
- **MTTR**: Tempo médio de recuperação (ex: 180 segundos)
- **Disponibilidade**: Percentual de uptime (ex: 99.85%)
- **Taxa de Falha**: Falhas por hora (ex: 0.022 falhas/h)

## 📋 Interpretação Acadêmica

### Para Artigos Científicos

**Confiabilidade do Sistema**:
```
R(t) = e^(-λt)
onde λ = 1/MTTF
```

**Disponibilidade**:
```
A = MTBF / (MTBF + MTTR)
```

**Exemplo de Texto para Artigo**:
> "Os resultados experimentais mostram que o cluster apresentou MTTF de 45.2±3.1 horas, indicando alta previsibilidade de falhas. O MTTR médio de 180±25 segundos demonstra capacidade eficiente de auto-recuperação, resultando em disponibilidade de 99.85%."

### Comparação com Literatura

- **MTTF > 24h**: Sistema confiável
- **MTTR < 300s**: Recuperação rápida  
- **Disponibilidade > 99.9%**: Alta disponibilidade
- **Coeficiente de variação < 0.3**: Comportamento previsível

## 🔧 Configurações Avançadas

### Arquivo de Configuração

Crie `reliability_config.json`:

```json
{
  "simulation": {
    "time_acceleration": 10000.0,
    "base_mttf_hours": 24.0,
    "base_mttr_seconds": 300.0,
    "failure_distribution": "exponential"
  },
  "failure_modes": [
    "pod_kill",
    "node_reboot"
  ],
  "kubernetes": {
    "namespace": "default",
    "exclude_masters": true
  },
  "logging": {
    "csv_path": "reliability_simulation.csv",
    "include_health_metrics": true,
    "detailed_logging": true
  }
}
```

### Distribuições Estatísticas

- **Exponential**: Falhas aleatórias (mais comum)
- **Weibull**: Desgaste progressivo
- **Normal**: Falhas previsíveis

## 📊 Análise Estatística com Python

### Script de Análise Personalizada

```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Carrega dados da simulação
df = pd.read_csv('estudo_anual.csv')
recovery_events = df[df['event_type'] == 'recovery_completed']

# Análise MTTF
mttf_values = recovery_events['mttf_hours']
print(f"MTTF: {mttf_values.mean():.2f} ± {mttf_values.std():.2f} horas")

# Análise MTTR  
mttr_values = recovery_events['mttr_seconds']
print(f"MTTR: {mttr_values.mean():.1f} ± {mttr_values.std():.1f} segundos")

# Gráfico de evolução temporal
plt.figure(figsize=(12, 6))
plt.subplot(1, 2, 1)
plt.plot(recovery_events['simulation_time_hours'], recovery_events['mttf_hours'])
plt.title('Evolução do MTTF')
plt.xlabel('Tempo Simulado (horas)')
plt.ylabel('MTTF (horas)')

plt.subplot(1, 2, 2)
plt.plot(recovery_events['simulation_time_hours'], recovery_events['mttr_seconds'])
plt.title('Evolução do MTTR')
plt.xlabel('Tempo Simulado (horas)')
plt.ylabel('MTTR (segundos)')

plt.tight_layout()
plt.savefig('evolucao_metricas.png', dpi=300)
```

## ⚠️ Considerações Importantes

### Limitações
- **Não simula cargas reais**: Cluster pode estar idle
- **Falhas sintéticas**: Não reflete falhas naturais
- **Escala temporal**: Compressão pode não capturar todos fenômenos
- **Ambiente controlado**: Resultados podem diferir da produção

### Boas Práticas para Pesquisa
- **Execute múltiplas simulações**: Para significância estatística
- **Varie parâmetros**: Teste diferentes configurações
- **Documente configurações**: Para reproducibilidade
- **Compare com baselines**: Use dados de sistemas similares
- **Valide resultados**: Confronte com literatura existente

## 📚 Referências Recomendadas

- **Reliability Engineering**: Kececioglu, Dimitri (2002)
- **Fault Tolerance**: Jalote, Pankaj (1994)  
- **Chaos Engineering**: Principles of Chaos Engineering (2017)
- **Kubernetes Reliability**: CNCF Reliability Working Group

## 🆘 Solução de Problemas

### Erro: "No targets available"
```bash
# Verifique se há pods/nós disponíveis
kubectl get pods -n default
kubectl get nodes
```

### Erro: "Permission denied"
```bash
# Verifique permissões kubectl
kubectl auth can-i create pods
kubectl auth can-i get nodes
```

### Simulação não inicia falhas
```bash
# Verifique logs em tempo real
tail -f /var/log/chaos_simulator.log

# Execute em modo verbose
python chaos_cli.py --verbose reliability start
```

### CSV vazio ou incompleto
```bash
# Verifique se simulação teve tempo suficiente
# MTTF alto pode causar poucas falhas em simulações curtas
# Aumente duração ou diminua MTTF base
```

---

**⚡ O Simulador de Confiabilidade está pronto para suas pesquisas acadêmicas!**

Para dúvidas específicas sobre implementação ou interpretação de resultados, consulte os logs detalhados e a documentação do framework principal.