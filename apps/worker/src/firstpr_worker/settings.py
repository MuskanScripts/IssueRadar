"""Worker settings, read from FIRSTPR_* environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIRSTPR_")

    # The platform database (users, watches, catalogue, sync state).
    database_url: str = "postgresql+psycopg://firstpr:firstpr@localhost:5432/firstpr"
    # The engine's own database: repos, issues, PRs, ETags. Separate, because the
    # engine keeps the schema it already has for the CLI.
    catalogue_database_url: str = (
        "postgresql+psycopg://firstpr:firstpr@localhost:5432/firstpr_catalogue"
    )
    redis_url: str = "redis://localhost:6379/0"

    # The GitHub App: its own token syncs the shared catalogue.
    github_app_id: str = ""
    github_app_private_key: SecretStr = SecretStr("")
    github_installation_id: int | None = None
    # Needed to refresh users' tokens before a personal sync.
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    token_keys: SecretStr = SecretStr("")

    # Personal syncs only run for people who used the site in this many days.
    active_days: int = 14
    # Stop starting new requests when this share of a token's hourly limit is left.
    budget_pause_share: float = 0.2

    @property
    def app_configured(self) -> bool:
        return bool(self.github_app_id and self.github_app_private_key.get_secret_value())

    @property
    def users_configured(self) -> bool:
        return bool(
            self.github_client_id
            and self.github_client_secret.get_secret_value()
            and self.token_keys.get_secret_value()
        )
