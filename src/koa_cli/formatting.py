"""Beautiful terminal formatting for koa-cli output."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.table import Table


def format_jobs_table(raw_output: str, username: str) -> None:
    """
    Format squeue output as a beautiful table.

    Args:
        raw_output: Raw pipe-delimited squeue output
        username: Current user's username (for highlighting)
    """
    console = Console()

    lines = raw_output.strip().split('\n') if raw_output else []
    if not lines:
        console.print("[yellow]No jobs found[/yellow]")
        return

    # Parse header
    header = lines[0].split('|') if lines else []

    # Create table
    table = Table(
        title="Jobs",
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
        border_style="bright_blue",
    )

    # Add columns with appropriate widths
    column_config = {
        "JOBID": {"style": "cyan", "no_wrap": True, "min_width": 8},
        "NAME": {"style": "white", "no_wrap": False, "max_width": 35},
        "STATE": {"style": "yellow", "no_wrap": True, "min_width": 10},
        "TIME": {"style": "green", "no_wrap": True, "min_width": 10},
        "TIME_LIMIT": {"style": "green", "no_wrap": True, "min_width": 12},
        "NODES": {"style": "magenta", "no_wrap": True, "min_width": 6},
        "NODELIST(REASON)": {"style": "white", "no_wrap": False, "max_width": 30},
    }

    for col in header:
        config = column_config.get(col, {"style": "cyan", "no_wrap": True})
        table.add_column(col, **config)

    # Add rows
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split('|')

        # Style based on job state
        state = parts[2] if len(parts) > 2 else ""
        if state == "RUNNING":
            row_style = "green"
        elif state == "PENDING":
            row_style = "yellow"
        elif state in ("FAILED", "TIMEOUT", "CANCELLED"):
            row_style = "red"
        else:
            row_style = "white"

        table.add_row(*parts, style=row_style)

    console.print(table)


def format_queue_table(raw_output: str, username: str, partition: Optional[str] = None) -> None:
    """
    Format squeue output as a beautiful table with user job highlighting.

    Args:
        raw_output: Raw pipe-delimited squeue output
        username: Current user's username (for highlighting)
        partition: Optional partition name to show in title
    """
    console = Console()

    lines = raw_output.strip().split('\n') if raw_output else []
    if not lines:
        console.print("[yellow]No jobs in queue[/yellow]")
        return

    # Parse header
    header = lines[0].split('|') if lines else []

    # Create table
    title = "Queue"
    if partition:
        title += f" (partition: {partition})"

    table = Table(
        title=title,
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
        border_style="bright_blue",
        caption_style="dim",
    )

    # Add columns with appropriate styling
    column_styles = {
        "JOBID": {"style": "cyan", "no_wrap": True, "min_width": 8},
        "USER": {"style": "blue", "no_wrap": True, "min_width": 10},
        "NAME": {"style": "white", "no_wrap": False, "max_width": 30},
        "STATE": {"style": "yellow", "no_wrap": True, "min_width": 10},
        "TIME": {"style": "green", "no_wrap": True, "min_width": 10},
        "TIME_LIMIT": {"style": "green", "no_wrap": True, "min_width": 12},
        "NODES": {"style": "magenta", "no_wrap": True, "min_width": 6},
        "CPUS": {"style": "magenta", "no_wrap": True, "min_width": 5},
        "MIN_MEMORY": {"style": "magenta", "no_wrap": True, "min_width": 11},
        "NODELIST(REASON)": {"style": "white", "no_wrap": False, "max_width": 35},
    }

    for col in header:
        col_config = column_styles.get(col, {"style": "white", "no_wrap": True})
        table.add_column(col, **col_config)

    # Track user jobs for caption
    user_job_count = 0

    # Add rows
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split('|')

        # Check if this is the user's job
        is_user_job = len(parts) > 1 and parts[1] == username
        if is_user_job:
            user_job_count += 1

        # Style based on job state and ownership
        state = parts[3] if len(parts) > 3 else ""

        if is_user_job:
            # User's jobs are highlighted
            if state == "RUNNING":
                row_style = "bold green"
            elif state == "PENDING":
                row_style = "bold yellow"
            elif state in ("FAILED", "TIMEOUT", "CANCELLED"):
                row_style = "bold red"
            else:
                row_style = "bold white"
        else:
            # Other users' jobs are dimmed
            if state == "RUNNING":
                row_style = "dim green"
            elif state == "PENDING":
                row_style = "dim yellow"
            elif state in ("FAILED", "TIMEOUT", "CANCELLED"):
                row_style = "dim red"
            else:
                row_style = "dim white"

        table.add_row(*parts, style=row_style)

    # Set caption
    if user_job_count > 0:
        table.caption = f"[bold green]You have {user_job_count} job(s) in the queue[/bold green]"

    console.print(table)
