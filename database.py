import asyncpg
import time
import random
import string
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        import logging
        if not DATABASE_URL:
            logging.error("[db] DATABASE_URL is empty!")
            raise RuntimeError("DATABASE_URL not set")
        logging.info(f"[db] connecting to: {DATABASE_URL[:50]}...")
        try:
            _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, command_timeout=10)
            logging.info("[db] pool created successfully")
        except Exception as e:
            logging.error(f"[db] pool creation failed: {e}")
            raise
    return _pool


async def get_avatar_url(telegram_id: int) -> str | None:
    try:
        import httpx
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
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS nexus_users (
                id SERIAL PRIMARY KEY,
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS nexus_stats (
                id INTEGER PRIMARY KEY,
                total_activations INTEGER DEFAULT 0,
                last_activation INTEGER
            )
        """)
        await conn.execute("""
            INSERT INTO nexus_stats (id, total_activations) VALUES (1, 0)
            ON CONFLICT (id) DO NOTHING
        """)


def generate_code():
    return ''.join(random.choices(string.digits, k=6))


async def create_code(telegram_id: str, username: str) -> tuple[str, int]:
    code = generate_code()
    expires = int(time.time()) + 60  # 1 минута
    avatar = await get_avatar_url(int(telegram_id)) if BOT_TOKEN else None

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO nexus_users (telegram_id, username, avatar_url, code, code_expires, created_at, last_seen)
            VALUES ($1, $2, $3, $4, $5, $6, $6)
            ON CONFLICT (telegram_id) DO UPDATE SET
                code = EXCLUDED.code,
                code_expires = EXCLUDED.code_expires,
                username = EXCLUDED.username,
                avatar_url = EXCLUDED.avatar_url,
                activated = 0,
                last_seen = EXCLUDED.last_seen
        """, telegram_id, username, avatar, code, expires, int(time.time()))

    return code, expires


async def get_user_by_telegram_id(telegram_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT telegram_id, username, avatar_url, activated, banned, created_at, last_seen FROM nexus_users WHERE telegram_id = $1",
            telegram_id
        )
        return dict(row) if row else None


async def touch_user(telegram_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE nexus_users SET last_seen = $1 WHERE telegram_id = $2", int(time.time()), telegram_id)


async def ban_user(telegram_id: str, banned: bool = True) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE nexus_users SET banned = $1 WHERE telegram_id = $2", 1 if banned else 0, telegram_id)
    return True


async def activate(code: str) -> dict | None:
    now = int(time.time())
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM nexus_users WHERE code = $1 AND code_expires > $2 AND activated = 0",
            code, now
        )
        if not row:
            return None

        await conn.execute(
            "UPDATE nexus_users SET activated = 1, code = NULL, code_expires = NULL WHERE id = $1",
            row["id"]
        )
        await conn.execute(
            "UPDATE nexus_stats SET total_activations = total_activations + 1, last_activation = $1 WHERE id = 1",
            now
        )

        return {
            "telegram_id": row["telegram_id"],
            "username": row["username"],
            "avatar_url": row["avatar_url"],
        }


async def get_all_users() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT telegram_id, username, avatar_url, activated, banned, created_at, last_seen FROM nexus_users ORDER BY created_at DESC"
        )
        return [dict(row) for row in rows]


async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM nexus_stats WHERE id = 1")
        return dict(row) if row else {"total_activations": 0, "last_activation": None}
