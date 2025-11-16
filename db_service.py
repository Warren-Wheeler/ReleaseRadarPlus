#!/usr/bin/env python3
import os
import sqlite3
import glob
import datetime
from pathlib import Path
from flask import Flask, jsonify

DATA_DB = Path("/data/bot.sqlite3")
BACKUP_DIR = Path("/backups")

app = Flask(__name__)

# ------------------------------------------------------
# HELPERS
# ------------------------------------------------------

def db_is_valid(path: Path) -> bool:
    """Return True if SQLite DB is readable, else False."""
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA integrity_check;")
        conn.close()
        return True
    except Exception:
        return False

def find_latest_backup() -> Path:
    """Return most recent backup file, or None."""
    backups = sorted(BACKUP_DIR.glob("*.db"))
    return backups[-1] if backups else None

def restore_from_backup(src: Path, dest: Path = DATA_DB):
    """Safely restore backup → live using sqlite .backup()."""
    tmp_live = sqlite3.connect(str(dest))
    tmp_src = sqlite3.connect(str(src))
    tmp_src.backup(tmp_live)
    tmp_live.close()
    tmp_src.close()


# ------------------------------------------------------
# AUTO-RESTORE ON STARTUP
# ------------------------------------------------------

def auto_restore_if_needed():
    if db_is_valid(DATA_DB):
        print("[db-service] Live DB valid. No restore needed.")
        return

    print("[db-service] Live DB missing or invalid — restoring from latest backup…")

    latest = find_latest_backup()
    if not latest:
        print("[db-service] ERROR: No backups available to restore!")
        return

    print(f"[db-service] Restoring from {latest.name}")
    restore_from_backup(latest)
    print("[db-service] Restore complete.")


# ------------------------------------------------------
# BACKUP ENDPOINT
# ------------------------------------------------------

@app.route("/backup", methods=["POST"])
def backup_now():
    """Perform safe backup when triggered by discord-bot."""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    out_file = BACKUP_DIR / f"bot_backup_{now}.db"

    src = sqlite3.connect(str(DATA_DB))
    dest = sqlite3.connect(str(out_file))
    src.backup(dest)
    src.close()
    dest.close()

    # cleanup > 7 days old
    for f in BACKUP_DIR.glob("*.db"):
        age = datetime.datetime.utcnow() - datetime.datetime.utcfromtimestamp(f.stat().st_mtime)
        if age.days > 7:
            f.unlink()

    return jsonify({"status": "ok", "backup": out_file.name}), 200


# ------------------------------------------------------
# MAIN ENTRYPOINT
# ------------------------------------------------------

if __name__ == "__main__":
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DB.parent.mkdir(parents=True, exist_ok=True)

    auto_restore_if_needed()

    # start HTTP server
    app.run(host="0.0.0.0", port=8000)
