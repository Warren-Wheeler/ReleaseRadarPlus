# -*- coding: utf-8 -*-
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, validator

ENV_FILE = ".env"
DEFAULT_DATA_DIR = Path(os.environ.get("DATA_DIR") or "./data").resolve()

class Settings(BaseSettings):
    # Secrets
    discord_bot_token: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    # Paths
    data_dir: Path = DEFAULT_DATA_DIR
    db_path: Path = DEFAULT_DATA_DIR / "bot.sqlite3"
    cache_path: Path = DEFAULT_DATA_DIR / "http_cache"

    # Behavior
    weekly_hour: int = 6       # 06:00
    weekly_minute: int = 0
    weekly_day_of_week: str = "fri"  # Friday
    max_retries: int = 6

    class Config:
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator("data_dir", pre=True)
    def _ensure_data_dir(cls, v):
        p = Path(v).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @validator("db_path", "cache_path", pre=True)
    def _to_path(cls, v):
        return Path(v)

def _load_from_docker_secrets(env_key: str) -> Optional[str]:
    """
    If running in Docker with secrets mounted at /run/secrets/<ENV_KEY>,
    load them transparently.
    """
    candidate = Path("/run/secrets") / env_key
    if candidate.exists():
        return candidate.read_text(encoding="utf-8").strip()
    return None

def load_config() -> Settings:
    s = Settings()  # loads from .env if present
    # Fill secrets from Docker secrets when available and not already set.
    s.discord_bot_token = s.discord_bot_token or (_load_from_docker_secrets("DISCORD_BOT_TOKEN") or "")
    s.spotify_client_id = s.spotify_client_id or (_load_from_docker_secrets("SPOTIFY_CLIENT_ID") or "")
    s.spotify_client_secret = s.spotify_client_secret or (_load_from_docker_secrets("SPOTIFY_CLIENT_SECRET") or "")
    # Basic validation
    missing = []
    if not s.discord_bot_token:
        missing.append("DISCORD_BOT_TOKEN")
    if not s.spotify_client_id:
        missing.append("SPOTIFY_CLIENT_ID")
    if not s.spotify_client_secret:
        missing.append("SPOTIFY_CLIENT_SECRET")
    if missing:
        raise SystemExit(f"Missing required secrets: {', '.join(missing)}")
    return s
