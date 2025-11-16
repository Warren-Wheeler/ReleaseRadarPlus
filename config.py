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
    spotify_refresh_token: str = ""   # <-- NEW

    # Optional (only used by your patch script, not required at runtime)
    spotify_redirect_uri: str = ""

    # Paths
    data_dir: Path = DEFAULT_DATA_DIR
    db_path: Path = DEFAULT_DATA_DIR / "bot.sqlite3"
    cache_path: Path = DEFAULT_DATA_DIR / "http_cache"

    # Behavior
    weekly_hour: int = 6
    weekly_minute: int = 0
    weekly_day_of_week: str = "fri"
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
    candidate = Path("/run/secrets") / env_key
    if candidate.exists():
        return candidate.read_text(encoding="utf-8").strip()
    return None

def load_config() -> Settings:
    s = Settings()
    # backfill from Docker secrets if env missing
    for key in ("DISCORD_BOT_TOKEN","SPOTIFY_CLIENT_ID","SPOTIFY_CLIENT_SECRET","SPOTIFY_REFRESH_TOKEN"):
        cur = getattr(s, key.lower(), "")
        if not cur:
            secret = _load_from_docker_secrets(key)
            if secret:
                setattr(s, key.lower(), secret)

    missing = [k for k in ("discord_bot_token","spotify_client_id","spotify_client_secret","spotify_refresh_token")
               if not getattr(s, k)]
    if missing:
        raise SystemExit(f"Missing required secrets: {', '.join(missing)}")
    return s
