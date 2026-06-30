"""Env-driven settings. Reads {{MODULE_ENV}}_* vars and an optional .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Override any field via a {{MODULE_ENV}}_<FIELD> env var
    (e.g. {{MODULE_ENV}}_DEBUG=true) or a local .env (copied from .env.example)."""

    model_config = SettingsConfigDict(
        env_prefix="{{MODULE_ENV}}_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "{{MODULE}}"
    debug: bool = False


settings = Settings()
