#!/usr/bin/env python3
"""
Teste de Integração das Injeções de Falhas - Contexto AWS
=========================================================

Testa se todas as injeções de falha estão funcionando com a configuração real 
do sistema no contexto AWS.
"""

import sys
import os
import json
import time

# Adicionar path do kuber_bomber
sys.path.append('./kuber_bomber')

from kuber_bomber.simulation.availability_simulator import AvailabilitySimulator, Component
from kuber_bomber.core.config_simples import ConfigSimples

def load_real_components():
    """Carrega os componentes reais do arquivo de configuração."""
    try:
        # Tentar diferentes caminhos possíveis
        possible_paths = [
            "./kuber_bomber/configs/config_simples_used.json",
            "./configs/config_simples_used.json", 
        ]
        
        config_path = None
        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break
        
        if not config_path:
            print(f"❌ Arquivo de configuração não encontrado em nenhum dos caminhos:")
            for path in possible_paths:
                print(f"  • {path}")
            return []
            
        print(f"✅ Usando arquivo de configuração: {config_path}")
        
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        # Verificar se existe mttf_config em vez de components
        if 'mttf_config' not in data:
            print("❌ Seção 'mttf_config' não encontrada na configuração")
            return []
        
        config = ConfigSimples(data)
        components = config.get_component_config()
        
        print(f"✅ Carregados {len(components)} componentes reais da configuração")
        return components
        
    except Exception as e:
        print(f"❌ Erro ao carregar configuração: {e}")
        return []

def test_single_injection_aws(simulator, component, injection_type="test"):
    """Testa uma única injeção de falha no contexto AWS."""
    print(f"\n🎯 Testando injeção AWS em: {component.name} (tipo: {component.component_type})")
    
    try:
        start_time = time.time()
        
        # Simular uma injeção de falha baseada no tipo do componente
        success = False
        
        if component.component_type == "pod":
            print("  📦 Injeção de pod não disponível no modo AWS (usa kubectl)")
            return True  # Pular pods no AWS
        elif component.component_type == "container":
            print("  🐳 Injeção de container não disponível no modo AWS (usa kubectl)")
            return True  # Pular containers no AWS
        elif component.component_type == "worker_node":
            success = simulator._inject_worker_node_failure(component, "kill_worker_node_processes")
        elif component.component_type == "control_plane":
            success = simulator._inject_control_plane_failure(component, "kill_control_plane_processes")
        elif component.component_type == "wn_runtime":
            success = simulator._inject_runtime_failure(component, "restart_containerd")
        elif component.component_type == "wn_proxy":
            success = simulator._inject_proxy_failure(component, "delete_kube_proxy")
        elif component.component_type == "wn_kubelet":
            success = simulator._inject_kubelet_failure(component, "kill_kubelet")
        elif component.component_type == "cp_apiserver":
            success = simulator._inject_apiserver_failure(component, "kill_kube_apiserver")
        elif component.component_type == "cp_manager":
            success = simulator._inject_manager_failure(component, "kill_kube_controller_manager")
        elif component.component_type == "cp_scheduler":
            success = simulator._inject_scheduler_failure(component, "kill_kube_scheduler")
        elif component.component_type == "cp_etcd":
            success = simulator._inject_etcd_failure(component, "kill_etcd")
        else:
            print(f"  ⚠️ Tipo não reconhecido: {component.component_type}")
            return False
        
        elapsed_time = time.time() - start_time
        
        if success:
            print(f"  ✅ SUCESSO - Tempo: {elapsed_time:.2f}s")
        else:
            print(f"  ❌ FALHOU - Tempo: {elapsed_time:.2f}s")
        
        return success
        
    except Exception as e:
        print(f"  ❌ ERRO: {e}")
        return False

def test_node_name_extraction_real(components):
    """Testa extração de nomes com componentes reais."""
    print("\n🧪 === TESTANDO EXTRAÇÃO DE NOMES COM COMPONENTES REAIS ===")
    
    node_components = [c for c in components if 
                      c.component_type in ['control_plane', 'worker_node'] or
                      c.component_type.startswith('cp_') or
                      c.component_type.startswith('wn_')]
    
    for component in node_components:
        print(f"\n📍 Componente: {component.name}")
        print(f"  • Tipo: {component.component_type}")
        
        # Simular extração de nome do nó
        node_name = None
        
        if component.name.startswith('control_plane-'):
            node_name = component.name[len('control_plane-'):]
        elif component.name.startswith('worker_node-'):
            node_name = component.name[len('worker_node-'):]
        elif '-' in component.name:
            node_name = component.name.split('-', 1)[1]
        
        if node_name:
            print(f"  • Nome do nó extraído: {node_name}")
            print(f"  • ✅ Será passado para AWS Injector como: {node_name}")
        else:
            print(f"  • ❌ Falha na extração do nome do nó")

def test_by_component_type_aws(simulator, components):
    """Testa injeções agrupadas por tipo de componente no contexto AWS."""
    
    # Filtrar apenas componentes que funcionam com AWS
    aws_components = [c for c in components if 
                     c.component_type in ['control_plane', 'worker_node'] or
                     c.component_type.startswith('cp_') or
                     c.component_type.startswith('wn_')]
    
    # Agrupar por tipo
    component_types = {}
    for component in aws_components:
        comp_type = component.component_type
        if comp_type not in component_types:
            component_types[comp_type] = []
        component_types[comp_type].append(component)
    
    print(f"\n📊 Encontrados {len(component_types)} tipos de componentes AWS:")
    for comp_type, comps in component_types.items():
        print(f"  • {comp_type}: {len(comps)} componente(s)")
    
    # Testar cada tipo
    for comp_type, comps in component_types.items():
        print(f"\n🧪 === TESTANDO TIPO AWS: {comp_type.upper()} ===")
        
        success_count = 0
        total_count = len(comps)
        
        for component in comps:
            success = test_single_injection_aws(simulator, component)
            if success:
                success_count += 1
        
        print(f"\n📈 Resultado para {comp_type}: {success_count}/{total_count} sucessos ({success_count/total_count*100:.1f}%)")

def configure_aws_mode(simulator):
    """Configura o simulador para modo AWS."""
    print("\n🔧 === CONFIGURANDO MODO AWS ===")
    
    try:
        # Importar e carregar configuração AWS
        from kuber_bomber.utils.aws_config_loader import load_aws_config
        from kuber_bomber.failure_injectors.aws_injector import AWSFailureInjector
        
        aws_config = load_aws_config()
        if not aws_config:
            print("❌ Não foi possível carregar configuração AWS")
            return False
        
        # Configurar simulador para AWS
        simulator.aws_config = aws_config
        simulator.is_aws_mode = True
        
        print(f"✅ Configuração AWS carregada:")
        print(f"  • SSH Host: {aws_config.get('ssh_host', 'N/A')}")
        print(f"  • SSH User: {aws_config.get('ssh_user', 'N/A')}")
        print(f"  • SSH Key: {aws_config.get('ssh_key', 'N/A')}")
        
        # Criar AWS injector manualmente
        ssh_host = aws_config.get('ssh_host', '')
        simulator.aws_injector = AWSFailureInjector(
            ssh_host=ssh_host,
            ssh_user=aws_config.get('ssh_user', 'ubuntu'),
            ssh_key=aws_config.get('ssh_key', '~/.ssh/vockey.pem')
        )
        
        print(f"✅ AWS injector configurado para {ssh_host}")
        
        # Verificar se pode conectar
        if hasattr(simulator, 'aws_injector') and simulator.aws_injector:
            print("✅ AWS Injector inicializado")
        else:
            print("❌ AWS Injector não inicializado")
            
        return True
        
    except Exception as e:
        print(f"❌ Erro ao configurar AWS: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Executa o teste de integração AWS."""
    print("🧪 === INICIANDO TESTE DE INTEGRAÇÃO AWS DAS INJEÇÕES ===")
    print("="*60)
    
    try:
        # Carregar componentes reais
        components = load_real_components()
        if not components:
            print("❌ Não foi possível carregar componentes. Abortando teste.")
            return
        
        # Carregar configuração AWS primeiro
        from kuber_bomber.utils.aws_config_loader import load_aws_config
        aws_config = load_aws_config()
        
        if not aws_config:
            print("❌ Não foi possível carregar configuração AWS. Abortando teste.")
            return
        
        # Criar simulador com configuração AWS
        simulator = AvailabilitySimulator(aws_config=aws_config)
        
        # Verificar se AWS foi configurado corretamente
        if not simulator.is_aws_mode:
            print("❌ Simulador não está em modo AWS. Abortando teste.")
            return
        
        # Testar extração de nomes
        test_node_name_extraction_real(components)
        
        # Testar injeções por tipo
        test_by_component_type_aws(simulator, components)
        
        print("\n" + "="*60)
        print("🎉 === TESTE DE INTEGRAÇÃO AWS CONCLUÍDO ===")
        
    except Exception as e:
        print(f"\n❌ === ERRO NO TESTE DE INTEGRAÇÃO AWS ===")
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()