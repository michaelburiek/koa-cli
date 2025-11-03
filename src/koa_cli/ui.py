"""UI utilities for rich terminal output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


BONSAI = """
    [bold green]🌳[/bold green]
"""


def print_bonsai() -> None:
    """Print a cute bonsai tree."""
    console.print(BONSAI, justify="center")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]✗[/bold red] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def print_header(title: str, subtitle: str | None = None) -> None:
    """Print a styled header."""
    text = Text()
    text.append(title, style="bold cyan")
    if subtitle:
        text.append(f"\n{subtitle}", style="dim")

    panel = Panel(
        text,
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def print_step(step: int, total: int, message: str) -> None:
    """Print a step indicator."""
    console.print(f"[bold cyan][{step}/{total}][/bold cyan] {message}")


def prompt(message: str, default: str | None = None) -> str:
    """Prompt user for input with optional default."""
    if default:
        prompt_text = f"[bold]{message}[/bold] [dim]({default})[/dim]: "
    else:
        prompt_text = f"[bold]{message}[/bold]: "

    console.print(prompt_text, end="")
    response = input().strip()
    return response if response else (default or "")


def confirm(message: str, default: bool = True) -> bool:
    """Ask user for yes/no confirmation."""
    default_text = "Y/n" if default else "y/N"
    console.print(f"[bold]{message}[/bold] [dim]({default_text})[/dim]: ", end="")
    response = input().strip().lower()

    if not response:
        return default
    return response in ("y", "yes")
