"""Secret provider interface for retrieving sensitive credentials.

Supports pluggable providers:
- Environment variable (CANVAS_API_TOKEN)
- 1Password CLI integration (op read)

Tokens are NEVER logged, stored in config files, or exposed in error messages.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from abc import ABC, abstractmethod

# Module-level cache for tokens (avoids repeated CLI calls)
_cached_token: str | None = None


class SecretProviderError(Exception):
    """Raised when secret retrieval fails."""

    pass


class SecretProvider(ABC):
    """Abstract base class for secret providers."""

    @abstractmethod
    def get_canvas_token(self) -> str:
        """Retrieve the Canvas API token.

        Returns:
            The Canvas API token.

        Raises:
            SecretProviderError: If the token cannot be retrieved.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is configured and available."""
        pass


class EnvironmentSecretProvider(SecretProvider):
    """Retrieves secrets from environment variables.

    Looks for CANVAS_API_TOKEN environment variable.
    """

    TOKEN_VAR = "CANVAS_API_TOKEN"

    def get_canvas_token(self) -> str:
        """Retrieve Canvas API token from environment variable."""
        global _cached_token
        if _cached_token:
            return _cached_token

        token = os.environ.get(self.TOKEN_VAR)
        if not token:
            raise SecretProviderError(
                f"Environment variable {self.TOKEN_VAR} is not set. "
                "Set it with your Canvas API token."
            )
        _cached_token = token
        return token

    def is_available(self) -> bool:
        """Check if the environment variable is set."""
        return bool(os.environ.get(self.TOKEN_VAR))


class OnePasswordSecretProvider(SecretProvider):
    """Retrieves secrets from 1Password using the op CLI.

    Uses `op read` to fetch secrets by reference path.
    Example reference: "op://Dev/Canvas/credential"
    """

    def __init__(self, op_reference: str) -> None:
        """Initialize 1Password provider.

        Args:
            op_reference: 1Password secret reference (e.g., "op://Vault/Item/field").
        """
        self.op_reference = op_reference

    def get_canvas_token(self) -> str:
        """Retrieve Canvas API token from 1Password.

        Returns:
            The Canvas API token.

        Raises:
            SecretProviderError: If op CLI is not found or read fails.
        """
        global _cached_token
        if _cached_token:
            return _cached_token

        if not self.op_reference:
            raise SecretProviderError(
                "1Password reference not configured. "
                "Set op_reference in config (e.g., 'op://Dev/Canvas/credential')."
            )

        try:
            result = subprocess.run(
                ["op", "read", self.op_reference],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            raise SecretProviderError(
                "1Password CLI (op) not found. "
                "Install it from https://1password.com/downloads/command-line/ "
                "or use CANVAS_API_TOKEN environment variable instead."
            ) from None

        if result.returncode != 0:
            raise SecretProviderError(f"Failed to read from 1Password: {result.stderr.strip()}")

        _cached_token = result.stdout.strip()
        return _cached_token

    def is_available(self) -> bool:
        """Check if 1Password CLI is installed and reference is configured."""
        if not self.op_reference:
            return False
        return shutil.which("op") is not None


def get_secret_provider(
    provider_name: str = "env",
    op_reference: str = "",
) -> SecretProvider:
    """Get a secret provider by name.

    Args:
        provider_name: Name of the provider ('env' or '1password').
        op_reference: 1Password reference (required if provider_name is '1password').

    Returns:
        A SecretProvider instance.

    Raises:
        ValueError: If the provider name is not recognized.
    """
    if provider_name == "env":
        return EnvironmentSecretProvider()
    elif provider_name == "1password":
        return OnePasswordSecretProvider(op_reference)
    else:
        raise ValueError(
            f"Unknown secret provider: {provider_name}. Available providers: env, 1password"
        )


def get_canvas_token(provider_name: str = "env", op_reference: str = "") -> str:
    """Convenience function to get Canvas token using specified provider.

    Falls back to environment variable if specified provider is unavailable or fails.

    Args:
        provider_name: Preferred provider name.
        op_reference: 1Password reference (if using 1password provider).

    Returns:
        The Canvas API token.

    Raises:
        SecretProviderError: If no provider can supply the token.
    """
    provider = get_secret_provider(provider_name, op_reference)

    # Try the preferred provider first
    if provider.is_available():
        try:
            return provider.get_canvas_token()
        except SecretProviderError:
            # If preferred provider fails, try fallback
            pass

    # Fall back to environment variable (if not already using it)
    if provider_name != "env":
        env_provider = EnvironmentSecretProvider()
        if env_provider.is_available():
            return env_provider.get_canvas_token()

    # If we get here with env provider, try it anyway to get a proper error
    if provider_name == "env":
        return provider.get_canvas_token()

    raise SecretProviderError(
        "No Canvas API token available. "
        "Set CANVAS_API_TOKEN environment variable or configure 1Password."
    )


def clear_token_cache() -> None:
    """Clear the cached token (useful for testing)."""
    global _cached_token
    _cached_token = None
