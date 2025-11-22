# 🛠️ Kuber Bomber - Configuração de Ferramentas

## ✅ Status Atual

**TODOS OS PODS ESTÃO PRONTOS PARA USAR O KUBER BOMBER!**

Os pods AWS estão configurados com todas as ferramentas necessárias:
- ✅ `bar-app-69bc4fffc-b82p9`: ps, kill, curl, pgrep
- ✅ `foo-app-b8f6c549f-rhw62`: ps, kill, curl, pgrep  
- ✅ `test-app-9c59fd7c7-hhlqs`: ps, kill, curl, pgrep

## 🚀 Comandos Disponíveis no Makefile

### Verificação Rápida
```bash
# Verificar se pods AWS têm ferramentas necessárias
make check_aws_pods_tools
```

### Instalação (se necessário)
```bash
# Instalar ferramentas em pods AWS que não têm
make install_tools_aws_pods

# Workflow completo: instalar + verificar + testar
make setup_aws_pods_complete
```

### Para Ambiente Local (Kind)
```bash
# Verificar pods locais
make check_pods_tools

# Instalar em pods locais
make install_tools_current_pods
```

### Solução Definitiva (Dockerfile)
```bash
# Criar imagem enhanced com ferramentas pré-instaladas
make build_enhanced_image

# Atualizar deployments para usar imagem enhanced
make update_deployments_enhanced

# Workflow completo: build + update + deploy
make deploy_enhanced_setup
```

## 📋 Ferramentas Instaladas

Em cada pod foi instalado:

### Pacotes de Sistema
- `procps` → Comandos: ps, kill, pgrep, pkill
- `psmisc` → Comandos: killall, fuser
- `net-tools` → Comandos: netstat, route
- `iputils-ping` → Comando: ping
- `curl` → Comando: curl

### Comandos Testados
```bash
# Estes comandos funcionam em todos os pods:
kubectl exec <pod> -- ps aux              # Listar processos
kubectl exec <pod> -- kill -9 -1          # Matar todos os processos
kubectl exec <pod> -- kill -9 1           # Matar processo init  
kubectl exec <pod> -- pgrep java          # Buscar processo java
kubectl exec <pod> -- curl http://...     # Teste de conectividade
```

## 🎯 Comandos de Teste do Framework

Agora você pode executar qualquer comando do Kuber Bomber:

### Teste de Pods
```bash
cd kuber_bomber && python3 reliability_tester.py \
  --component pod \
  --failure-method kill_processes \
  --target bar-app-69bc4fffc-b82p9 \
  --iterations 5 \
  --interval 10 \
  --aws
```

### Simulação Completa
```bash
# Executar simulação AWS
make run_simulation_aws

# Gerar configuração AWS  
make generate_config_aws
```

## ⚠️ Importante

**Esta configuração é temporária!** Se os pods forem reiniciados, você precisará:
1. Executar novamente `make install_tools_aws_pods`, OU
2. Usar a solução definitiva com `make deploy_enhanced_setup`

## 🔧 Troubleshooting

### Erro: "executable file not found"
```bash
# Verificar primeiro
make check_aws_pods_tools

# Se aparecer ❌ MISSING, executar:
make install_tools_aws_pods
```

### Pods Diferentes?
Se os nomes dos pods mudaram, eles ainda serão detectados automaticamente pelos comandos `make`, pois usamos filtros por padrão (`foo-app`, `bar-app`, `test-app`).

---

**Data:** 21 de Novembro de 2025  
**Status:** ✅ PRONTO PARA PRODUÇÃO  
**Teste:** Verificado em AWS com 3 pods funcionando perfeitamente