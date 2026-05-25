import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

@router.message(Command("start"))
async def cmd_start(msg: Message):
    telegram_id = str(msg.from_user.id)
    username = msg.from_user.username or msg.from_user.full_name

    code = await db.create_code(telegram_id, username)

    await msg.answer(
        f"🔑 Ваш код активации NEXUS:\n\n"
        f"<code>{' '.join(code)}</code>\n\n"
        f"Введите его в лаунчере.\n"
        f"⏰ Код действует 10 минут."
    )

@router.message(F.text)
async def any_text(msg: Message):
    if msg.text.startswith("/"):
        return
    await msg.answer("Напишите /start чтобы получить код активации.")

async def main():
    await db.init_db()
    dp.include_router(router)
    logger.info("Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
