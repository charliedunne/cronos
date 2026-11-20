"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Cronos backend.

    Values are read from environment variables prefixed with ``CRONOS_``
    or from a local ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_prefix="CRONOS_", env_file=".env", extra="ignore"
    )

    #: SQLAlchemy database URL for the PostgreSQL instance.
    database_url: str = "postgresql+psycopg://cronos:cronos@localhost:5432/cronos"

    #: Whether the session cookie carries the Secure flag (keep true behind
    #: HTTPS; set false only for plain-HTTP development setups).
    cookie_secure: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings.

    @return The process-wide :class:`Settings` instance.
    """
    return Settings()
