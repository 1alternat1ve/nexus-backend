import asyncio
import logging
import os
import sys
from datetime import datetime

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
ADMIN_ID = 7398936492


async def check_subscription(telegram_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, telegram_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


async def send_code(msg: Message, telegram_id: str):
    code = await db.create_code(telegram_id, msg.from_user.username or msg.from_user.full_name)
    await msg.answer(
        f"🔑 Ваш код активации NEXUS:\n\n"
        f"<code>{code}</code>\n\n"
        f"⏰ Код действует 3 минуты.\n\n"
        f"Введите код вручную в лаунчере NEXUS.",
        parse_mode="HTML"
    )


async def notify_admin(text: str):
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="HTML")
    except Exception:
        pass


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


@router.message(Command("users"))
async def cmd_users(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Нет доступа.")
        return

    users = await db.get_all_users()
    if not users:
        await msg.answer("📭 Пока никто не логинился.")
        return

    lines = []
    for u in users:
        username = u.get("username") or "—"
        status = "🔴 забанен" if u.get("banned") else "🟢 активен"
        created = datetime.fromtimestamp(u["created_at"]).strftime("%d.%m.%Y %H:%M") if u.get("created_at") else "—"
        lines.append(f"• <b>{username}</b> (ID: <code>{u['telegram_id']}</code>) — {status}")

    await msg.answer(
        f"👥 Всего пользователей: {len(users)}\n\n" + "\n".join(lines),
        parse_mode="HTML"
    )


@router.message(Command("user"))
async def cmd_user(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Нет доступа.")
        return

    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("📖 Использование: /user <telegram_id>\nПример: /user 7398936492")
        return

    target_id = parts[1].strip().lstrip("@")
    user = await db.get_user_by_telegram_id(target_id)

    if not user:
        await msg.answer("❌ Пользователь не найден.")
        return

    username = user.get("username") or "—"
    status = "🔴 Забанен" if user.get("banned") else "🟢 Активен"
    activated = "✅ Да" if user.get("activated") else "❌ Нет"
    created = datetime.fromtimestamp(user["created_at"]).strftime("%d.%m.%Y %H:%M") if user.get("created_at") else "—"

    text = (
        f"<b>👤 Информация о пользователе</b>\n\n"
        f"• <b>ID:</b> <code>{user['telegram_id']}</code>\n"
        f"• <b>Username:</b> @{username}\n"
        f"• <b>Статус:</b> {status}\n"
        f"• <b>Активирован:</b> {activated}\n"
        f"• <b>Первый вход:</b> {created}\n"
    )

    await msg.answer(text, parse_mode="HTML")


@router.message(Command("ban"))
async def cmd_ban(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Нет доступа.")
        return

    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("📖 Использование:\n/ban <telegram_id> — заблокировать\n/unban <telegram_id> — разблокировать")
        return

    target_id = parts[1].strip()
    user = await db.get_user_by_telegram_id(target_id)

    if not user:
        await msg.answer("❌ Пользователь не найден.")
        return

    await db.ban_user(target_id, True)
    await msg.answer(f"🔴 Пользователь <b>{user.get('username') or target_id}</b> заблокирован.", parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Нет доступа.")
        return

    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("📖 Использование: /unban <telegram_id>")
        return

    target_id = parts[1].strip()
    user = await db.get_user_by_telegram_id(target_id)

    if not user:
        await msg.answer("❌ Пользователь не найден.")
        return

    await db.ban_user(target_id, False)
    await msg.answer(f"🟢 Пользователь <b>{user.get('username') or target_id}</b> разблокирован.", parse_mode="HTML")


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
