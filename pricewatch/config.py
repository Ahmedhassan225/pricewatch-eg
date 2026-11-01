from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level settings. Secrets and tunables live here; user-facing
    preferences (ntfy topic, thresholds) can also be overridden in the Settings page
    and are stored in the `settings` table."""

    model_config = SettingsConfigDict(env_prefix="PW_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8765
    db_path: Path = Path("data/pricewatch.db")
    scan_interval_sec: int = 120
    market_interval_sec: int = 900
    fetch_concurrency: int = 3
    request_timeout_sec: float = 25.0
    playwright_profile_dir: Path = Path(".playwright-profile")
    playwright_headless: bool = True
    # optional: path to a Chromium binary if you don't want `playwright install chromium`
    chromium_path: str = ""

    # Simple HTTP Basic Auth for when the dashboard is exposed (e.g. through ngrok).
    # Auth is enforced as soon as auth_password is set.
    auth_user: str = "admin"
    auth_password: str = ""

    ntfy_topics: str = ""  # comma separated; each subscriber phone follows one of them
    ntfy_server: str = "https://ntfy.sh"
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""  # comma separated

    # analysis defaults (overridable in Settings page)
    flash_drop_pct: float = 10.0
    alert_cooldown_hours: int = 6
    match_threshold: int = 70

    @property
    def sqlalchemy_url(self) -> str:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_path}"


settings = Settings()
