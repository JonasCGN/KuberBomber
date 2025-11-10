from pynput.mouse import Controller, Button
import time

unidade = "s"  # "s" para segundos, "h" para horas
valor = 5      # intervalo

intervalo = valor * 3600 if unidade == "h" else valor

print(f"Iniciando cliques a cada {intervalo} segundos...")

mouse = Controller()

try:
    while True:
        pos = mouse.position  # pega a posição atual
        mouse.position = pos  # garante que o cursor "mantenha" a posição
        mouse.click(Button.left)
        print(f"Clique em {pos}")
        time.sleep(intervalo)
except KeyboardInterrupt:
    print("Auto clicker interrompido.") 
