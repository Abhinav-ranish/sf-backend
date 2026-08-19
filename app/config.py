from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, overridable via environment variables."""

    model_config = SettingsConfigDict(env_prefix="CONTACTS_", env_file=".env", extra="ignore")

    app_name: str = "Contacts API"

    # Defaults to an in-process SQLite database so the app is self-contained.
    # Point this at a file (sqlite:///./contacts.db) or Postgres to persist data.
    database_url: str = "sqlite+pysqlite:///:memory:"

    # Insert a few sample contacts on startup. Handy for the in-memory default,
    # which starts empty on every boot.
    seed_data: bool = True

    host: str = "127.0.0.1"
    port: int = 8000
    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
