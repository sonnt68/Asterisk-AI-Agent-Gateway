"""Environment-backed application settings."""

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    session_secret: str
    api_key_pepper: str
    bootstrap_email: str | None
    bootstrap_password: str | None
    realtime_issuer: str


def get_settings() -> Settings:
    return Settings(
        database_url=getenv("GATEWAY_DATABASE_URL", "sqlite:///./runtime-data/gateway.db"),
        session_secret=getenv("GATEWAY_SESSION_SECRET", "development-only-change-me"),
        api_key_pepper=getenv("GATEWAY_API_KEY_PEPPER", "development-only-change-me"),
        bootstrap_email=getenv("GATEWAY_BOOTSTRAP_EMAIL"),
        bootstrap_password=getenv("GATEWAY_BOOTSTRAP_PASSWORD"),
        realtime_issuer=getenv("GATEWAY_REALTIME_ISSUER", "asterisk-ai-agent-gateway"),
    )
