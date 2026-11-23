import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ENV_FILE = Path(__file__).parents[1] / ".env"


@dataclass(frozen=True, slots=True)
class Settings:
    storage_url: str
    tables_url: str
    managed_identity_client_id: str | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv(ENV_FILE)
        return cls(
            storage_url=_required_url("STORAGE_URL"),
            tables_url=_required_url("TABLES_URL"),
            managed_identity_client_id=os.getenv("AZURE_MANAGED_IDENTITY_CLIENT_ID") or None,
        )


def _required_url(name: str) -> str:
    value = os.getenv(name, "")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"{name} must be configured with an absolute URL.")
    return value
