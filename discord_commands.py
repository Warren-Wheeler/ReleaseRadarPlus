# -*- coding: utf-8 -*-
import logging
from typing import Optional, List

import discord
from discord.ext import commands

from db import Database
from spotify_client import SpotifyClient, classify_release

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# PERMISSION CHECK
# ---------------------------------------------------------------------

def is_allowed():
    async def predicate(ctx: commands.Context) -> bool:
        db: Database = ctx.bot.db  # type: ignore[attr-defined]
        gs = db.get_guild_settings(ctx.guild.id)  # type: ignore
        if gs["allow_non_admins"]:
            return True
        return bool(ctx.author.guild_permissions.administrator)
    return commands.check(predicate)

# ---------------------------------------------------------------------
# HELP FORMATTER
# ---------------------------------------------------------------------

def _format_help(prefix: str, admin_only: bool) -> str:
    ao = "(admin-only)" if admin_only else ""
    lines = [
        f"**Spotify Release Notifier Commands**",
        f"`{prefix}follow <artist1, artist2, ...>` — Follow one or more artists {ao}",
        f"`{prefix}unfollow <artist1, artist2, ...>` — Unfollow one or more artists {ao}",
        f"`{prefix}list [prefix]` — List followed artists (optional: only those starting with prefix)",
        f"`{prefix}setsingleschannel #channel` — Set channel for singles {ao}",
        f"`{prefix}setalbumschannel #channel` — Set channel for albums/EPs {ao}",
        f"`{prefix}setreleasetime HH:MM` — Set daily notification time (UTC) {ao}",
        f"`{prefix}getreleasetime` — Show current daily notification time",
        f"`{prefix}allow_non_admins <on|off>` — Allow non-admins to use commands {ao}",
        f"`{prefix}checknow` — Manually run a new-release check {ao}",
        f"`{prefix}help` — Show this help",
        "",
        "Supports comma-separated follow/unfollow:",
        f"  `{prefix}follow charli xcx, fka twigs, bladee`",
        f"  `{prefix}unfollow lil peep, 8485`",
        "",
        "Prefix filtering examples:",
        f"  `{prefix}list a` → artists starting with 'a'",
        f"  `{prefix}list lil` → artists starting with 'lil'",
        "",
        "Release classification: singles vs albums via Spotify metadata.",
        "Daily detection runs at 08:00 UTC (03:00 EST).",
        "Notifications are sent at each server's configured UTC time.",
    ]
    return "\n".join(lines)

# ---------------------------------------------------------------------
# DISCORD EMBEDS
# ---------------------------------------------------------------------

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

# ---------------------------------------------------------------------
# SAFE MESSAGE SENDING
# ---------------------------------------------------------------------

async def send_long(ctx, text: str, limit: int = 2000):
    """
    Safely send long messages by splitting them into chunks ≤ Discord's 2000-char limit.
    Splits only at newline boundaries.
    """
    if len(text) <= limit:
        return await ctx.send(text)

    lines = text.split("\n")
    chunk = ""

    for line in lines:
        if len(chunk) + len(line) + 1 > limit:
            await ctx.send(chunk)
            chunk = line + "\n"
        else:
            chunk += line + "\n"

    if chunk.strip():
        await ctx.send(chunk)

# ---------------------------------------------------------------------
# REGISTER COMMANDS
# ---------------------------------------------------------------------

def register_commands(bot: commands.Bot):

    # --------------------------------------------------------------
    # HELP
    # --------------------------------------------------------------
    @bot.command(name="help")
    async def help_cmd(ctx: commands.Context):
        db: Database = ctx.bot.db  # type: ignore
        settings = db.get_guild_settings(ctx.guild.id)  # type: ignore
        text = _format_help(prefix=">", admin_only=not bool(settings["allow_non_admins"]))
        await ctx.send(text)

    # --------------------------------------------------------------
    # ALLOW NON ADMINS
    # --------------------------------------------------------------
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

    # --------------------------------------------------------------
    # SET CHANNELS
    # --------------------------------------------------------------
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

    # --------------------------------------------------------------
    # SET / GET RELEASE TIME
    # --------------------------------------------------------------
    @bot.command(name="setreleasetime")
    @is_allowed()
    async def set_release_time(ctx: commands.Context, time_str: str):
        """
        Set the daily notification time in UTC for this server.

        Usage:
            >setreleasetime HH:MM
        Example:
            >setreleasetime 10:00   (10:00 UTC)
        """
        time_str = time_str.strip()
        try:
            hour_str, minute_str = time_str.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except Exception:
            return await ctx.send("Usage: `>setreleasetime HH:MM` (24-hour UTC, e.g. 10:00)")

        notify_minute_utc = hour * 60 + minute
        db: Database = ctx.bot.db  # type: ignore
        db.set_guild_notify_minute(ctx.guild.id, notify_minute_utc)  # type: ignore

        await ctx.send(f"Daily release notifications set to **{hour:02d}:{minute:02d} UTC**.")

    @bot.command(name="getreleasetime")
    async def get_release_time(ctx: commands.Context):
        """
        Show the currently configured daily notification time (UTC).
        """
        db: Database = ctx.bot.db  # type: ignore
        settings = db.get_guild_settings(ctx.guild.id)  # type: ignore
        minute_total = (
            settings["notify_minute_utc"]
            if "notify_minute_utc" in settings.keys()
            else None  # type: ignore
        )
        if minute_total is None:
            minute_total = 600  # default 10:00 UTC == 5:00 EST
        hour = minute_total // 60
        minute = minute_total % 60
        await ctx.send(
            f"Daily release notifications are scheduled for **{hour:02d}:{minute:02d} UTC**."
        )

    # --------------------------------------------------------------
    # FOLLOW
    # --------------------------------------------------------------
    @bot.command(name="follow")
    @is_allowed()
    async def follow_cmd(ctx: commands.Context, *, query: str):
        """
        Follow one or more artists.
        Supports comma-separated lists:
            >follow charli xcx, fka twigs, bladee
        """
        sp: SpotifyClient = ctx.bot.spotify  # type: ignore
        db: Database = ctx.bot.db           # type: ignore

        entries = [q.strip() for q in query.split(",") if q.strip()]

        for entry in entries:
            try:
                artist_id, artist_name = sp.search_artist_first(entry)
                db.add_follow(ctx.guild.id, artist_id, artist_name)  # EXACT same DB call as before
                await ctx.send(f"Following **{artist_name}**.")
            except Exception as e:
                LOG.exception("Search failed for %s: %s", entry, e)
                await ctx.send(f"❌ Could not find artist for query: `{entry}`")

    # --------------------------------------------------------------
    # UNFOLLOW
    # --------------------------------------------------------------
    @bot.command(name="unfollow")
    @is_allowed()
    async def unfollow_cmd(ctx: commands.Context, *, artist_name: str):
        """
        Unfollow one or more artists.
        Supports comma-separated lists:
            >unfollow charli xcx, fka twigs
        """
        db: Database = ctx.bot.db  # type: ignore

        entries = [q.strip() for q in artist_name.split(",") if q.strip()]

        for entry in entries:
            n = db.remove_follow_by_name(ctx.guild.id, entry)
            if n:
                await ctx.send(f"Unfollowed **{entry}**.")
            else:
                await ctx.send(f"**{entry}** was not followed.")

    # --------------------------------------------------------------
    # LIST (with optional prefix filter)
    # --------------------------------------------------------------
    @bot.command(name="list")
    async def list_cmd(ctx: commands.Context, prefix: Optional[str] = None):
        """
        List followed artists.
        Optionally filter by case-insensitive prefix:
            >list a
            >list lil
        """
        db: Database = ctx.bot.db  # type: ignore
        rows = db.list_follows(ctx.guild.id)  # type: ignore

        if not rows:
            return await ctx.send("No followed artists yet. Use `>follow <query>` to add one.")

        if prefix:
            p = prefix.lower()
            rows = [
                r for r in rows
                if r["artist_name"].lower().startswith(p)
            ]

        if not rows:
            return await ctx.send(f"No followed artists start with `{prefix}`.")

        msg = "**Followed artists:**\n" + "\n".join(
            f"• {r['artist_name']} (`{r['artist_id']}`)"
            for r in rows
        )

        await send_long(ctx, msg)

    # --------------------------------------------------------------
    # CHECK NOW
    # --------------------------------------------------------------
    @bot.command(name="checknow")
    @is_allowed()
    async def checknow_cmd(ctx: commands.Context):
        from scheduler import run_release_check
        await ctx.send("Checking for new releases…")
        try:
            # Only run for this guild (preserves previous behavior but
            # uses the new decoupled detection/dispatch pipeline).
            await run_release_check(bot=ctx.bot, guild_id=ctx.guild.id)  # type: ignore
            await ctx.send("Done.")
        except Exception as e:
            LOG.exception("Manual check failed: %s", e)
            await ctx.send("An error occurred during manual check. See logs.")
