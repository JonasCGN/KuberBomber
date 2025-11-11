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
from ..utils.kubectl_executor import KubectlExecutor
import threading

class HealthChecker:
    """
    ⚕️ Monitor de Saúde das Aplicações
    
    Verifica a disponibilidade de aplicações em Kubernetes através de HTTP/HTTPS,
    com suporte para descoberta automática de URLs e modo AWS transparente.
    """
    # Cache estático para evitar descoberta duplicada
    _discovered_apps_cache = None
    _discovery_logged = False
    
    def __init__(self, aws_config: Optional[dict] = None):
        """
        Inicializa o verificador de saúde.
        
        Args:
            aws_config: Configuração AWS para conexão remota
        """
        self.aws_config = aws_config
        self.is_aws_mode = aws_config is not None

        if self.is_aws_mode and aws_config:
            # MODO AWS: Usar APENAS aws_injector
            print("🔧 Inicializando APENAS AWS injector...")
            from ..failure_injectors.aws_injector import AWSFailureInjector
            self.aws_injector = AWSFailureInjector(
                ssh_key=aws_config['ssh_key'],
                ssh_host=aws_config['ssh_host'],
                ssh_user=aws_config['ssh_user']
            )
            print("✅ AWS injector configurado - injetores locais não serão usados")
        
        self.config = get_config(aws_mode=self.is_aws_mode)
        self.kubectl = KubectlExecutor(aws_config=aws_config if self.is_aws_mode else None)
        
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
        # Se for modo AWS, usar URLs diretamente do IP público
        if self.is_aws_mode and self.aws_config:
            return self._check_aws_application_health(service, verbose)
        
        # Primeiro tentar descobrir URLs dinamicamente
        discovered_urls = self._discover_service_url(service)
        
        if not discovered_urls:
            return {
                'healthy': False,
                'error': f'Nenhuma URL descoberta para {service}',
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
        
        # Se estamos em modo AWS, usar lista conhecida de aplicações
        if self.is_aws_mode:
            aws_apps = ['bar-app', 'foo-app', 'test-app']  # Aplicações conhecidas no AWS
            if verbose:
                print(f"📱 Testando aplicações AWS via control plane: {aws_apps}")
            
            for app in aws_apps:
                if verbose:
                    print(f"🔍 Verificando {app}...")
                results[app] = self.check_application_health(app, verbose=verbose)
            
            return results
        
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
                
                # Usar cache se disponível
                if HealthChecker._discovered_apps_cache is not None:
                    discovered_apps = HealthChecker._discovered_apps_cache
                else:
                    simulator = AvailabilitySimulator(aws_config=self.aws_config)
                    info = simulator.get_discovered_components_info()
                    discovered_apps = [pod.name for pod in info['pods']]
                    HealthChecker._discovered_apps_cache = discovered_apps
                
                if discovered_apps:
                    if verbose and not HealthChecker._discovery_logged:
                        print(f"🔍 Descobertas {len(discovered_apps)} aplicações automaticamente")
                        HealthChecker._discovery_logged = True
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
                result = self.kubectl.execute_kubectl(['get', 'pods'])
                
                if result['success']:
                    lines = result['output'].strip().split('\n')
                    for line in lines:
                        print(f"   {line}")
                else:
                    print(f"❌ Erro ao executar kubectl get pods: {result['error']}")
            except Exception as e:
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
            elif healthy_count > 0:
                print(f"\n⚠️ Apenas {healthy_count}/{total_services} aplicações saudáveis - continuando verificação...")
                # Não retorna True aqui - continua verificando até TODAS estarem saudáveis
            
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
            result = self.kubectl.execute_kubectl([
                'get', 'pods', 
                '-l', f'app={app_name}',
                '-o', 'json'
            ])
            
            if not result['success']:
                return []
            
            import json
            data = json.loads(result['output'])
            
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
    
    def get_pods_by_name_prefix(self, app_name: str) -> list:
        """
        Obtém pods filtrados pelo prefixo do nome (fallback quando label não funciona).
        
        Args:
            app_name: Nome da aplicação (ex: 'bar-app', 'foo-app', 'test-app')
            
        Returns:
            Lista de pods com informações básicas
        """
        try:
            result = self.kubectl.execute_kubectl([
                'get', 'pods', 
                '-o', 'json'
            ])
            
            if not result['success']:
                return []
            
            import json
            data = json.loads(result['output'])
            
            pods = []
            for item in data.get('items', []):
                pod_name = item['metadata']['name']
                
                # Filtrar pods que começam com o nome da aplicação
                if pod_name.startswith(app_name):
                    pod_info = {
                        'name': pod_name,
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
            print(f"❌ Erro ao obter pods por prefixo {app_name}: {e}")
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
            result = self.kubectl.execute_kubectl([
                'get', 'node', node_name,
                '-o', 'json'
            ])
            
            if not result['success']:
                return False
            
            import json
            data = json.loads(result['output'])
            
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
            result = self.kubectl.execute_kubectl(['get', 'services', '-o', 'json'])
            
            if not result['success']:
                print(f"❌ Erro ao obter services: {result.get('error', 'Unknown error')}")
                return discovered_urls
                
            services_data = json.loads(result['output'])
            
            for service in services_data['items']:
                svc_name = service['metadata']['name']
                
                # Verificar se o serviço corresponde ao app
                # foo-app -> foo-loadbalancer, foo-service, foo-service-nodeport
                # bar-app -> bar-loadbalancer, bar-service, bar-service-nodeport  
                # test-app -> test-loadbalancer, test-service, test-service-nodeport
                app_base = service_name.replace('-app', '')  # foo-app -> foo
                
                if (svc_name == f"{app_base}-loadbalancer" or 
                    svc_name == f"{app_base}-service" or
                    svc_name == f"{app_base}-service-nodeport" or
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
                        nodes_result = self.kubectl.execute_kubectl([
                            'get', 'nodes',
                            '-o', 'jsonpath={.items[0].status.addresses[?(@.type=="InternalIP")].address}'
                        ])
                        
                        if nodes_result['success'] and nodes_result['output'].strip():
                            node_ip = nodes_result['output'].strip()
                            endpoint = f"/{app_base}"  # /foo, /bar, /test  
                            discovered_urls['nodeport_url'] = f"http://{node_ip}:{node_port}{endpoint}"
            
            # 2. Descobrir Ingress
            try:
                ingress_result = self.kubectl.execute_kubectl([
                    'get', 'ingress',
                    '-o', 'json'
                ])
                
                if ingress_result['success']:
                    ingress_data = json.loads(ingress_result['output'])
                    
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
            except Exception:
                # Ingress não disponível ou sem permissões
                pass
        
        except Exception as e:
            # Suprimir erros quando cluster está temporariamente indisponível
            if "non-zero exit status" in str(e) or "kubectl" in str(e).lower():
                # Cluster temporariamente indisponível, não imprimir erro
                pass
            else:
                print(f"⚠️ Erro ao descobrir URLs para {service_name}: {e}")
        
        return discovered_urls
    
    def _check_aws_application_health(self, service: str, verbose: bool = True) -> Dict:
        """
        Verifica saúde de aplicação AWS usando descoberta automática de NodePort.
        
        Args:
            service: Nome do serviço (foo-app, bar-app, test-app)
            verbose: Se deve imprimir mensagens detalhadas
            
        Returns:
            Dict com status da verificação
        """
        # OBRIGATÓRIO: usar aws_config.json - SEM fallback!
        if not self.aws_config:
            return {
                'healthy': False,
                'error': 'AWS config obrigatório! Carregue aws_config.json primeiro',
                'status_code': None,
                'response_time': None,
                'url': None,
                'url_type': 'Config Missing'
            }
        
        # Descobrir NodePort automaticamente via kubectl get svc
        app_base = service.replace('-app', '')  # foo-app -> foo
        service_name = f"{app_base}-service-nodeport"
        
        try:
            # Obter informações de TODOS os serviços NodePort
            result = self.kubectl.execute_kubectl([
                'get', 'svc', 
                '-o', 'json'
            ])
            
            if not result['success']:
                if verbose:
                    print(f"❌ Erro ao obter serviços: {result.get('error', 'Unknown error')}")
                return {
                    'healthy': False,
                    'error': f"Erro ao obter serviços: {result.get('error', 'Unknown error')}",
                    'status_code': None,
                    'response_time': None,
                    'url': None,
                    'url_type': 'Discovery Failed'
                }
            
            services_data = json.loads(result['output'])
            node_port = None
            
            # Procurar o serviço NodePort correto
            for svc in services_data.get('items', []):
                svc_name = svc['metadata']['name']
                svc_type = svc['spec'].get('type', '')
                
                # Verificar se é o serviço NodePort que queremos
                if svc_name == service_name and svc_type == 'NodePort':
                    ports = svc['spec'].get('ports', [])
                    if ports:
                        node_port = ports[0].get('nodePort')
                        break
            
            if not node_port:
                if verbose:
                    print(f"❌ NodePort não encontrado para {service_name}")
                return {
                    'healthy': False,
                    'error': f'NodePort não encontrado para {service_name}',
                    'status_code': None,
                    'response_time': None,
                    'url': None,
                    'url_type': 'NodePort Missing'
                }
            
            # Obter IP do control plane (nós vamos fazer curl LOCAL no control plane)
            ssh_host = self.aws_config['ssh_host']
            endpoint = f"/{app_base}"  # /foo, /bar, /test
            
            # OPÇÃO 1: Tentar localhost no control plane
            local_url = f"http://localhost:{node_port}{endpoint}"
            
            if verbose:
                print(f"🌐 Verificando {service} via control plane: {local_url}")
            
            # Usar aws_injector para executar curl no control plane
            from ..failure_injectors.aws_injector import AWSFailureInjector
            
            ssh_key = self.aws_config['ssh_key']
            ssh_user = self.aws_config['ssh_user']
            aws_injector = AWSFailureInjector(ssh_key, ssh_host, ssh_user)
            
            # Executar curl no control plane via SSH usando aws_injector
            curl_cmd = f"curl -sS -o /dev/null -w '%{{http_code}} %{{time_total}}' --max-time 5 '{local_url}'"
            
            instances = aws_injector._get_aws_instances()
            
            # Encontrar o node_name do ControlPlane dentro do dicionário instances
            control_plane_node = next(
                (k for k, v in instances.items() if v.get('Name') == 'ControlPlane' or v.get('Name', '').lower().startswith('control')),
                None
            )
            if not control_plane_node:
                print("   ❌ ControlPlane não encontrado em instances")
                return {
                    'healthy': False,
                    'response_time': None,
                    'error': 'ControlPlane instance not found',
                    'url': local_url,
                    'url_type': "Control Plane NodePort"
                }

            node_name = control_plane_node
            
            curl_result = aws_injector._execute_ssh_command(control_plane_node, curl_cmd, timeout=15)
            
            if not curl_result[0]:
                # Se localhost não funcionar, tentar com IP interno do node
                if verbose:
                    print(f"⚠️ localhost falhou, tentando via IP interno...")
                
                # Tentar descobrir IP interno do node onde o pod está rodando
                return self._check_aws_application_health_via_node_ip(service, node_port, verbose)
            
            # Parse da resposta do curl: "200 0.123456"
            output_parts = curl_result[1].strip().split() if curl_result[1] else []
            if len(output_parts) >= 2:
                status_code = int(output_parts[0])
                response_time = float(output_parts[1])
                
                if status_code == 200:
                    if verbose:
                        print(f"✅ {service}: OK ({response_time:.3f}s) via control plane")
                    return {
                        'healthy': True,
                        'status_code': status_code,
                        'response_time': response_time,
                        'url': local_url,
                        'url_type': "Control Plane NodePort"
                    }
                else:
                    if verbose:
                        print(f"⚠️ {service}: HTTP {status_code} ({response_time:.3f}s) via control plane")
                    return {
                        'healthy': False,
                        'status_code': status_code,
                        'response_time': response_time,
                        'error': f'HTTP {status_code}',
                        'url': local_url,
                        'url_type': "Control Plane NodePort"
                    }
            else:
                return {
                    'healthy': False,
                    'response_time': None,
                    'error': 'Invalid curl response',
                    'url': local_url,
                    'url_type': "Control Plane NodePort"
                }
                
        except subprocess.TimeoutExpired:
            if verbose:
                print(f"❌ {service}: SSH timeout")
            return {
                'healthy': False,
                'response_time': None,
                'error': 'SSH timeout',
                'url': None,
                'url_type': "Control Plane NodePort"
            }
        except Exception as e:
            if verbose:
                print(f"❌ {service}: {e}")
            return {
                'healthy': False,
                'response_time': None,
                'error': str(e),
                'url': None,
                'url_type': "Control Plane NodePort"
            }
    
    def _check_aws_application_health_via_node_ip(self, service: str, node_port: int, verbose: bool = True) -> Dict:
        """
        Tenta verificar aplicação via IP interno do node onde o pod está rodando.
        
        Args:
            service: Nome do serviço
            node_port: Porta NodePort descoberta
            verbose: Se deve imprimir mensagens
            
        Returns:
            Dict com status da verificação
        """
        try:
            app_base = service.replace('-app', '')
            endpoint = f"/{app_base}"
            
            # Descobrir em qual node o pod está rodando
            result = self.kubectl.execute_kubectl([
                'get', 'pods', 
                '-o', 'json'
            ])
            
            if not result['success']:
                return self._check_aws_application_health_fallback(service, verbose)
            
            pods_data = json.loads(result['output'])
            node_ip = None
            
            # Procurar o pod da aplicação e pegar o node IP
            for pod in pods_data.get('items', []):
                pod_name = pod['metadata']['name']
                if pod_name.startswith(service.replace('-app', '-')):  # foo-app -> foo-
                    node_name = pod['spec'].get('nodeName')
                    if node_name:
                        # Pegar IP interno do node
                        node_result = self.kubectl.execute_kubectl([
                            'get', 'node', node_name,
                            '-o', 'jsonpath={.status.addresses[?(@.type=="InternalIP")].address}'
                        ])
                        if node_result['success'] and node_result['output'].strip():
                            node_ip = node_result['output'].strip()
                            break
            
            if not node_ip:
                if verbose:
                    print(f"❌ IP do node não encontrado para {service}")
                return self._check_aws_application_health_fallback(service, verbose)
            
            # URL usando IP interno do node
            node_url = f"http://{node_ip}:{node_port}{endpoint}"

            if verbose:
                print(f"🌐 Verificando {service} via node IP: {node_url}")
            
            # Executar curl no control plane via SSH usando IP do node
            curl_cmd = f"curl -sS -o /dev/null -w '%{{http_code}} %{{time_total}}' --max-time 5 '{node_url}'"
            
            ssh_key = self.aws_config['ssh_key']
            ssh_user = self.aws_config['ssh_user'] 
            ssh_host = self.aws_config['ssh_host']
            
            ssh_cmd = [
                'ssh', '-i', ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                f"{ssh_user}@{ssh_host}",
                curl_cmd
            ]
            
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode != 0:
                err = result.stderr.strip() or 'SSH/curl failed'
                if verbose:
                    print(f"❌ {service} (via node IP): {err}")
                return self._check_aws_application_health_fallback(service, verbose)
            
            # Parse da resposta do curl: "200 0.123456"
            output_parts = result.stdout.strip().split()
            if len(output_parts) >= 2:
                status_code = int(output_parts[0])
                response_time = float(output_parts[1])
                
                if status_code == 200:
                    if verbose:
                        print(f"✅ {service}: OK ({response_time:.3f}s) via node IP")
                    return {
                        'healthy': True,
                        'status_code': status_code,
                        'response_time': response_time,
                        'url': node_url,
                        'url_type': "Node IP NodePort"
                    }
                else:
                    if verbose:
                        print(f"⚠️ {service}: HTTP {status_code} ({response_time:.3f}s) via node IP")
                    return {
                        'healthy': False,
                        'status_code': status_code,
                        'response_time': response_time,
                        'error': f'HTTP {status_code}',
                        'url': node_url,
                        'url_type': "Node IP NodePort"
                    }
            else:
                return {
                    'healthy': False,
                    'response_time': None,
                    'error': 'Invalid curl response',
                    'url': node_url,
                    'url_type': "Node IP NodePort"
                }
                
        except Exception as e:
            if verbose:
                print(f"❌ {service} (via node IP): {e}")
            return self._check_aws_application_health_fallback(service, verbose)
    
    def _check_aws_application_health_fallback(self, service: str, verbose: bool = True) -> Dict:
        """
        Fallback para verificação AWS usando configuração hardcoded apenas para NodePorts conhecidos.
        """
        # OBRIGATÓRIO: usar aws_config.json - SEM configuração hardcoded!
        if not self.aws_config or 'ssh_host' not in self.aws_config:
            return {
                'healthy': False,
                'error': 'AWS config obrigatório! Carregue aws_config.json',
                'status_code': None,
                'response_time': None,
                'url': None,
                'url_type': 'Config Missing'
            }
        
        # Mapear nome do serviço para NodePort conhecido (fallback final)
        app_name = service.replace('-app', '')  # foo-app -> foo
        
        # NodePorts padrão das aplicações AWS (apenas como fallback)
        app_configs = {
            'foo': {'port': 30081, 'path': '/foo'},
            'bar': {'port': 30082, 'path': '/bar'}, 
            'test': {'port': 30083, 'path': '/test'}
        }
        
        if app_name not in app_configs:
            return {
                'healthy': False,
                'error': f'Aplicação {app_name} não configurada para AWS',
                'status_code': None,
                'response_time': None,
                'url': None,
                'url_type': 'Não configurado'
            }
        
        config = app_configs[app_name]
        host = self.aws_config['ssh_host']
        url = f"http://{host}:{config['port']}{config['path']}"
        
        if verbose:
            print(f"🌐 Verificando {service} (fallback hardcoded): {url}")
        
        # Usar curl para medir status e tempo total
        try:
            result = subprocess.run(
                ['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code} %{time_total}', '--max-time', '5', url],
                capture_output=True, text=True, timeout=10
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
                    'url_type': "AWS NodePort (fallback)"
                }
            
            # Parse da resposta do curl: "200 0.123456"
            output_parts = result.stdout.strip().split()
            if len(output_parts) >= 2:
                status_code = int(output_parts[0])
                response_time = float(output_parts[1])
                
                if status_code == 200:
                    if verbose:
                        print(f"✅ {service}: OK ({response_time:.3f}s)")
                    return {
                        'healthy': True,
                        'status_code': status_code,
                        'response_time': response_time,
                        'url': url,
                        'url_type': "AWS NodePort (fallback)"
                    }
                else:
                    if verbose:
                        print(f"⚠️ {service}: HTTP {status_code} ({response_time:.3f}s)")
                    return {
                        'healthy': False,
                        'status_code': status_code,
                        'response_time': response_time,
                        'error': f'HTTP {status_code}',
                        'url': url,
                        'url_type': "AWS NodePort (fallback)"
                    }
            else:
                return {
                    'healthy': False,
                    'response_time': None,
                    'error': 'Invalid curl response',
                    'url': url,
                    'url_type': "AWS NodePort (fallback)"
                }
        except subprocess.TimeoutExpired:
            if verbose:
                print(f"❌ {service}: curl timeout")
            return {
                'healthy': False,
                'response_time': None,
                'error': 'curl timeout',
                'url': url,
                'url_type': "AWS NodePort (fallback)"
            }
        except Exception as e:
            if verbose:
                print(f"❌ {service}: {e}")
            return {
                'healthy': False,
                'response_time': None,
                'error': str(e),
                'url': url,
                'url_type': "AWS NodePort (fallback)"
            }
            
    def wait_for_pods_recovery(self) -> Tuple[bool, float]:
        """Aguarda recuperação via CURL nos IPs dos pods usando threads, sem bloquear pelo get_pods_info."""
        import time
        from concurrent.futures import ThreadPoolExecutor

        start_time = time.time()
        timeout = self.config.current_recovery_timeout
        check_interval = 2.0

        print(f"⏳ Aguardando recuperação via CURL do sistema...")
        print(f"📊 Timeout: {timeout}s | Verificação a cada {check_interval}s")

        # def update_pods_info():
        #     while not stop_thread.is_set():
        #         info = self.kubectl.get_pods_info()
        #         with pods_lock:
        #             pods_info.clear()
        #             pods_info.extend(info)
        #         time.sleep(check_interval)
    
        stop_thread = threading.Event()

        def fetch(pod_info):
            pod_ip = pod_info.get('ip')
            pod_port = pod_info.get('port')
            pod_node = pod_info.get('node')
            pod_name = pod_info.get('name')

            if not pod_ip or not pod_port or not pod_node:
                print(f"❌ IP, porta ou node não encontrados para pod: {pod_name}")
                return False

            url = f"http://{pod_ip}:{pod_port}/"
            # print(f"   🔗 Testando: {url} via SSH no node {pod_node}")

            curl_cmd = f'curl -s -o /dev/null -w "%{{http_code}}" --max-time 3 {url}'
            try:
                curl_result = self.aws_injector._execute_ssh_command(
                    pod_node,
                    curl_cmd,
                    timeout=5
                )

                if curl_result[0] and curl_result[1].strip():
                    status_code = curl_result[1].strip()
                    if status_code in ['200', '404']:
                        print(f"   ✅ Aplicação respondeu: HTTP {status_code} (considerado ativo)")
                        return True
                    else:
                        print(f"   ❌ Aplicação com erro: HTTP {status_code}")
                        return False
                else:
                    print(f"   ❌ Curl falhou ou sem resposta")
                    return False
            except Exception as e:
                print(f"   ⚠️ Erro no curl: {e}")
                return False
            
        try:
            # tempo_get_pods_start = time.time()
            current_pods = self.kubectl.get_pods_info()
            # tempo_get_pods += time.time() - tempo_get_pods_start
            
            start_time = time.time()
            ultimo_tempo = time.time()
            
            tempo_get_pods = 0.0
            
            while time.time() - start_time < timeout:
                ultimo_tempo = time.time()

                elapsed = time.time() - start_time
                check_num = int(elapsed / check_interval) + 1

                print(f"\n🔍 Verificação #{check_num} (tempo: {elapsed:.1f}s/{timeout}s)")
                
                if current_pods:
                    with ThreadPoolExecutor(max_workers=len(current_pods)) as executor:
                        results = list(executor.map(fetch, current_pods))
                    all_healthy = all(results)
                    for idx, healthy in enumerate(results):
                        if not healthy:
                            print(f"❌ Pod {current_pods[idx]['name']} ainda não responde via curl")
                else:
                    all_healthy = False
                    

                if all_healthy and current_pods:
                    recovery_time = ultimo_tempo - start_time
                    # recovery_time = ultimo_tempo - start_time - tempo_get_pods
                    
                    print(f"🎉 Todos os pods responderam via curl (HTTP 200 ou 404)!")
                    print(f"⏱️ Tempo de recuperação: {recovery_time:.2f}s")
                    stop_thread.set()
                    return True, recovery_time
                
                tempo_get_pods_start = time.time()
                current_pods = self.kubectl.get_pods_info()
                tempo_get_pods += time.time() - tempo_get_pods_start
                    
                # print(f"⏸️ Aguardando {check_interval}s...")
                # time.sleep(check_interval)
            
            final_time = ultimo_tempo - start_time
            # final_time = ultimo_tempo - start_time - tempo_get_pods
            
            print(f"⏰ Timeout de {final_time:.1f}s atingido")
            print(f"⏰ Tempo de verificacao de pods {tempo_get_pods:.1f}s")
            
            stop_thread.set()
            return False, final_time
        except Exception as e:
            stop_thread.set()
            raise e
