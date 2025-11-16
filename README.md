# Discord Spotify Release Notifier

A multi-container Discord bot that posts **new Spotify releases** to per-guild channels, with:
- Daily global detection (03:00 EST / 08:00 UTC)
- Per-guild configurable send times
- SQLite DB with automated daily backups
- Auto-restore from latest backup if DB is missing/corrupted
- Manual restore command via `docker exec`

---

# 📦 Features

### Commands
- >follow <query>  
- >unfollow <artist>  
- >list [prefix]  
- >setsingleschannel #channel  
- >setalbumschannel #channel  
- >allow_non_admins <on|off>  
- >checknow  
- >setreleasetime HH:MM (UTC)  
- >getreleasetime  

### Scheduling
- **Daily detection:** 08:00 UTC  
- **Per-guild dispatch:** every minute  
- **Mode A:** Only sends notifications if new releases exist  

### Backups
- Daily SQLite backups saved to host  
- Retains last 7 days  
- Auto-restore if DB is missing or invalid  
- Manual restore supported  

---

# 📁 Project Structure

```
project/
├── bot.py
├── scheduler.py
├── discord_commands.py
├── db.py
├── db_service.py
├── restore_backup.py
├── Dockerfile.discord-bot
├── Dockerfile.db-container
├── docker-compose.yml
├── data/        # live DB (host)
└── backups/     # backup .db files (host)
```

---

# 🐳 Deploying With Docker

## 🚀 Deploy Both Containers (Normal Deployment)

From the project root:

```
docker-compose up -d --build
```

This:
- Builds + deploys `discord-bot`
- Builds + deploys `db-container`
- Auto-restores DB if needed
- Starts backup API

---

# 🔁 Redeploy Only the Discord Bot (DB Unchanged)

```
docker-compose up -d --no-deps --build discord-bot
```

This rebuilds only the bot code and doesn't restart the DB container.

---

# 🛢 Redeploy Only the DB Container

```
docker-compose up -d --no-deps --build db-container
```

Useful when:
- You update backup logic
- You modify auto-restore behavior
- You change the DB service API

The DB auto-restore behavior runs on every db-container startup.

---

# 💾 Backup Behavior

Backups are written to:

```
./backups/bot_backup_YYYY-MM-DD.db
```

These files are:
- Valid SQLite backups  
- Safe to restore  
- Retained for 7 days  

Auto-restore occurs when:
- `/data/bot.sqlite3` is missing  
- zero bytes  
- corrupted (integrity check fails)  

---

# ⏪ Manual Backup Restore

To manually restore a specific file:

```
docker exec db-container python restore_backup.py bot_backup_2025-11-17.db
```

This overwrites:

```
./data/bot.sqlite3
```

You can inspect available backups with:

```
ls -l backups
```

---

# 🧪 Local (Non-Docker) Development

```
python3.8 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

---

# 📡 Backup API (db-container)

Triggered daily by the bot:

```
POST /backup
http://db-container:8000/backup
```

You can manually test:

```
curl -X POST localhost:8000/backup
```