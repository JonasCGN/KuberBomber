import requests
import time
import statistics

URL = "http://hpalb-1951537090.us-east-1.elb.amazonaws.com/bar"

def medir_respostas(n_requisicoes, repeticoes=100):
    tempos = []
    for _ in range(repeticoes):
        inicio = time.time()
        for _ in range(n_requisicoes):
            try:
                requests.get(URL, timeout=10)
            except Exception as e:
                print(f"Erro: {e}")
        fim = time.time()
        tempos.append(fim - inicio)
    media = statistics.mean(tempos)
    return media

if __name__ == "__main__":
    for n in [1, 2, 3]:
        media = medir_respostas(n)
        print(f"Média de tempo para {n} requisição(ões) (100 repetições): {media:.4f} segundos")
