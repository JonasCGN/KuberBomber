"""
CSV Reporter em Tempo Real
=========================

Gerador de relatórios em formato CSV com escrita em tempo real
durante a execução dos testes.
"""

import os
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class CSVReporter:
    """
    ⭐ GERADOR DE RELATÓRIOS CSV EM TEMPO REAL ⭐
    
    Gerador de relatórios CSV para resultados de testes de confiabilidade
    com escrita em tempo real durante a execução dos testes.
    
    Organiza resultados em estrutura de pastas por data (ano/mês/dia)
    e salva tanto dados de iterações quanto métricas de componentes.
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Inicializa o gerador de relatórios CSV.
        
        Args:
            base_dir: Diretório base para salvar relatórios
        """
        if base_dir is None:
            # Usar diretório atual por padrão
            base_dir = "."
        
        self.base_dir = base_dir
        self.current_file = None
        self.current_writer = None
        self.current_csvfile = None
        self._is_realtime_active = False
    
    def _create_date_directory(self) -> str:
        """
        Cria estrutura de diretórios por data (ano/mês/dia).
        
        Returns:
            Caminho do diretório criado
        """
        now = datetime.now()
        year = now.strftime('%Y')
        month = now.strftime('%m')
        day = now.strftime('%d')
        
        date_dir = os.path.join(self.base_dir, year, month, day)
        os.makedirs(date_dir, exist_ok=True)
        
        return date_dir
    
    def start_realtime_report(self, component_type: str, failure_method: str, target: str) -> str:
        """
        ⭐ INICIA RELATÓRIO CSV EM TEMPO REAL ⭐
        
        Inicia relatório CSV que é escrito em tempo real durante o teste.
        Cada iteração é salva imediatamente no arquivo.
        
        Args:
            component_type: Tipo do componente testado
            failure_method: Método de falha usado
            target: Alvo específico testado
            
        Returns:
            Caminho do arquivo criado
        """
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        date_dir = self._create_date_directory()
        
        # Nome do arquivo com informações do teste
        filename = f"realtime_reliability_test_{component_type}_{failure_method}_{timestamp}.csv"
        filepath = os.path.join(date_dir, filename)
        
        # Campos do CSV
        fieldnames = [
            'iteration', 'component_type', 'component_id', 'failure_method',
            'executed_command', 'failure_timestamp', 'recovery_time_seconds',
            'total_time_seconds', 'recovered', 'initial_healthy_apps',
            'test_progress', 'real_time_saved'
        ]
        
        try:
            self.current_csvfile = open(filepath, 'w', newline='', encoding='utf-8')
            self.current_writer = csv.DictWriter(self.current_csvfile, fieldnames=fieldnames)
            self.current_writer.writeheader()
            self.current_csvfile.flush()  # Forçar escrita do cabeçalho
            self.current_file = filepath
            self._is_realtime_active = True
            
            print(f"📊 📝 Relatório em tempo real iniciado: {filepath}")
            print(f"⚡ CSV será atualizado a cada iteração concluída")
            return filepath
            
        except Exception as e:
            print(f"❌ Erro ao iniciar relatório em tempo real: {e}")
            return ""
    
    def add_realtime_result(self, result: Dict, total_iterations: Optional[int] = None):
        """
        ⭐ ADICIONA RESULTADO AO CSV EM TEMPO REAL ⭐
        
        Adiciona resultado de uma iteração ao CSV imediatamente,
        sem aguardar o fim do teste.
        
        Args:
            result: Dicionário com resultado da iteração
            total_iterations: Total de iterações do teste (para cálculo de progresso)
        """
        if not self._is_realtime_active or not self.current_writer or not self.current_csvfile:
            print("⚠️ Relatório em tempo real não foi iniciado")
            return
        
        try:
            # Filtrar apenas campos que existem no CSV
            fieldnames = self.current_writer.fieldnames
            csv_result = {k: v for k, v in result.items() if k in fieldnames}
            
            # Adicionar informações em tempo real
            csv_result['real_time_saved'] = datetime.now().isoformat()
            
            if total_iterations and 'iteration' in result:
                progress = (result['iteration'] / total_iterations) * 100
                csv_result['test_progress'] = f"{progress:.1f}%"
            
            self.current_writer.writerow(csv_result)
            self.current_csvfile.flush()  # ⭐ FORÇAR ESCRITA IMEDIATA ⭐
            
            iteration_num = result.get('iteration', '?')
            recovery_time = result.get('recovery_time_seconds', 0)
            recovered = result.get('recovered', False)
            
            print(f"📊 ✅ Iteração {iteration_num} salva em tempo real!")
            print(f"   ⏱️ MTTR: {recovery_time:.2f}s | Recuperou: {'✅' if recovered else '❌'}")
            print(f"   📁 Arquivo: {os.path.basename(self.current_file) if self.current_file else 'N/A'}")
            
        except Exception as e:
            print(f"❌ Erro ao salvar resultado em tempo real: {e}")
    
    def update_realtime_progress(self, iteration: int, total_iterations: int, message: str = ""):
        """
        Atualiza progresso no arquivo em tempo real com uma linha de status.
        
        Args:
            iteration: Iteração atual
            total_iterations: Total de iterações
            message: Mensagem adicional
        """
        if not self._is_realtime_active:
            return
        
        progress = (iteration / total_iterations) * 100
        status_msg = f"Progresso: {iteration}/{total_iterations} ({progress:.1f}%)"
        if message:
            status_msg += f" - {message}"
        
        print(f"📊 {status_msg}")
    
    def finish_realtime_report(self, summary_stats: Optional[Dict] = None):
        """
        ⭐ FINALIZA RELATÓRIO CSV EM TEMPO REAL ⭐
        
        Finaliza o relatório em tempo real e opcionalmente adiciona
        estatísticas de resumo.
        
        Args:
            summary_stats: Estatísticas finais para adicionar (opcional)
        """
        try:
            if summary_stats and self.current_writer and self.current_csvfile:
                # Adicionar linha de resumo ao final
                summary_row = {
                    'iteration': 'RESUMO',
                    'component_type': summary_stats.get('component_type', ''),
                    'component_id': summary_stats.get('target', ''),
                    'failure_method': summary_stats.get('failure_method', ''),
                    'executed_command': f"Total: {summary_stats.get('total_iterations', 0)} iterações",
                    'failure_timestamp': datetime.now().isoformat(),
                    'recovery_time_seconds': summary_stats.get('average_mttr', 0),
                    'total_time_seconds': summary_stats.get('total_test_time', 0),
                    'recovered': f"{summary_stats.get('success_rate', 0):.1f}% sucesso",
                    'initial_healthy_apps': '',
                    'test_progress': '100%',
                    'real_time_saved': datetime.now().isoformat()
                }
                
                self.current_writer.writerow(summary_row)
                self.current_csvfile.flush()
            
            if self.current_csvfile:
                self.current_csvfile.close()
                print(f"✅ 📝 Relatório em tempo real finalizado: {self.current_file}")
                print(f"📊 Dados salvos continuamente durante todo o teste")
            
            self.current_csvfile = None
            self.current_writer = None
            self.current_file = None
            self._is_realtime_active = False
            
        except Exception as e:
            print(f"❌ Erro ao finalizar relatório: {e}")
    
    def start_simulation_report(self) -> str:
        """
        Inicia relatório de simulação acelerada em tempo real.
        
        Returns:
            Caminho do arquivo criado
        """
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        date_dir = self._create_date_directory()
        
        filename = f"realtime_accelerated_simulation_{timestamp}.csv"
        filepath = os.path.join(date_dir, filename)
        
        fieldnames = [
            'failure_number', 'simulation_time_hours', 'real_time_seconds', 
            'target', 'failure_method', 'executed_command', 
            'recovery_time_seconds', 'recovered', 'failure_interval_hours',
            'real_time_saved'
        ]
        
        try:
            self.current_csvfile = open(filepath, 'w', newline='', encoding='utf-8')
            self.current_writer = csv.DictWriter(self.current_csvfile, fieldnames=fieldnames)
            self.current_writer.writeheader()
            self.current_csvfile.flush()
            self.current_file = filepath
            self._is_realtime_active = True
            
            print(f"⚡ 📝 Relatório de simulação em tempo real iniciado: {filepath}")
            return filepath
            
        except Exception as e:
            print(f"❌ Erro ao iniciar relatório de simulação: {e}")
            return ""
    
    def add_simulation_record(self, record: Dict, failure_number: int):
        """
        Adiciona registro de falha à simulação em tempo real.
        
        Args:
            record: Registro da falha
            failure_number: Número da falha
        """
        if not self._is_realtime_active or not self.current_writer or not self.current_csvfile:
            print("⚠️ Relatório de simulação não foi iniciado")
            return
        
        try:
            row = {
                'failure_number': failure_number,
                'simulation_time_hours': record['simulation_time_hours'],
                'real_time_seconds': record['real_time_seconds'],
                'target': record['target'],
                'failure_method': record['failure_method'],
                'executed_command': record['executed_command'],
                'recovery_time_seconds': record['recovery_time_seconds'],
                'recovered': record['recovered'],
                'failure_interval_hours': record['failure_interval_hours'],
                'real_time_saved': datetime.now().isoformat()
            }
            
            self.current_writer.writerow(row)
            self.current_csvfile.flush()  # ⭐ ESCRITA IMEDIATA ⭐
            
            print(f"⚡ 📊 Falha #{failure_number} salva em tempo real")
            
        except Exception as e:
            print(f"❌ Erro ao salvar registro de simulação: {e}")
    
    def save_component_metrics(self, component_metrics: Dict, suffix: str = ""):
        """
        Salva métricas individuais por componente em CSV.
        
        Args:
            component_metrics: Dicionário com métricas por componente
            suffix: Sufixo para o nome do arquivo
        """
        if not component_metrics:
            print("📊 Nenhuma métrica de componente para salvar")
            return
        
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        date_dir = self._create_date_directory()
        
        filename_suffix = f"_{suffix}" if suffix else ""
        filename = f"component_metrics{filename_suffix}_{timestamp}.csv"
        filepath = os.path.join(date_dir, filename)
        
        # Campos das métricas de componente
        fieldnames = [
            'component_id', 'component_type', 'total_failures', 'successful_recoveries',
            'availability_percent', 'mttr_mean', 'mttr_median', 'mttr_min', 'mttr_max', 'mttr_std_dev'
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for component_id, metrics in component_metrics.items():
                    # Calcular estatísticas para este componente
                    stats = self._calculate_component_stats(component_id, metrics)
                    if stats:
                        writer.writerow(stats)
            
            print(f"💾 Métricas de componentes salvas em: {filepath}")
            
        except Exception as e:
            print(f"❌ Erro ao salvar métricas de componentes: {e}")
    
    def _calculate_component_stats(self, component_id: str, metrics: Dict) -> Dict:
        """
        Calcula estatísticas para um componente específico.
        
        Args:
            component_id: ID do componente
            metrics: Métricas do componente
            
        Returns:
            Dicionário com estatísticas calculadas
        """
        try:
            import statistics
            
            recovery_times = metrics.get('recovery_times', [])
            total_failures = metrics.get('total_failures', 0)
            successful_recoveries = metrics.get('successful_recoveries', 0)
            
            stats = {
                'component_id': component_id,
                'component_type': metrics.get('component_type', 'unknown'),
                'total_failures': total_failures,
                'successful_recoveries': successful_recoveries,
                'availability_percent': (successful_recoveries / total_failures * 100) if total_failures > 0 else 0,
                'mttr_mean': statistics.mean(recovery_times) if recovery_times else 0,
                'mttr_median': statistics.median(recovery_times) if recovery_times else 0,
                'mttr_min': min(recovery_times) if recovery_times else 0,
                'mttr_max': max(recovery_times) if recovery_times else 0,
                'mttr_std_dev': statistics.stdev(recovery_times) if len(recovery_times) > 1 else 0
            }
            
            return stats
            
        except Exception as e:
            print(f"❌ Erro ao calcular estatísticas para {component_id}: {e}")
            return {}
    
    def is_realtime_active(self) -> bool:
        """
        Verifica se relatório em tempo real está ativo.
        
        Returns:
            True se ativo, False caso contrário
        """
        return self._is_realtime_active
    
    def get_current_file_path(self) -> Optional[str]:
        """
        Retorna caminho do arquivo atual sendo escrito.
        
        Returns:
            Caminho do arquivo ou None se não ativo
        """
        return self.current_file if self._is_realtime_active else None
    
    def load_test_results(self, filepath: str) -> List[Dict]:
        """
        Carrega resultados de teste de um arquivo CSV.
        
        Args:
            filepath: Caminho para o arquivo CSV
            
        Returns:
            Lista com dados carregados
        """
        try:
            results = []
            with open(filepath, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Pular linhas de resumo
                    if row.get('iteration') == 'RESUMO':
                        continue
                    
                    # Converter tipos de dados apropriados
                    if 'iteration' in row and row['iteration'].isdigit():
                        row['iteration'] = int(row['iteration'])
                    if 'recovery_time_seconds' in row:
                        try:
                            row['recovery_time_seconds'] = float(row['recovery_time_seconds'])
                        except ValueError:
                            pass
                    if 'total_time_seconds' in row:
                        try:
                            row['total_time_seconds'] = float(row['total_time_seconds'])
                        except ValueError:
                            pass
                    if 'recovered' in row:
                        row['recovered'] = row['recovered'].lower() == 'true'
                    
                    results.append(row)
            
            print(f"📊 Carregados {len(results)} resultados de {filepath}")
            return results
            
        except Exception as e:
            print(f"❌ Erro ao carregar arquivo {filepath}: {e}")
            return []