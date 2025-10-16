"""
Seletor Interativo
=================

Módulo para seleções interativas no terminal.
"""

import sys
import subprocess
import termios
import tty
from typing import List, Optional


class InteractiveSelector:
    """
    Seletor interativo para escolhas no terminal.
    
    Permite navegação com setas ou teclas w/s.
    """
    
    def __init__(self):
        """Inicializa o seletor interativo."""
        pass
    
    def get_single_char(self):
        """Lê um único caractere do terminal sem pressionar Enter."""
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                char = sys.stdin.read(1)
                return char
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except:
            return input("Pressione Enter: ")[0] if input("Pressione Enter: ") else '\n'
    
    def select_from_list(self, options: List[str], title: str) -> Optional[str]:
        """
        Seleção interativa genérica de uma lista.
        
        Args:
            options: Lista de opções para selecionar
            title: Título da seleção
            
        Returns:
            Opção selecionada ou None se cancelado
        """
        if not options:
            print(f"❌ Nenhuma opção disponível para {title}")
            return None
        
        if len(options) == 1:
            print(f"🎯 Apenas uma opção disponível: {options[0]}")
            return options[0]
        
        current_selection = 0
        
        def draw_menu():
            subprocess.run(['clear'], shell=True)
            print(f"🎯 {title}:")
            print("Use ↑/↓ (ou w/s) para navegar, Enter para confirmar, q para cancelar\n")
            
            for i, option in enumerate(options):
                if i == current_selection:
                    print(f"➤ {option} ⭐")
                else:
                    print(f"  {option}")
            
            print(f"\n🎯 Selecionado: {options[current_selection]}")
            print("📋 Controles: ↑/↓ ou w/s (navegar), Enter (confirmar), q (cancelar)")
        
        draw_menu()
        
        while True:
            try:
                char = self.get_single_char()
                
                if char in ['\r', '\n']:
                    selected = options[current_selection]
                    subprocess.run(['clear'], shell=True)
                    print(f"✅ Selecionado: {selected}")
                    return selected
                
                elif char in ['q', 'Q']:
                    subprocess.run(['clear'], shell=True)
                    print("❌ Seleção cancelada")
                    return None
                
                elif char in ['w', 'W']:
                    current_selection = (current_selection - 1) % len(options)
                    draw_menu()
                
                elif char in ['s', 'S']:
                    current_selection = (current_selection + 1) % len(options)
                    draw_menu()
                
                elif ord(char) == 27:
                    try:
                        next_chars = sys.stdin.read(2)
                        if next_chars == '[A':
                            current_selection = (current_selection - 1) % len(options)
                            draw_menu()
                        elif next_chars == '[B':
                            current_selection = (current_selection + 1) % len(options)
                            draw_menu()
                    except:
                        pass
                
            except KeyboardInterrupt:
                subprocess.run(['clear'], shell=True)
                print("❌ Teste cancelado")
                return None