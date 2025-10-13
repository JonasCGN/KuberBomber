#!/usr/bin/env python3
"""
Chaos Engineering CLI
=====================

Interface de linha de comando para o framework de chaos engineering.
"""

import click
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich import box
import time

# Imports dos módulos do framework
from ..core.base import (
    ChaosOrchestrator, FailureType, logger,
    format_duration
)
from ..injectors.pod_injector import PodFailureInjector, PodMonitor
from ..injectors.process_injector import ProcessFailureInjector, ProcessMonitor
from ..injectors.node_injector import NodeFailureInjector, NodeMonitor
from ..monitoring.system_monitor import SystemMonitor, ResourceType, print_cluster_summary
from ..monitoring.metrics_collector import AdvancedMetricsCollector, MetricsAggregator
from ..monitoring.visualization import ChaosVisualization, quick_visualization
from ..scenarios.advanced_scenarios import AdvancedChaosScenarios
from ..reliability.reliability_simulator import ReliabilitySimulator

# Configurações globais
console = Console()
DEFAULT_CONFIG_FILE = "chaos_config.json"

class ChaosConfig:
    """Gerenciador de configurações do chaos engineering"""
    
    def __init__(self, config_file: str = DEFAULT_CONFIG_FILE):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Carrega configurações do arquivo"""
        if Path(self.config_file).exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[red]Error loading config: {e}[/red]")
                return self.default_config()
        else:
            return self.default_config()
    
    def save_config(self):
        """Salva configurações no arquivo"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2, default=str)
        except Exception as e:
            console.print(f"[red]Error saving config: {e}[/red]")
    
    def default_config(self) -> Dict[str, Any]:
        """Configurações padrão"""
        return {
            'kubernetes': {
                'namespace': 'default',
                'kubeconfig_path': None
            },
            'aws': {
                'region': 'us-east-1',
                'enabled': False
            },
            'ssh': {
                'key_path': None,
                'user': 'ubuntu',
                'enabled': False
            },
            'metrics': {
                'database_path': 'chaos_metrics.db',
                'retention_days': 90
            },
            'visualization': {
                'auto_generate': True,
                'output_dir': 'reports'
            }
        }


@click.group()
@click.option('--config', '-c', default=DEFAULT_CONFIG_FILE, help='Configuration file path')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, config, verbose):
    """
    🔥 Kubernetes Chaos Engineering Framework
    
    A comprehensive toolkit for testing system resilience through controlled failure injection.
    """
    ctx.ensure_object(dict)
    ctx.obj['config'] = ChaosConfig(config)
    ctx.obj['verbose'] = verbose
    
    if verbose:
        logger.setLevel('DEBUG')


@cli.group()
@click.pass_context
def pod(ctx):
    """Pod-level failure injection commands"""
    pass


@pod.command('list')
@click.option('--namespace', '-n', help='Kubernetes namespace')
@click.pass_context
def pod_list(ctx, namespace):
    """List available pods"""
    config = ctx.obj['config']
    ns = namespace or config.config['kubernetes']['namespace']
    
    try:
        injector = PodFailureInjector(namespace=ns)
        targets = injector.list_targets()
        
        if not targets:
            console.print(f"[yellow]No pods found in namespace '{ns}'[/yellow]")
            return
        
        table = Table(title=f"Available Pods in '{ns}'", box=box.ROUNDED)
        table.add_column("Pod Name", style="cyan")
        table.add_column("Status", style="green")
        
        monitor = PodMonitor(namespace=ns)
        
        for target in targets:
            status = "✅ Running" if monitor.is_healthy(target) else "❌ Unhealthy"
            table.add_row(target, status)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing pods: {e}[/red]")


@pod.command('delete')
@click.argument('pod_name')
@click.option('--namespace', '-n', help='Kubernetes namespace')
@click.option('--grace-period', default=0, help='Grace period in seconds')
@click.option('--monitor', is_flag=True, help='Monitor recovery')
@click.pass_context
def pod_delete(ctx, pod_name, namespace, grace_period, monitor):
    """Delete a specific pod"""
    config = ctx.obj['config']
    ns = namespace or config.config['kubernetes']['namespace']
    
    if not Confirm.ask(f"Delete pod [bold red]{pod_name}[/bold red] in namespace [cyan]{ns}[/cyan]?"):
        console.print("[yellow]Operation cancelled[/yellow]")
        return
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            # Injeta falha
            task = progress.add_task("Deleting pod...", total=None)
            injector = PodFailureInjector(namespace=ns)
            metrics = injector.inject_failure(
                pod_name, 
                failure_type="delete",
                grace_period_seconds=grace_period
            )
            
            progress.update(task, description="✅ Pod deleted")
            
            if monitor:
                # Monitora recuperação
                progress.update(task, description="Monitoring recovery...")
                pod_monitor = PodMonitor(namespace=ns)
                
                try:
                    recovery_metrics = pod_monitor.wait_for_recovery(pod_name, timeout=300)
                    metrics.recovery_time = recovery_metrics.total_recovery_time
                    
                    progress.update(task, description=f"✅ Recovery completed in {format_duration(recovery_metrics.total_recovery_time)}")
                    
                except Exception as e:
                    progress.update(task, description=f"⚠️ Recovery monitoring failed: {e}")
        
        # Mostra resultados
        result_panel = Panel(
            f"[green]Pod deletion completed[/green]\n\n"
            f"[bold]Target:[/bold] {pod_name}\n"
            f"[bold]Namespace:[/bold] {ns}\n"
            f"[bold]Grace Period:[/bold] {grace_period}s\n"
            f"[bold]Recovery Time:[/bold] {format_duration(metrics.recovery_time) if metrics.recovery_time else 'Not monitored'}\n"
            f"[bold]Success:[/bold] {'✅' if metrics.success else '❌'}",
            title="Failure Injection Results",
            box=box.ROUNDED
        )
        console.print(result_panel)
        
        # Salva métricas
        collector = AdvancedMetricsCollector(config.config['metrics']['database_path'])
        collector.record_failure(metrics)
        
    except Exception as e:
        console.print(f"[red]Error deleting pod: {e}[/red]")


@pod.command('stress')
@click.option('--namespace', '-n', help='Kubernetes namespace')
@click.option('--app-label', help='Filter pods by app label')
@click.option('--duration', default=10, help='Test duration in minutes')
@click.option('--interval', default=30, help='Interval between failures in seconds')
@click.pass_context
def pod_stress(ctx, namespace, app_label, duration, interval):
    """Run stress test on pods"""
    config = ctx.obj['config']
    ns = namespace or config.config['kubernetes']['namespace']
    
    console.print(Panel(
        f"Starting pod stress test\n\n"
        f"[bold]Namespace:[/bold] {ns}\n"
        f"[bold]App Label:[/bold] {app_label or 'Any'}\n"
        f"[bold]Duration:[/bold] {duration} minutes\n"
        f"[bold]Interval:[/bold] {interval} seconds",
        title="🔥 Pod Stress Test",
        box=box.ROUNDED
    ))
    
    if not Confirm.ask("Start stress test?"):
        console.print("[yellow]Operation cancelled[/yellow]")
        return
    
    try:
        from ..injectors.pod_injector import stress_test_pods
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Running stress test...", total=duration*60)
            
            results = stress_test_pods(
                namespace=ns,
                duration_minutes=duration,
                interval_seconds=interval
            )
            
            progress.update(task, completed=duration*60)
        
        # Mostra resultados
        if results:
            table = Table(title="Stress Test Results", box=box.ROUNDED)
            table.add_column("Pod", style="cyan")
            table.add_column("Recovery Time", style="green")
            table.add_column("Status", style="yellow")
            
            for result in results:
                status = "✅ Success" if result.success else "❌ Failed"
                recovery = format_duration(result.recovery_time) if result.recovery_time else "N/A"
                table.add_row(result.target, recovery, status)
            
            console.print(table)
            
            # Salva métricas
            collector = AdvancedMetricsCollector(config.config['metrics']['database_path'])
            for result in results:
                collector.record_failure(result)
        
    except Exception as e:
        console.print(f"[red]Error running stress test: {e}[/red]")


@pod.command('reboot')
@click.argument('pod_name', required=False)
@click.option('--namespace', '-n', help='Kubernetes namespace')
@click.option('--random', is_flag=True, help='Select random pod')
@click.pass_context
def pod_reboot(ctx, pod_name, namespace, random):
    """Force reboot pod via delete and recreate"""
    config = ctx.obj['config']
    ns = namespace or config.config['kubernetes']['namespace']
    
    try:
        injector = PodFailureInjector(namespace=ns)
        
        # Seleciona pod
        if not pod_name:
            available_pods = injector.list_targets()
            if not available_pods:
                console.print("[red]No pods found[/red]")
                return
                
            if random:
                import random as rand
                pod_name = rand.choice(available_pods)
            else:
                # Lista pods para escolha
                table = Table(title="Available Pods", box=box.ROUNDED)
                table.add_column("Pod Name", style="cyan")
                for pod in available_pods:
                    table.add_row(pod)
                console.print(table)
                
                pod_name = Prompt.ask("Select pod to reboot")
                if pod_name not in available_pods:
                    console.print("[red]Invalid pod name[/red]")
                    return
        
        console.print(Panel(
            f"[bold]Pod:[/bold] {pod_name}\n"
            f"[bold]Namespace:[/bold] {ns}\n"
            f"[bold]Action:[/bold] Force reboot (delete + recreate)\n"
            f"[yellow]⚠️  This will forcefully delete the pod![/yellow]",
            title="🔄 Pod Reboot",
            box=box.ROUNDED
        ))
        
        if not Confirm.ask("Proceed with pod reboot?"):
            console.print("[yellow]Operation cancelled[/yellow]")
            return
        
        # Executa reboot
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Rebooting pod...", total=None)
            
            # Simula o reboot usando reliability simulator
            from ..reliability.reliability_simulator import ReliabilitySimulator, FailureMode
            simulator = ReliabilitySimulator(namespace=ns)
            
            success = simulator._reboot_pod(pod_name)
            progress.update(task, completed=1)
        
        # Mostra resultado
        if success:
            result_panel = Panel(
                f"[green]✅ Pod {pod_name} successfully rebooted[/green]\n\n"
                f"The pod has been forcefully deleted and should be recreated "
                f"by its controller (Deployment, ReplicaSet, etc.)",
                title="✅ Success",
                box=box.ROUNDED
            )
        else:
            result_panel = Panel(
                f"[red]❌ Failed to reboot pod {pod_name}[/red]\n\n"
                f"Check logs for details.",
                title="❌ Failed",
                box=box.ROUNDED
            )
        
        console.print(result_panel)
        
    except Exception as e:
        console.print(f"[red]Error rebooting pod: {e}[/red]")


@cli.group()
@click.pass_context
def node(ctx):
    """Node-level failure injection commands"""
    pass


@node.command('list')
@click.pass_context
def node_list(ctx):
    """List available nodes"""
    try:
        injector = NodeFailureInjector()
        targets = injector.list_targets()
        
        if not targets:
            console.print("[yellow]No nodes found[/yellow]")
            return
        
        table = Table(title="Available Nodes", box=box.ROUNDED)
        table.add_column("Node Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Role", style="yellow")
        
        monitor = NodeMonitor()
        
        for target in targets:
            status = "✅ Ready" if monitor.is_healthy(target) else "❌ Not Ready"
            
            # Determina role baseado no nome (simplificado)
            role = "Master" if "master" in target.lower() or "control" in target.lower() else "Worker"
            
            table.add_row(target, status, role)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing nodes: {e}[/red]")


@node.command('drain')
@click.argument('node_name')
@click.option('--ignore-daemonsets', is_flag=True, default=True, help='Ignore DaemonSets')
@click.option('--force', is_flag=True, help='Force drain')
@click.option('--monitor', is_flag=True, help='Monitor recovery')
@click.pass_context
def node_drain(ctx, node_name, ignore_daemonsets, force, monitor):
    """Drain a specific node"""
    if not Confirm.ask(f"Drain node [bold red]{node_name}[/bold red]?"):
        console.print("[yellow]Operation cancelled[/yellow]")
        return
    
    try:
        config = ctx.obj['config']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Draining node...", total=None)
            
            injector = NodeFailureInjector()
            metrics = injector.inject_failure(
                node_name,
                failure_type="drain",
                ignore_daemonsets=ignore_daemonsets,
                force=force
            )
            
            progress.update(task, description="✅ Node drained")
            
            if monitor:
                progress.update(task, description="Monitoring recovery...")
                node_monitor = NodeMonitor()
                
                try:
                    recovery_metrics = node_monitor.wait_for_recovery(node_name, timeout=600)
                    metrics.recovery_time = recovery_metrics.total_recovery_time
                    
                    progress.update(task, description=f"✅ Recovery completed in {format_duration(recovery_metrics.total_recovery_time)}")
                    
                except Exception as e:
                    progress.update(task, description=f"⚠️ Recovery monitoring failed: {e}")
        
        # Mostra resultados
        result_panel = Panel(
            f"[green]Node drain completed[/green]\n\n"
            f"[bold]Target:[/bold] {node_name}\n"
            f"[bold]Ignore DaemonSets:[/bold] {ignore_daemonsets}\n"
            f"[bold]Force:[/bold] {force}\n"
            f"[bold]Recovery Time:[/bold] {format_duration(metrics.recovery_time) if metrics.recovery_time else 'Not monitored'}\n"
            f"[bold]Success:[/bold] {'✅' if metrics.success else '❌'}",
            title="Node Drain Results",
            box=box.ROUNDED
        )
        console.print(result_panel)
        
        # Salva métricas
        collector = AdvancedMetricsCollector(config.config['metrics']['database_path'])
        collector.record_failure(metrics)
        
    except Exception as e:
        console.print(f"[red]Error draining node: {e}[/red]")


@cli.group()
@click.pass_context
def process(ctx):
    """Process-level failure injection commands"""
    pass


@process.command('list')
@click.option('--filter', help='Filter processes by name')
@click.option('--limit', default=20, help='Limit number of results')
@click.pass_context
def process_list(ctx, filter, limit):
    """List running processes"""
    try:
        injector = ProcessFailureInjector()
        targets = injector.list_targets()
        
        if filter:
            targets = [t for t in targets if filter.lower() in t.lower()]
        
        targets = targets[:limit]
        
        if not targets:
            console.print("[yellow]No processes found[/yellow]")
            return
        
        table = Table(title=f"Running Processes (showing {len(targets)})", box=box.ROUNDED)
        table.add_column("PID:Name", style="cyan")
        table.add_column("Status", style="green")
        
        monitor = ProcessMonitor()
        
        for target in targets:
            status = "✅ Running" if monitor.is_healthy(target) else "❌ Not Running"
            table.add_row(target, status)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing processes: {e}[/red]")


@cli.group()
@click.pass_context
def monitor(ctx):
    """System monitoring commands"""
    pass


@monitor.command('status')
@click.pass_context
def monitor_status(ctx):
    """Show cluster health status"""
    try:
        print_cluster_summary()
        
    except Exception as e:
        console.print(f"[red]Error getting cluster status: {e}[/red]")


@monitor.command('resources')
@click.option('--type', 'resource_type', 
              type=click.Choice(['pod', 'node', 'service', 'deployment', 'namespace', 'process']),
              help='Resource type to list')
@click.option('--namespace', '-n', help='Kubernetes namespace (for pod/service/deployment)')
@click.pass_context
def monitor_resources(ctx, resource_type, namespace):
    """List and monitor resources"""
    try:
        from ..monitoring.system_monitor import print_resource_list, ResourceType
        
        if resource_type:
            rt = ResourceType(resource_type)
            print_resource_list(rt, namespace)
        else:
            # Mostra todos os tipos
            for rt in ResourceType:
                if rt in [ResourceType.POD, ResourceType.SERVICE, ResourceType.DEPLOYMENT]:
                    print_resource_list(rt, namespace)
                else:
                    print_resource_list(rt)
        
    except Exception as e:
        console.print(f"[red]Error monitoring resources: {e}[/red]")


@cli.group()
@click.pass_context
def metrics(ctx):
    """Metrics and analysis commands"""
    pass


@metrics.command('report')
@click.option('--target', help='Specific target to analyze')
@click.option('--days', default=30, help='Days to analyze')
@click.option('--format', 'output_format', 
              type=click.Choice(['json', 'csv']), 
              default='json', help='Output format')
@click.pass_context
def metrics_report(ctx, target, days, output_format):
    """Generate metrics report"""
    try:
        config = ctx.obj['config']
        collector = AdvancedMetricsCollector(config.config['metrics']['database_path'])
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Generating report...", total=None)
            
            filename = collector.export_metrics_report(target, output_format)
            
            progress.update(task, description=f"✅ Report generated: {filename}")
        
        console.print(f"[green]Report saved to: {filename}[/green]")
        
        # Mostra resumo
        if target:
            availability = collector.calculate_availability_metrics(target, period_hours=24*days)
            resilience = collector.calculate_resilience_score(target)
            
            summary_panel = Panel(
                f"[bold]Target:[/bold] {target}\n"
                f"[bold]Period:[/bold] {days} days\n\n"
                f"[bold]Availability:[/bold] {availability.availability_percentage:.2f}%\n"
                f"[bold]MTTR:[/bold] {format_duration(availability.mttr)}\n"
                f"[bold]Incidents:[/bold] {availability.incident_count}\n\n"
                f"[bold]Resilience Score:[/bold] {resilience.overall_score}/100 (Grade: {resilience.grade})",
                title="📊 Metrics Summary",
                box=box.ROUNDED
            )
            console.print(summary_panel)
        
    except Exception as e:
        console.print(f"[red]Error generating report: {e}[/red]")


@metrics.command('visualize')
@click.option('--target', help='Specific target to visualize')
@click.option('--days', default=7, help='Days to visualize')
@click.option('--type', 'viz_type',
              type=click.Choice(['timeline', 'heatmap', 'distribution', 'dashboard', 'all']),
              default='all', help='Visualization type')
@click.pass_context
def metrics_visualize(ctx, target, days, viz_type):
    """Generate visualizations"""
    try:
        config = ctx.obj['config']
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Generating visualizations...", total=None)
            
            if viz_type == 'all':
                files = quick_visualization(config.config['metrics']['database_path'], target)
            else:
                collector = AdvancedMetricsCollector(config.config['metrics']['database_path'])
                viz = ChaosVisualization(collector)
                
                if viz_type == 'timeline' and target:
                    files = {'timeline': viz.plot_recovery_timeline(target, days)}
                elif viz_type == 'dashboard':
                    files = {'dashboard': viz.create_interactive_dashboard(days=days)}
                # Adicionar outros tipos específicos conforme necessário
                else:
                    files = {}
            
            progress.update(task, description=f"✅ Generated {len(files)} visualizations")
        
        if files:
            console.print("[green]Visualizations generated:[/green]")
            for viz_name, filename in files.items():
                console.print(f"  • {viz_name}: [cyan]{filename}[/cyan]")
        else:
            console.print("[yellow]No visualizations generated[/yellow]")
        
    except Exception as e:
        console.print(f"[red]Error generating visualizations: {e}[/red]")


@cli.group()
@click.pass_context
def config(ctx):
    """Configuration management"""
    pass


@config.command('show')
@click.pass_context
def config_show(ctx):
    """Show current configuration"""
    config = ctx.obj['config']
    
    console.print(Panel(
        json.dumps(config.config, indent=2),
        title="Current Configuration",
        box=box.ROUNDED
    ))


@config.command('set')
@click.argument('key')
@click.argument('value')
@click.pass_context
def config_set(ctx, key, value):
    """Set configuration value"""
    config = ctx.obj['config']
    
    # Navega pela estrutura aninhada usando dot notation
    keys = key.split('.')
    current = config.config
    
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    
    # Converte valor para tipo apropriado
    if value.lower() in ['true', 'false']:
        value = value.lower() == 'true'
    elif value.isdigit():
        value = int(value)
    elif value == 'null':
        value = None
    
    current[keys[-1]] = value
    config.save_config()
    
    console.print(f"[green]Configuration updated: {key} = {value}[/green]")


@cli.command()
@click.option('--interactive', '-i', is_flag=True, help='Interactive mode')
@click.pass_context
def scenario(ctx, interactive):
    """Run predefined chaos scenarios"""
    scenarios = {
        '1': {'name': 'Pod Resilience Test', 'desc': 'Test pod recovery capabilities'},
        '2': {'name': 'Node Drain Simulation', 'desc': 'Simulate node maintenance'},
        '3': {'name': 'Network Partition', 'desc': 'Test network failure recovery'},
        '4': {'name': 'Resource Exhaustion', 'desc': 'Test resource limit handling'},
        '5': {'name': 'Multi-Component Failure', 'desc': 'Test cascade failure recovery'}
    }
    
    if interactive:
        console.print(Panel(
            "🎭 Chaos Scenarios\n\nChoose a scenario to run:",
            title="Interactive Mode",
            box=box.ROUNDED
        ))
        
        table = Table(box=box.SIMPLE)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Description", style="yellow")
        
        for sid, scenario_info in scenarios.items():
            table.add_row(sid, scenario_info['name'], scenario_info['desc'])
        
        console.print(table)
        
        choice = Prompt.ask("Select scenario", choices=list(scenarios.keys()))
        
        selected = scenarios[choice]
        console.print(f"\n[green]Running scenario: {selected['name']}[/green]")
        
        # Implementar execução do cenário baseado na escolha
        # Por enquanto, apenas mostra que seria executado
        console.print(f"[yellow]Scenario '{selected['name']}' would be executed here[/yellow]")
        
    else:
        console.print("[yellow]Use --interactive flag to select and run scenarios[/yellow]")


@cli.group()
def reliability():
    """Comandos de simulação de confiabilidade para análise acadêmica"""
    pass


@reliability.command()
@click.option('--duration', '-d', default=1.0, help='Duração em horas reais')
@click.option('--acceleration', '-a', default=10000.0, help='Fator de aceleração temporal')
@click.option('--csv-path', '-o', default='reliability_simulation.csv', help='Arquivo CSV de saída')
@click.option('--namespace', '-n', default='default', help='Namespace Kubernetes')
def start(duration: float, acceleration: float, csv_path: str, namespace: str):
    """Inicia simulação de confiabilidade com métricas MTTF/MTBF/MTTR"""
    
    console.print(Panel.fit(
        f"[bold green]Simulação de Confiabilidade[/bold green]\n\n"
        f"Duração: {duration} horas reais\n"
        f"Aceleração: {acceleration}x (1h real = {acceleration}h simuladas)\n"
        f"Arquivo CSV: {csv_path}\n"
        f"Namespace: {namespace}",
        title="Configuração",
        box=box.ROUNDED
    ))
    
    if not Confirm.ask("Iniciar simulação?"):
        console.print("[yellow]Simulação cancelada[/yellow]")
        return
    
    try:
        simulator = ReliabilitySimulator(
            namespace=namespace,
            csv_log_path=csv_path,
            time_acceleration=acceleration
        )
        
        console.print("[green]🚀 Iniciando simulação...[/green]")
        
        if not simulator.start_simulation(duration_hours=duration):
            console.print("[red]❌ Falha ao iniciar simulação[/red]")
            return
        
        # Monitora progresso
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            task = progress.add_task("Executando simulação...", total=None)
            
            last_failures = 0
            start_time = time.time()
            
            while simulator.is_running:
                time.sleep(5)  # Atualiza a cada 5 segundos
                
                status = simulator.get_simulation_status()
                current_failures = status['total_failures']
                
                # Calcula tempo decorrido
                elapsed_real = time.time() - start_time
                elapsed_sim = status['simulation_time_hours']
                
                # Atualiza descrição da tarefa
                progress.update(
                    task, 
                    description=f"Simulação: {elapsed_sim:.1f}h simuladas "
                                f"({elapsed_real:.0f}s reais) | "
                                f"Falhas: {current_failures} | "
                                f"MTTF: {status['current_mttf_hours']:.1f}h | "
                                f"MTTR: {status['current_mttr_seconds']:.0f}s"
                )
                
                # Se houve nova falha, mostra notificação
                if current_failures > last_failures:
                    console.print(f"[yellow]💥 Nova falha detectada (Total: {current_failures})[/yellow]")
                    last_failures = current_failures
        
        # Resultados finais
        final_status = simulator.get_simulation_status()
        
        console.print(Panel.fit(
            f"[bold green]Simulação Concluída[/bold green]\n\n"
            f"⏱️  Tempo Simulado: {final_status['simulation_time_hours']:.2f} horas\n"
            f"💥 Total de Falhas: {final_status['total_failures']}\n"
            f"📊 MTTF: {final_status['current_mttf_hours']:.2f} horas\n"
            f"📊 MTBF: {final_status['current_mtbf_hours']:.2f} horas\n"
            f"📊 MTTR: {final_status['current_mttr_seconds']:.1f} segundos\n\n"
            f"📁 Log salvo em: {csv_path}",
            title="Resultados",
            box=box.ROUNDED
        ))
        
    except KeyboardInterrupt:
        console.print("\n[yellow]⏹️ Simulação interrompida pelo usuário[/yellow]")
        if 'simulator' in locals():
            simulator.stop_simulation()
    except Exception as e:
        console.print(f"[red]❌ Erro na simulação: {e}[/red]")


@reliability.command()
@click.option('--csv-path', '-f', required=True, help='Arquivo CSV da simulação')
@click.option('--output', '-o', default='reliability_analysis.json', help='Arquivo de saída da análise')
def analyze(csv_path: str, output: str):
    """Analisa resultados de simulação CSV e gera relatório detalhado"""
    
    if not Path(csv_path).exists():
        console.print(f"[red]❌ Arquivo não encontrado: {csv_path}[/red]")
        return
    
    try:
        import pandas as pd
        
        # Carrega dados
        console.print(f"[cyan]📊 Analisando dados de: {csv_path}[/cyan]")
        df = pd.read_csv(csv_path)
        
        if len(df) == 0:
            console.print("[yellow]⚠️ Arquivo CSV está vazio[/yellow]")
            return
        
        # Filtra eventos de recuperação completa
        recovery_events = df[df['event_type'] == 'recovery_completed'].copy()
        
        if len(recovery_events) == 0:
            console.print("[yellow]⚠️ Nenhum evento de recuperação encontrado[/yellow]")
            return
        
        # Análise estatística
        analysis = {
            'summary': {
                'total_events': len(df),
                'total_failures': len(recovery_events),
                'simulation_duration_hours': df['simulation_time_hours'].max(),
                'analysis_timestamp': datetime.now().isoformat()
            },
            'mttf_analysis': {
                'mean_hours': recovery_events['mttf_hours'].mean(),
                'std_hours': recovery_events['mttf_hours'].std(),
                'min_hours': recovery_events['mttf_hours'].min(),
                'max_hours': recovery_events['mttf_hours'].max(),
                'median_hours': recovery_events['mttf_hours'].median()
            },
            'mtbf_analysis': {
                'mean_hours': recovery_events['mtbf_hours'].mean(),
                'std_hours': recovery_events['mtbf_hours'].std(),
                'min_hours': recovery_events['mtbf_hours'].min(),
                'max_hours': recovery_events['mtbf_hours'].max(),
                'median_hours': recovery_events['mtbf_hours'].median()
            },
            'mttr_analysis': {
                'mean_seconds': recovery_events['mttr_seconds'].mean(),
                'std_seconds': recovery_events['mttr_seconds'].std(),
                'min_seconds': recovery_events['mttr_seconds'].min(),
                'max_seconds': recovery_events['mttr_seconds'].max(),
                'median_seconds': recovery_events['mttr_seconds'].median()
            },
            'failure_types': recovery_events['failure_mode'].value_counts().to_dict(),
            'availability_estimate': None
        }
        
        # Calcula disponibilidade estimada
        total_downtime = recovery_events['duration_seconds'].sum()
        total_simulation_seconds = df['simulation_time_hours'].max() * 3600
        if total_simulation_seconds > 0:
            availability = max(0, (total_simulation_seconds - total_downtime) / total_simulation_seconds * 100)
            analysis['availability_estimate'] = availability
        
        # Salva análise
        with open(output, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        
        # Exibe resumo
        table = Table(title="Análise de Confiabilidade", box=box.ROUNDED)
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green")
        table.add_column("Unidade", style="yellow")
        
        table.add_row("Total de Falhas", str(analysis['summary']['total_failures']), "falhas")
        table.add_row("Duração Simulada", f"{analysis['summary']['simulation_duration_hours']:.2f}", "horas")
        table.add_row("MTTF Médio", f"{analysis['mttf_analysis']['mean_hours']:.2f}", "horas")
        table.add_row("MTBF Médio", f"{analysis['mtbf_analysis']['mean_hours']:.2f}", "horas")
        table.add_row("MTTR Médio", f"{analysis['mttr_analysis']['mean_seconds']:.1f}", "segundos")
        
        if analysis['availability_estimate']:
            table.add_row("Disponibilidade", f"{analysis['availability_estimate']:.2f}", "%")
        
        console.print(table)
        
        # Mostra tipos de falha
        if analysis['failure_types']:
            failure_table = Table(title="Distribuição de Tipos de Falha", box=box.SIMPLE)
            failure_table.add_column("Tipo", style="cyan")
            failure_table.add_column("Quantidade", style="green")
            failure_table.add_column("Percentual", style="yellow")
            
            total_failures = sum(analysis['failure_types'].values())
            for failure_type, count in analysis['failure_types'].items():
                percentage = (count / total_failures) * 100
                failure_table.add_row(failure_type, str(count), f"{percentage:.1f}%")
            
            console.print(failure_table)
        
        console.print(f"\n[green]✅ Análise salva em: {output}[/green]")
        
    except ImportError:
        console.print("[red]❌ pandas não está instalado. Use: pip install pandas[/red]")
    except Exception as e:
        console.print(f"[red]❌ Erro na análise: {e}[/red]")


@reliability.command()
@click.option('--preset', '-p', type=click.Choice(['quick', 'standard', 'extended']), 
              default='standard', help='Preset de configuração')
def test(preset: str):
    """Executa teste rápido de confiabilidade com presets"""
    
    presets = {
        'quick': {
            'duration': 0.05,    # 3 minutos
            'acceleration': 1000.0,
            'description': 'Teste rápido (3 min, 1000x aceleração)'
        },
        'standard': {
            'duration': 0.1,     # 6 minutos
            'acceleration': 5000.0,
            'description': 'Teste padrão (6 min, 5000x aceleração)'
        },
        'extended': {
            'duration': 0.25,    # 15 minutos
            'acceleration': 10000.0,
            'description': 'Teste estendido (15 min, 10000x aceleração)'
        }
    }
    
    config = presets[preset]
    csv_path = f"reliability_test_{preset}_{int(time.time())}.csv"
    
    console.print(Panel.fit(
        f"[bold blue]Teste de Confiabilidade - {preset.title()}[/bold blue]\n\n"
        f"{config['description']}\n"
        f"Arquivo: {csv_path}",
        title="Teste Rápido",
        box=box.ROUNDED
    ))
    
    try:
        from ..reliability.reliability_simulator import run_reliability_simulation
        
        status = run_reliability_simulation(
            duration_hours=config['duration'],
            time_acceleration=config['acceleration'],
            csv_path=csv_path
        )
        
        console.print("[green]✅ Teste concluído com sucesso![/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Erro no teste: {e}[/red]")


if __name__ == '__main__':
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        if '--verbose' in sys.argv or '-v' in sys.argv:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)