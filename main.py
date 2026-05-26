import os
import time
import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import database as db
import models as m
import asyncio

app = FastAPI(title="NEXUS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await db.init_db()

@app.get("/")
async def root():
    return {"status": "ok", "service": "NEXUS Backend v1.0"}

@app.get("/stats")
async def stats():
    s = await db.get_stats()
    return s

@app.post("/activate")
async def activate(req: m.ActivateRequest):
    import httpx
    now = int(time.time())
    bot_token = os.environ.get("BOT_TOKEN", "")

    # Получаем telegram_id по коду (без активации)
    async with aiosqlite.connect(db.DATABASE) as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute(
            "SELECT telegram_id FROM users WHERE code = ? AND code_expires > ? AND activated = 0",
            (req.code, now)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        return {"success": False, "error": "Неверный или просроченный код"}

    telegram_id = row["telegram_id"]

    # Проверяем подписку через Bot API
    if bot_token:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getChatMember",
                    params={"chat_id": "@nickblite", "user_id": telegram_id},
                    timeout=5.0
                )
                data = r.json()
                if data.get("ok"):
                    status = data["result"]["status"]
                    if status not in ("member", "administrator", "creator"):
                        return {"success": False, "error": "Подписка на канал не подтверждена"}
                else:
                    # getChatMember вернул ошибку — пропускаем проверку
                    print(f"[activate] getChatMember error: {data}")
        except Exception as e:
            print(f"[activate] subscription check error: {e}")

    # Подписка в порядке — активируем
    result = await db.activate(req.code)
    if result:
        return {"success": True, "user": result}
    return {"success": False, "error": "Неверный или просроченный код"}

@app.get("/check_subscription/{telegram_id}")
async def check_subscription(telegram_id: str):
    import httpx
    bot_token = os.environ.get("BOT_TOKEN", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getChatMember",
                params={"chat_id": "@nickblite", "user_id": telegram_id},
                timeout=5.0
            )
            data = r.json()
            if data.get("ok"):
                status = data["result"]["status"]
                return {"subscribed": status in ("member", "administrator", "creator")}
    except Exception as e:
        print(f"[check_subscription] error: {e}")
    return {"subscribed": False}

@app.get("/user/{code}")
async def get_user(code: str):
    now = int(time.time())
    async with aiosqlite.connect(db.DATABASE) as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute(
            "SELECT username, code_expires FROM users WHERE code = ?",
            (code,)
        ) as cursor:
            row = await cursor.fetchone()
    if row and row["code_expires"] > now:
        return {"valid": True, "username": row["username"]}
    return {"valid": False}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
