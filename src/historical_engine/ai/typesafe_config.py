from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TYPESAFE_API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_TYPESAFE_MODEL = "jev-latest"
DEFAULT_TYPESAFE_AUTH_HEADER = "Authorization"
DEFAULT_TYPESAFE_AUTH_PREFIX = "Bearer"


def load_env_file(path: Path | str = ".env", *, override: bool = False, export: bool = True) -> dict[str, str]:
    """Load a small dotenv-style file without adding a runtime dependency.

    Supports KEY=value, optional single/double quotes, blank lines, and comments.
    Existing environment variables win unless override=True.
    """

    path = Path(path)
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=value")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"{path}:{line_number}: environment key is empty")

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        loaded[key] = value
        if export and (override or key not in os.environ):
            os.environ[key] = value

    return loaded


@dataclass(frozen=True, slots=True)
class TypeSafeConfig:
    api_key: str | None
    api_url: str | None
    auth_header: str | None
    auth_prefix: str | None
    model: str

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @property
    def has_api_url(self) -> bool:
        return bool(self.api_url and self.api_url.strip())

    @property
    def ready_for_transport(self) -> bool:
        return self.has_api_key and self.has_api_url

    def safe_status(self) -> dict[str, object]:
        return {
            "api_key_configured": self.has_api_key,
            "api_url_configured": self.has_api_url,
            "auth_header_configured": bool(self.auth_header and self.auth_header.strip()),
            "auth_prefix_configured": bool(self.auth_prefix and self.auth_prefix.strip()),
            "model": self.model,
            "ready_for_transport": self.ready_for_transport,
        }


def typesafe_config_from_env(
    *,
    load_dotenv: bool = True,
    dotenv_path: Path | str = ".env",
) -> TypeSafeConfig:
    # Read fresh local settings without freezing them into process environment.
    values = load_env_file(dotenv_path, export=False) if load_dotenv else {}
    values.update(os.environ)

    return TypeSafeConfig(
        api_key=values.get("TYPESAFE_API_KEY"),
        api_url=values.get("TYPESAFE_API_URL") or DEFAULT_TYPESAFE_API_URL,
        auth_header=values.get("TYPESAFE_API_AUTH_HEADER") or DEFAULT_TYPESAFE_AUTH_HEADER,
        auth_prefix=values.get("TYPESAFE_API_AUTH_PREFIX") or DEFAULT_TYPESAFE_AUTH_PREFIX,
        model=values.get("TYPESAFE_MODEL") or DEFAULT_TYPESAFE_MODEL,
    )
