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
    ari_base_url: str | None
    ari_username: str | None
    ari_password: str | None
    audiosocket_host: str
    audiosocket_port: int
    audiosocket_advertise_host: str
    web_origin: str
    redis_url: str | None
    cookie_secure: bool
    browser_session_max_age: int
    media_transport: str
    external_media_host: str
    external_media_advertise_host: str
    token_rate_limit_per_minute: int


def get_settings() -> Settings:
    return Settings(
        database_url=getenv("GATEWAY_DATABASE_URL", "sqlite:///./runtime-data/gateway.db"),
        session_secret=getenv("GATEWAY_SESSION_SECRET", "development-only-change-me"),
        api_key_pepper=getenv("GATEWAY_API_KEY_PEPPER", "development-only-change-me"),
        bootstrap_email=getenv("GATEWAY_BOOTSTRAP_EMAIL"),
        bootstrap_password=getenv("GATEWAY_BOOTSTRAP_PASSWORD"),
        realtime_issuer=getenv("GATEWAY_REALTIME_ISSUER", "asterisk-ai-agent-gateway"),
        ari_base_url=getenv("ASTERISK_ARI_BASE_URL"),
        ari_username=getenv("ASTERISK_ARI_USERNAME"),
        ari_password=getenv("ASTERISK_ARI_PASSWORD"),
        audiosocket_host=getenv("AUDIOSOCKET_HOST", "0.0.0.0"),
        audiosocket_port=int(getenv("AUDIOSOCKET_PORT", "8090")),
        audiosocket_advertise_host=getenv("AUDIOSOCKET_ADVERTISE_HOST", "api"),
        web_origin=getenv("GATEWAY_WEB_ORIGIN", "http://localhost:5173"),
        redis_url=getenv("REDIS_URL"),
        cookie_secure=getenv("GATEWAY_COOKIE_SECURE", "false").lower() == "true",
        browser_session_max_age=int(getenv("GATEWAY_BROWSER_SESSION_MAX_AGE", "28800")),
        media_transport=getenv("GATEWAY_MEDIA_TRANSPORT", "audiosocket").lower(),
        external_media_host=getenv("EXTERNAL_MEDIA_HOST", "0.0.0.0"),
        external_media_advertise_host=getenv("EXTERNAL_MEDIA_ADVERTISE_HOST", "api"),
        token_rate_limit_per_minute=int(
            getenv("GATEWAY_TOKEN_RATE_LIMIT_PER_MINUTE", "60")
        ),
    )
