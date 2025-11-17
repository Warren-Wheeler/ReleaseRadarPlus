# -*- coding: utf-8 -*-
import logging
import sqlite3
import json
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict

from config import Settings

LOG = logging.getLogger(__name__)

SCHEMA_VERSION = "2"


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
        cur.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        # Ensure new schema pieces exist even on older DBs
        self._ensure_notify_column(cur)
        self._ensure_pending_notifications_table(cur)
        self._conn.commit()

    def _ensure_notify_column(self, cur: sqlite3.Cursor):
        """
        Ensure guild_settings has notify_minute_utc column.
        Default is 10:00 UTC (600 minutes) == 5:00 EST.
        """
        try:
            cur.execute("PRAGMA table_info(guild_settings)")
            cols = {row["name"] for row in cur.fetchall()}
            if "notify_minute_utc" not in cols:
                LOG.info("Adding notify_minute_utc column to guild_settings (default 600).")
                cur.execute(
                    "ALTER TABLE guild_settings "
                    "ADD COLUMN notify_minute_utc INTEGER DEFAULT 600"
                )
        except Exception:
            LOG.exception("Failed ensuring notify_minute_utc column.")

    def _ensure_pending_notifications_table(self, cur: sqlite3.Cursor):
        """
        Ensure the pending_notifications table exists.

        This holds per-guild releases that have been detected but not yet
        sent according to the guild's configured notification time.
        """
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                release_id TEXT NOT NULL,
                release_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_pending_guild_id
                ON pending_notifications(guild_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_unique
                ON pending_notifications(guild_id, release_id);
            """
        )

    def get_all_guild_ids(self) -> List[int]:
        """
        Return all guild IDs that have a guild_settings row.
        Used by the per-minute scheduler.
        """
        cur = self._conn.execute("SELECT guild_id FROM guild_settings;")
        return [row["guild_id"] for row in cur.fetchall()]

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
                "INSERT INTO guild_settings("
                "guild_id, singles_channel_id, albums_channel_id, allow_non_admins"
                ") VALUES(?,?,?,?)",
                (guild_id, singles_channel_id, albums_channel_id, int(allow_non_admins or 0)),
            )
        else:
            if singles_channel_id is not None:
                cur.execute(
                    "UPDATE guild_settings "
                    "SET singles_channel_id=?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE guild_id=?",
                    (singles_channel_id, guild_id),
                )
            if albums_channel_id is not None:
                cur.execute(
                    "UPDATE guild_settings "
                    "SET albums_channel_id=?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE guild_id=?",
                    (albums_channel_id, guild_id),
                )
            if allow_non_admins is not None:
                cur.execute(
                    "UPDATE guild_settings "
                    "SET allow_non_admins=?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE guild_id=?",
                    (int(allow_non_admins), guild_id),
                )
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

    def set_guild_notify_minute(self, guild_id: int, minute_utc: int):
        """
        Set the daily notification time for a guild as minutes since midnight UTC.
        """
        # ensure row exists
        _ = self.get_guild_settings(guild_id)
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE guild_settings "
            "SET notify_minute_utc=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE guild_id=?",
            (minute_utc, guild_id),
        )
        self._conn.commit()

    def iter_guild_notification_times(self) -> Iterable[Tuple[int, int]]:
        """
        Yield (guild_id, notify_minute_utc) for all guilds.
        If column is NULL, default to 600 (10:00 UTC == 5:00 EST).
        """
        cur = self._conn.cursor()
        cur.execute("SELECT guild_id, notify_minute_utc FROM guild_settings")
        rows = cur.fetchall()
        for row in rows:
            minute = row["notify_minute_utc"]
            if minute is None:
                minute = 600
            yield row["guild_id"], int(minute)

    # --- follows ---
    def add_follow(self, guild_id: int, artist_id: str, artist_name: str):
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO follows(guild_id, artist_id, artist_name) "
            "VALUES(?,?,?)",
            (guild_id, artist_id, artist_name),
        )
        self._conn.commit()

    def remove_follow_by_name(self, guild_id: int, artist_name: str) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "DELETE FROM follows "
            "WHERE guild_id=? AND lower(artist_name)=lower(?)",
            (guild_id, artist_name),
        )
        self._conn.commit()
        return cur.rowcount

    def list_follows(self, guild_id: int) -> List[sqlite3.Row]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT artist_id, artist_name, added_at "
            "FROM follows WHERE guild_id=? ORDER BY artist_name",
            (guild_id,),
        )
        return cur.fetchall()

    def iter_all_guild_follows(self) -> Iterable[Tuple[int, List[sqlite3.Row]]]:
        cur = self._conn.cursor()
        cur.execute("SELECT DISTINCT guild_id FROM follows ORDER BY guild_id")
        guilds = [r["guild_id"] for r in cur.fetchall()]
        for gid in guilds:
            yield gid, self.list_follows(gid)

    # --- pending notifications ---
    def queue_notification(
        self,
        guild_id: int,
        release_id: str,
        release_type: str,
        payload: Dict,
    ):
        """
        Queue a notification for later sending. payload is a JSON-serializable
        dict (Spotify release item).
        """
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO pending_notifications("
            "guild_id, release_id, release_type, payload_json"
            ") VALUES(?,?,?,?)",
            (guild_id, release_id, release_type, json.dumps(payload)),
        )
        self._conn.commit()

    def get_pending_notifications_for_guild(
        self, guild_id: int
    ) -> List[sqlite3.Row]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM pending_notifications WHERE guild_id=? ORDER BY id",
            (guild_id,),
        )
        return cur.fetchall()

    def remove_pending_notification(self, notif_id: int):
        cur = self._conn.cursor()
        cur.execute("DELETE FROM pending_notifications WHERE id=?", (notif_id,))
        self._conn.commit()

    # --- seen releases ---
    def has_seen(self, guild_id: int, release_id: str) -> bool:
        """
        True if a release has either already been sent or is queued
        for this guild.
        """
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM seen_releases
             WHERE guild_id=? AND release_id=?
            UNION
            SELECT 1 FROM pending_notifications
             WHERE guild_id=? AND release_id=?
            LIMIT 1
            """,
            (guild_id, release_id, guild_id, release_id),
        )
        return cur.fetchone() is not None

    def mark_seen(self, guild_id: int, release_id: str, release_type: str):
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO seen_releases("
            "guild_id, release_id, release_type"
            ") VALUES(?,?,?)",
            (guild_id, release_id, release_type),
        )
        self._conn.commit()
