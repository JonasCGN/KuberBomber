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
import json
from typing import Dict, Tuple, Optional, List
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
    
    def check_application_health(self, service: str, verbose: bool = True, use_ingress: bool = False) -> Dict:
        """
        Verifica a saúde de uma aplicação usando descoberta dinâmica de URLs.
        
        Args:
            service: Nome do serviço
            verbose: Se deve imprimir mensagens detalhadas
            use_ingress: Se deve preferir ingress sobre LoadBalancer
            
        Returns:
            Dict com status da verificação
        """
        # Primeiro tentar descobrir URLs dinamicamente
        discovered_urls = self._discover_service_url(service)
        
        if not discovered_urls:
            return {
                'healthy': False,
                'error': f'Serviço {service} não descoberto automaticamente',
                'status_code': None,
                'response_time': None,
                'url': None,
                'url_type': 'Não descoberto'
            }
        
        # Escolher a melhor URL disponível
        url = None
        url_type = None
        
        if use_ingress and 'ingress_url' in discovered_urls:
            url = discovered_urls['ingress_url']
            url_type = "Ingress"
        elif 'loadbalancer_url' in discovered_urls:
            url = discovered_urls['loadbalancer_url']
            url_type = "LoadBalancer"
        elif 'nodeport_url' in discovered_urls:
            url = discovered_urls['nodeport_url']
            url_type = "NodePort"
        else:
            # Se chegou aqui, só tem configuração hardcoded no config (fallback legacy)
            if self.config.services:
                service_config = self.config.services.get(service, {})
                if service_config and 'port' in service_config and 'endpoint' in service_config:
                    url = f"http://localhost:{service_config['port']}{service_config['endpoint']}"
                    url_type = "Port-forward (legacy)"
                else:
                    return {
                        'healthy': False,
                        'error': f'Nenhuma URL descoberta para {service}',
                        'status_code': None,
                        'response_time': None,
                        'url': None,
                        'url_type': 'Não disponível'
                    }
            else:
                return {
                    'healthy': False,
                    'error': f'Nenhuma URL descoberta para {service}',
                    'status_code': None,
                    'response_time': None,
                    'url': None,
                    'url_type': 'Não disponível'
                }
        
        if verbose:
            print(f"🔍 Testando {service} via {url_type}: {url}")
        
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
                    'healthy': False,
                    'response_time': None,
                    'error': (result.stderr.strip() or 'curl failed'),
                    'url': url,
                    'url_type': url_type
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
                    'healthy': True,
                    'response_time': response_time,
                    'status_code': status_code,
                    'url': url,
                    'url_type': url_type
                }
            else:
                if verbose:
                    rt = response_time if response_time is not None else 0.0
                    print(f"⚠️ {service}: HTTP {status_code} ({rt:.3f}s)")
                return {
                    'healthy': False,
                    'response_time': response_time,
                    'status_code': status_code,
                    'error': f"HTTP {status_code}",
                    'url': url,
                    'url_type': url_type
                }
        except Exception as e:
            if verbose:
                print(f"❌ {service}: {str(e)}")
            return {
                'healthy': False,
                'response_time': None,
                'error': str(e),
                'url': url,
                'url_type': url_type
            }
    
    def check_all_applications(self, verbose: bool = True, use_ingress: bool = False, discovered_apps: Optional[List[str]] = None) -> Dict:
        """
        Verifica saúde de todas as aplicações configuradas ou descobertas.
        
        Args:
            verbose: Se deve imprimir mensagens detalhadas
            use_ingress: Se deve usar URLs do Ingress em vez do LoadBalancer
            discovered_apps: Lista de aplicações descobertas dinamicamente
            
        Returns:
            Dicionário com status de todas as aplicações
        """
        results = {}
        
        # Se temos aplicações descobertas, usar elas
        if discovered_apps:
            for app in discovered_apps:
                results[app] = self.check_application_health(app, verbose, use_ingress)
        # Senão, tentar usar as configuradas (fallback)
        elif self.config.services:
            for service in self.config.services.keys():
                results[service] = self.check_application_health(service, verbose, use_ingress)
        else:
            # Se não tem nada configurado, descobrir automaticamente
            try:
                from kuber_bomber.simulation.availability_simulator import AvailabilitySimulator
                simulator = AvailabilitySimulator()
                info = simulator.get_discovered_components_info()
                discovered_apps = [pod.name for pod in info['pods']]
                
                if discovered_apps:
                    if verbose:
                        print(f"🔍 Descobertas {len(discovered_apps)} aplicações automaticamente")
                    for app in discovered_apps:
                        results[app] = self.check_application_health(app, verbose, use_ingress)
                else:
                    if verbose:
                        print("❌ Nenhuma aplicação descoberta no cluster")
            except Exception as e:
                if verbose:
                    print(f"❌ Erro ao descobrir aplicações: {e}")
        
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
    
    def wait_for_recovery(self, timeout: Optional[int] = None, discovered_apps: Optional[List[str]] = None) -> Tuple[bool, float]:
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
            health_status = self.check_all_applications(verbose=False, discovered_apps=discovered_apps)
            healthy_count = sum(1 for status in health_status.values() if status.get('healthy', False))
            total_services = len(health_status) if health_status else 0
            
            print(f"🏥 Status das aplicações: {healthy_count}/{total_services} saudáveis")
            for service, status in health_status.items():
                emoji = "✅" if status.get('healthy', False) else "❌"
                if status.get('healthy', False):
                    resp_time = status.get('response_time', 0.0) or 0.0
                    print(f"  {emoji} {service}: saudável (tempo: {resp_time:.3f}s)")
                else:
                    print(f"  {emoji} {service}: indisponível")
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
    
    def wait_for_specific_recovery(self, target_services: list, timeout: Optional[int] = None, use_ingress: bool = False) -> Tuple[bool, float]:
        """
        Aguarda recuperação de serviços específicos.
        
        Args:
            target_services: Lista de serviços específicos para aguardar
            timeout: Timeout específico. Se None, usa o configurado globalmente.
            use_ingress: Se deve usar URLs do Ingress em vez do LoadBalancer
            
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
                        status = self.check_application_health(service, verbose=False, use_ingress=use_ingress)
                        if not status.get('healthy', False):
                            all_healthy = False
                            break
            
            if all_healthy:
                recovery_time = time.time() - start_time
                print(f"✅ Serviços {target_services} recuperados em {recovery_time:.2f}s")
                return True, recovery_time
            
            time.sleep(self.config.health_check_interval)
        
        print(f"❌ Timeout: Serviços {target_services} não se recuperaram em {timeout}s")
        return False, timeout
    
    def test_connectivity(self):
        """
        Testa conectividade com LoadBalancer e Ingress para todas as aplicações.
        """
        print("🌐 === TESTE DE CONECTIVIDADE ===")
        print()
        
        print("📡 Testando LoadBalancer (MetalLB):")
        lb_results = self.check_all_applications(verbose=True, use_ingress=False)
        lb_healthy = sum(1 for r in lb_results.values() if r.get('healthy', False))
        print(f"   ✅ LoadBalancer: {lb_healthy}/{len(lb_results)} serviços saudáveis")
        print()
        
        print("🚪 Testando Ingress (NGINX):")
        ing_results = self.check_all_applications(verbose=True, use_ingress=True)
        ing_healthy = sum(1 for r in ing_results.values() if r.get('healthy', False))
        print(f"   ✅ Ingress: {ing_healthy}/{len(ing_results)} serviços saudáveis")
        print()
        
        print("📊 === RESUMO ===")
        if lb_healthy == len(lb_results) and ing_healthy == len(ing_results):
            print("🎉 Todas as aplicações estão acessíveis via LoadBalancer e Ingress!")
        else:
            print("⚠️ Alguns serviços podem estar com problemas.")
            print("💡 Verifique se os pods estão Ready e se o MetalLB/Ingress estão funcionando.")
        
        return {
            'loadbalancer': lb_results,
            'ingress': ing_results,
            'summary': {
                'lb_healthy': lb_healthy,
                'ing_healthy': ing_healthy,
                'total': len(lb_results)
            }
        }
    
    def get_pods_by_app_label(self, app_name: str) -> list:
        """
        Obtém pods filtrados pelo label app.
        
        Args:
            app_name: Nome da aplicação (ex: 'foo', 'bar', 'test')
            
        Returns:
            Lista de pods com informações básicas
        """
        try:
            result = subprocess.run([
                'kubectl', 'get', 'pods', 
                '-l', f'app={app_name}',
                '-o', 'json',
                '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            import json
            data = json.loads(result.stdout)
            
            pods = []
            for item in data.get('items', []):
                pod_info = {
                    'name': item['metadata']['name'],
                    'ready': False,
                    'status': item['status'].get('phase', 'Unknown'),
                    'restarts': 0
                }
                
                # Verificar se está Ready
                conditions = item['status'].get('conditions', [])
                for condition in conditions:
                    if condition['type'] == 'Ready':
                        pod_info['ready'] = condition['status'] == 'True'
                        break
                
                # Contar restarts
                container_statuses = item['status'].get('containerStatuses', [])
                if container_statuses:
                    pod_info['restarts'] = container_statuses[0].get('restartCount', 0)
                
                pods.append(pod_info)
            
            return pods
            
        except Exception as e:
            print(f"❌ Erro ao obter pods por label app={app_name}: {e}")
            return []
    
    def is_node_ready(self, node_name: str) -> bool:
        """
        Verifica se um node está Ready.
        
        Args:
            node_name: Nome do node
            
        Returns:
            True se node está Ready
        """
        try:
            result = subprocess.run([
                'kubectl', 'get', 'node', node_name,
                '-o', 'json',
                '--context', self.config.context
            ], capture_output=True, text=True, check=True)
            
            import json
            data = json.loads(result.stdout)
            
            conditions = data['status'].get('conditions', [])
            for condition in conditions:
                if condition['type'] == 'Ready':
                    return condition['status'] == 'True'
            
            return False
            
        except Exception as e:
            print(f"❌ Erro ao verificar node {node_name}: {e}")
            return False
    
    def _discover_service_url(self, service_name: str) -> Dict[str, str]:
        """
        Descobre URLs de um serviço específico dinamicamente.
        
        Args:
            service_name: Nome do serviço (ex: 'foo-app', 'bar-app')
            
        Returns:
            Dict com URLs descobertas
        """
        discovered_urls = {}
        
        try:
            # 1. Descobrir LoadBalancer Services
            result = subprocess.run([
                'kubectl', 'get', 'services', 
                '--context', self.config.context,
                '-o', 'json'
            ], capture_output=True, text=True, check=True)
            
            services_data = json.loads(result.stdout)
            
            for service in services_data['items']:
                svc_name = service['metadata']['name']
                
                # Verificar se o serviço corresponde ao app
                # foo-app -> foo-loadbalancer, foo-service
                # bar-app -> bar-loadbalancer, bar-service  
                # test-app -> test-loadbalancer, test-service
                app_base = service_name.replace('-app', '')  # foo-app -> foo
                
                if (svc_name == f"{app_base}-loadbalancer" or 
                    svc_name == f"{app_base}-service" or
                    svc_name.startswith(f"{app_base}-")):
                    
                    # LoadBalancer
                    if service['spec'].get('type') == 'LoadBalancer':
                        ingress = service['status'].get('loadBalancer', {}).get('ingress', [])
                        if ingress and ingress[0].get('ip'):
                            ip = ingress[0]['ip']
                            port = service['spec']['ports'][0]['port']
                            
                            # Inferir endpoint baseado no nome do app
                            endpoint = f"/{app_base}"  # /foo, /bar, /test
                            discovered_urls['loadbalancer_url'] = f"http://{ip}:{port}{endpoint}"
                    
                    # NodePort
                    elif service['spec'].get('type') == 'NodePort':
                        node_port = service['spec']['ports'][0]['nodePort']
                        # Obter IP de qualquer nó
                        nodes_result = subprocess.run([
                            'kubectl', 'get', 'nodes',
                            '--context', self.config.context,
                            '-o', 'jsonpath={.items[0].status.addresses[?(@.type=="InternalIP")].address}'
                        ], capture_output=True, text=True, check=True)
                        
                        if nodes_result.stdout.strip():
                            node_ip = nodes_result.stdout.strip()
                            endpoint = f"/{app_base}"  # /foo, /bar, /test  
                            discovered_urls['nodeport_url'] = f"http://{node_ip}:{node_port}{endpoint}"
            
            # 2. Descobrir Ingress
            try:
                ingress_result = subprocess.run([
                    'kubectl', 'get', 'ingress',
                    '--context', self.config.context,
                    '-o', 'json'
                ], capture_output=True, text=True, check=True)
                
                ingress_data = json.loads(ingress_result.stdout)
                
                for ingress in ingress_data['items']:
                    rules = ingress['spec'].get('rules', [])
                    for rule in rules:
                        paths = rule.get('http', {}).get('paths', [])
                        for path in paths:
                            backend_service = path['backend']['service']['name']
                            # Verificar se o backend service corresponde ao app
                            app_base = service_name.replace('-app', '')
                            if (backend_service == f"{app_base}-service" or 
                                backend_service.startswith(f"{app_base}-")):
                                host = rule.get('host', 'localhost')
                                path_str = path.get('path', '/')
                                discovered_urls['ingress_url'] = f"http://{host}{path_str}"
                                break
            except subprocess.CalledProcessError:
                # Ingress não disponível ou sem permissões
                pass
        
        except Exception as e:
            print(f"⚠️ Erro ao descobrir URLs para {service_name}: {e}")
        
        return discovered_urls