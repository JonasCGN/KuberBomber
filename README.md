# Kuber Bomber - Framework de Testes de Confiabilidade

O **Kuber Bomber** é um framework para testes de confiabilidade em clusters Kubernetes, com suporte tanto para ambientes locais quanto AWS EKS. O framework mede métricas como MTTR (Mean Time To Recovery), disponibilidade e resiliência do sistema através de injeção controlada de falhas.

## 🚀 Início Rápido

### 1. Configuração Inicial

#### Para Ambientes Locais (minikube, kind, k3s):
```bash
# 1. Configurar ambiente Python
python3 -m venv ~/venv/py3env
source ~/venv/py3env/bin/activate
pip install -r kuber_bomber/requirements.txt

# 2. Verificar conectividade com cluster
kubectl cluster-info
kubectl get nodes
kubectl get pods --all-namespaces
```

#### Para AWS EKS:
```bash
# 1. Configurar ambiente Python (mesmo processo)
python3 -m venv ~/venv/py3env
source ~/venv/py3env/bin/activate
pip install -r kuber_bomber/requirements.txt

# 2. Configurar credenciais AWS
aws configure
# OU configurar via IAM Role se estiver em EC2

# 3. Configurar arquivo AWS
cp kuber_bomber/configs/aws_config_exemplo.json kuber_bomber/configs/aws_config.json
# Editar aws_config.json com sua chave SSH:
{
  "ssh_key": "~/.ssh/sua-chave.pem",
  "ssh_user": "ubuntu"
}

# 4. Verificar conectividade
kubectl cluster-info
aws ec2 describe-instances --output table
```

### 2. Executar Testes

#### Comando Principal (Interface Simplificada):
```bash
cd /caminho/para/kuber_bomber
source ~/venv/py3env/bin/activate
python3 kuber_bomber/core/exemplo_uso.py
```

#### O que acontece:
1. **Interface Interativa** pergunta o contexto (Local ou AWS)
2. **Menu Principal** com 6 opções:
   - `1` - Get_Config: Descoberta básica da infraestrutura
   - `2` - Teste de disponibilidade: Verifica se sistema está funcionando
   - `3` - get_config_all: Descoberta + análise MTTR completa
   - `4` - Verificar saúde dos pods: Testa métodos Running + Curl
   - `5` - Testar métodos de recuperação: Compara diferentes métodos
   - `6` - **Executar fluxo completo (RECOMENDADO)**

#### Fluxo Recomendado:
```bash
# Executar o comando acima e seguir:
# 1. Escolher contexto: 1 (Local) ou 2 (AWS)
# 2. No menu principal, digite: 6 (Executar fluxo completo)
```

### 3. O que o Fluxo Completo Faz

O **fluxo completo** automatiza todo o processo de teste:

1. 🔍 **Descoberta Automática**
   - Identifica pods, services, nodes automaticamente
   - Mapeia arquitetura do cluster
   - Detecta aplicações em execução

2. 📊 **Análise MTTR Real**
   - Executa testes em cada componente
   - Mede tempos de recuperação reais
   - Calcula MTTR por tipo de falha

3. ✅ **Verificação de Disponibilidade**
   - Verifica saúde inicial do sistema
   - Testa conectividade dos pods
   - Valida configuração

4. 🧪 **Teste de Confiabilidade**
   - Executa injeção controlada de falhas
   - Monitora recuperação automática
   - Gera métricas de resiliência

5. 📈 **Relatórios Automáticos**
   - CSVs com dados detalhados
   - Métricas de disponibilidade
   - Análise de desempenho

## 📊 Resultados

Após a execução, você terá:

```
kuber_bomber/
├── 2025/11/24/component/           # Resultados dos testes por data
│   ├── control_plane/
│   │   └── shutdown_control_plane/
│   │       └── interactions.csv    # Dados detalhados de cada teste
│   └── worker_node/
├── reports/                        # Relatórios de disponibilidade
│   ├── availability_report.csv
│   └── mttr_analysis.csv
└── configs/
    └── config_simples_used.json    # Configuração gerada automaticamente
```

## 🔧 Comandos Manuais (Opcional)

Para usuários avançados, também é possível executar comandos específicos:

### Descoberta de Configuração:
```bash
# Descoberta básica
make generate_config        # Local
make generate_config_aws    # AWS

# Descoberta + MTTR (recomendado)
make generate_config_all     # Local  
make generate_config_all_aws # AWS
```

### Testes Específicos:
```bash
# Teste de worker node (AWS)
cd kuber_bomber
python3 reliability_tester.py --component worker_node --failure-method shutdown_worker_node --target ip-10-0-0-10 --iterations 1 --aws

# Teste de control plane (AWS)  
cd kuber_bomber
python3 reliability_tester.py --component control_plane --failure-method shutdown_control_plane --target ip-10-0-0-219 --iterations 1 --aws
```

### Simulação de Disponibilidade:
```bash
make run_simulation     # Local
make run_simulation_aws # AWS
```

## 📋 Requisitos

- **Python 3.8+** com ambiente virtual
- **kubectl** configurado e conectado ao cluster
- **Para AWS:** credenciais AWS configuradas (`aws configure`)
- **Para AWS:** chave SSH para acesso aos nodes
- **Cluster Kubernetes** em funcionamento com aplicações deployadas

## 🛠️ Estrutura do Projeto

- `kuber_bomber/core/exemplo_uso.py` - Interface principal simplificada
- `kuber_bomber/core/reliability_tester.py` - Engine de testes
- `kuber_bomber/configs/` - Configurações (geradas automaticamente)
- `makefile` - Comandos de automação
- `2025/` - Resultados organizados por data

## ⚙️ Configurações Disponíveis

O framework possui 4 arquivos de configuração na pasta `kuber_bomber/configs/`:

### 📁 **kuber_bomber/configs/**

#### **1. aws_config.json** (Para uso AWS)
```json
{
  "ssh_key": "~/.ssh/vockey.pem",
  "ssh_user": "ubuntu"
}
```
**🔧 O que você pode ajustar:**
- `ssh_key`: Caminho para sua chave SSH privada AWS
- `ssh_user`: Usuário SSH (normalmente "ubuntu" ou "ec2-user")

#### **2. aws_config_exemplo.json** (Template)
- Arquivo exemplo para copiar e personalizar
- Use: `cp aws_config_exemplo.json aws_config.json`

#### **3. config_simples_used.json** (Configuração Principal - GERADO AUTOMATICAMENTE)
```json
{
  "experiment_config": {
    "applications": {
      "bar-app-df9db64d6-bh55z": true,    # Aplicação ativa nos testes
      "foo-app-86d576dd47-5w6s2": true,   # Aplicação ativa nos testes
      "test-app-5847796ff8-fbhmk": false  # Aplicação desabilitada
    },
    "worker_node": {
      "ip-10-0-0-10": true,               # Worker node ativo
      "ip-10-0-0-80": true                # Worker node ativo
    },
    "control_plane": {
      "ip-10-0-0-219": true               # Control plane ativo
    }
  },
  "mttr_config": {                        # Tempos de recuperação MEDIDOS
    "pods": {
      "bar-app-df9db64d6-bh55z": 0.052,  # MTTR real em horas
      ...
    },
    "worker_node": {
      "ip-10-0-0-10": 1,                 # MTTR shutdown completo
      "wn_kubelet-ip-10-0-0-10": 0.003   # MTTR kill kubelet
    },
    "control_plane": {
      "cp_apiserver-ip-10-0-0-219": 0.056,  # MTTR kill apiserver
      "cp_etcd-ip-10-0-0-219": 0.055        # MTTR kill etcd
    }
  },
  "mttf_config": {                        # Tempo entre falhas (padrão)
    ...
  },
  "iterations": 15,                       # Iterações por teste
  "delay": 10,                            # Delay entre iterações (segundos)
  "duration": 1000                        # Duração da simulação
}
```

#### **4. config_simples_used_exemplo.json** (Template Completo)
- Exemplo com todos os campos possíveis
- Use como referência para entender a estrutura

### 🎛️ **O que o Usuário Pode Modificar:**

#### **Para AWS:**
```bash
# Editar credenciais SSH
nano kuber_bomber/configs/aws_config.json
```

#### **Para Configuração Principal (após primeira execução):**
```bash
# Editar configuração gerada automaticamente
nano kuber_bomber/configs/config_simples_used.json
```

**🔧 Campos que você pode ajustar:**

1. **`experiment_config`**:
   - `true/false`: Ativar/desativar componentes específicos nos testes
   - Útil para focar em componentes específicos

2. **`iterations`**: Número de iterações por teste (padrão: 15)
   - Mais iterações = dados mais precisos, mas testes mais longos
   - Recomendado: 5-30 dependendo do tempo disponível

3. **`delay`**: Intervalo entre testes em segundos (padrão: 10)
   - Tempo para o sistema se estabilizar entre falhas
   - Recomendado: 5-30 segundos

4. **`duration`**: Duração da simulação em segundos (padrão: 1000)
   - Usado nas simulações de disponibilidade
   - Recomendado: 1000-3600 segundos

5. **`availability_criteria`**: Quantos pods necessários para considerar aplicação disponível
   - `1`: Precisa de pelo menos 1 pod funcionando
   - `2`: Precisa de pelo menos 2 pods funcionando

### 🔄 **Regeneração Automática:**

```bash
# Para regenerar configuração (descoberta + MTTR):
make generate_config_all_aws   # AWS
make generate_config_all       # Local

# Para regenerar apenas descoberta:
make generate_config_aws       # AWS  
make generate_config           # Local
```

### ⚠️ **Importante:**
- **Não edite manualmente** os valores de `mttr_config` - eles são medidos automaticamente
- **Sempre faça backup** antes de modificar configurações
- **Regenere a configuração** quando a infraestrutura mudar (novos pods, nodes, etc.)

## 🎯 Próximos Passos

1. Execute o fluxo completo uma vez para gerar a configuração base
2. Analise os CSVs gerados para entender o comportamento do sistema
3. Ajuste parâmetros como número de iterações conforme necessário
4. Execute testes periódicos para monitorar a evolução da confiabilidade

---

**🚀 Para começar rapidamente, execute apenas:**
```bash
source ~/venv/py3env/bin/activate && python3 kuber_bomber/core/exemplo_uso.py
```