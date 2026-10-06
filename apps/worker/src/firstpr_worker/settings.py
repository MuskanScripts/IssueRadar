"""Worker settings, read from FIRSTPR_* environment variables."""

from __future__ import annotations

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url

from firstpr_platform.db import database_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIRSTPR_")

    # The platform database (users, watches, catalogue, sync state).
    database_url: str = "postgresql+psycopg://firstpr:firstpr@localhost:5432/firstpr"
    # The engine's own database: repos, issues, PRs, ETags. Separate, because the
    # engine keeps the schema it already has for the CLI.
    # Empty: the same server as database_url, database "firstpr_catalogue" (made
    # on first start when missing).
    catalogue_database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # The GitHub App: its own token syncs the shared catalogue.
    github_app_id: str = ""
    github_app_private_key: SecretStr = SecretStr("")
    github_installation_id: int | None = None
    # Needed to refresh users' tokens before a personal sync.
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    token_keys: SecretStr = SecretStr("")
    # Only changed to point at a fake GitHub in local end-to-end tests.
    github_api_url: str = "https://api.github.com"

    # Email through Resend (https://resend.com). Without a key no email is sent.
    resend_api_key: SecretStr = SecretStr("")
    email_from: str = "FirstPR <hello@example.com>"
    # Only changed to point at a fake in local end-to-end tests.
    resend_url: str = "https://api.resend.com/emails"
    # Where people reach the site, for links in emails.
    public_url: str = "http://localhost:8080"

    # PostHog project key and host for the sign-up funnel. Empty: no analytics.
    posthog_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"

    # Error reports. Empty: none are sent.
    sentry_dsn: str = ""
    # development, staging or production; shown in Sentry.
    environment: str = "development"

    # How long one sync job may spend on GitHub before it stops between repos and
    # leaves the rest to the next run. Below the job's own 30-minute limit, so the
    # repos it did finish are always saved.
    sync_time_budget_seconds: int = 20 * 60

    # Personal syncs only run for people who used the site in this many days.
    active_days: int = 14
    # Stop starting new requests when this share of a token's hourly limit is left.
    budget_pause_share: float = 0.2

    @model_validator(mode="after")
    def _urls(self) -> Settings:
        self.database_url = database_url(self.database_url)
        if not self.catalogue_database_url:
            platform = make_url(self.database_url)
            self.catalogue_database_url = platform.set(
                database="firstpr_catalogue"
            ).render_as_string(hide_password=False)
        self.catalogue_database_url = database_url(self.catalogue_database_url)
        return self

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
