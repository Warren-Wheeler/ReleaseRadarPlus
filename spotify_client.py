# -*- coding: utf-8 -*-
import logging
import time
from typing import Dict, List, Tuple

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from config import Settings
from util_retry import with_backoff

LOG = logging.getLogger(__name__)

def classify_release(item: dict) -> str:
    """
    Return 'single' or 'album' based on Spotify metadata.
    Rules:
      - If album_group or album_type indicates 'single' -> single
      - Else albums and EPs -> album
      - Fallback: total_tracks==1 -> single else album
    """
    group = item.get("album_group") or item.get("album", {}).get("album_group")
    a_type = item.get("album_type") or item.get("album", {}).get("album_type")
    total_tracks = item.get("total_tracks") or item.get("album", {}).get("total_tracks") or 0
    if (group and group.lower() == "single") or (a_type and a_type.lower() == "single"):
        return "single"
    return "single" if int(total_tracks or 0) == 1 else "album"

class SpotifyClient:
    def __init__(self, settings: Settings):
        auth = SpotifyClientCredentials(
            client_id=settings.spotify_client_id,
            client_secret=settings.spotify_client_secret,
        )
        self.sp = spotipy.Spotify(auth_manager=auth, requests_timeout=10, retries=0)  # our own backoff
        self.market = "US"
        self.max_retries = settings.max_retries

    def close(self):
        # spotipy does not expose close hooks; rely on GC
        pass

    @with_backoff()
    def search_artist_first(self, query: str) -> Tuple[str, str]:
        res = self.sp.search(q=query, type="artist", limit=1, market=self.market)
        items = res.get("artists", {}).get("items", [])
        if not items:
            raise ValueError("No artists found.")
        artist = items[0]
        return artist["id"], artist["name"]

    @with_backoff()
    def fetch_artist_releases(self, artist_id: str) -> List[Dict]:
        # include albums and singles
        items: List[Dict] = []
        next_url = None
        params = dict(album_type="album,single", limit=50)
        data = self.sp.artist_albums(artist_id, **params)
        while True:
            items.extend(data.get("items", []))
            next_url = data.get("next")
            if not next_url:
                break
            data = self.sp.next(data)
        # Deduplicate by id (Spotify may return duplicates across groups)
        seen = set()
        unique = []
        for it in items:
            rid = it["id"]
            if rid not in seen:
                unique.append(it)
                seen.add(rid)
        return unique
