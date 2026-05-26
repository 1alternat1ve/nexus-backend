import aiosqlite
import time
import random
import string
import asyncio
import os
import httpx

DATABASE = "nexus.db"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

async def get_avatar_url(telegram_id: int) -> str | None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos",
                params={"user_id": telegram_id, "limit": 1},
                timeout=5.0
            )
            data = r.json()
            if data.get("ok") and data["result"]["photos"]:
                file_id = data["result"]["photos"][0][-1]["file_id"]
                r2 = await client.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                    params={"file_id": file_id},
                    timeout=5.0
                )
                fdata = r2.json()
                if fdata.get("ok"):
                    return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fdata['result']['file_path']}"
    except Exception:
        pass
    return None

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id TEXT UNIQUE,
                username TEXT,
                avatar_url TEXT,
                code TEXT,
                code_expires INTEGER,
                activated INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                created_at INTEGER,
                last_seen INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY,
                total_activations INTEGER DEFAULT 0,
                last_activation INTEGER
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO stats (id, total_activations) VALUES (1, 0)
        """)
                # Миграция: добавить last_seen если не существует
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_seen INTEGER")
        except Exception:
            pass
        await db.commit()


async def get_pending_code(telegram_id: str) -> dict | None:
    """Возвращает код и оставшееся время, если код ещё активен."""
    now = int(time.time())
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT code, code_expires FROM users
            WHERE telegram_id = ? AND code_expires > ? AND activated = 0
        """, (telegram_id, now)) as cursor:
            row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

async def create_code(telegram_id: str, username: str) -> str:
    code = generate_code()
    expires = int(time.time()) + 60  # 1 минута
    avatar = await get_avatar_url(int(telegram_id)) if BOT_TOKEN else None

    async with aiosqlite.connect(DATABASE) as db:
        now = int(time.time())
        await db.execute("""
            INSERT INTO users (telegram_id, username, avatar_url, code, code_expires, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                code = excluded.code,
                code_expires = excluded.code_expires,
                username = excluded.username,
                avatar_url = excluded.avatar_url,
                activated = 0,
                last_seen = excluded.last_seen
        """, (telegram_id, username, avatar, code, expires, now, now))
        await db.commit()

    return code

async def get_user_by_telegram_id(telegram_id: str) -> dict | None:
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT telegram_id, username, avatar_url, activated, banned, created_at, last_seen FROM users WHERE telegram_id = ?
        """, (telegram_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None


async def touch_user(telegram_id: str):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET last_seen = ? WHERE telegram_id = ?", (int(time.time()), telegram_id))
        await db.commit()

async def ban_user(telegram_id: str, banned: bool = True) -> bool:
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET banned = ? WHERE telegram_id = ?", (1 if banned else 0, telegram_id))
        await db.commit()
        return True

async def activate(code: str) -> dict | None:
    now = int(time.time())

    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users WHERE code = ? AND code_expires > ? AND activated = 0
        """, (code, now)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        await db.execute("""
            UPDATE users SET activated = 1, code = NULL, code_expires = NULL WHERE id = ?
        """, (row["id"],))
        await db.execute("""
            UPDATE stats SET total_activations = total_activations + 1, last_activation = ?
            WHERE id = 1
        """, (now,))
        await db.commit()

        return {
            "telegram_id": row["telegram_id"],
            "username": row["username"],
            "avatar_url": row["avatar_url"],
        }

async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT telegram_id, username, avatar_url, activated, banned, created_at, last_seen FROM users ORDER BY created_at DESC
        """) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_stats() -> dict:
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM stats WHERE id = 1") as cursor:
            row = await cursor.fetchone()
        if row:
            return dict(row)
        return {"total_activations": 0, "last_activation": None}
