import os
from pathlib import Path

from historical_engine.ai.typesafe_config import (
    load_env_file,
    typesafe_config_from_env,
)


def test_load_env_file_reads_typesafe_settings(tmp_path: Path, monkeypatch) -> None:
    for key in (
        "TYPESAFE_API_KEY",
        "TYPESAFE_API_URL",
        "TYPESAFE_API_AUTH_HEADER",
        "TYPESAFE_API_AUTH_PREFIX",
    ):
        monkeypatch.delenv(key, raising=False)

    path = tmp_path / ".env"
    path.write_text(
        "\n".join(
            [
                "TYPESAFE_API_KEY=secret-value",
                "TYPESAFE_API_URL=https://api.example.test/jev",
                "TYPESAFE_API_AUTH_HEADER=Authorization",
                "TYPESAFE_API_AUTH_PREFIX=Bearer",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_env_file(path)
    config = typesafe_config_from_env(load_dotenv=False)

    assert loaded["TYPESAFE_API_KEY"] == "secret-value"
    assert config.api_key == "secret-value"
    assert config.api_url == "https://api.example.test/jev"
    assert config.ready_for_transport is True


def test_existing_environment_wins_over_dotenv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-environment")
    path = tmp_path / ".env"
    path.write_text("TYPESAFE_API_KEY=from-file\n", encoding="utf-8")

    load_env_file(path)

    assert os.environ["TYPESAFE_API_KEY"] == "from-environment"


def test_safe_status_never_contains_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "do-not-print-this")
    monkeypatch.setenv("TYPESAFE_API_URL", "https://api.example.test/jev")

    status = typesafe_config_from_env(load_dotenv=False).safe_status()
    rendered = repr(status)

    assert status["api_key_configured"] is True
    assert status["api_url_configured"] is True
    assert status["ready_for_transport"] is True
    assert "do-not-print-this" not in rendered


def test_documented_endpoint_is_default(monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "configured")
    monkeypatch.delenv("TYPESAFE_API_URL", raising=False)
    monkeypatch.delenv("TYPESAFE_MODEL", raising=False)

    config = typesafe_config_from_env(load_dotenv=False)

    assert config.has_api_key is True
    assert config.api_url == "https://api.typesafe.ai/v1/systemone"
    assert config.model == "jev-latest"
    assert config.ready_for_transport is True


def test_local_settings_refresh_without_mutating_environment(tmp_path, monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    path = tmp_path / '.env'
    path.write_text('TYPESAFE_API_KEY=\n')
    assert not typesafe_config_from_env(dotenv_path=path).has_api_key
    path.write_text('TYPESAFE_API_KEY=updated\n')
    assert typesafe_config_from_env(dotenv_path=path).api_key == 'updated'
    path.write_text('TYPESAFE_API_KEY=rotated\n')
    assert typesafe_config_from_env(dotenv_path=path).api_key == 'rotated'
    assert 'TYPESAFE_API_KEY' not in __import__('os').environ
