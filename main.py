import os
import time
import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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

@app.get("/open")
async def open_nexus(code: str = None):
    """Страница для авто-открытия лаунчера. Используется из Telegram браузера."""
    if code:
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>NEXUS</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh; margin: 0; background: #0f1629; color: #2dd4bf;
  flex-direction: column; gap: 16px;
}}
h1 {{ margin: 0; font-size: 24px; }}
p {{ color: #94a3b8; margin: 0; }}
</style>
<script>
window.onload = function() {{
  // Пробуем открыть лаунчер через custom protocol
  var opened = false;
  try {{
    window.location = 'nexus://activate?code={code}';
    opened = true;
  }} catch(e) {{}}
  // Показываем код если лаунчер не открылся
  setTimeout(function() {{
    if (!opened || document.hidden) {{
      document.body.innerHTML = `
        <h1>🔑 Код активации</h1>
        <p style="font-size:32px;letter-spacing:0.2em;color:#fff;">{code}</p>
        <p>Скопируйте код и вставьте в лаунчер NEXUS</p>
      `;
    }} else {{
      document.body.innerHTML = '<h1>✅ Лаунчер открыт!</h1><p>Введите код вручную если потребуется: <strong>{code}</strong></p>';
    }}
  }}, 1000);
}};
</script>
</head>
<body>
<h1>🚀 Запуск NEXUS...</h1>
<p>Если лаунчер не открылся автоматически, скопируйте код ниже</p>
</body>
</html>"""
        return HTMLResponse(content=html, media_type="text/html")
    return HTMLResponse(content="<h1>Code required</h1>", status_code=400)

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
