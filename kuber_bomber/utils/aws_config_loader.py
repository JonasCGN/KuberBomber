#!/usr/bin/env python3
"""
Carregador Central de Configuração AWS
=====================================

Função centralizada para carregar aws_config.json e validar configurações.
Remove todos os hardcoded values e força uso do arquivo de configuração.
"""

import json
import os
import sys
from typing import Dict, Optional


def load_aws_config() -> Optional[Dict]:
    """
    Carrega configuração AWS do arquivo aws_config.json.
    
    Returns:
        Dict com configuração AWS ou None se arquivo não existe/inválido
    """
    config_path = "aws_config.json"
    
    # Verificar se arquivo existe
    if not os.path.exists(config_path):
        print(f"❌ ERRO: Arquivo {config_path} não encontrado!")
        print(f"📁 Crie o arquivo com:")
        print(f"{{")
        print(f"  \"ssh_host\": \"SEU_IP_AWS\",")
        print(f"  \"ssh_key\": \"~/.ssh/vockey.pem\",")
        print(f"  \"ssh_user\": \"ubuntu\"")
        print(f"}}")
        return None
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Validar campos obrigatórios
        required_fields = ['ssh_host', 'ssh_key', 'ssh_user']
        for field in required_fields:
            if field not in config:
                print(f"❌ ERRO: Campo '{field}' não encontrado em {config_path}")
                return None
            if not config[field] or not isinstance(config[field], str):
                print(f"❌ ERRO: Campo '{field}' inválido em {config_path}")
                return None
        
        # Validar formato do IP
        ssh_host = config['ssh_host']
        if not _is_valid_ip(ssh_host):
            print(f"❌ ERRO: SSH host '{ssh_host}' não é um IP válido!")
            print(f"📝 Verifique se o IP em {config_path} está correto")
            return None
        
        print(f"✅ Configuração AWS carregada de {config_path}")
        print(f"🌐 SSH Host: {config['ssh_host']}")
        print(f"🔑 SSH Key: {config['ssh_key']}")
        print(f"👤 SSH User: {config['ssh_user']}")
        
        return config
        
    except json.JSONDecodeError as e:
        print(f"❌ ERRO: Arquivo {config_path} não é um JSON válido: {e}")
        return None
    except Exception as e:
        print(f"❌ ERRO: Falha ao carregar {config_path}: {e}")
        return None


def validate_aws_connection(aws_config: Dict) -> bool:
    """
    Testa conectividade SSH com o servidor AWS.
    
    Args:
        aws_config: Configuração AWS carregada
        
    Returns:
        True se conexão funcionou
    """
    import subprocess
    
    print(f"🔍 Testando conectividade SSH...")
    
    try:
        cmd = [
            'ssh', '-i', aws_config['ssh_key'],
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ConnectTimeout=10',
            f"{aws_config['ssh_user']}@{aws_config['ssh_host']}",
            'echo "SSH OK"'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        
        if result.returncode == 0 and "SSH OK" in result.stdout:
            print(f"✅ Conectividade SSH confirmada!")
            return True
        else:
            print(f"❌ Falha na conectividade SSH!")
            print(f"💡 Verifique se:")
            print(f"   1. IP {aws_config['ssh_host']} está correto")
            print(f"   2. Instância AWS está rodando")
            print(f"   3. Chave SSH {aws_config['ssh_key']} existe e tem permissões corretas")
            print(f"   4. Security Group permite SSH na porta 22")
            if result.stderr:
                print(f"🔍 Erro SSH: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ Timeout na conexão SSH!")
        print(f"💡 Verifique se o IP {aws_config['ssh_host']} está acessível")
        return False
    except Exception as e:
        print(f"❌ Erro ao testar SSH: {e}")
        return False


def require_aws_config() -> Dict:
    """
    Carrega configuração AWS obrigatoriamente ou sai do programa.
    
    Returns:
        Dict com configuração AWS válida
    """
    config = load_aws_config()
    if config is None:
        print(f"💥 ERRO FATAL: Configuração AWS é obrigatória para modo AWS!")
        print(f"🔧 Corrija o arquivo aws_config.json e tente novamente")
        sys.exit(1)
    return config


def _is_valid_ip(ip: str) -> bool:
    """Verifica se string é um IP válido."""
    import re
    pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    return bool(re.match(pattern, ip))