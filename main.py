import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import database as db
import models as m

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
    bot_token = os.environ.get("BOT_TOKEN", "")

    # Находим код через базу
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT telegram_id FROM nexus_users WHERE code = $1 AND code_expires > $2 AND activated = 0",
            req.code, int(time.time())
        )

    if not row:
        return {"success": False, "error": "Неверный или просроченный код"}

    telegram_id = row["telegram_id"]

    # Проверяем бан
    user = await db.get_user_by_telegram_id(telegram_id)
    if user and user.get("banned"):
        return {"success": False, "error": "Доступ заблокирован"}

    # Проверяем подписку
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
                    print(f"[activate] getChatMember error: {data}")
        except Exception as e:
            print(f"[activate] subscription check error: {e}")

    # Активируем
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
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username, code_expires FROM nexus_users WHERE code = $1",
            code
        )
    if row and row["code_expires"] > int(time.time()):
        return {"valid": True, "username": row["username"]}
    return {"valid": False}

@app.get("/banned/{telegram_id}")
async def check_banned(telegram_id: str):
    user = await db.get_user_by_telegram_id(telegram_id)
    if user and user.get("banned"):
        return {"banned": True}
    await db.touch_user(telegram_id)
    return {"banned": False}

@app.post("/offline/{telegram_id}")
async def set_offline(telegram_id: str):
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE nexus_users SET last_seen = $1 WHERE telegram_id = $2",
            int(time.time()) - 61, telegram_id
        )
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
