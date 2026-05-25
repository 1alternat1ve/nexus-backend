import asyncio
import threading
import uvicorn
import bot as bot_module


def run_bot():
    asyncio.run(bot_module.main())


def run_api():
    uvicorn.run("main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    run_api()
