# -*- coding: utf-8 -*-
"""
Spotify client - fully correct Client Credentials Flow
No disk caching, no requests-cache interference, no sticky headers.

This matches Postman's behavior exactly:
- POST https://accounts.spotify.com/api/token
- Header: Authorization: Basic <base64(client_id:secret)>
- Body: grant_type=client_credentials
- All search/release requests include a fresh Bearer token
"""
import base64
import difflib
import logging
import time
from typing import Dict, List, Tuple

import requests

from config import Settings
from util_retry import with_backoff

LOG = logging.getLogger(__name__)


def classify_release(item: dict) -> str:
    """Return 'single' or 'album'."""
    album_type = (
        item.get("album_type")
        or item.get("album", {}).get("album_type")
        or ""
    ).lower()
    tracks = (
        item.get("total_tracks")
        or item.get("album", {}).get("total_tracks")
        or 0
    )
    return "single" if album_type == "single" or int(tracks) == 1 else "album"


# ---------------------------------------------------------------------
# **NO DISK, NO CACHE, NO SESSION**
# ---------------------------------------------------------------------

class SpotifyClient:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, settings: Settings):
        self.client_id = settings.spotify_client_id
        self.client_secret = settings.spotify_client_secret

        self.access_token = None
        self.token_expiry = 0

        # Immediately fetch token
        self._refresh_token()

    # ------------------------------------------------------------------
    # TOKEN MANAGEMENT (Client Credentials Flow)
    # ------------------------------------------------------------------

    def _refresh_token(self):
        """Fetch a new access token exactly following Spotify's docs & your Postman test."""
        LOG.info("Fetching new Spotify access token...")

        creds = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        auth_header = base64.b64encode(creds).decode("utf-8")

        resp = requests.post(
            self.TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Token request failed ({resp.status_code}): {resp.text}")

        js = resp.json()
        self.access_token = js["access_token"]
        self.token_expiry = time.time() + js.get("expires_in", 3600) - 30

        LOG.info("Spotify token refreshed (suffix=%s)", self.access_token[-8:])

    def _ensure_token(self):
        if not self.access_token or time.time() >= self.token_expiry:
            self._refresh_token()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # GENERIC GET (auto-refresh 401 once)
    # ------------------------------------------------------------------

    def _get(self, url: str, *, params: dict = None):
        self._ensure_token()

        r = requests.get(url, headers=self._headers(), params=params, timeout=10)

        if r.status_code == 401:
            LOG.warning("401 Unauthorized → refreshing token and retrying once...")
            self._refresh_token()
            r = requests.get(url, headers=self._headers(), params=params, timeout=10)

        return r

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------

    @with_backoff()
    def search_artist_first(self, query: str) -> Tuple[str, str]:
        """Search using client-credentials user-less search."""
        url = f"{self.BASE_URL}/search"
        params = {"q": query, "type": "artist", "limit": 10}

        r = self._get(url, params=params)
        r.raise_for_status()

        items = r.json().get("artists", {}).get("items", [])
        if not items:
            raise ValueError(f"No artists found for '{query}'")

        # best fuzzy match
        q = query.lower()
        best = None
        best_score = -1

        for a in items:
            name = a.get("name", "").lower()
            score = difflib.SequenceMatcher(None, name, q).ratio()
            if score > best_score:
                best_score = score
                best = a

        LOG.info("Matched '%s' → '%s' (score=%.2f)", query, best["name"], best_score)
        return best["id"], best["name"]

    # ------------------------------------------------------------------
    # ARTIST RELEASES
    # ------------------------------------------------------------------

    @with_backoff()
    def fetch_artist_releases(self, artist_id: str) -> List[Dict]:
        """Fetch all singles & albums."""
        url = f"{self.BASE_URL}/artists/{artist_id}/albums"
        params = {"include_groups": "album,single", "limit": 50}

        releases = []
        while True:
            r = self._get(url, params=params)
            r.raise_for_status()

            js = r.json()
            releases.extend(js.get("items", []))

            url = js.get("next")
            if not url:
                break
            params = None  # next includes params

        # dedupe
        seen = set()
        uniq = []
        for rel in releases:
            rid = rel.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                uniq.append(rel)

        LOG.debug("Fetched %d releases for artist %s", len(uniq), artist_id)
        return uniq


    def close(self):
        pass
