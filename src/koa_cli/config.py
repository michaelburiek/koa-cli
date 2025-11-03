from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import yaml


DEFAULT_CONFIG_PATH = Path("~/.config/koa-cli/config.yaml").expanduser()


@dataclass
class Config:
    """Configuration for connecting to Koa HPC cluster."""

    user: str
    host: str
    identity_file: Optional[Path] = None
    remote_workdir: Path = Path("~/koa-jobs")
    remote_data_dir: Optional[Path] = None  # For large outputs, typically /mnt/lustre/...
    proxy_command: Optional[str] = None

    @property
    def login(self) -> str:
        """Return the SSH login string (user@host)."""
        return f"{self.user}@{self.host}"


PathLikeOrStr = Union[os.PathLike[str], str]


def load_config(config_path: Optional[PathLikeOrStr] = None) -> Config:
    """
    Load configuration from disk. When no path is provided we fall back to
    ~/.config/koa-cli/config.yaml and merge it with environment overrides.
    """
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found at {path}. "
            "Create ~/.config/koa-cli/config.yaml with your Koa credentials:\n\n"
            "user: your_koa_netid\n"
            "host: koa.its.hawaii.edu\n"
            "remote_workdir: ~/koa-jobs  # optional\n"
            "identity_file: ~/.ssh/id_rsa  # optional\n"
            "proxy_command: ssh -W %h:%p jumphost  # optional"
        )

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    # Environment variable overrides
    env_overrides = {
        "user": os.getenv("KOA_USER"),
        "host": os.getenv("KOA_HOST"),
        "identity_file": os.getenv("KOA_IDENTITY_FILE"),
        "remote_workdir": os.getenv("KOA_REMOTE_WORKDIR"),
        "remote_data_dir": os.getenv("KOA_REMOTE_DATA_DIR"),
        "proxy_command": os.getenv("KOA_PROXY_COMMAND"),
    }

    for key, value in env_overrides.items():
        if value is not None:
            data[key] = value

    # Validate required fields
    missing = [key for key in ("user", "host") if not data.get(key)]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    # Process identity file
    identity_file = data.get("identity_file") or None
    identity_path: Optional[Path] = None
    if identity_file:
        identity_path = Path(identity_file).expanduser()
        if not identity_path.exists():
            raise FileNotFoundError(
                f"Configured identity_file not found: {identity_path}. "
                "Update the path or remove the identity_file setting to rely on your SSH defaults."
            )

    # Get remote workdir and data dir
    # Note: These are remote paths, so we store them as-is (including ~)
    # They will be expanded on the remote host during initialization
    remote_workdir_str = data.get("remote_workdir", "~/koa-jobs")
    remote_data_dir_str = data.get("remote_data_dir")

    # Create Path objects without expansion (they're remote paths)
    remote_workdir = Path(remote_workdir_str)
    remote_data_path: Optional[Path] = Path(remote_data_dir_str) if remote_data_dir_str else None

    return Config(
        user=data["user"],
        host=data["host"],
        identity_file=identity_path,
        remote_workdir=remote_workdir,
        remote_data_dir=remote_data_path,
        proxy_command=data.get("proxy_command") or None,
    )
