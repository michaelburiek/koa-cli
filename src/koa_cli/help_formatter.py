"""Custom help formatter using rich for beautiful output."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def print_help(parser: argparse.ArgumentParser) -> None:
    """Print beautiful help using rich formatting."""
    console = Console()

    # Title
    console.print()
    console.print(
        Panel(
            "[bold cyan]koa[/bold cyan] - Koa HPC Cluster CLI",
            subtitle="Command-line tool for submitting jobs to Koa",
            border_style="cyan",
        )
    )
    console.print()

    # Commands table
    table = Table(
        title="[bold magenta]Commands[/bold magenta]",
        show_header=True,
        header_style="bold cyan",
        border_style="bright_blue",
        title_style="bold magenta",
    )

    table.add_column("Command", style="bold green", no_wrap=True, min_width=12)
    table.add_column("Description", style="white", no_wrap=False)

    # Add commands with their descriptions
    commands = [
        ("setup", "Interactive setup wizard for first-time configuration"),
        ("check", "Run Koa connectivity health checks"),
        ("jobs", "List your active jobs"),
        ("queue", "Show full queue status with your jobs highlighted"),
        ("cancel", "Cancel a job by ID"),
        ("submit", "Submit a job script via sbatch"),
        ("sync", "Sync current directory to remote Koa workdir"),
        ("build-env", "Build a persistent Python environment on Koa"),
    ]

    for cmd, desc in commands:
        table.add_row(cmd, desc)

    console.print(table)
    console.print()

    # Usage examples
    console.print("[bold cyan]Usage Examples:[/bold cyan]")
    console.print()
    console.print("  [dim]#[/dim] First time setup")
    console.print("  [green]koa setup[/green]")
    console.print()
    console.print("  [dim]#[/dim] Check your jobs")
    console.print("  [green]koa jobs[/green]")
    console.print()
    console.print("  [dim]#[/dim] View the queue")
    console.print("  [green]koa queue[/green]")
    console.print()
    console.print("  [dim]#[/dim] Submit a job")
    console.print("  [green]koa submit my_job.slurm[/green]")
    console.print()
    console.print("  [dim]#[/dim] Sync your code to Koa")
    console.print("  [green]koa sync[/green]")
    console.print()

    # Get help for specific command
    console.print("[dim]For help on a specific command, use:[/dim]")
    console.print("  [yellow]koa <command> --help[/yellow]")
    console.print()


def print_command_help(parser: argparse.ArgumentParser, command: str) -> None:
    """Print help for a specific subcommand."""
    console = Console()

    # Get the subparser for this command
    subparsers_actions = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]

    if not subparsers_actions:
        # Fall back to default help
        parser.print_help()
        return

    for subparsers_action in subparsers_actions:
        if command in subparsers_action.choices:
            subparser = subparsers_action.choices[command]

            # Title
            console.print()
            console.print(
                Panel(
                    f"[bold cyan]koa {command}[/bold cyan]",
                    subtitle=subparser.description or subparser.format_help().split('\n')[0],
                    border_style="cyan",
                )
            )
            console.print()

            # Get all arguments (excluding positionals that are from parent parser)
            positionals = []
            options = []

            for action in subparser._actions:
                if action.dest == 'help':
                    continue
                if action.option_strings:
                    options.append(action)
                else:
                    positionals.append(action)

            # Positional arguments
            if positionals:
                table = Table(
                    title="[bold magenta]Arguments[/bold magenta]",
                    show_header=True,
                    header_style="bold cyan",
                    border_style="bright_blue",
                    title_style="bold magenta",
                )
                table.add_column("Argument", style="bold green", no_wrap=True)
                table.add_column("Description", style="white", no_wrap=False)

                for action in positionals:
                    name = action.dest.upper()
                    help_text = action.help or ""
                    table.add_row(name, help_text)

                console.print(table)
                console.print()

            # Options
            if options:
                table = Table(
                    title="[bold magenta]Options[/bold magenta]",
                    show_header=True,
                    header_style="bold cyan",
                    border_style="bright_blue",
                    title_style="bold magenta",
                )
                table.add_column("Option", style="bold yellow", no_wrap=True, min_width=20)
                table.add_column("Description", style="white", no_wrap=False)

                for action in options:
                    # Format option strings
                    opts = ", ".join(action.option_strings)
                    if action.metavar:
                        opts += f" {action.metavar}"
                    elif action.type:
                        opts += f" <{action.dest}>"

                    help_text = action.help or ""
                    table.add_row(opts, help_text)

                console.print(table)
                console.print()

            return

    # Command not found, fall back to default
    parser.print_help()
