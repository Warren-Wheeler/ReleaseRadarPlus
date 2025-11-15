# -*- coding: utf-8 -*-
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Settings
from db import Database
from spotify_client import SpotifyClient, classify_release

LOG = logging.getLogger(__name__)

def make_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler()

def schedule_weekly_release_job(
    scheduler: AsyncIOScheduler,
    settings: Settings,
    db: Database,
    sp: SpotifyClient,
    bot: discord.Client,
    clear_cache_fn,
):
    # run every Friday 06:00 (server local time; no timezone customization)
    scheduler.add_job(
        lambda: weekly_job_wrapper(bot, clear_cache_fn),
        trigger="cron",
        day_of_week=settings.weekly_day_of_week,
        hour=settings.weekly_hour,
        minute=settings.weekly_minute,
        id="weekly_release_check",
        replace_existing=True,
    )
    LOG.info("Weekly job scheduled: %s  %02d:%02d",
             settings.weekly_day_of_week, settings.weekly_hour, settings.weekly_minute)

async def weekly_job_wrapper(bot: discord.Client, clear_cache_fn):
    LOG.info("Weekly job: clearing cache then checking releases.")
    try:
        clear_cache_fn()
    except Exception:
        LOG.exception("Failed to clear cache.")
    await run_release_check(bot)

async def run_release_check(bot: discord.Client):
    db: Database = bot.db  # type: ignore[attr-defined]
    sp: SpotifyClient = bot.spotify  # type: ignore[attr-defined]

    LOG.info("Starting release check for all guilds...")
    for guild_id, rows in db.iter_all_guild_follows():
        guild = bot.get_guild(guild_id)
        if guild is None:
            LOG.warning("Guild %s not found in bot cache.", guild_id)
            continue

        settings = db.get_guild_settings(guild_id)
        singles_chan = guild.get_channel(settings["singles_channel_id"]) if settings["singles_channel_id"] else None
        albums_chan = guild.get_channel(settings["albums_channel_id"]) if settings["albums_channel_id"] else None
        if singles_chan is None or albums_chan is None:
            LOG.info("Guild %s missing channel configuration; skipping.", guild_id)
            continue

        LOG.info("Guild %s: %d followed artists", guild_id, len(rows))
        for r in rows:
            artist_id = r["artist_id"]
            artist_name = r["artist_name"]

            try:
                releases = sp.fetch_artist_releases(artist_id)
            except Exception as e:
                LOG.exception("Failed fetching releases for %s (%s): %s", artist_name, artist_id, e)
                continue

            # Optional: only consider last 30 days to avoid flood on first run
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            new_singles = []
            new_albums = []

            for item in releases:
                rid = item["id"]
                # parse release date
                rel_date = item.get("release_date")
                rel_precision = item.get("release_date_precision", "day")
                try:
                    # Spotify may give year or month precision
                    if rel_precision == "day":
                        dt = datetime.strptime(rel_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    elif rel_precision == "month":
                        dt = datetime.strptime(rel_date, "%Y-%m").replace(tzinfo=timezone.utc)
                    else:
                        dt = datetime.strptime(rel_date, "%Y").replace(tzinfo=timezone.utc)
                except Exception:
                    dt = cutoff  # if parse fails, let it pass through once

                if dt < cutoff:
                    continue
                if db.has_seen(guild_id, rid):
                    continue

                rtype = classify_release(item)
                if rtype == "single":
                    new_singles.append(item)
                else:
                    new_albums.append(item)

            # post to channels
            for item in new_singles:
                await _post_release(singles_chan, "single", item)
                db.mark_seen(guild_id, item["id"], "single")

            for item in new_albums:
                await _post_release(albums_chan, "album", item)
                db.mark_seen(guild_id, item["id"], "album")

    LOG.info("Release check done.")

async def _post_release(channel: discord.abc.Messageable, rtype: str, item: dict):
    try:
        embed = _build_embed(item, rtype)
        await channel.send(embed=embed)
    except Exception as e:
        LOG.exception("Failed to post %s: %s", rtype, e)

def _build_embed(item: dict, rtype: str) -> discord.Embed:
    name = item.get("name")
    url = item.get("external_urls", {}).get("spotify")
    images = item.get("images") or []
    art = images[0]["url"] if images else None
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    title = f"New {rtype.title()}: {name}"
    desc = f"by {artists}"
    embed = discord.Embed(title=title, url=url, description=desc)
    if art:
        embed.set_thumbnail(url=art)
    return embed
