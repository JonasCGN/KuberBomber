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
    _control_plane_cache = None
    _control_plane_cache_time = None
    _cache_duration = 60  # Cache por 60 segundos
    
    def __init__(self, aws_config: Optional[dict] = None):
        """
        Inicializa o verificador de saúde.
        
        Args:
            aws_config: Configuração AWS para conexão remota
        """
        self.aws_config = aws_config
        self.is_aws_mode = aws_config is not None

        if self.is_aws_mode and aws_config:
            # MODO AWS: Usar APENAS aws_injector com descoberta automática
            print("🔧 Inicializando AWS injector com descoberta automática...")
            from ..failure_injectors.aws_injector import AWSFailureInjector
            self.aws_injector = AWSFailureInjector(
                ssh_key=aws_config['ssh_key'],
                ssh_user=aws_config['ssh_user'],
                aws_config=aws_config  # Passar config completo para discovery
            )
            print("✅ AWS injector configurado - injetores locais não serão usados")
        
        self.config = get_config(aws_mode=self.is_aws_mode)
        self.kubectl = KubectlExecutor(aws_config=aws_config if self.is_aws_mode else None)
    
    def _get_cached_control_plane(self, verbose: bool = True):
        """
        Obtém control plane com cache para evitar descobertas repetidas.
        
        Args:
            verbose: Se deve imprimir mensagens (apenas na primeira descoberta)
            
        Returns:
            IP do control plane ou None se não encontrado
        """
        import time
        
        # Verificar se o cache ainda é válido
        current_time = time.time()
        if (self._control_plane_cache is not None and 
            self._control_plane_cache_time is not None and
            current_time - self._control_plane_cache_time < self._cache_duration):
            return self._control_plane_cache
            
        # Cache expirou ou não existe, fazer nova descoberta
        if verbose and self._control_plane_cache is None:
            print("🔍 Descobrindo control plane automaticamente...")
            
        from ..utils.control_plane_discovery import ControlPlaneDiscovery
        discovery = ControlPlaneDiscovery(self.aws_config)
        control_plane_ip = discovery.discover_control_plane_ip()
        
        if control_plane_ip:
            # Atualizar cache
            self._control_plane_cache = control_plane_ip
            self._control_plane_cache_time = current_time
            
            if verbose and not self._discovery_logged:
                print(f"✅ Control plane descoberto: ControlPlane ({control_plane_ip})")
                self._discovery_logged = True
                
            return control_plane_ip
        else:
            if verbose:
                print("❌ Control plane não encontrado")
            return None
    
    def _clear_control_plane_cache(self):
        """Limpa o cache do control plane (útil para testes ou quando há mudanças)."""
        self._control_plane_cache = None
        self._control_plane_cache_time = None
        self._discovery_logged = False
        
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
            # Descobrir aplicações dinamicamente via kubectl
            aws_apps = self._discover_app_names()
            if verbose:
                print(f"📱 Testando aplicações AWS via control plane: {aws_apps}")
            
            for app in aws_apps:
                if verbose:
                    print(f"🔍 Verificando {app}...")
                results[app] = self.check_application_health(app, verbose=verbose)
            
            return results
    
    def _discover_app_names(self) -> List[str]:
        """
        Descobre dinamicamente nomes de aplicações baseado nos pods em execução.
        Procura por pods que terminam com padrões de aplicação.
        
        Returns:
            Lista com nomes das aplicações descobertas
        """
        try:
            result = self.kubectl.execute_kubectl(['get', 'pods', '-o', 'json'])
            
            if not result['success']:
                print(f"⚠️ Erro ao descobrir aplicações: {result.get('error', 'Unknown error')}")
                return []
            
            import json
            pods_data = json.loads(result['output'])
            app_names = set()
            
            # Procurar pods que seguem padrão nome-app-*
            for pod in pods_data.get('items', []):
                pod_name = pod['metadata']['name']
                
                # Procurar por pods que têm padrão app-name-hash-hash
                if '-app-' in pod_name:
                    # Extrair nome da aplicação: foo-app-69bc4fffc-b82p9 -> foo-app
                    parts = pod_name.split('-')
                    for i, part in enumerate(parts):
                        if part == 'app' and i > 0:
                            app_name = '-'.join(parts[:i+1])  # foo-app
                            app_names.add(app_name)
                            break
            
            return sorted(list(app_names))
            
        except Exception as e:
            print(f"⚠️ Erro ao descobrir aplicações: {e}")
            return []
        
    
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
            app_name: Nome da aplicação (ex: 'myapp-app')
            
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
            service_name: Nome do serviço (ex: 'myapp-app')
            
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
                # app-name -> app-loadbalancer, app-service
                # Exemplo: foo-app -> foo-loadbalancer, foo-service
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
        Verifica saúde de aplicação AWS usando descoberta automática de serviços.
        
        Args:
            service: Nome do serviço (ex: myapp-app)
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
        
        # Descobrir serviços LoadBalancer automaticamente via kubectl get svc
        app_base = service.replace('-app', '')  # myapp-app -> myapp
        
        try:
            # Obter informações de TODOS os serviços LoadBalancer
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
            loadbalancer_url = None
            
            # Procurar serviços LoadBalancer
            for svc in services_data.get('items', []):
                svc_name = svc['metadata']['name']
                svc_type = svc['spec'].get('type', '')
                
                # Verificar se é um serviço LoadBalancer para nossa aplicação
                if (svc_name.startswith(f"{app_base}-") and svc_type == 'LoadBalancer'):
                    ingress = svc['status'].get('loadBalancer', {}).get('ingress', [])
                    if ingress and ingress[0].get('ip'):
                        lb_ip = ingress[0]['ip']
                        ports = svc['spec'].get('ports', [])
                        if ports:
                            lb_port = ports[0].get('port', 80)
                            endpoint = f"/{app_base}"  # /foo, /bar, /test
                            loadbalancer_url = f"http://{lb_ip}:{lb_port}{endpoint}"
                            break
            
            if not loadbalancer_url:
                if verbose:
                    print(f"❌ LoadBalancer não encontrado para {app_base}-*")
                return {
                    'healthy': False,
                    'error': f'LoadBalancer não encontrado para {app_base}-*',
                    'status_code': None,
                    'response_time': None,
                    'url': None,
                    'url_type': 'LoadBalancer Missing'
                }
            
            # Usar a URL do LoadBalancer descoberta
            ssh_host = self.aws_config['ssh_host']
            
            # Usar a URL do LoadBalancer descoberta
            test_url = loadbalancer_url
            
            if verbose:
                print(f"🌐 Verificando {service} via LoadBalancer: {test_url}")
            
            # Usar aws_injector para executar curl no control plane
            from ..failure_injectors.aws_injector import AWSFailureInjector
            
            ssh_key = self.aws_config['ssh_key']
            ssh_user = self.aws_config['ssh_user']
            aws_injector = AWSFailureInjector(
                ssh_key=ssh_key,
                ssh_user=ssh_user,
                aws_config=self.aws_config  # Passar config completo para discovery
            )
            
            # Executar curl no control plane via SSH usando aws_injector
            curl_cmd = f"curl -sS -o /dev/null -w '%{{http_code}} %{{time_total}}' --max-time 5 '{test_url}'"
            
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
                    'url': test_url,
                    'url_type': "LoadBalancer via Control Plane"
                }

            node_name = control_plane_node
            
            curl_result = aws_injector._execute_ssh_command(control_plane_node, curl_cmd, timeout=15)
            
            if not curl_result[0]:
                # Se não conseguir acessar o LoadBalancer, retornar erro
                if verbose:
                    print(f"⚠️ LoadBalancer não acessível via control plane")
                
                return {
                    'healthy': False,
                    'error': f'LoadBalancer não acessível: {curl_result[1] if curl_result[1] else "Connection failed"}',
                    'status_code': None,
                    'response_time': None,
                    'url': test_url,
                    'url_type': 'LoadBalancer via Control Plane'
                }
            
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
                        'url': test_url,
                        'url_type': "LoadBalancer via Control Plane"
                    }
            else:
                return {
                    'healthy': False,
                    'response_time': None,
                    'error': 'Invalid curl response',
                    'url': test_url,
                    'url_type': "LoadBalancer via Control Plane"
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
    
    def _check_aws_application_health_fallback(self, service: str, verbose: bool = True) -> Dict:
        """
        Fallback para verificação AWS - retorna erro pois NodePort foi removido.
        """
        return {
            'healthy': False,
            'error': 'NodePort support removed - use LoadBalancer services only',
            'status_code': None,
            'response_time': None,
            'url': None,
            'url_type': 'NodePort Deprecated'
        }
            
    def check_pods_running_status(self, verbose: bool = True) -> Tuple[bool, Dict]:
        """
        Verifica se todos os pods estão no status 'Running' e prontos.
        
        Args:
            verbose: Se deve imprimir mensagens detalhadas
            
        Returns:
            Tuple com (todos_pods_running, detalhes_pods)
        """
        try:
            result = self.kubectl.execute_kubectl(['get', 'pods', '-o', 'json'])
            
            if not result['success']:
                if verbose:
                    print(f"❌ Erro ao obter pods: {result.get('error', 'Unknown error')}")
                return False, {}
            
            import json
            pods_data = json.loads(result['output'])
            pod_details = {}
            all_running = True
            
            for pod in pods_data.get('items', []):
                pod_name = pod['metadata']['name']
                pod_status = pod['status'].get('phase', 'Unknown')
                
                # Verificar se está Ready
                ready = False
                conditions = pod['status'].get('conditions', [])
                for condition in conditions:
                    if condition['type'] == 'Ready':
                        ready = condition['status'] == 'True'
                        break
                
                # Contar restarts
                restarts = 0
                container_statuses = pod['status'].get('containerStatuses', [])
                if container_statuses:
                    restarts = container_statuses[0].get('restartCount', 0)
                
                pod_details[pod_name] = {
                    'status': pod_status,
                    'ready': ready,
                    'restarts': restarts,
                    'running_and_ready': pod_status == 'Running' and ready
                }
                
                if not (pod_status == 'Running' and ready):
                    all_running = False
                
                if verbose:
                    emoji = "✅" if pod_status == 'Running' and ready else "❌"
                    print(f"  {emoji} {pod_name}: {pod_status}, Ready: {ready}, Restarts: {restarts}")
            
            if verbose:
                ready_pods = sum(1 for details in pod_details.values() if details['running_and_ready'])
                total_pods = len(pod_details)
                print(f"📊 Pods Running e Ready: {ready_pods}/{total_pods}")
            
            return all_running, pod_details
            
        except Exception as e:
            if verbose:
                print(f"❌ Erro ao verificar status dos pods: {e}")
            return False, {}
    
    def check_pods_via_curl(self, verbose: bool = True) -> Tuple[bool, Dict]:
        """
        Verifica se todos os pods respondem via curl no control plane.
        
        Args:
            verbose: Se deve imprimir mensagens detalhadas
            
        Returns:
            Tuple com (todos_pods_respondem, detalhes_responses)
        """
        try:
            # Obter informações dos pods com IPs
            pods_info = self.kubectl.get_pods_info()
            
            if not pods_info:
                if verbose:
                    print("❌ Nenhuma informação de pods obtida")
                return False, {}
            
            response_details = {}
            all_responding = True
            
            if verbose:
                print(f"🌐 Testando {len(pods_info)} pods via curl...")
            
            for pod_info in pods_info:
                pod_name = pod_info.get('name')
                pod_ip = pod_info.get('ip')
                pod_port = pod_info.get('port')
                pod_node = pod_info.get('node')
                
                if not pod_ip or not pod_port:
                    if verbose:
                        print(f"  ❌ {pod_name}: IP ou porta não encontrados")
                    response_details[pod_name] = {
                        'responding': False,
                        'error': 'IP ou porta não encontrados',
                        'status_code': None
                    }
                    all_responding = False
                    continue
                
                # Fazer curl via SSH se estiver em modo AWS
                url = f"http://{pod_ip}:{pod_port}/"
                
                try:
                    if self.is_aws_mode and hasattr(self, 'aws_injector') and self.aws_injector:
                        # Usar SSH para fazer curl no control plane
                        if not pod_node:
                            response_details[pod_name] = {
                                'responding': False,
                                'error': 'Node não encontrado para SSH',
                                'url': url,
                                'method': 'SSH curl'
                            }
                            all_responding = False
                            if verbose:
                                print(f"  ❌ {pod_name}: Node não encontrado para SSH")
                            continue
                            
                        curl_cmd = f'curl -s -o /dev/null -w "%{{http_code}}" --max-time 3 {url}'
                        curl_result = self.aws_injector._execute_ssh_command(
                            pod_node,
                            curl_cmd,
                            timeout=5,
                            show_print=False
                        )
                        
                        if curl_result[0] and curl_result[1].strip():
                            status_code = curl_result[1].strip()
                            responding = status_code in ['200', '404']  # 404 também é válido (app ativa)
                            
                            response_details[pod_name] = {
                                'responding': responding,
                                'status_code': status_code,
                                'url': url,
                                'method': 'SSH curl'
                            }
                            
                            if verbose:
                                emoji = "✅" if responding else "❌"
                                print(f"  {emoji} {pod_name}: HTTP {status_code} ({url})")
                        else:
                            response_details[pod_name] = {
                                'responding': False,
                                'error': 'Curl falhou ou sem resposta',
                                'url': url,
                                'method': 'SSH curl'
                            }
                            all_responding = False
                            
                            if verbose:
                                print(f"  ❌ {pod_name}: Curl falhou ({url})")
                    else:
                        # Modo local - usar curl direto
                        import subprocess
                        result = subprocess.run(
                            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '3', url],
                            capture_output=True, text=True, timeout=5
                        )
                        
                        if result.returncode == 0:
                            status_code = result.stdout.strip()
                            responding = status_code in ['200', '404']
                            
                            response_details[pod_name] = {
                                'responding': responding,
                                'status_code': status_code,
                                'url': url,
                                'method': 'Local curl'
                            }
                            
                            if verbose:
                                emoji = "✅" if responding else "❌"
                                print(f"  {emoji} {pod_name}: HTTP {status_code} ({url})")
                        else:
                            response_details[pod_name] = {
                                'responding': False,
                                'error': result.stderr.strip() or 'Curl failed',
                                'url': url,
                                'method': 'Local curl'
                            }
                            all_responding = False
                            
                            if verbose:
                                print(f"  ❌ {pod_name}: {result.stderr.strip() or 'Curl failed'} ({url})")
                    
                    if not response_details[pod_name]['responding']:
                        all_responding = False
                        
                except Exception as e:
                    response_details[pod_name] = {
                        'responding': False,
                        'error': str(e),
                        'url': url
                    }
                    all_responding = False
                    
                    if verbose:
                        print(f"  ❌ {pod_name}: Erro no curl - {e}")
            
            if verbose:
                responding_pods = sum(1 for details in response_details.values() if details['responding'])
                total_pods = len(response_details)
                print(f"📊 Pods respondendo via curl: {responding_pods}/{total_pods}")
            
            return all_responding, response_details
            
        except Exception as e:
            if verbose:
                print(f"❌ Erro ao verificar pods via curl: {e}")
            return False, {}
    
    def check_pods_combined(self, verbose: bool = True) -> Tuple[bool, Dict]:
        """
        Verifica pods usando ambos os métodos: running status e curl.
        
        Args:
            verbose: Se deve imprimir mensagens detalhadas
            
        Returns:
            Tuple com (todos_pods_saudaveis, detalhes_combinados)
        """
        if verbose:
            print("🔍 === VERIFICAÇÃO COMBINADA DE PODS ===")
        
        # Verificar status running
        if verbose:
            print("📋 Verificando status 'Running' dos pods...")
        all_running, running_details = self.check_pods_running_status(verbose=verbose)
        
        # Verificar via curl
        if verbose:
            print("\n🌐 Verificando pods via curl...")
        all_responding, curl_details = self.check_pods_via_curl(verbose=verbose)
        
        # Combinar resultados
        combined_details = {}
        all_healthy = True
        
        # Usar pods do running_details como base
        for pod_name in running_details.keys():
            running_info = running_details[pod_name]
            curl_info = curl_details.get(pod_name, {'responding': False, 'error': 'Pod not found in curl check'})
            
            pod_healthy = running_info['running_and_ready'] and curl_info['responding']
            
            combined_details[pod_name] = {
                'running_and_ready': running_info['running_and_ready'],
                'status': running_info['status'],
                'ready': running_info['ready'],
                'restarts': running_info['restarts'],
                'responding_curl': curl_info['responding'],
                'curl_status_code': curl_info.get('status_code'),
                'curl_error': curl_info.get('error'),
                'healthy': pod_healthy
            }
            
            if not pod_healthy:
                all_healthy = False
        
        if verbose:
            print("\n📊 === RESULTADO COMBINADO ===")
            healthy_pods = sum(1 for details in combined_details.values() if details['healthy'])
            total_pods = len(combined_details)
            print(f"✅ Pods saudáveis (Running + Respondendo): {healthy_pods}/{total_pods}")
            
            for pod_name, details in combined_details.items():
                emoji = "✅" if details['healthy'] else "❌"
                status_msg = "Saudável" if details['healthy'] else "Problema"
                print(f"  {emoji} {pod_name}: {status_msg}")
                if not details['healthy']:
                    if not details['running_and_ready']:
                        print(f"    📋 Status: {details['status']}, Ready: {details['ready']}")
                    if not details['responding_curl']:
                        print(f"    🌐 Curl: {details.get('curl_error', 'Não respondendo')}")
        
        return all_healthy, combined_details
    
    def wait_for_pods_recovery_combined(self, timeout: Optional[int] = None) -> Tuple[bool, float]:
        """
        Aguarda recuperação dos pods usando verificação combinada (running + curl).
        
        Args:
            timeout: Timeout específico em segundos. Se None, usa o timeout global.
            
        Returns:
            Tuple com (recuperou_com_sucesso, tempo_de_recuperacao)
        """
        import time
        
        if timeout is None:
            timeout = self.config.current_recovery_timeout
        
        print(f"⏳ Aguardando recuperação combinada (running + curl)")
        print(f"📊 Timeout: {timeout}s")
        
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            check_count += 1
            
            print(f"\n🔍 Verificação #{check_count} (tempo: {elapsed:.1f}s/{timeout}s)")
            
            # Verificar pods de forma combinada
            all_healthy, pod_details = self.check_pods_combined(verbose=True)
            
            if all_healthy:
                recovery_time = time.time() - start_time
                print(f"\n✅ Todos os pods recuperados (running + curl) em {recovery_time:.2f}s")
                return True, recovery_time
            else:
                unhealthy_pods = [name for name, details in pod_details.items() if not details['healthy']]
                print(f"⚠️ Pods ainda com problemas: {len(unhealthy_pods)} de {len(pod_details)}")
                for pod_name in unhealthy_pods:
                    details = pod_details[pod_name]
                    issues = []
                    if not details['running_and_ready']:
                        issues.append(f"Status: {details['status']}")
                    if not details['responding_curl']:
                        issues.append("Não responde curl")
                    print(f"  ❌ {pod_name}: {', '.join(issues)}")
            
            print(f"⏸️ Aguardando {self.config.health_check_interval}s antes da próxima verificação...")
            time.sleep(self.config.health_check_interval)
        
        print(f"❌ Timeout: Pods não se recuperaram (running + curl) em {timeout}s")
        return False, timeout
    
    def check_pods_combined_silent(self, timeout: int = 5) -> Tuple[bool, Dict]:
        """
        Versão silenciosa da verificação combinada - aguarda kubectl funcionar primeiro.
        
        Args:
            timeout: Timeout em segundos para a verificação
            
        Returns:
            tuple: (bool sucesso, dict detalhes)
        """
        # Verificar status Running (silenciosamente)
        all_running, running_details = self.check_pods_running_status(verbose=False)
        
        # Se kubectl não está funcionando, retornar falha
        if not running_details:
            print("❌ Kubectl indisponível - aguardando recuperação...")
            return False, {}
        
        # Verificar curl (silenciosamente) 
        all_responding, curl_details = self.check_pods_via_curl(verbose=False)
        
        # Combinar resultados em formato de tabela
        all_pods = {}
        
        # Processar pods com status Running
        for pod_name in running_details.keys():
            running_info = running_details[pod_name]
            all_pods[pod_name] = {
                'name': pod_name,
                'running': running_info['running_and_ready'],
                'responding': False,
                'kubectl_status': f"{running_info['status']}/{running_info['ready']}",
                'curl_status': 'Pending'
            }
        
        # Processar pods com curl
        for pod_name in curl_details.keys():
            curl_info = curl_details[pod_name]
            if pod_name in all_pods:
                all_pods[pod_name]['responding'] = curl_info['responding']
                if curl_info['responding']:
                    all_pods[pod_name]['curl_status'] = 'OK'
                else:
                    error_msg = curl_info.get('error', 'Failed')
                    all_pods[pod_name]['curl_status'] = error_msg[:10] + "..." if len(error_msg) > 10 else error_msg
        
        # Mostrar tabela resumo
        print("\\n📊 Status (Kubectl + Curl):")
        print("─" * 70)
        print(f"{'Pod Name':<30} {'Kubectl':<15} {'Curl':<15}")
        print("─" * 70)
        
        for pod_name, pod_info in sorted(all_pods.items()):
            kubectl_display = "✅ Ready" if pod_info['running'] else f"❌ {pod_info['kubectl_status']}"
            curl_display = "✅ OK" if pod_info['responding'] else f"❌ {pod_info['curl_status']}"
            print(f"{pod_name:<30} {kubectl_display:<15} {curl_display:<15}")
        
        # Contar pods saudáveis
        healthy_count = sum(1 for pod in all_pods.values() 
                          if pod['running'] and pod['responding'])
        total_count = len(all_pods)
        
        print("─" * 70)
        print(f"📊 Resumo: {healthy_count}/{total_count} pods saudáveis")
        
        # Preparar detalhes de retorno
        combined_details = {}
        for pod_name, pod_info in all_pods.items():
            running_info = running_details.get(pod_name, {})
            curl_info = curl_details.get(pod_name, {})
            
            combined_details[pod_name] = {
                'running_and_ready': pod_info['running'],
                'responding_curl': pod_info['responding'],
                'healthy': pod_info['running'] and pod_info['responding'],
                'status': running_info.get('status', 'Unknown'),
                'ready': running_info.get('ready', False),
                'restarts': running_info.get('restarts', 0),
                'curl_status_code': curl_info.get('status_code'),
                'curl_error': curl_info.get('error')
            }
        
        return healthy_count == total_count, combined_details

    def wait_for_pods_recovery_combined_silent(self, timeout: Optional[int] = None) -> Tuple[bool, float]:
        """
        Versão silenciosa da espera por recuperação combinada.
        Aguarda o kubectl voltar a funcionar primeiro, depois verifica pods.
        
        Args:
            timeout: Timeout específico em segundos. Se None, usa o timeout global.
            
        Returns:
            Tuple com (recuperou_com_sucesso, tempo_de_recuperacao)
        """
        import time
        
        if timeout is None:
            timeout = self.config.current_recovery_timeout
        
        print(f"⏳ Verificação combinada (timeout: {timeout}s)")
        
        start_time = time.time()
        check_count = 0
        kubectl_working = False
        
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            check_count += 1
            
            print(f"\\n🔍 Verificação #{check_count} ({elapsed:.1f}s/{timeout}s)")
            
            # Se kubectl não está funcionando, mostrar status especial
            if not kubectl_working:
                # Testar se kubectl está funcionando
                result = self.kubectl.execute_kubectl(['get', 'pods', '-o', 'json'])
                
                if not result['success']:
                    print(f"⚠️ Kubectl indisponível: {result.get('error', 'Connection refused')}")
                    print("📊 Aguardando kubectl voltar a funcionar...")
                    print(f"⏸️ Aguardando {self.config.health_check_interval}s...")
                    time.sleep(self.config.health_check_interval)
                    continue
                else:
                    kubectl_working = True
                    print("✅ Kubectl voltou a funcionar!")
            
            # Verificar pods de forma combinada e silenciosa
            all_healthy, pod_details = self.check_pods_combined_silent()
            
            if all_healthy and pod_details:  # Garantir que há pods para verificar
                recovery_time = time.time() - start_time
                print(f"\\n✅ Recuperação completa em {recovery_time:.2f}s")
                return True, recovery_time
            
            print(f"⏸️ Aguardando {self.config.health_check_interval}s...")
            time.sleep(self.config.health_check_interval)
        
        print(f"❌ Timeout: {timeout}s esgotado")
        return False, timeout
    
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
