#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entry point: initializes config, cache, DB, Spotify client, Discord bot, and scheduler.
"""
import asyncio
import logging
import signal
from typing import Optional

import discord
from discord.ext import commands

from config import load_config, Settings
from cache import install_http_cache, clear_http_cache
from db import Database
from spotify_client import SpotifyClient
from discord_commands import register_commands
from scheduler import make_scheduler, schedule_weekly_release_job

LOG = logging.getLogger("bot")


async def main():
    # --- logging ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    LOG.info("Starting bot...")

    # --- config, cache, db, spotify ---
    settings: Settings = load_config()
    install_http_cache(db_path=settings.cache_path, ttl_days=7)

    db = Database(settings)
    db.init_schema()

    sp = SpotifyClient(settings)

    # --- discord bot ---
    intents = discord.Intents.default()
    intents.message_content = True  # required for prefix ">" commands
    intents.guilds = True
    intents.messages = True  # receive normal message events

    bot = commands.Bot(command_prefix=">", intents=intents, help_command=None)

    # shared state to pass around
    bot.db = db          # type: ignore[attr-defined]
    bot.settings = settings  # type: ignore[attr-defined]
    bot.spotify = sp     # type: ignore[attr-defined]

    # register commands on the bot
    register_commands(bot)

    # --- scheduler ---
    scheduler = make_scheduler()
    schedule_weekly_release_job(
        scheduler=scheduler,
        settings=settings,
        db=db,
        sp=sp,
        bot=bot,
        clear_cache_fn=clear_http_cache,
    )
    scheduler.start()

    # graceful shutdown
    stop_event: Optional[asyncio.Event] = asyncio.Event()

    def _graceful(*_):
        if stop_event and not stop_event.is_set():
            LOG.info("Shutdown signal received.")
            stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _graceful)
        except NotImplementedError:
            # On Windows / certain envs, signals may not be supported
            pass

    # run the bot
    try:
        await bot.start(settings.discord_bot_token)
    finally:
        LOG.info("Stopping scheduler...")
        scheduler.shutdown(wait=False)
        LOG.info("Closing Spotify client...")
        sp.close()
        LOG.info("Closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
