"""Settings read from FIRSTPR_* environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIRSTPR_")

    database_url: str = "postgresql+psycopg://firstpr:firstpr@localhost:5432/firstpr"
    redis_url: str = "redis://localhost:6379/0"
    # The worker writes a heartbeat every minute; older than this means it stopped.
    worker_stale_after_seconds: int = 180

    # Where people reach the site. The GitHub callback URL is built from it.
    public_url: str = "http://localhost:8080"
    # From the GitHub App's settings page. Sign-in is off until both are set.
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    # Only changed to point at a fake GitHub in local end-to-end tests.
    github_web_url: str = "https://github.com"
    github_api_url: str = "https://api.github.com"
    # Fernet keys, comma-separated, newest first. Old keys still decrypt, so keys
    # can be rotated by putting a new one in front.
    token_keys: SecretStr = SecretStr("")

    # Secure cookies need HTTPS. Turn off only for http://localhost.
    cookie_secure: bool = True
    session_days: int = 30
    # How often /me re-checks with GitHub that the user's access still works.
    github_verify_every_seconds: int = 300
    # Sign-in attempts per IP address in 10 minutes.
    login_attempts_per_10_minutes: int = 20
    # GitHub logins (comma-separated) that get the admin pages.
    admin_logins: str = ""
    # Shared secret for GitHub webhook deliveries. Webhooks are refused until it is set.
    github_webhook_secret: SecretStr = SecretStr("")
    # How many repos one person can watch.
    max_watches_per_user: int = 50
    # The Refresh button on Explore works once in this many seconds per user.
    refresh_every_seconds: int = 300
    # The issue page asks GitHub for the latest state when the card is older than this.
    live_after_seconds: int = 600
    # The app's URL name (github.com/apps/<slug>), for the "Install FirstPR" link.
    github_app_slug: str = ""
    # Where everyone opens their first pull request, e.g. "MuskanScripts/firstpr-practice".
    # Empty turns the practice rule off.
    practice_repo: str = ""
    # Only used to tell people whether email is set up on this server (the worker sends).
    resend_api_key: SecretStr = SecretStr("")
    # Open pull requests a person can have waiting at once.
    max_open_prs: int = 3

    @property
    def admin_login_set(self) -> frozenset[str]:
        return frozenset(x.strip().lower() for x in self.admin_logins.split(",") if x.strip())

    @property
    def callback_url(self) -> str:
        return f"{self.public_url.rstrip('/')}/api/v1/auth/github/callback"

    @property
    def sign_in_configured(self) -> bool:
        return bool(
            self.github_client_id
            and self.github_client_secret.get_secret_value()
            and self.token_keys.get_secret_value()
        )
