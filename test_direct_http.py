#!/usr/bin/env python3
"""
Teste direto HTTP sem usar kubectl.
"""

import requests
import time

def test_direct_http():
    """Testa HTTP diretamente nas aplicações AWS."""
    
    host = "3.235.58.98"
    apps = [
        {'name': 'foo', 'port': 30081, 'path': '/foo'},
        {'name': 'bar', 'port': 30082, 'path': '/bar'},
        {'name': 'test', 'port': 30083, 'path': '/test'}
    ]
    
    print("🌐 === TESTE HTTP DIRETO ===")
    print(f"Host: {host}")
    print()
    
    for app in apps:
        name = app['name']
        port = app['port']
        path = app['path']
        url = f"http://{host}:{port}{path}"
        
        print(f"🔍 {name}: {url}")
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=10)
            end_time = time.time()
            
            response_time = end_time - start_time
            status = response.status_code
            
            if status == 200:
                print(f"   ✅ OK - {status} ({response_time:.3f}s)")
                print(f"   📄 Conteúdo: {response.text[:100]}...")
            else:
                print(f"   ⚠️ Status {status} ({response_time:.3f}s)")
                print(f"   📄 Conteúdo: {response.text[:100]}...")
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ TIMEOUT (>10s)")
        except requests.exceptions.ConnectionError:
            print(f"   ❌ CONEXÃO RECUSADA")
        except Exception as e:
            print(f"   ❌ ERRO: {e}")
        
        print()
    
    print("🏁 Teste finalizado")

if __name__ == "__main__":
    test_direct_http()