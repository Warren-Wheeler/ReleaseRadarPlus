# Discord Spotify Release Notifier (Python 3.8)

A Discord bot that follows artists and posts **new Spotify releases** to per-guild channels.  
Uses **discord.py (prefix commands)**, **Spotipy**, **APScheduler**, **requests-cache**, **sqlite3**, and **Pydantic**.

## Features

- `>follow <query>` — follows the **first Spotify artist** search result.
- `>unfollow <artist_name>` — unfollows by name.
- `>list` — lists followed artists.
- `>setsingleschannel #channel` / `>setalbumschannel #channel` — configure destinations.
- `>allow_non_admins <on|off>` — toggle admin-only commands (default admin-only).
- `>checknow` — manual run.
- `>help` — command guide.
- Weekly job **Friday 06:00**:
  1. Clear requests cache.
  2. Check all guilds and artists.
  3. Post **Singles** vs **Albums/EPs** to different channels.
  4. Avoid duplicates using `seen_releases`.

## Requirements

- Python **3.8** only.
- Discord bot with **Message Content Intent** enabled in Developer Portal.
- Spotify app credentials (Client Credentials Flow).

## Quickstart (Local)

```bash
python3.8 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill DISCORD_BOT_TOKEN, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET in .env
python bot.py
