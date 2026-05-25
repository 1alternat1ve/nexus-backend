import aiosqlite
import time
import random
import string
import asyncio

DATABASE = "nexus.db"

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id TEXT UNIQUE,
                username TEXT,
                code TEXT,
                code_expires INTEGER,
                activated INTEGER DEFAULT 0,
                created_at INTEGER
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
        await db.commit()

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

async def create_code(telegram_id: str, username: str) -> str:
    code = generate_code()
    expires = int(time.time()) + 600  # 10 минут

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, username, code, code_expires, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                code = excluded.code,
                code_expires = excluded.code_expires,
                username = excluded.username,
                activated = 0
        """, (telegram_id, username, code, expires, int(time.time())))
        await db.commit()

    return code

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
        }

async def get_stats() -> dict:
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM stats WHERE id = 1") as cursor:
            row = await cursor.fetchone()
        if row:
            return dict(row)
        return {"total_activations": 0, "last_activation": None}
