"""Configuration management for canvas-ledger.

Handles loading, saving, and validating configuration settings.
Tokens are NEVER stored in config files - use the secret provider instead.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w


def get_default_config_path() -> Path:
    """Return the default configuration file path."""
    return Path.home() / ".config" / "cl" / "config.toml"


def get_default_db_path() -> Path:
    """Return the default database file path."""
    return Path.home() / ".local" / "share" / "cl" / "ledger.db"


@dataclass
class Settings:
    """Application settings loaded from config file.

    Tokens/secrets are NOT stored here - they come from the secret provider.
    """

    canvas_base_url: str = ""
    db_path: Path = field(default_factory=get_default_db_path)
    config_path: Path = field(default_factory=get_default_config_path)
    log_level: str = "warning"
    secret_provider: str = "env"  # 'env' or '1password'
    op_reference: str = ""  # 1Password reference, e.g., "op://Dev/Canvas/credential"

    def validate(self) -> list[str]:
        """Validate settings and return list of validation errors."""
        errors = []
        if not self.canvas_base_url:
            errors.append("canvas_base_url is required")
        if self.log_level not in ("debug", "info", "warning", "error"):
            errors.append(f"Invalid log_level: {self.log_level}")
        if self.secret_provider not in ("env", "1password"):
            errors.append(f"Invalid secret_provider: {self.secret_provider}")
        if self.secret_provider == "1password" and not self.op_reference:
            errors.append("op_reference is required when using 1password provider")
        return errors

    def is_valid(self) -> bool:
        """Check if settings are valid."""
        return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to a dictionary for TOML serialization."""
        data: dict[str, Any] = {
            "canvas_base_url": self.canvas_base_url,
            "db_path": str(self.db_path),
            "log_level": self.log_level,
            "secret_provider": self.secret_provider,
        }
        # Only include op_reference if set (avoid cluttering config)
        if self.op_reference:
            data["op_reference"] = self.op_reference
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], config_path: Path | None = None) -> Settings:
        """Create Settings from a dictionary (loaded from TOML)."""
        db_path_str = data.get("db_path")
        db_path = Path(db_path_str) if db_path_str else get_default_db_path()

        return cls(
            canvas_base_url=data.get("canvas_base_url", ""),
            db_path=db_path,
            config_path=config_path or get_default_config_path(),
            log_level=data.get("log_level", "warning"),
            secret_provider=data.get("secret_provider", "env"),
            op_reference=data.get("op_reference", ""),
        )


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from TOML config file.

    Args:
        config_path: Path to config file. Uses default if not provided.

    Returns:
        Settings instance. Returns defaults if file doesn't exist.
    """
    path = config_path or get_default_config_path()

    if not path.exists():
        return Settings(config_path=path)

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return Settings.from_dict(data, config_path=path)


def save_settings(settings: Settings, config_path: Path | None = None) -> None:
    """Save settings to TOML config file.

    Args:
        settings: Settings to save.
        config_path: Path to config file. Uses settings.config_path if not provided.
    """
    path = config_path or settings.config_path

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as f:
        tomli_w.dump(settings.to_dict(), f)


def ensure_directories(settings: Settings) -> None:
    """Ensure required directories exist for config and database."""
    settings.config_path.parent.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
