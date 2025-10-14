# 🧪 Scripts de Teste de Resiliência Kubernetes

Este diretório contém scripts para testar a resiliência das aplicações Kubernetes através de simulação de falhas.

## 📋 Arquivos

- `main.py` - Script principal de teste de resiliência
- `port-forward-monitor.sh` - Monitor automático de port-forwards
- `requirements.txt` - Dependências Python
- `README.md` - Este arquivo

## 🚀 Como usar

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Iniciar monitor de port-forwards (em background)

```bash
cd /home/jonascgn/Programas_Curso/1_Artigo/testes
nohup bash port-forward-monitor.sh > /tmp/pf-monitor.log 2>&1 &
```

### 3. Executar testes de resiliência

#### Verificar status das aplicações
```bash
./main.py --check
```

#### Teste de matar todos os processos de um pod
```bash
./main.py --kill_process
```

#### Teste de shutdown de um pod
```bash
./main.py --shutdown
```

#### Testar pod específico
```bash
./main.py --kill_process --pod foo-app-7bd489cd57-8ds68
./main.py --shutdown --pod bar-app-6d4f4c8998-9mwxk
```

## 🔍 O que os testes fazem

### Teste Kill Process (`--kill_process`)
1. Verifica estado inicial das aplicações
2. Executa `kubectl exec {pod} -- sh -c "kill -9 -1"` no pod alvo
3. Monitora o tempo de recuperação
4. Verifica se todas as aplicações voltaram ao estado normal

### Teste Shutdown (`--shutdown`)
1. Verifica estado inicial das aplicações  
2. Deleta o pod completamente (simula shutdown)
3. Aguarda o Kubernetes recriar o pod
4. Monitora o tempo de recuperação
5. Verifica se todas as aplicações voltaram ao estado normal

## 📊 Resultados

Os resultados são salvos automaticamente em arquivos JSON com timestamp:
- `test_results_YYYYMMDD_HHMMSS.json`

## 🔧 Monitor de Port-forwards

O script `port-forward-monitor.sh` roda em background e:
- Monitora se os port-forwards estão ativos a cada 30 segundos
- Reinicia automaticamente port-forwards que caíram
- Mantém as aplicações sempre acessíveis em localhost

### URLs das aplicações:
- **foo**: http://localhost:8080/foo
- **bar**: http://localhost:8081/bar  
- **test**: http://localhost:8082/test

### Parar o monitor:
```bash
pkill -f "port-forward-monitor.sh"
```

### Ver logs do monitor:
```bash
tail -f /tmp/pf-monitor.log
```

## 🎯 Exemplo de uso completo

```bash
# 1. Iniciar monitor de port-forwards
cd /home/jonascgn/Programas_Curso/1_Artigo/testes
nohup bash port-forward-monitor.sh > /tmp/pf-monitor.log 2>&1 &

# 2. Verificar se aplicações estão funcionando
./main.py --check

# 3. Executar teste de kill process
./main.py --kill_process

# 4. Aguardar alguns minutos e executar teste de shutdown
./main.py --shutdown

# 5. Ver logs do monitor
tail -f /tmp/pf-monitor.log
```

## 🚨 Importante

- Certifique-se de que o cluster Kubernetes está funcionando
- Execute o deploy das aplicações antes dos testes
- O monitor de port-forwards deve estar rodando para os testes funcionarem corretamente
- Os testes podem demorar alguns minutos para completar (aguardam recuperação)