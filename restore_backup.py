#!/usr/bin/env python3
import sys
import sqlite3
from pathlib import Path

DATA_DB = Path("/data/bot.sqlite3")
BACKUP_DIR = Path("/backups")

def restore(src: Path, dest: Path = DATA_DB):
    print(f"[manual-restore] Restoring {src.name} → {dest}")
    src_db = sqlite3.connect(str(src))
    dest_db = sqlite3.connect(str(dest))
    src_db.backup(dest_db)
    src_db.close()
    dest_db.close()
    print("[manual-restore] Done.")

def main():
    if len(sys.argv) != 2:
        print("Usage: restore_backup.py <backup_filename>")
        sys.exit(1)

    filename = sys.argv[1]
    src = BACKUP_DIR / filename

    if not src.exists():
        print(f"Backup {filename} not found in /backups")
        sys.exit(1)

    restore(src)

if __name__ == "__main__":
    main()
