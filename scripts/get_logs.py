#!/usr/bin/env python3
"""
log_viewer.py - Display logs from both PostgreSQL and Qdrant databases nicely
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

# Import your existing modules
from db_manager import get_db_manager
from config_manager import get_config

console = Console()

class LogViewer:
    def __init__(self):
        self.config = get_config()
        self.db = get_db_manager()
        
    def display_postgres_logs(self, limit: int = 10):
        """Display PostgreSQL chat logs in a nice table"""
        console.print("\n[bold blue]📊 PostgreSQL Chat Messages[/bold blue]")
        
        try:
            logs = self.db.get_recent_chat_logs(limit)
            
            if not logs:
                console.print("[yellow]No chat messages found[/yellow]")
                return
            
            table = Table(
                title=f"Recent {len(logs)} Chat Messages",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold magenta"
            )
            
            table.add_column("Time", style="cyan", width=20)
            table.add_column("Role", style="green", width=10)
            table.add_column("User", style="blue", width=15)
            table.add_column("Message", style="white", width=50)
            table.add_column("Conv ID", style="dim", width=12)
            
            for log in logs:
                timestamp = log.get('timestamp', 'Unknown')
                if isinstance(timestamp, datetime):
                    time_str = timestamp.strftime('%m-%d %H:%M:%S')
                else:
                    time_str = str(timestamp)[:19] if timestamp else 'Unknown'
                
                role = log.get('role', 'unknown')
                user_info = f"{log.get('user_type', 'unknown')}/{log.get('user_id', 'unknown')}"
                content = log.get('content', '')
                conv_id = str(log.get('conversation_id', ''))[:10] + '...' if log.get('conversation_id') else 'None'
                
                # Truncate long messages
                if len(content) > 50:
                    content = content[:47] + "..."
                
                # Color code by role
                role_style = "green" if role == "user" else "blue" if role == "assistant" else "white"
                
                table.add_row(
                    time_str,
                    f"[{role_style}]{role}[/{role_style}]",
                    user_info,
                    content,
                    conv_id
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Error fetching PostgreSQL logs: {e}[/red]")
    
    def display_qdrant_logs(self, limit: int = 10):
        """Display Qdrant telemetry logs in a nice format"""
        console.print("\n[bold green]🤖 Qdrant Telemetry Data[/bold green]")
        
        try:
            logs = self.db.get_recent_telemetry_logs(limit)
            
            if not logs:
                console.print("[yellow]No telemetry data found[/yellow]")
                return
            
            # Group by robot for better display
            robot_data = {}
            for log in logs:
                payload = log.get('payload', {})
                robot_id = payload.get('robot_id', 'unknown')
                
                if robot_id not in robot_data:
                    robot_data[robot_id] = []
                robot_data[robot_id].append(payload)
            
            # Display each robot's data
            panels = []
            for robot_id, telemetry_list in robot_data.items():
                latest = telemetry_list[0] if telemetry_list else {}
                telemetry = latest.get('telemetry', {})
                
                # Create robot status panel
                position = telemetry.get('position', {})
                pos_str = f"({position.get('x', 0):.1f}, {position.get('y', 0):.1f})"
                
                status_lines = [
                    f"[cyan]Position:[/cyan] {pos_str}",
                    f"[yellow]Status:[/yellow] {telemetry.get('navigation_status', 'unknown')}",
                    f"[green]Battery:[/green] {telemetry.get('battery_level', 'unknown')}%",
                    f"[red]Stuck:[/red] {'Yes' if telemetry.get('is_stuck', False) else 'No'}",
                    f"[blue]Waypoint:[/blue] {telemetry.get('current_waypoint', 'none')}",
                    f"[dim]Last Update:[/dim] {latest.get('timestamp', 'unknown')[:19]}"
                ]
                
                panel_content = "\n".join(status_lines)
                panel = Panel(
                    panel_content,
                    title=f"🤖 Robot {robot_id}",
                    border_style="green" if not telemetry.get('is_stuck', False) else "red"
                )
                panels.append(panel)
            
            # Display panels in columns
            if panels:
                if len(panels) <= 2:
                    console.print(Columns(panels, equal=True, expand=True))
                else:
                    # Show first few in columns, rest individually
                    console.print(Columns(panels[:2], equal=True, expand=True))
                    for panel in panels[2:]:
                        console.print(panel)
            
            # Summary table
            table = Table(
                title="Telemetry Summary",
                box=box.SIMPLE,
                show_header=True,
                header_style="bold cyan"
            )
            
            table.add_column("Robot ID", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Position", style="cyan")
            table.add_column("Battery", style="blue")
            table.add_column("Last Seen", style="dim")
            
            for robot_id, telemetry_list in robot_data.items():
                latest = telemetry_list[0] if telemetry_list else {}
                telemetry = latest.get('telemetry', {})
                position = telemetry.get('position', {})
                
                table.add_row(
                    robot_id,
                    telemetry.get('navigation_status', 'unknown'),
                    f"({position.get('x', 0):.1f}, {position.get('y', 0):.1f})",
                    f"{telemetry.get('battery_level', 'unknown')}%",
                    latest.get('timestamp', 'unknown')[:19]
                )
            
            console.print("\n")
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Error fetching Qdrant logs: {e}[/red]")
    
    def display_system_health(self):
        """Display system health information"""
        console.print("\n[bold magenta]🏥 System Health[/bold magenta]")
        
        try:
            health = self.db.check_system_health()
            
            health_table = Table(
                title="Database Health Status",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold magenta"
            )
            
            health_table.add_column("Component", style="cyan")
            health_table.add_column("Status", style="green")
            health_table.add_column("Details", style="white")
            
            # PostgreSQL status
            pg_status = health.get('postgres_status', 'unknown')
            pg_color = "green" if pg_status == "healthy" else "red"
            health_table.add_row(
                "PostgreSQL",
                f"[{pg_color}]{pg_status}[/{pg_color}]",
                f"Messages: {health.get('postgres_messages', 'unknown')}"
            )
            
            # Qdrant status
            qd_status = health.get('qdrant_status', 'unknown')
            qd_color = "green" if qd_status == "healthy" else "red"
            health_table.add_row(
                "Qdrant",
                f"[{qd_color}]{qd_status}[/{qd_color}]",
                f"Vectors: {health.get('qdrant_vectors', 'unknown')}"
            )
            
            # Overall status
            overall = health.get('overall_status', 'unknown')
            overall_color = "green" if overall == "healthy" else "red"
            health_table.add_row(
                "Overall",
                f"[{overall_color}]{overall}[/{overall_color}]",
                f"Checked: {health.get('timestamp', 'unknown')[:19]}"
            )
            
            console.print(health_table)
            
        except Exception as e:
            console.print(f"[red]Error checking system health: {e}[/red]")
    
    def display_active_robots(self):
        """Display active robots summary"""
        console.print("\n[bold yellow]🤖 Active Robots[/bold yellow]")
        
        try:
            active_robots = self.db.get_active_robots(hours=24)
            
            if not active_robots:
                console.print("[yellow]No active robots found in the last 24 hours[/yellow]")
                return
            
            console.print(f"[green]Found {len(active_robots)} active robots:[/green]")
            
            for i, robot_id in enumerate(sorted(active_robots), 1):
                console.print(f"  {i}. [cyan]{robot_id}[/cyan]")
            
        except Exception as e:
            console.print(f"[red]Error getting active robots: {e}[/red]")
    
    async def run_interactive(self):
        """Run interactive log viewer"""
        console.print("[bold blue]🔍 Interactive Log Viewer[/bold blue]")
        console.print("Commands: [cyan]postgres[/cyan], [cyan]qdrant[/cyan], [cyan]health[/cyan], [cyan]robots[/cyan], [cyan]all[/cyan], [cyan]quit[/cyan]")
        
        while True:
            try:
                command = console.input("\n[bold]Enter command: [/bold]").strip().lower()
                
                if command in ['quit', 'exit', 'q']:
                    console.print("[yellow]Goodbye! 👋[/yellow]")
                    break
                elif command in ['postgres', 'pg']:
                    self.display_postgres_logs()
                elif command in ['qdrant', 'qd']:
                    self.display_qdrant_logs()
                elif command in ['health', 'h']:
                    self.display_system_health()
                elif command in ['robots', 'r']:
                    self.display_active_robots()
                elif command in ['all', 'a']:
                    self.display_system_health()
                    self.display_active_robots()
                    self.display_postgres_logs()
                    self.display_qdrant_logs()
                else:
                    console.print(f"[red]Unknown command: {command}[/red]")
                    console.print("Available: [cyan]postgres, qdrant, health, robots, all, quit[/cyan]")
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]Exiting... 👋[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

def main():
    """Main entry point"""
    try:
        viewer = LogViewer()
        
        # Check if running interactively
        import sys
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()
            if command in ['postgres', 'pg']:
                viewer.display_postgres_logs()
            elif command in ['qdrant', 'qd']:
                viewer.display_qdrant_logs()
            elif command in ['health', 'h']:
                viewer.display_system_health()
            elif command in ['robots', 'r']:
                viewer.display_active_robots()
            elif command in ['all', 'a']:
                viewer.display_system_health()
                viewer.display_active_robots()
                viewer.display_postgres_logs()
                viewer.display_qdrant_logs()
            else:
                console.print(f"[red]Unknown command: {command}[/red]")
                console.print("Usage: python log_viewer.py [postgres|qdrant|health|robots|all]")
        else:
            # Interactive mode
            asyncio.run(viewer.run_interactive())
            
    except Exception as e:
        console.print(f"[red]Failed to start log viewer: {e}[/red]")

if __name__ == "__main__":
    main()