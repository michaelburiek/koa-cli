from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .config import Config, load_config
from .setup import run_setup
from .slurm import build_environment, cancel_job, list_jobs, queue_status, run_health_checks, submit_job
from .ssh import SSHError, sync_directory_to_remote
from .ui import print_error, print_info, print_success

# Common patterns to exclude when syncing code
DEFAULT_EXCLUDES: list[str] = [
    ".git/",
    ".gitignore",
    ".venv/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.log",
    "*.tmp",
    ".DS_Store",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".coverage",
    ".idea/",
    ".vscode/",
    ".claude/",
    "node_modules/",
    "*.egg-info/",
    "dist/",
    "build/",
]


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common CLI arguments to parser."""
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to the Koa config file (defaults to ~/.config/koa-cli/config.yaml).",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="koa",
        description="Command-line tool for submitting jobs to Koa HPC cluster.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # koa setup
    subparsers.add_parser("setup", help="Interactive setup wizard for first-time configuration.")

    # koa check
    check_parser = subparsers.add_parser("check", help="Run Koa connectivity health checks.")
    _add_common_arguments(check_parser)

    # koa jobs
    jobs_parser = subparsers.add_parser("jobs", help="List active jobs for the configured user.")
    _add_common_arguments(jobs_parser)

    # koa queue
    queue_parser = subparsers.add_parser("queue", help="Show full queue status with your jobs highlighted.")
    _add_common_arguments(queue_parser)
    queue_parser.add_argument(
        "--partition",
        help="Filter by partition (e.g., kill-shared).",
    )

    # koa cancel <job_id>
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a job by ID.")
    _add_common_arguments(cancel_parser)
    cancel_parser.add_argument("job_id", help="SLURM job ID to cancel.")

    # koa submit <job_script>
    submit_parser = subparsers.add_parser("submit", help="Submit a job script via sbatch.")
    _add_common_arguments(submit_parser)
    submit_parser.add_argument("job_script", type=Path, help="Path to the local job script.")
    submit_parser.add_argument("--remote-name", help="Override the filename on Koa.")
    submit_parser.add_argument(
        "--partition",
        help="SLURM partition (queue) to submit to. Defaults to kill-shared.",
    )
    submit_parser.add_argument("--time", help="Walltime request (e.g. 02:00:00).")
    submit_parser.add_argument("--gpus", type=int, help="Number of GPUs to request.")
    submit_parser.add_argument("--gres", help="GRES specification (e.g. gpu:2, gpu:h100:1).")
    submit_parser.add_argument("--cpus", type=int, help="Number of CPUs to request.")
    submit_parser.add_argument("--memory", help="Memory request (e.g. 32G).")
    submit_parser.add_argument("--account", help="SLURM account if required.")
    submit_parser.add_argument("--qos", help="Quality of service if required.")
    submit_parser.add_argument(
        "--sbatch-arg",
        action="append",
        default=[],
        help="Additional raw sbatch arguments. Repeat for multiple flags.",
    )
    submit_parser.add_argument(
        "--no-auto-gpu",
        action="store_true",
        help="Disable automatic GPU selection (use GPU from script or --gpus flag).",
    )

    # koa sync
    sync_parser = subparsers.add_parser(
        "sync", help="Sync the current directory to the remote Koa workdir."
    )
    _add_common_arguments(sync_parser)
    sync_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Local directory to sync (defaults to current working directory).",
    )
    sync_parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Exclude pattern for rsync (repeatable).",
    )

    # koa build-env
    build_env_parser = subparsers.add_parser(
        "build-env",
        help="Build a persistent Python environment for the current repo on Koa.",
    )
    _add_common_arguments(build_env_parser)
    build_env_parser.add_argument(
        "--requirements",
        type=Path,
        default=None,
        help="Path to requirements.txt (defaults to auto-detect).",
    )
    build_env_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Remove existing environment and rebuild from scratch.",
    )

    return parser


def _load(args: argparse.Namespace) -> Config:
    """Load configuration from file or environment."""
    return load_config(args.config)


def _submit(args: argparse.Namespace, config: Config) -> int:
    """Handle 'koa submit' command."""
    sbatch_args: list[str] = []
    if args.partition:
        sbatch_args.extend(["--partition", args.partition])
    if args.time:
        sbatch_args.extend(["--time", args.time])
    if args.gpus:
        sbatch_args.append(f"--gres=gpu:{args.gpus}")
    if args.gres:
        sbatch_args.append(f"--gres={args.gres}")
    if args.cpus:
        sbatch_args.extend(["--cpus-per-task", str(args.cpus)])
    if args.memory:
        sbatch_args.extend(["--mem", args.memory])
    if args.account:
        sbatch_args.extend(["--account", args.account])
    if args.qos:
        sbatch_args.extend(["--qos", args.qos])
    sbatch_args.extend(args.sbatch_arg or [])

    # Disable auto-GPU if user specifies --gpus, --gres, or --no-auto-gpu
    auto_gpu = not (args.no_auto_gpu or args.gpus or args.gres)

    job_id = submit_job(
        config,
        args.job_script,
        sbatch_args=sbatch_args,
        remote_name=args.remote_name,
        auto_gpu=auto_gpu,
    )
    print_success(f"Submitted job {job_id} to Koa")
    return 0


def _cancel(args: argparse.Namespace, config: Config) -> int:
    """Handle 'koa cancel' command."""
    cancel_job(config, args.job_id)
    print_success(f"Cancelled job {args.job_id}")
    return 0


def _jobs(_: argparse.Namespace, config: Config) -> int:
    """Handle 'koa jobs' command."""
    print(list_jobs(config), end="")
    return 0


def _queue(args: argparse.Namespace, config: Config) -> int:
    """Handle 'koa queue' command."""
    print(queue_status(config, partition=args.partition), end="")
    return 0


def _check(_: argparse.Namespace, config: Config) -> int:
    """Handle 'koa check' command."""
    print(run_health_checks(config), end="")
    return 0


def _sync(args: argparse.Namespace, config: Config) -> int:
    """Handle 'koa sync' command."""
    local_path = Path(args.path).expanduser().resolve() if args.path else Path.cwd()
    excludes = list(DEFAULT_EXCLUDES)
    if args.exclude:
        excludes.extend(args.exclude)

    # Create a subdirectory for each repo to avoid mixing files
    # Validate directory name to prevent path traversal
    dir_name = local_path.name
    if dir_name in (".", "..", "") or "/" in dir_name or "\\" in dir_name:
        print_error(f"Invalid directory name: {dir_name}")
        return 1

    remote_repo_dir = config.remote_workdir / dir_name

    print_info(f"Syncing {dir_name} to Koa...")
    sync_directory_to_remote(
        config,
        local_path,
        remote_repo_dir,
        excludes=excludes,
    )
    print_success(f"Synced to {config.login}:{remote_repo_dir}")
    return 0


def _build_env(args: argparse.Namespace, config: Config) -> int:
    """Handle 'koa build-env' command."""
    # Get current repo name
    repo_name = Path.cwd().name

    # Validate directory name
    if repo_name in (".", "..", "") or "/" in repo_name or "\\" in repo_name:
        print_error(f"Invalid directory name: {repo_name}")
        return 1

    try:
        build_environment(
            config,
            repo_name,
            requirements_file=args.requirements,
            rebuild=args.rebuild,
        )
        print_success("Environment built successfully!")
        return 0
    except Exception as exc:
        print_error(f"Failed to build environment: {exc}")
        return 1


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Setup doesn't need config
    if args.command == "setup":
        return run_setup()

    try:
        config = _load(args)
    except (FileNotFoundError, ValueError) as exc:
        print_error(str(exc))
        print_info("Run 'koa setup' to configure koa-cli")
        return 1

    try:
        if args.command == "submit":
            return _submit(args, config)
        if args.command == "cancel":
            return _cancel(args, config)
        if args.command == "jobs":
            return _jobs(args, config)
        if args.command == "queue":
            return _queue(args, config)
        if args.command == "check":
            return _check(args, config)
        if args.command == "sync":
            return _sync(args, config)
        if args.command == "build-env":
            return _build_env(args, config)
    except (SSHError, FileNotFoundError) as exc:
        print_error(str(exc))
        return 1

    parser.error(f"Unhandled command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
