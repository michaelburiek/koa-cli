from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, Optional

from .config import Config
from .ssh import SSHError, copy_to_remote, run_ssh

SBATCH_JOB_ID_PATTERN = re.compile(r"Submitted batch job (\d+)")
DEFAULT_PARTITION = "kill-shared"

# GPU priority ranking (higher score = better GPU)
GPU_PRIORITY = {
    "h200": 110,
    "nvidiah200nvl": 110,
    "h100": 100,
    "nvidiah100": 100,
    "a100": 90,
    "nvidiaa100": 90,
    "a30": 80,
    "nvidiaa30": 80,
    "v100": 70,
    "nvidiav100": 70,
    "rtx2080ti": 50,
    "rtx_2080_ti": 50,
    "geforce_rtx_2080_ti": 50,
    "nvidiageforcertx2080ti": 50,
}

# Default GPU to request if detection fails
FALLBACK_GPU = "rtx2080ti"

# Map detected GPU names to SLURM GRES names
GPU_NAME_MAP = {
    "nvidiah200nvl": "nvidia_h200_nvl",
    "nvidiah100": "nvidia_h100",
    "nvidiaa100": "nvidia_a100",
    "nvidiaa30": "nvidia_a30",
    "nvidiav100": "nvidia_v100",
    "nvidiageforcertx2080ti": "geforce_rtx_2080_ti",
}


def _has_partition_flag(args: Iterable[str]) -> bool:
    """Return True if any sbatch argument sets the partition."""
    for arg in args:
        if arg in {"--partition", "-p"}:
            return True
        if arg.startswith("--partition="):
            return True
        if arg.startswith("-p") and arg != "-p":
            return True
    return False


def _has_gres_flag(args: Iterable[str]) -> bool:
    """Return True if any sbatch argument sets the GPU/GRES."""
    for arg in args:
        if arg in {"--gres", "--gpus", "--gpus-per-node"}:
            return True
        if arg.startswith("--gres=") or arg.startswith("--gpus="):
            return True
    return False


def get_available_gpus(config: Config, partition: str = DEFAULT_PARTITION) -> Dict[str, int]:
    """
    Query available GPUs on Koa partition.

    Returns:
        Dict mapping GPU type to count of available nodes
        Example: {"h100": 2, "a100": 5, "rtx2080ti": 10}
    """
    try:
        result = run_ssh(
            config,
            [
                "sinfo",
                "-p",
                partition,
                "--Format=nodehost,gres:30,statecompact",
                "--noheader",
            ],
            capture_output=True,
        )

        gpu_counts: Dict[str, int] = {}
        lines = result.stdout.strip().split("\n") if result.stdout else []

        for line in lines:
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) < 3:
                continue

            gres = parts[1].lower()
            state = parts[2].lower()

            # Only count idle or mixed nodes
            if state not in ["idle", "mix", "mixed"]:
                continue

            # Extract GPU type from GRES (e.g., "gpu:h100:1" -> "h100")
            if "gpu:" in gres:
                gpu_parts = gres.split(":")
                if len(gpu_parts) >= 2:
                    gpu_type = gpu_parts[1].replace("_", "")
                    gpu_counts[gpu_type] = gpu_counts.get(gpu_type, 0) + 1

        return gpu_counts

    except Exception as e:
        print(f"Warning: Could not detect available GPUs: {e}")
        return {}


def select_best_gpu(config: Config, partition: str = DEFAULT_PARTITION) -> str:
    """
    Automatically select the best available GPU based on priority ranking.

    Returns:
        GPU type string in SLURM GRES format (e.g., "nvidia_h100", "a100", "rtx2080ti")
    """
    available = get_available_gpus(config, partition)

    if not available:
        print(f"No GPU info available, using fallback: {FALLBACK_GPU}")
        return FALLBACK_GPU

    # Find highest priority GPU that's available
    best_gpu = None
    best_score = -1

    for gpu_type, count in available.items():
        if count > 0:
            score = GPU_PRIORITY.get(gpu_type, 0)
            if score > best_score:
                best_score = score
                best_gpu = gpu_type

    if best_gpu:
        slurm_gpu_name = GPU_NAME_MAP.get(best_gpu, best_gpu)
        print(
            f"Auto-selected GPU: {best_gpu} -> {slurm_gpu_name} "
            f"(priority: {best_score}, {available[best_gpu]} nodes available)"
        )
        return slurm_gpu_name

    print(f"No recognized GPUs available, using fallback: {FALLBACK_GPU}")
    return FALLBACK_GPU


def ensure_remote_workspace(config: Config) -> None:
    """Create remote working directory if it doesn't exist."""
    run_ssh(config, ["mkdir", "-p", str(config.remote_workdir)])


def parse_gpu_count_from_script(script_path: Path) -> Optional[int]:
    """
    Parse the GPU count from #SBATCH --gres=gpu:N directive in a SLURM script.

    Returns:
        GPU count as integer, or None if not found
    """
    try:
        with open(script_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Look for #SBATCH --gres=gpu:N
                if line.startswith('#SBATCH') and '--gres' in line:
                    # Handle formats like:
                    # #SBATCH --gres=gpu:2
                    # #SBATCH --gres=gpu:nvidia_h100:2
                    # #SBATCH --gres gpu:2
                    match = re.search(r'--gres[=\s]+gpu:(?:[^:]+:)?(\d+)', line)
                    if match:
                        return int(match.group(1))
    except Exception:
        pass
    return None


def submit_job(
    config: Config,
    local_job_script: Path,
    *,
    sbatch_args: Optional[Iterable[str]] = None,
    remote_name: Optional[str] = None,
    auto_gpu: bool = True,
) -> str:
    """
    Copy a job script to Koa and submit it with sbatch. Returns the job id.

    Args:
        config: Koa configuration
        local_job_script: Path to SLURM script to submit
        sbatch_args: Additional sbatch arguments
        remote_name: Remote filename (default: same as local)
        auto_gpu: If True, automatically select best available GPU (default: True)

    Returns:
        Job ID as string

    Raises:
        FileNotFoundError: If job script doesn't exist
        SSHError: If submission fails
    """
    if not local_job_script.exists():
        raise FileNotFoundError(f"Job script not found: {local_job_script}")

    ensure_remote_workspace(config)

    # Copy script to the current repo's subdirectory on remote
    # Use the current working directory name to determine the repo folder
    cwd_name = Path.cwd().name

    # Validate directory name to prevent path traversal
    if cwd_name in (".", "..", "") or "/" in cwd_name or "\\" in cwd_name:
        raise ValueError(f"Invalid directory name: {cwd_name}")

    remote_repo_dir = config.remote_workdir / cwd_name

    # Preserve relative path structure if the script is in a subdirectory
    if remote_name:
        remote_script = remote_repo_dir / remote_name
    else:
        # Get the relative path from cwd to the script
        try:
            relative_script_path = local_job_script.resolve().relative_to(Path.cwd().resolve())
            remote_script = remote_repo_dir / relative_script_path
        except ValueError:
            # Script is outside cwd, just use the filename
            remote_script = remote_repo_dir / local_job_script.name

    copy_to_remote(config, local_job_script, remote_script)

    args = ["sbatch"]
    sbatch_args_list = list(sbatch_args or [])

    # Add default partition if not specified
    if not _has_partition_flag(sbatch_args_list):
        args.extend(["--partition", DEFAULT_PARTITION])

    # Auto-select best GPU if enabled and no GPU already specified
    if auto_gpu and not _has_gres_flag(sbatch_args_list):
        # Determine partition for GPU query
        partition = DEFAULT_PARTITION
        for i, arg in enumerate(sbatch_args_list):
            if arg in {"--partition", "-p"} and i + 1 < len(sbatch_args_list):
                partition = sbatch_args_list[i + 1]
            elif arg.startswith("--partition="):
                partition = arg.split("=", 1)[1]

        # Parse GPU count from the script itself
        gpu_count = parse_gpu_count_from_script(local_job_script)
        if gpu_count is None:
            gpu_count = 1  # Default to 1 if not specified in script

        best_gpu = select_best_gpu(config, partition)

        # Show user what GPU configuration will be used
        if gpu_count > 1:
            print(f"Requesting {gpu_count} x {best_gpu} GPUs (from script)")

        args.extend(["--gres", f"gpu:{best_gpu}:{gpu_count}"])

    if sbatch_args_list:
        args.extend(sbatch_args_list)
    args.append(str(remote_script))

    # Disable TTY for sbatch to avoid MOTD errors interfering with output parsing
    result = run_ssh(config, args, capture_output=True, force_tty=False)
    output = result.stdout.strip() if result.stdout else ""
    match = SBATCH_JOB_ID_PATTERN.search(output)
    if not match:
        raise SSHError(f"Unable to parse sbatch output for job id: {output}")
    return match.group(1)


def cancel_job(config: Config, job_id: str) -> None:
    """Cancel a SLURM job by ID."""
    run_ssh(config, ["scancel", job_id])


def list_jobs(config: Config) -> str:
    """List all active jobs for the configured user."""
    result = run_ssh(
        config,
        [
            "squeue",
            "-u",
            config.user,
            "-o",
            r"%i|%j|%T|%M|%l|%D|%R",
        ],
        capture_output=True,
    )
    return result.stdout


def queue_status(config: Config, partition: Optional[str] = None) -> str:
    """
    Show the full queue status, highlighting the user's jobs.

    Args:
        config: Koa configuration
        partition: Optional partition filter (e.g., "kill-shared")

    Returns:
        Formatted queue status output
    """
    cmd = [
        "squeue",
        "-o",
        r"%i|%u|%j|%T|%M|%l|%D|%C|%m|%R",
        "--sort=P,t,-p",  # Sort by priority, time, descending priority
    ]

    if partition:
        cmd.extend(["-p", partition])

    result = run_ssh(config, cmd, capture_output=True)

    # Add header and highlight user's jobs
    lines = result.stdout.strip().split('\n') if result.stdout else []
    if not lines:
        return "No jobs in queue\n"

    output = []
    output.append("=" * 100)
    output.append(f"Queue Status{f' (partition: {partition})' if partition else ''}")
    output.append("=" * 100)

    # Process each line and highlight user's jobs
    for i, line in enumerate(lines):
        if i == 0:
            # Header line
            output.append(line)
            output.append("-" * 100)
        else:
            # Check if this is the user's job
            parts = line.split('|')
            if len(parts) > 1 and parts[1] == config.user:
                output.append(f">>> {line} <<<")  # Highlight user's jobs
            else:
                output.append(line)

    output.append("=" * 100)
    output.append(f"Your jobs are marked with >>> <<<")
    output.append("=" * 100)

    return '\n'.join(output) + '\n'


def build_environment(
    config: Config,
    repo_name: str,
    requirements_file: Optional[Path] = None,
    rebuild: bool = False,
) -> None:
    """
    Build a persistent virtual environment for a repository on Koa.

    Args:
        config: Koa configuration
        repo_name: Name of the repository
        requirements_file: Optional path to requirements.txt or setup.py
        rebuild: If True, remove existing venv and rebuild from scratch

    The environment will be created at:
    /mnt/lustre/koa/scratch/$USER/koa-jobs/<repo-name>/.venv
    """
    # Code directory is in home (for syncing)
    remote_repo_dir = config.remote_workdir / repo_name

    # But venv goes in Lustre scratch for space
    remote_venv_dir = f"/mnt/lustre/koa/scratch/{config.user}/koa-jobs/{repo_name}/.venv"

    print(f"Building environment for {repo_name} on Koa...")
    print(f"Location: {config.login}:{remote_venv_dir}")

    # Build the setup script
    setup_script_lines = [
        "set -e",
        "set -u",
        "set -o pipefail",
        "",
        f"REPO_DIR='{remote_repo_dir}'",
        f"VENV_DIR='{remote_venv_dir}'",
        "",
        "echo '================================================================'",
        "echo 'Building Python Environment on Koa'",
        "echo '================================================================'",
        "echo \"Repository: ${REPO_DIR}\"",
        "echo \"Environment: ${VENV_DIR}\"",
        "echo ''",
        "",
        "# Check if repo directory exists",
        "if [ ! -d \"${REPO_DIR}\" ]; then",
        "  echo 'Error: Repository directory does not exist!'",
        "  echo 'Run: koa sync'",
        "  exit 1",
        "fi",
        "",
        "cd \"${REPO_DIR}\"",
        "",
    ]

    if rebuild:
        setup_script_lines.extend([
            "# Remove existing environment",
            "if [ -d \"${VENV_DIR}\" ]; then",
            "  echo 'Removing existing environment...'",
            "  rm -rf \"${VENV_DIR}\"",
            "  echo '✓ Removed'",
            "fi",
            "",
        ])

    setup_script_lines.extend([
        "# Load Python module",
        "module load lang/Python/3.11.5-GCCcore-13.2.0",
        "echo \"✓ Loaded Python $(python --version)\"",
        "echo ''",
        "",
        "# Ensure parent directory exists",
        "mkdir -p \"$(dirname ${VENV_DIR})\"",
        "",
        "# Configure pip to use Lustre for temp files (not /tmp which is small)",
        f"export TMPDIR=\"/mnt/lustre/koa/scratch/{config.user}/tmp\"",
        "mkdir -p \"${TMPDIR}\"",
        "echo \"✓ Using ${TMPDIR} for temporary files\"",
        "echo ''",
        "",
        "# Create virtual environment if it doesn't exist",
        "if [ ! -d \"${VENV_DIR}\" ]; then",
        "  echo 'Creating virtual environment...'",
        "  python -m venv \"${VENV_DIR}\"",
        "  chmod -R u+rwx \"${VENV_DIR}\"",
        "  echo '✓ Virtual environment created'",
        "else",
        "  echo '✓ Virtual environment already exists'",
        "fi",
        "",
        "# Activate environment",
        "source \"${VENV_DIR}/bin/activate\"",
        "echo '✓ Environment activated'",
        "echo ''",
        "",
        "# Upgrade pip",
        "echo 'Upgrading pip...'",
        "python -m pip install --quiet 'pip<24.1'",
        "echo '✓ pip upgraded'",
        "echo ''",
        "",
    ])

    # Install from requirements or setup.py if provided
    if requirements_file:
        setup_script_lines.extend([
            f"# Install from {requirements_file.name}",
            f"if [ -f \"{requirements_file.name}\" ]; then",
            f"  echo 'Installing from {requirements_file.name}...'",
            f"  python -m pip install -r \"{requirements_file.name}\"",
            "  echo '✓ Dependencies installed'",
            "else",
            f"  echo 'Warning: {requirements_file.name} not found'",
            "fi",
            "echo ''",
            "",
        ])
    else:
        # Try to detect and install from common files
        setup_script_lines.extend([
            "# Install project dependencies",
            "if [ -f 'setup.py' ] || [ -f 'pyproject.toml' ]; then",
            "  echo 'Installing project in editable mode...'",
            "  python -m pip install -e .",
            "  echo '✓ Project installed'",
            "elif [ -f 'requirements.txt' ]; then",
            "  echo 'Installing from requirements.txt...'",
            "  python -m pip install -r requirements.txt",
            "  echo '✓ Requirements installed'",
            "else",
            "  echo 'No setup.py, pyproject.toml, or requirements.txt found'",
            "  echo 'Environment created but no dependencies installed'",
            "fi",
            "echo ''",
            "",
        ])

    setup_script_lines.extend([
        "# Show installed packages",
        "echo 'Installed packages:'",
        "python -m pip list",
        "echo ''",
        "",
        "echo '================================================================'",
        "echo '✓ Environment ready!'",
        "echo '================================================================'",
        "echo \"To use in SLURM scripts:\"",
        "echo \"  source ${VENV_DIR}/bin/activate\"",
        "echo '================================================================'",
    ])

    setup_script = "\n".join(setup_script_lines)

    # Execute the setup script on Koa
    run_ssh(
        config,
        ["bash", "-c", setup_script],
        capture_output=False,  # Show output to user
    )


def run_health_checks(config: Config) -> str:
    """Run basic connectivity and SLURM health checks."""
    result = run_ssh(
        config,
        [
            "bash",
            "-lc",
            (
                "set -euo pipefail;"
                "echo '== hostname =='; hostname;"
                "echo '== sinfo =='; sinfo -o '%P %a %l %D %G %m'"
            ),
        ],
        capture_output=True,
    )
    return result.stdout
