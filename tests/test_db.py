# -*- coding: utf-8 -*-
from pathlib import Path
import sqlite3
import os

from config import Settings
from db import Database
from scheduler import make_scheduler

def _temp_settings(tmp_path: Path) -> Settings:
    return Settings(
        discord_bot_token="x",
        spotify_client_id="y",
        spotify_client_secret="z",
        data_dir=tmp_path,
        db_path=tmp_path / "test.sqlite3",
        cache_path=tmp_path / "cache.sqlite",
    )

def test_schema_creation(tmp_path):
    s = _temp_settings(tmp_path)
    db = Database(s)
    db.init_schema()

    con = sqlite3.connect(s.db_path)
    cur = con.cursor()
    for t in ("guild_settings", "follows", "seen_releases", "meta"):
        cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}'")
        assert cur.fetchone() is not None

def test_scheduler_smoke():
    sch = make_scheduler()
    sch.start()
    sch.shutdown(wait=False)
