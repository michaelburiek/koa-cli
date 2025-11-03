# koa-cli

A lightweight command-line tool for submitting jobs to the Koa HPC cluster at the University of Hawaii. Designed to work seamlessly with any repository, koa-cli simplifies job submission by handling SSH, SLURM, and storage management.

## Overview

koa-cli is task-focused: sync your code, submit jobs, and manage outputs. It's designed to work **inside any repository** (like oumi-ai, transformers, etc.) - you use their scripts and architectures, koa-cli just makes execution on Koa HPC easier.

## Key Features

- Interactive setup wizard with storage configuration
- Smart two-tier storage (home directory for code, Lustre scratch for data)
- Auto GPU selection (H200 > H100 > A100 > etc.)
- Simple commands: `setup`, `check`, `sync`, `submit`, `jobs`, `cancel`
- Works from any repository - no example scripts needed

## Installation

### From Source (Recommended)

```bash
git clone https://github.com/michaelburiek/koa-cli.git
cd koa-cli
pip install -e .
```

### From PyPI (Future)

```bash
pip install koa-cli
```

## Quick Start

### 1. Run Setup

```bash
koa setup
```

The interactive wizard will guide you through:

- UH NetID configuration
- Storage setup (home directory vs Lustre scratch)
- SSH connection testing

### 2. Test Connection

```bash
koa check
```

### 3. Use with Any Repository

```bash
# Clone any ML/AI repository
git clone https://github.com/oumi-ai/oumi.git
cd oumi

# Sync code to Koa (creates ~/koa-jobs/oumi/)
koa sync

# Submit a job (create your own SLURM script following the storage pattern)
koa submit train.slurm --gpus 2
```

**Note:** `koa sync` automatically creates a subdirectory for each repository (e.g., `~/koa-jobs/oumi/`, `~/koa-jobs/VLMEvalKit/`) to keep projects organized and prevent file conflicts.

## Storage Architecture

Koa HPC has strict storage constraints that koa-cli handles automatically:

| Storage Type       | Location                                  | Quota                | Use Case                       |
| ------------------ | ----------------------------------------- | -------------------- | ------------------------------ |
| **Home Directory** | `~/koa-jobs/<repo-name>/`                 | 50 GB                | Code, configs, scripts         |
| **Lustre Scratch** | `/mnt/lustre/koa/scratch/$USER/koa-jobs/` | Large (90-day purge) | Datasets, results, checkpoints |

### The Pattern

koa-cli uses a three-tier approach:

1. **Code in Home Directory** - Small, synced via `koa sync`
2. **Virtual Environments on Compute Nodes** - Built in `/tmp/` during job execution
3. **Outputs in Lustre Scratch** - Unlimited storage for large artifacts

This avoids the 50GB home directory limit while keeping everything organized.

## Configuration

### Setup Wizard

Run `koa setup` for interactive configuration. It creates `~/.config/koa-cli/config.yaml`:

```yaml
user: your_netid
host: koa.its.hawaii.edu
remote_workdir: ~/koa-jobs # Code (50GB limit)
remote_data_dir: /mnt/lustre/koa/scratch/your_netid/koa-jobs # Data (large)
```

### Environment Variables

Override config with environment variables:

```bash
export KOA_USER=mynetid
export KOA_REMOTE_WORKDIR=~/koa-jobs
export KOA_REMOTE_DATA_DIR=/mnt/lustre/koa/scratch/$USER/koa-jobs
```

## SLURM Script Pattern

When creating job scripts for use with koa-cli, follow this pattern:

```bash
#!/bin/bash
#SBATCH --job-name=my-training
#SBATCH --partition=gpu
#SBATCH --gres=gpu:2
#SBATCH --mem=64G
#SBATCH --time=24:00:00

set -e

# Storage setup
CODE_DIR="${HOME}/koa-jobs/$(basename $(pwd))"
DATA_DIR="${KOA_REMOTE_DATA_DIR:-/mnt/lustre/koa/scratch/$USER/koa-jobs}"
RESULTS_DIR="${DATA_DIR}/results/${SLURM_JOB_ID}"
mkdir -p "${RESULTS_DIR}"

# Build venv on compute node (in /tmp - no quota issues)
VENV_DIR="/tmp/${USER}-venv-${SLURM_JOB_ID}"
module load lang/Python/3.11.5-GCCcore-13.2.0
python -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

# Install dependencies
cd "${CODE_DIR}"
pip install -e .

# Run training (outputs go to Lustre)
python train.py --output_dir "${RESULTS_DIR}"

# Cleanup
deactivate
rm -rf "${VENV_DIR}"
```

### Why This Works

- **Code is small** - Fits in 50GB home directory
- **Virtual envs are temporary** - Built in `/tmp/` on compute nodes
- **Large outputs go to Lustre** - Unlimited storage, no home quota issues
- **Fresh environment every job** - Reproducible builds
- **Automatic cleanup** - `/tmp/` cleared when job ends

## Commands

### `koa setup`

Interactive setup wizard. Creates config file with storage settings.

### `koa check`

Test SSH connection and show Koa cluster info.

### `koa sync [--path DIR] [--exclude PATTERN]`

Sync code from local directory to remote workdir. Each repository is synced to its own subdirectory (e.g., `oumi` → `~/koa-jobs/oumi/`).

```bash
# Sync current directory to ~/koa-jobs/<current-dir-name>/
koa sync

# Sync specific directory to ~/koa-jobs/<dir-name>/
koa sync --path ~/my-project

# Custom excludes
koa sync --exclude "*.data" --exclude "large_files/"
```

### `koa submit SCRIPT [OPTIONS]`

Submit a SLURM job script.

```bash
# Basic submit
koa submit train.slurm

# With GPU auto-selection
koa submit train.slurm --gpus 2

# Override resources
koa submit train.slurm --partition gpu --time 48:00:00 --mem 128G

# Disable auto-GPU
koa submit train.slurm --no-auto-gpu
```

### `koa jobs`

List your active jobs.

### `koa cancel JOB_ID`

Cancel a job by ID.

## Example Workflow: Training with OUMI

```bash
# 1. Clone the repo
git clone https://github.com/oumi-ai/oumi.git
cd oumi

# 2. Create SLURM script following the pattern above
# Save as train.slurm

# 3. Sync code to Koa (creates ~/koa-jobs/oumi/)
koa sync

# 4. Submit job (automatically uses ~/koa-jobs/oumi/)
koa submit train.slurm --gpus 2

# 5. Monitor
koa jobs

# 6. Retrieve results (after job completes)
scp -r koa.its.hawaii.edu:/mnt/lustre/koa/scratch/$USER/koa-jobs/results/123456 ./
```

**Multiple Projects Example:**

```bash
# Work with multiple repos without conflicts
cd ~/repos/oumi
koa sync              # → ~/koa-jobs/oumi/
koa submit train.slurm

cd ~/repos/VLMEvalKit
koa sync              # → ~/koa-jobs/VLMEvalKit/
koa submit eval.slurm
```

## Storage Management

### Check Usage

```bash
# Home directory
ssh koa.its.hawaii.edu "du -sh ~"

# Lustre scratch
ssh koa.its.hawaii.edu "du -sh /mnt/lustre/koa/scratch/$USER/koa-jobs"
```

### Cleanup Old Results

```bash
# List results by date
ssh koa.its.hawaii.edu "ls -lht /mnt/lustre/koa/scratch/$USER/koa-jobs/results/"

# Delete old job
ssh koa.its.hawaii.edu "rm -rf /mnt/lustre/koa/scratch/$USER/koa-jobs/results/123456"
```

### 90-Day Purge Policy

Files on Lustre scratch are automatically deleted after 90 days of no modification. Download important results locally or push to cloud storage.

## Advanced Configuration

### HuggingFace Cache in Lustre

Prevent HF cache from filling home directory:

```bash
# In your SLURM script
HF_CACHE_DIR="${DATA_DIR}/hf_cache"
mkdir -p "${HF_CACHE_DIR}"

export HF_HOME="${HF_CACHE_DIR}"
export TRANSFORMERS_CACHE="${HF_CACHE_DIR}"
export HF_DATASETS_CACHE="${HF_CACHE_DIR}"
```

### SSH Identity Files

If using a specific SSH key:

```yaml
# In config.yaml
identity_file: ~/.ssh/koa_rsa
```

### Proxy/Jump Hosts

For jump host access:

```yaml
# In config.yaml
proxy_command: ssh -W %h:%p jumphost.example.com
```

## Troubleshooting

### "Configuration file not found"

Run `koa setup` to create the config file.

### "SSH command failed"

1. Test SSH manually: `ssh your_netid@koa.its.hawaii.edu`
2. Set up SSH keys if needed:
   ```bash
   ssh-keygen -t rsa
   ssh-copy-id your_netid@koa.its.hawaii.edu
   ```

### "Disk quota exceeded"

Check home directory usage:

```bash
ssh koa.its.hawaii.edu "du -sh ~/*"
```

Ensure your SLURM scripts save outputs to `$RESULTS_DIR` (Lustre), not home directory.

### Strange `~` directory created (Fixed in latest version)

Early versions had a bug where a literal directory named `~` was created on Koa. To clean it up:

```bash
ssh koa.its.hawaii.edu "rm -rf '~'"
```

This bug is fixed - update to the latest version with `pip install -e . --upgrade`.

### Job Fails During pip install

- Retry the job (network issues are common)
- Use `pip install --retries 5`
- Pre-download wheels to Lustre and install from there

## Development

### Project Structure

```
koa-cli/
├── src/koa_cli/          # Main package
│   ├── __init__.py       # Package exports
│   ├── __main__.py       # CLI entry point
│   ├── config.py         # Configuration management
│   ├── setup.py          # Setup wizard
│   ├── ssh.py            # SSH/rsync operations
│   ├── slurm.py          # SLURM job management
│   └── ui.py             # Rich terminal UI
├── pyproject.toml        # Package metadata
├── setup.py              # Setup script
├── config.example.yaml   # Example config
└── README.md             # This file
```

### Development Setup

```bash
git clone https://github.com/michaelburiek/koa-cli.git
cd koa-cli
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Testing

```bash
# Test setup
koa setup

# Test connection
koa check

# Test sync
cd /path/to/any/repo
koa sync

# Test submit (create a simple test.slurm first)
koa submit test.slurm
```

### Building

```bash
pip install build
python -m build
```

## Resources

- [Koa HPC Documentation](https://www.hawaii.edu/its/ci/koa/)
- [SLURM Documentation](https://slurm.schedmd.com/)
- [GitHub Issues](https://github.com/michaelburiek/koa-cli/issues)

## License

MIT License - see LICENSE file for details.

## Support

- GitHub Issues: https://github.com/michaelburiek/koa-cli/issues
- Koa Support: https://www.hawaii.edu/its/help/

---

Happy computing on Koa!
