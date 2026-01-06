"""Unit tests for configuration module."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from cl.config.secrets import (
    EnvironmentSecretProvider,
    OnePasswordSecretProvider,
    SecretProviderError,
    clear_token_cache,
    get_canvas_token,
    get_secret_provider,
)
from cl.config.settings import (
    Settings,
    get_default_config_path,
    get_default_db_path,
    load_settings,
    save_settings,
)


@pytest.fixture(autouse=True)
def clear_cache() -> Generator[None]:
    """Clear the token cache before and after each test."""
    clear_token_cache()
    yield
    clear_token_cache()


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self) -> None:
        """Settings should have sensible defaults."""
        settings = Settings()

        assert settings.canvas_base_url == ""
        assert settings.db_path == get_default_db_path()
        assert settings.config_path == get_default_config_path()
        assert settings.log_level == "warning"
        assert settings.secret_provider == "env"
        assert settings.op_reference == ""

    def test_validate_missing_url(self) -> None:
        """Validation should fail without canvas_base_url."""
        settings = Settings()
        errors = settings.validate()

        assert len(errors) == 1
        assert "canvas_base_url is required" in errors[0]

    def test_validate_valid_settings(self) -> None:
        """Validation should pass with required fields."""
        settings = Settings(canvas_base_url="https://canvas.example.edu")
        errors = settings.validate()

        assert len(errors) == 0
        assert settings.is_valid()

    def test_validate_invalid_log_level(self) -> None:
        """Validation should fail with invalid log_level."""
        settings = Settings(
            canvas_base_url="https://canvas.example.edu",
            log_level="invalid",
        )
        errors = settings.validate()

        assert any("log_level" in e for e in errors)

    def test_validate_invalid_secret_provider(self) -> None:
        """Validation should fail with invalid secret_provider."""
        settings = Settings(
            canvas_base_url="https://canvas.example.edu",
            secret_provider="invalid",
        )
        errors = settings.validate()

        assert any("secret_provider" in e for e in errors)

    def test_validate_1password_requires_op_reference(self) -> None:
        """Validation should fail when 1password provider is used without op_reference."""
        settings = Settings(
            canvas_base_url="https://canvas.example.edu",
            secret_provider="1password",
            op_reference="",
        )
        errors = settings.validate()

        assert any("op_reference is required" in e for e in errors)

    def test_validate_1password_with_op_reference(self) -> None:
        """Validation should pass when 1password provider has op_reference."""
        settings = Settings(
            canvas_base_url="https://canvas.example.edu",
            secret_provider="1password",
            op_reference="op://Dev/Canvas/credential",
        )
        errors = settings.validate()

        assert len(errors) == 0

    def test_to_dict(self) -> None:
        """Settings should convert to dictionary correctly."""
        settings = Settings(
            canvas_base_url="https://canvas.example.edu",
            db_path=Path("/tmp/test.db"),
            log_level="info",
            secret_provider="env",
        )
        data = settings.to_dict()

        assert data["canvas_base_url"] == "https://canvas.example.edu"
        assert data["db_path"] == "/tmp/test.db"
        assert data["log_level"] == "info"
        assert data["secret_provider"] == "env"
        assert "op_reference" not in data  # Not included when empty

    def test_to_dict_with_op_reference(self) -> None:
        """Settings.to_dict should include op_reference when set."""
        settings = Settings(
            canvas_base_url="https://canvas.example.edu",
            secret_provider="1password",
            op_reference="op://Dev/Canvas/credential",
        )
        data = settings.to_dict()

        assert data["op_reference"] == "op://Dev/Canvas/credential"

    def test_from_dict(self) -> None:
        """Settings should be created from dictionary correctly."""
        data = {
            "canvas_base_url": "https://canvas.example.edu",
            "db_path": "/tmp/test.db",
            "log_level": "debug",
            "secret_provider": "env",
        }
        settings = Settings.from_dict(data)

        assert settings.canvas_base_url == "https://canvas.example.edu"
        assert settings.db_path == Path("/tmp/test.db")
        assert settings.log_level == "debug"
        assert settings.secret_provider == "env"
        assert settings.op_reference == ""

    def test_from_dict_with_op_reference(self) -> None:
        """Settings.from_dict should load op_reference."""
        data = {
            "canvas_base_url": "https://canvas.example.edu",
            "secret_provider": "1password",
            "op_reference": "op://Dev/Canvas/credential",
        }
        settings = Settings.from_dict(data)

        assert settings.op_reference == "op://Dev/Canvas/credential"

    def test_from_dict_defaults(self) -> None:
        """Settings.from_dict should use defaults for missing values."""
        settings = Settings.from_dict({})

        assert settings.canvas_base_url == ""
        assert settings.log_level == "warning"
        assert settings.secret_provider == "env"
        assert settings.op_reference == ""


class TestSettingsIO:
    """Tests for settings file I/O."""

    @pytest.fixture
    def temp_config_path(self, tmp_path: Path) -> Path:
        """Create a temporary config path."""
        return tmp_path / "config.toml"

    def test_save_and_load_settings(self, temp_config_path: Path) -> None:
        """Settings should round-trip through save/load."""
        original = Settings(
            canvas_base_url="https://canvas.example.edu",
            db_path=Path("/tmp/test.db"),
            config_path=temp_config_path,
            log_level="info",
            secret_provider="env",
        )

        save_settings(original, temp_config_path)
        loaded = load_settings(temp_config_path)

        assert loaded.canvas_base_url == original.canvas_base_url
        assert str(loaded.db_path) == str(original.db_path)
        assert loaded.log_level == original.log_level
        assert loaded.secret_provider == original.secret_provider

    def test_save_and_load_with_op_reference(self, temp_config_path: Path) -> None:
        """Settings with op_reference should round-trip correctly."""
        original = Settings(
            canvas_base_url="https://canvas.example.edu",
            config_path=temp_config_path,
            secret_provider="1password",
            op_reference="op://Dev/Canvas/credential",
        )

        save_settings(original, temp_config_path)
        loaded = load_settings(temp_config_path)

        assert loaded.secret_provider == "1password"
        assert loaded.op_reference == "op://Dev/Canvas/credential"

    def test_load_nonexistent_returns_defaults(self, tmp_path: Path) -> None:
        """Loading nonexistent config should return defaults."""
        nonexistent = tmp_path / "does_not_exist.toml"
        settings = load_settings(nonexistent)

        assert settings.canvas_base_url == ""
        assert settings.config_path == nonexistent

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """save_settings should create parent directories."""
        deep_path = tmp_path / "a" / "b" / "c" / "config.toml"
        settings = Settings(canvas_base_url="https://canvas.example.edu")

        save_settings(settings, deep_path)

        assert deep_path.exists()


class TestSecretProviders:
    """Tests for secret providers."""

    @pytest.fixture
    def clean_env(self) -> Generator[None]:
        """Remove CANVAS_API_TOKEN from environment for clean tests."""
        token = os.environ.pop("CANVAS_API_TOKEN", None)
        yield
        if token is not None:
            os.environ["CANVAS_API_TOKEN"] = token

    def test_env_provider_available_when_set(self) -> None:
        """EnvironmentSecretProvider should be available when env var is set."""
        os.environ["CANVAS_API_TOKEN"] = "test-token"
        try:
            provider = EnvironmentSecretProvider()
            assert provider.is_available()
        finally:
            del os.environ["CANVAS_API_TOKEN"]

    def test_env_provider_unavailable_when_unset(self, clean_env: None) -> None:  # noqa: ARG002
        """EnvironmentSecretProvider should be unavailable when env var is unset."""
        provider = EnvironmentSecretProvider()
        assert not provider.is_available()

    def test_env_provider_get_token(self) -> None:
        """EnvironmentSecretProvider should return token from env var."""
        os.environ["CANVAS_API_TOKEN"] = "my-secret-token"
        try:
            provider = EnvironmentSecretProvider()
            assert provider.get_canvas_token() == "my-secret-token"
        finally:
            del os.environ["CANVAS_API_TOKEN"]

    def test_env_provider_raises_when_missing(self, clean_env: None) -> None:  # noqa: ARG002
        """EnvironmentSecretProvider should raise when token is missing."""
        provider = EnvironmentSecretProvider()

        with pytest.raises(SecretProviderError) as exc_info:
            provider.get_canvas_token()

        assert "CANVAS_API_TOKEN" in str(exc_info.value)

    def test_onepassword_provider_requires_reference(self) -> None:
        """OnePasswordSecretProvider should require op_reference."""
        provider = OnePasswordSecretProvider("")

        with pytest.raises(SecretProviderError) as exc_info:
            provider.get_canvas_token()

        assert "reference not configured" in str(exc_info.value)

    def test_onepassword_provider_not_available_without_reference(self) -> None:
        """OnePasswordSecretProvider is_available should return False without reference."""
        provider = OnePasswordSecretProvider("")
        assert not provider.is_available()

    def test_get_secret_provider_env(self) -> None:
        """get_secret_provider should return env provider."""
        provider = get_secret_provider("env")
        assert isinstance(provider, EnvironmentSecretProvider)

    def test_get_secret_provider_1password(self) -> None:
        """get_secret_provider should return 1password provider."""
        provider = get_secret_provider("1password", "op://Dev/Canvas/credential")
        assert isinstance(provider, OnePasswordSecretProvider)
        assert provider.op_reference == "op://Dev/Canvas/credential"

    def test_get_secret_provider_invalid(self) -> None:
        """get_secret_provider should raise for invalid provider name."""
        with pytest.raises(ValueError) as exc_info:
            get_secret_provider("invalid")

        assert "Unknown secret provider" in str(exc_info.value)

    def test_get_canvas_token_with_fallback(self) -> None:
        """get_canvas_token should work with env var set."""
        os.environ["CANVAS_API_TOKEN"] = "fallback-token"
        try:
            # Even if we request 1password (which isn't available),
            # it should fall back to env
            token = get_canvas_token("1password", "op://Dev/Canvas/credential")
            assert token == "fallback-token"
        finally:
            del os.environ["CANVAS_API_TOKEN"]

    def test_get_canvas_token_no_providers(self, clean_env: None) -> None:  # noqa: ARG002
        """get_canvas_token should raise when no provider has token."""
        with pytest.raises(SecretProviderError) as exc_info:
            get_canvas_token("env")

        assert "CANVAS_API_TOKEN" in str(exc_info.value)

    def test_token_caching(self) -> None:
        """Token should be cached after first retrieval."""
        os.environ["CANVAS_API_TOKEN"] = "cached-token"
        try:
            provider = EnvironmentSecretProvider()
            token1 = provider.get_canvas_token()

            # Change env var (shouldn't affect cached value)
            os.environ["CANVAS_API_TOKEN"] = "new-token"
            token2 = provider.get_canvas_token()

            assert token1 == token2 == "cached-token"
        finally:
            del os.environ["CANVAS_API_TOKEN"]


class TestDefaultPaths:
    """Tests for default path functions."""

    def test_default_config_path(self) -> None:
        """Default config path should be in .config/cl."""
        path = get_default_config_path()

        assert path.name == "config.toml"
        assert "cl" in str(path)
        assert ".config" in str(path)

    def test_default_db_path(self) -> None:
        """Default db path should be in .local/share/cl."""
        path = get_default_db_path()

        assert path.name == "ledger.db"
        assert "cl" in str(path)
        assert ".local" in str(path) or "share" in str(path)
