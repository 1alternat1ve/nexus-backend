import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

CHANNEL_USERNAME = "@nickblite"

async def check_subscription(telegram_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, telegram_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def get_avatar_url(telegram_id: int) -> str | None:
    try:
        photos = await bot.get_user_profile_photos(telegram_id, limit=1)
        if photos.photos and len(photos.photos) > 0:
            file_id = photos.photos[0][-1].file_id
            file_path = (await bot.get_file(file_id)).file_path
            return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    except Exception:
        pass
    return None

async def send_code(msg: Message, telegram_id: str):
    code = await db.create_code(telegram_id, msg.from_user.username or msg.from_user.full_name)
    code_str = "".join(code)
    await msg.answer(
        f"🔑 Ваш код активации NEXUS:\n\n"
        f"<code>{code_str}</code>\n\n"
        f"⏰ Код действует 3 минуты.",
        parse_mode="HTML"
    )

@router.message(Command("start"))
async def cmd_start(msg: Message):
    telegram_id = str(msg.from_user.id)

    if not await check_subscription(msg.from_user.id):
        await msg.answer(
            "❌ Для получения кода необходимо подписаться на канал:\n\n"
            "👉 https://t.me/nickblite\n\n"
            "После подписки нажмите кнопку ниже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Я подписан", callback_data="check_sub")
            ]])
        )
        return

    await send_code(msg, telegram_id)

@router.callback_query(F.data == "check_sub")
async def check_sub(call):
    if await check_subscription(call.from_user.id):
        await call.message.edit_text("✅ Подписка подтверждена! Вот ваш код:")
        await send_code(call.message, str(call.from_user.id))
        await call.answer()
    else:
        await call.answer("❌ Вы ещё не подписаны на канал!", show_alert=True)

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
