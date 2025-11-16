# -*- coding: utf-8 -*-
import logging
from pathlib import Path
import requests_cache

LOG = logging.getLogger(__name__)

def install_http_cache(db_path: Path, ttl_days: int = 7) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    requests_cache.install_cache(
        cache_name=str(db_path),
        backend="sqlite",
        expire_after=ttl_days * 24 * 3600,

        # Only cache GET, never POST (token refresh uses POST)
        allowable_methods=("GET",),

        # Only cache successful 200 responses (no cached 401/403)
        allowable_codes=(200,),

        # DO NOT CACHE token refresh requests
        ignored_urls=[
            "https://accounts.spotify.com/",  # token endpoint
        ],

        # Do NOT respect Cache-Control from Spotify
        cache_control=False,
    )

    LOG.info("HTTP cache installed at %s (TTL=%sd)", db_path, ttl_days)


def clear_http_cache() -> None:
    try:
        requests_cache.clear()
        LOG.info("HTTP cache cleared.")
    except Exception as e:
        LOG.exception("Failed to clear cache: %s", e)
