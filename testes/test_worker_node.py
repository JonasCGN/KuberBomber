#!/usr/bin/env python3
"""
Teste do novo método de matar processos do worker node
"""

import subprocess
from typing import Tuple

def kill_worker_node_processes(target: str) -> Tuple[bool, str]:
    """Mata processos críticos do worker node via docker exec (Kind cluster)"""
    # Lista de processos críticos do Kubernetes no worker node
    critical_processes = [
        "kubelet",      # Processo principal do worker node
        "kube-proxy",   # Proxy de rede do Kubernetes
        "containerd",   # Runtime de containers
        "dockerd"       # Docker daemon (se estiver rodando)
    ]
    
    commands_executed = []
    
    print(f"💀 Matando processos críticos do worker node {target}...")
    
    for process in critical_processes:
        command = f"docker exec {target} sh -c 'pkill -9 {process}'"
        print(f"🔪 Executando: docker exec {target} pkill -9 {process}")
        
        try:
            result = subprocess.run([
                'docker', 'exec', target, 'sh', '-c', f'pkill -9 {process}'
            ], capture_output=True, text=True)
            
            # pkill retorna 1 se não encontrou o processo, mas isso é normal
            if result.returncode == 0 or result.returncode == 1:
                commands_executed.append(f"pkill -9 {process}")
                print(f"✅ Comando executado para processo {process}")
            else:
                print(f"⚠️ Erro ao executar pkill para {process}: {result.stderr}")
                
        except Exception as e:
            print(f"⚠️ Erro ao executar comando para {process}: {e}")
            
    # Comando consolidado para logs
    full_command = f"docker exec {target} sh -c '" + "; ".join([f"pkill -9 {p}" for p in critical_processes]) + "'"
    
    if commands_executed:
        print(f"✅ Comandos executados no worker node {target}: {', '.join(commands_executed)}")
        print(f"🔄 Worker node pode precisar de alguns segundos para se recuperar...")
        return True, full_command
    else:
        print(f"❌ Nenhum comando foi executado com sucesso no worker node {target}")
        return False, full_command

def get_worker_nodes():
    """Obtém lista de worker nodes"""
    try:
        result = subprocess.run([
            'kubectl', 'get', 'nodes', '-l', '!node-role.kubernetes.io/control-plane',
            '-o', 'jsonpath={.items[*].metadata.name}', '--context=local-k8s'
        ], capture_output=True, text=True, check=True)
        
        nodes = result.stdout.strip().split()
        return [node for node in nodes if node]
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao obter worker nodes: {e}")
        return []

if __name__ == "__main__":
    print("🧪 Teste do método kill_worker_node_processes")
    
    # Listar worker nodes
    workers = get_worker_nodes()
    print(f"📋 Worker nodes encontrados: {workers}")
    
    if workers:
        # Testar com o primeiro worker
        target = workers[0]
        print(f"\n🎯 Testando com worker node: {target}")
        
        # Primeiro verificar se o node está acessível
        try:
            check_result = subprocess.run([
                'docker', 'exec', target, 'sh', '-c', 'echo "Node accessible"'
            ], capture_output=True, text=True, check=True)
            print(f"✅ Worker node {target} acessível via docker exec")
            
            # Executar teste
            success, command = kill_worker_node_processes(target)
            print(f"\n📊 Resultado:")
            print(f"   Sucesso: {success}")
            print(f"   Comando: {command}")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Worker node {target} não acessível via docker exec: {e}")
    else:
        print("❌ Nenhum worker node encontrado")