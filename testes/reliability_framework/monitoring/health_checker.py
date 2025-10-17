"""
Verificador de Saúde
==================

Módulo para verificação de saúde de aplicações e monitoramento
de recuperação com timeout configurável globalmente.
"""

import time
import requests
import socket
import subprocess
from typing import Dict, Tuple, Optional
from ..utils.config import get_config


class HealthChecker:
    """
    Verificador de saúde para aplicações Kubernetes.
    
    Monitora a saúde de aplicações através de HTTP endpoints
    e verifica port-forwards ativos. Usa timeout global configurável.
    """
    
    def __init__(self):
        """Inicializa o verificador de saúde."""
        self.config = get_config()
    
    def check_application_health(self, service: str, verbose: bool = True) -> Dict:
        """
        Verifica se uma aplicação está respondendo usando curl.
        
        Args:
            service: Nome do serviço a verificar
            verbose: Se deve imprimir mensagens detalhadas
            
        Returns:
            Dicionário com status da aplicação
        """
        if not self.config.services or service not in self.config.services:
            return {
                'status': 'unknown',
                'error': f"Serviço '{service}' não configurado"
            }
        
        service_config = self.config.services[service]
        url = f"http://localhost:{service_config['port']}{service_config['endpoint']}"
        
        if verbose:
            print(f"🔍 Testando {service} em {url}")
        
        # Usar curl para medir status e tempo total
        # -sS: silencioso com erros
        # -o /dev/null: descarta corpo
        # -w: imprime código HTTP e tempo total
        # --max-time 5: timeout de 5s
        try:
            result = subprocess.run(
                ['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code} %{time_total}', '--max-time', '5', url],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                if verbose:
                    err = result.stderr.strip() or 'curl failed'
                    print(f"❌ {service}: {err}")
                return {
                    'status': 'unreachable',
                    'response_time': None,
                    'error': (result.stderr.strip() or 'curl failed')
                }
            # Parse "<code> <time>"
            out = (result.stdout or '').strip()
            parts = out.split()
            status_code = int(parts[0]) if parts and parts[0].isdigit() else 0
            try:
                response_time = float(parts[1]) if len(parts) > 1 else None
            except ValueError:
                response_time = None
            
            if status_code == 200:
                if verbose:
                    rt = response_time if response_time is not None else 0.0
                    print(f"✅ {service}: OK (HTTP {status_code}, {rt:.3f}s)")
                return {
                    'status': 'healthy',
                    'response_time': response_time,
                    'status_code': status_code
                }
            else:
                if verbose:
                    rt = response_time if response_time is not None else 0.0
                    print(f"⚠️ {service}: HTTP {status_code} ({rt:.3f}s)")
                return {
                    'status': 'unhealthy',
                    'response_time': response_time,
                    'status_code': status_code,
                    'error': f"HTTP {status_code}"
                }
        except Exception as e:
            if verbose:
                print(f"❌ {service}: {str(e)}")
            return {
                'status': 'unreachable',
                'response_time': None,
                'error': str(e)
            }
    
    def check_all_applications(self, verbose: bool = True) -> Dict:
        """
        Verifica saúde de todas as aplicações configuradas.
        
        Args:
            verbose: Se deve imprimir mensagens detalhadas
            
        Returns:
            Dicionário com status de todas as aplicações
        """
        results = {}
        if self.config.services:
            for service in self.config.services.keys():
                results[service] = self.check_application_health(service, verbose)
        return results
    
    def check_port_forwards(self):
        """Verifica se os port-forwards estão ativos."""
        print("🔍 === VERIFICANDO PORT-FORWARDS ===")
        
        if not self.config.services:
            print("⚠️ Nenhum serviço configurado")
            return
        
        for service, service_config in self.config.services.items():
            port = service_config['port']
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                
                if result == 0:
                    print(f"✅ Porta {port} ({service}): Ativa")
                else:
                    print(f"❌ Porta {port} ({service}): Não disponível")
            except Exception as e:
                print(f"❌ Porta {port} ({service}): Erro - {e}")
        print()
    
    def wait_for_recovery(self, timeout: Optional[int] = None) -> Tuple[bool, float]:
        """
        ⭐ AGUARDA RECUPERAÇÃO COM TIMEOUT CONFIGURÁVEL ⭐
        
        Aguarda todas as aplicações ficarem saudáveis usando o timeout
        configurado globalmente ou um valor específico.
        
        Args:
            timeout: Timeout específico em segundos. Se None, usa o timeout global configurado.
            
        Returns:
            Tuple com (recuperou_com_sucesso, tempo_de_recuperacao)
        """
        # Usar timeout global se não especificado
        if timeout is None:
            timeout = self.config.current_recovery_timeout
        
        print(f"⏳ Aguardando recuperação (timeout: {timeout}s)")
        print(f"📊 Usando timeout configurado: {timeout}s")
        
        start_time = time.time()
        verification_count = 0
        
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            verification_count += 1
            
            print(f"\n🔍 Verificação #{verification_count} (tempo: {elapsed:.1f}s/{timeout}s)")
            
            # Mostrar status dos pods a cada verificação
            print("📋 kubectl get pods:")
            try:
                result = subprocess.run([
                    'kubectl', 'get', 'pods', '--context', self.config.context
                ], capture_output=True, text=True, check=True)
                
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    print(f"   {line}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Erro ao executar kubectl get pods: {e}")
            
            print()  # Linha em branco
            
            # Verificar saúde das aplicações (modo silencioso)
            health_status = self.check_all_applications(verbose=False)
            healthy_count = sum(1 for status in health_status.values() if status['status'] == 'healthy')
            total_services = len(self.config.services) if self.config.services else 0
            
            print(f"🏥 Status das aplicações: {healthy_count}/{total_services} saudáveis")
            for service, status in health_status.items():
                emoji = "✅" if status['status'] == 'healthy' else "❌"
                if status['status'] == 'healthy':
                    print(f"  {emoji} {service}: {status['status']} (tempo: {status['response_time']:.3f}s)")
                else:
                    print(f"  {emoji} {service}: {status['status']}")
                    if 'error' in status:
                        # Mostrar apenas parte do erro para não poluir
                        error_msg = str(status['error'])
                        if len(error_msg) > 80:
                            error_msg = error_msg[:80] + "..."
                        print(f"      🔍 Erro: {error_msg}")
            
            if healthy_count == total_services and total_services > 0:
                recovery_time = time.time() - start_time
                print(f"\n✅ Todas as aplicações recuperadas em {recovery_time:.2f}s")
                return True, recovery_time
            
            print(f"⏸️ Aguardando {self.config.health_check_interval}s antes da próxima verificação...")
            time.sleep(self.config.health_check_interval)
        
        print(f"❌ Timeout: Aplicações não se recuperaram em {timeout}s")
        return False, timeout
    
    def wait_for_specific_recovery(self, target_services: list, timeout: Optional[int] = None) -> Tuple[bool, float]:
        """
        Aguarda recuperação de serviços específicos.
        
        Args:
            target_services: Lista de serviços específicos para aguardar
            timeout: Timeout específico. Se None, usa o configurado globalmente.
            
        Returns:
            Tuple com (recuperou_com_sucesso, tempo_de_recuperacao)
        """
        if timeout is None:
            timeout = self.config.current_recovery_timeout
        
        print(f"⏳ Aguardando recuperação de serviços específicos: {target_services}")
        print(f"📊 Timeout: {timeout}s")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            
            # Verificar apenas os serviços específicos
            all_healthy = True
            if self.config.services:
                for service in target_services:
                    if service in self.config.services:
                        status = self.check_application_health(service, verbose=False)
                        if status['status'] != 'healthy':
                            all_healthy = False
                            break
            
            if all_healthy:
                recovery_time = time.time() - start_time
                print(f"✅ Serviços {target_services} recuperados em {recovery_time:.2f}s")
                return True, recovery_time
            
            time.sleep(self.config.health_check_interval)
        
        print(f"❌ Timeout: Serviços {target_services} não se recuperaram em {timeout}s")
        return False, timeout