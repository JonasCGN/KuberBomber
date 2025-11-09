import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import requests
from utils.kubectl_executor import KubectlExecutor
from failure_injectors.aws_injector import AWSFailureInjector

parent_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, parent_dir)


sM = KubectlExecutor(
    {
        "ssh_host": "3.237.204.249",
        "ssh_key": "~/.ssh/vockey.pem",
        "ssh_user": "ubuntu"
    }
)
awsFI = AWSFailureInjector(
        ssh_host= "3.237.204.249",
        ssh_key= "~/.ssh/vockey.pem",
        ssh_user= "ubuntu"
)

pods = sM.get_pods_info()
print("Pods encontrados:")
# for pod in pods:
#     print(f" - {pod}")

def fetch(pod):
    pod_ip = pod.get('ip')
    pod_port = pod.get('port')
    pod_node = pod.get('node')
    pod_name = pod.get('name')

    if not pod_ip or not pod_port or not pod_node:
        print(f"❌ IP, porta ou node não encontrados para pod: {pod_name}")
        return False

    url = f"http://{pod_ip}:{pod_port}/"
    print(f"   🔗 Testando: {url} via SSH no node {pod_node}")

    curl_cmd = f'curl -s -o /dev/null -w "%{{http_code}}" --max-time 3 {url}'
    try:
        curl_result = awsFI._execute_ssh_command(
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

start = time.time()
with ThreadPoolExecutor(max_workers=len(pods)) as executor:
    for _ in executor.map(fetch, pods):
        pass
end = time.time()

print(f"⏱️ Tempo total: {end - start:.2f}s")
