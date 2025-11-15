# -*- coding: utf-8 -*-
import logging
from typing import Optional, List

import discord
from discord.ext import commands

from db import Database
from spotify_client import SpotifyClient, classify_release

LOG = logging.getLogger(__name__)

def is_allowed():
    async def predicate(ctx: commands.Context) -> bool:
        db: Database = ctx.bot.db  # type: ignore[attr-defined]
        gs = db.get_guild_settings(ctx.guild.id)  # type: ignore
        if gs["allow_non_admins"]:
            return True
        return bool(ctx.author.guild_permissions.administrator)
    return commands.check(predicate)

def _format_help(prefix: str, admin_only: bool) -> str:
    ao = "(admin-only)" if admin_only else ""
    lines = [
        f"**Spotify Release Notifier Commands**",
        f"`{prefix}follow <query>` — Follow the first Spotify artist match {ao}",
        f"`{prefix}unfollow <artist_name>` — Unfollow an artist {ao}",
        f"`{prefix}list` — List followed artists",
        f"`{prefix}setsingleschannel #channel` — Set channel for singles {ao}",
        f"`{prefix}setalbumschannel #channel` — Set channel for albums/EPs {ao}",
        f"`{prefix}allow_non_admins <on|off>` — Allow non-admins to use commands {ao}",
        f"`{prefix}checknow` — Manually run a new-release check {ao}",
        f"`{prefix}help` — Show this help",
        "",
        "Singles vs Albums: uses Spotify metadata to classify.",
        "Weekly checks run Friday at 06:00 (server time). Cache clears right before.",
    ]
    return "\n".join(lines)

def _embed_for_release(item: dict, release_type: str) -> discord.Embed:
    name = item.get("name")
    url = item.get("external_urls", {}).get("spotify")
    images = item.get("images") or item.get("album", {}).get("images") or []
    art = images[0]["url"] if images else None
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    embed = discord.Embed(title=name, url=url, description=f"{release_type.title()} by {artists}")
    if art:
        embed.set_thumbnail(url=art)
    return embed

def register_commands(bot: commands.Bot):

    @bot.command(name="help")
    async def help_cmd(ctx: commands.Context):
        db: Database = ctx.bot.db  # type: ignore
        settings = db.get_guild_settings(ctx.guild.id)  # type: ignore
        text = _format_help(prefix=">", admin_only=not bool(settings["allow_non_admins"]))
        await ctx.send(text)

    @bot.command(name="allow_non_admins")
    @is_allowed()
    async def allow_non_admins_cmd(ctx: commands.Context, toggle: str):
        val = toggle.strip().lower()
        if val not in {"on", "off"}:
            return await ctx.send("Usage: `>allow_non_admins <on|off>`")
        allow = (val == "on")
        db: Database = ctx.bot.db  # type: ignore
        db.upsert_guild_settings(ctx.guild.id, allow_non_admins=allow)  # type: ignore
        await ctx.send(f"Non-admin command usage set to **{'enabled' if allow else 'disabled'}**.")

    @bot.command(name="setsingleschannel")
    @is_allowed()
    async def set_singles_channel(ctx: commands.Context, channel: discord.TextChannel):
        db: Database = ctx.bot.db  # type: ignore
        db.upsert_guild_settings(ctx.guild.id, singles_channel_id=channel.id)  # type: ignore
        await ctx.send(f"Singles channel set to {channel.mention}")

    @bot.command(name="setalbumschannel")
    @is_allowed()
    async def set_albums_channel(ctx: commands.Context, channel: discord.TextChannel):
        db: Database = ctx.bot.db  # type: ignore
        db.upsert_guild_settings(ctx.guild.id, albums_channel_id=channel.id)  # type: ignore
        await ctx.send(f"Albums channel set to {channel.mention}")

    @bot.command(name="follow")
    @is_allowed()
    async def follow_cmd(ctx: commands.Context, *, query: str):
        sp: SpotifyClient = ctx.bot.spotify  # type: ignore
        db: Database = ctx.bot.db  # type: ignore
        try:
            artist_id, artist_name = sp.search_artist_first(query)
        except Exception as e:
            LOG.exception("Search failed: %s", e)
            return await ctx.send(f"Could not find artist for query: `{query}`")

        db.add_follow(ctx.guild.id, artist_id, artist_name)  # type: ignore
        await ctx.send(f"Following **{artist_name}**.")

    @bot.command(name="unfollow")
    @is_allowed()
    async def unfollow_cmd(ctx: commands.Context, *, artist_name: str):
        db: Database = ctx.bot.db  # type: ignore
        n = db.remove_follow_by_name(ctx.guild.id, artist_name)  # type: ignore
        if n:
            await ctx.send(f"Unfollowed **{artist_name}**.")
        else:
            await ctx.send(f"**{artist_name}** was not followed.")

    @bot.command(name="list")
    async def list_cmd(ctx: commands.Context):
        db: Database = ctx.bot.db  # type: ignore
        rows = db.list_follows(ctx.guild.id)  # type: ignore
        if not rows:
            return await ctx.send("No followed artists yet. Use `>follow <query>` to add one.")
        msg = "**Followed artists:**\n" + "\n".join(f"• {r['artist_name']} (`{r['artist_id']}`)" for r in rows)
        await ctx.send(msg)

    @bot.command(name="checknow")
    @is_allowed()
    async def checknow_cmd(ctx: commands.Context):
        # Delegate to the same function scheduler uses
        from scheduler import run_release_check
        await ctx.send("Checking for new releases…")
        try:
            await run_release_check(bot=ctx.bot)  # type: ignore
            await ctx.send("Done.")
        except Exception as e:
            LOG.exception("Manual check failed: %s", e)
            await ctx.send("An error occurred during manual check. See logs.")
