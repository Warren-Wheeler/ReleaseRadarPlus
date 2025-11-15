# -*- coding: utf-8 -*-
"""
Container HEALTHCHECK: quick DB open and trivial query.
Exit code 0 = healthy, non-zero = unhealthy.
"""
import sys
from config import load_config
from db import Database

def main() -> int:
    try:
        settings = load_config()
        db = Database(settings)
        db.init_schema()
        # Lightweight query
        db.get_guild_settings(0)
        return 0
    except Exception as e:
        print(f"HEALTHCHECK FAIL: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
