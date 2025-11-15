# -*- coding: utf-8 -*-
import logging
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict

from config import Settings

LOG = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

class Database:
    def __init__(self, settings: Settings):
        self.db_path = settings.db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def close(self):
        self._conn.close()

    def init_schema(self):
        LOG.info("Ensuring DB schema at %s", self.db_path)
        with open(Path(__file__).parent / "create_tables.sql", "r", encoding="utf-8") as f:
            sql = f.read()
        cur = self._conn.cursor()
        cur.executescript(sql)
        # meta: schema version
        cur.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
        self._conn.commit()

    # --- guild settings ---
    def upsert_guild_settings(
        self,
        guild_id: int,
        singles_channel_id: Optional[int] = None,
        albums_channel_id: Optional[int] = None,
        allow_non_admins: Optional[bool] = None,
    ):
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO guild_settings(guild_id, singles_channel_id, albums_channel_id, allow_non_admins) VALUES(?,?,?,?)",
                (guild_id, singles_channel_id, albums_channel_id, int(allow_non_admins or 0)),
            )
        else:
            if singles_channel_id is not None:
                cur.execute("UPDATE guild_settings SET singles_channel_id=?, updated_at=CURRENT_TIMESTAMP WHERE guild_id=?",
                            (singles_channel_id, guild_id))
            if albums_channel_id is not None:
                cur.execute("UPDATE guild_settings SET albums_channel_id=?, updated_at=CURRENT_TIMESTAMP WHERE guild_id=?",
                            (albums_channel_id, guild_id))
            if allow_non_admins is not None:
                cur.execute("UPDATE guild_settings SET allow_non_admins=?, updated_at=CURRENT_TIMESTAMP WHERE guild_id=?",
                            (int(allow_non_admins), guild_id))
        self._conn.commit()

    def get_guild_settings(self, guild_id: int) -> sqlite3.Row:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,))
        row = cur.fetchone()
        if row is None:
            # create default
            self.upsert_guild_settings(guild_id)
            return self.get_guild_settings(guild_id)
        return row

    # --- follows ---
    def add_follow(self, guild_id: int, artist_id: str, artist_name: str):
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO follows(guild_id, artist_id, artist_name) VALUES(?,?,?)",
            (guild_id, artist_id, artist_name),
        )
        self._conn.commit()

    def remove_follow_by_name(self, guild_id: int, artist_name: str) -> int:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM follows WHERE guild_id=? AND lower(artist_name)=lower(?)", (guild_id, artist_name))
        self._conn.commit()
        return cur.rowcount

    def list_follows(self, guild_id: int) -> List[sqlite3.Row]:
        cur = self._conn.cursor()
        cur.execute("SELECT artist_id, artist_name, added_at FROM follows WHERE guild_id=? ORDER BY artist_name", (guild_id,))
        return cur.fetchall()

    def iter_all_guild_follows(self) -> Iterable[Tuple[int, List[sqlite3.Row]]]:
        cur = self._conn.cursor()
        cur.execute("SELECT DISTINCT guild_id FROM follows ORDER BY guild_id")
        guilds = [r["guild_id"] for r in cur.fetchall()]
        for gid in guilds:
            yield gid, self.list_follows(gid)

    # --- seen releases ---
    def has_seen(self, guild_id: int, release_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM seen_releases WHERE guild_id=? AND release_id=? LIMIT 1", (guild_id, release_id))
        return cur.fetchone() is not None

    def mark_seen(self, guild_id: int, release_id: str, release_type: str):
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO seen_releases(guild_id, release_id, release_type) VALUES(?,?,?)",
            (guild_id, release_id, release_type),
        )
        self._conn.commit()
