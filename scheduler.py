# -*- coding: utf-8 -*-
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import Database
from spotify_client import SpotifyClient, classify_release

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# SCHEDULER FACTORY
# ---------------------------------------------------------------------

def make_scheduler() -> AsyncIOScheduler:
    """
    Create AsyncIOScheduler pinned to UTC.
    """
    return AsyncIOScheduler(timezone="UTC")


# ---------------------------------------------------------------------
# JOB REGISTRATION
# ---------------------------------------------------------------------

def schedule_weekly_release_job(
    scheduler: AsyncIOScheduler,
    settings,
    db: Database,
    sp: SpotifyClient,
    bot: discord.Client,
    clear_cache_fn,
    backup_url: str,
):
    """
    New version — supports:
    - 03:00 EST (08:00 UTC) global detection
    - per-guild scheduled dispatch
    - backup trigger via HTTP
    """

    # 1. Daily detection (08:00 UTC)
    scheduler.add_job(
        run_global_detection_wrapper,
        trigger="cron",
        hour=8,
        minute=0,
        args=[db, sp, bot, clear_cache_fn, backup_url],
        id="global_detection",
        replace_existing=True,
    )

    # 2. Per-minute notifier dispatcher
    scheduler.add_job(
        per_minute_dispatcher,
        trigger="cron",
        second=0,
        args=[db, bot],
        id="dispatch_notifier",
        replace_existing=True,
    )

    LOG.info("Scheduled global detection daily at 08:00 UTC.")
    LOG.info("Scheduled dispatcher to run every minute.")


# ---------------------------------------------------------------------
# 1. GLOBAL DETECTION WRAPPER
# ---------------------------------------------------------------------

async def run_global_detection_wrapper(
    db: Database,
    sp: SpotifyClient,
    bot: discord.Client,
    clear_cache_fn,
    backup_url: str
):
    LOG.info("Running global detection (clear cache + fetch new releases).")

    try:
        clear_cache_fn()
    except Exception:
        LOG.exception("Failed to clear cache.")

    await run_global_detection(db, sp, bot)

    # Trigger backup in db-container
    await trigger_backup(backup_url)


async def run_global_detection(db: Database, sp: SpotifyClient, bot: discord.Client):
    """
    Runs a global release check for ALL guilds.
    Saves new releases into the 'pending_notifications' table.
    """

    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    LOG.info("Starting release detection for all guilds...")

    for guild_id, rows in db.iter_all_guild_follows():
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue

        for r in rows:
            artist_id = r["artist_id"]
            artist_name = r["artist_name"]

            try:
                releases = sp.fetch_artist_releases(artist_id)
            except Exception as e:
                LOG.error(f"Error fetching releases for {artist_name}: {e}")
                continue

            for item in releases:
                rid = item["id"]

                # parse date
                rel_date = item.get("release_date")
                precision = item.get("release_date_precision", "day")
                try:
                    if precision == "day":
                        dt = datetime.strptime(rel_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    elif precision == "month":
                        dt = datetime.strptime(rel_date, "%Y-%m").replace(tzinfo=timezone.utc)
                    else:
                        dt = datetime.strptime(rel_date, "%Y").replace(tzinfo=timezone.utc)
                except Exception:
                    dt = cutoff

                if dt < cutoff:
                    continue
                if db.has_seen(guild_id, rid):
                    continue

                rtype = classify_release(item)

                # Insert into pending table
                db.queue_pending_release(
                    guild_id=guild_id,
                    release_id=rid,
                    release_type=rtype,
                    payload=item,
                )

    LOG.info("Global detection complete.")


# ---------------------------------------------------------------------
# 2. PER-MINUTE DISPATCHER
# ---------------------------------------------------------------------

async def per_minute_dispatcher(db: Database, bot: discord.Client):
    """
    Looks at every guild and sends pending releases if the current
    UTC time == guild's configured send hour/minute.
    """

    now = datetime.now(timezone.utc)
    hour = now.hour
    minute = now.minute

    for guild_id in db.get_all_guild_ids():
        settings = db.get_guild_settings(guild_id)
        send_h = settings["release_hour_utc"]
        send_m = settings["release_minute_utc"]

        if send_h == hour and send_m == minute:
            await send_pending_for_guild(guild_id, db, bot)


async def send_pending_for_guild(guild_id: int, db: Database, bot: discord.Client):
    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    pending = db.get_pending_releases(guild_id)
    if not pending:
        return  # Mode A: silently skip

    settings = db.get_guild_settings(guild_id)
    singles_chan = guild.get_channel(settings["singles_channel_id"])
    albums_chan = guild.get_channel(settings["albums_channel_id"])

    if not singles_chan or not albums_chan:
        LOG.warning(f"Guild {guild_id} missing channels; cannot dispatch.")
        return

    for row in pending:
        rtype = row["release_type"]
        item = row["payload"]

        chan = singles_chan if rtype == "single" else albums_chan

        try:
            embed = build_embed(item, rtype)
            await chan.send(embed=embed)
        except Exception as e:
            LOG.error(f"Failed to send release for guild {guild_id}: {e}")
            continue

        db.mark_seen(guild_id, row["release_id"], rtype)

    db.clear_pending_releases(guild_id)
    LOG.info(f"Sent {len(pending)} releases to guild {guild_id}.")


# ---------------------------------------------------------------------
# BACKUP TRIGGER
# ---------------------------------------------------------------------

async def trigger_backup(url: str):
    LOG.info(f"Triggering backup via POST {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, timeout=10) as r:
                if r.status != 200:
                    LOG.error(f"Backup failed! HTTP {r.status}")
                else:
                    LOG.info("Backup completed.")
    except Exception as e:
        LOG.error(f"Error triggering backup: {e}")


# ---------------------------------------------------------------------
# EMBED BUILDER
# ---------------------------------------------------------------------

def build_embed(item: dict, rtype: str) -> discord.Embed:
    name = item.get("name")
    url = item.get("external_urls", {}).get("spotify")
    images = item.get("images") or item.get("album", {}).get("images") or []
    art = images[0]["url"] if images else None
    artists = ", ".join(a["name"] for a in item.get("artists", []))

    embed = discord.Embed(
        title=f"New {rtype.title()}: {name}",
        url=url,
        description=f"by {artists}",
    )
    if art:
        embed.set_thumbnail(url=art)

    return embed
