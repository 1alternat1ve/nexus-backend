import asyncio
import logging
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()


# Активные коды в памяти: {telegram_id: expires_timestamp}
active_codes: dict[str, int] = {}

# Состояние рассылки
broadcast_state: dict[int, bool] = {}

# Состояние поиска: {admin_id: True} если админ сейчас вводит запрос
search_state: dict[int, bool] = {}

CHANNEL_USERNAME = "@nickblite"
ADMIN_ID = 7398936492


def set_active_code(telegram_id: str, expires: int):
    active_codes[telegram_id] = expires


def has_active_code(telegram_id: str) -> bool:
    now = int(time.time())
    if telegram_id not in active_codes:
        return False
    if active_codes[telegram_id] <= now:
        active_codes.pop(telegram_id, None)
        return False
    return True


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="btn_users")],
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="btn_search")],
        [InlineKeyboardButton(text="🔴 Черный список", callback_data="btn_bans")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="btn_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="btn_broadcast")],
    ])


def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data="btn_back")],
    ])


async def check_subscription(telegram_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, telegram_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


async def send_code(msg: Message, telegram_id: str):
    code, expires = await db.create_code(telegram_id, msg.from_user.username or msg.from_user.full_name)
    set_active_code(telegram_id, expires)
    await msg.answer(
        f"🔑 Ваш код активации NEXUS:\n\n"
        f"<code>{code}</code>\n\n"
        f"⏰ Код действует 1 минуту.\n\n"
        f"Введите код вручную в лаунчере NEXUS.",
        parse_mode="HTML"
    )


async def delete_msg(msg: Message):
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception:
        pass


async def edit_with_menu(chat_id: int, message_id: int, text: str, markup=None):
    await bot.delete_message(chat_id, message_id)
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)


# === Пользовательские команды ===

@router.message(Command("start"))
async def cmd_start(msg: Message):
    await delete_msg(msg)

    # Если активный код уже есть — не отправляем ничего, только удаляем сообщение
    if msg.from_user.id != ADMIN_ID and has_active_code(str(msg.from_user.id)):
        return

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

    await send_code(msg, str(msg.from_user.id))


@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    await call.answer()
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        await send_code(call.message, str(call.from_user.id))
    else:
        await edit_with_menu(
            call.message.chat.id, call.message.message_id,
            "❌ Вы ещё не подписаны на канал!",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Я подписан", callback_data="check_sub")
            ]])
        )


# === Админ-панель ===

@router.message(Command("admin"))
@router.message(Command("menu"))
async def cmd_admin(msg: Message):
    logger.info(f"cmd_admin called by {msg.from_user.id}")
    if msg.from_user.id != ADMIN_ID:
        logger.info(f"Not admin: {msg.from_user.id} != {ADMIN_ID}")
        return
    await delete_msg(msg)

    text = "<b>⚙️ Админ-панель NEXUS</b>\n\nВыберите действие:"
    await msg.answer(text, parse_mode="HTML", reply_markup=admin_menu())
    logger.info("Admin menu sent")


@router.callback_query(F.data == "btn_back")
async def btn_back(call: CallbackQuery):
    await call.answer()
    broadcast_state.pop(call.from_user.id, None)
    search_state.pop(call.from_user.id, None)
    text = "<b>⚙️ Админ-панель NEXUS</b>\n\nВыберите действие:"
    await edit_with_menu(call.message.chat.id, call.message.message_id, text, admin_menu())


@router.callback_query(F.data == "btn_users")
async def btn_users(call: CallbackQuery):
    await call.answer()
    users = await db.get_all_users()

    if not users:
        text = "📭 Пока никто не логинился."
        await edit_with_menu(call.message.chat.id, call.message.message_id, text, back_menu())
        return

    lines = []
    now = int(time.time())
    for u in users:
        username = u.get("username") or "—"
        banned = u.get("banned")
        last_seen = u.get("last_seen") or 0
        online = (now - last_seen) < 60

        if banned:
            status = "🔴"
            online_ico = ""
        elif online:
            status = "🟢"
            online_ico = " 🟢"
        else:
            status = "⚪"
            online_ico = " ⚪"

        lines.append(f"{status} <b>{username}</b>{online_ico} — <code>{u['telegram_id']}</code>")

    text = f"<b>👥 Пользователи ({len(users)})</b>\n\n" + "\n".join(lines)
    text += "\n\n🟢 = онлайн  ⚪ = оффлайн  🔴 = заблокирован"

    buttons = []
    for u in users:
        username = u.get("username") or u["telegram_id"]
        buttons.append([InlineKeyboardButton(
            text=f"👤 {username}",
            callback_data=f"info_{u['telegram_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="btn_back")])

    await edit_with_menu(
        call.message.chat.id, call.message.message_id, text,
        InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data == "btn_bans")
async def btn_bans(call: CallbackQuery):
    await call.answer()
    users = await db.get_all_users()
    banned = [u for u in users if u.get("banned")]

    if not banned:
        text = "🔴 <b>Черный список</b>\n\nПусто — нет заблокированных."
        await edit_with_menu(call.message.chat.id, call.message.message_id, text, back_menu())
        return

    buttons = []
    for u in banned:
        username = u.get("username") or u["telegram_id"]
        buttons.append([InlineKeyboardButton(
            text=f"🟢 {username}",
            callback_data=f"unban_{u['telegram_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="btn_back")])

    text = f"🔴 <b>Черный список ({len(banned)})</b>\n\nНажмите на пользователя чтобы разблокировать:"
    await edit_with_menu(call.message.chat.id, call.message.message_id, text,
        InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "btn_stats")
async def btn_stats(call: CallbackQuery):
    await call.answer()
    s = await db.get_stats()
    users = await db.get_all_users()
    active = len([u for u in users if u.get("activated")])
    banned = len([u for u in users if u.get("banned")])
    last = datetime.fromtimestamp(s["last_activation"]).strftime("%d.%m.%Y %H:%M") if s.get("last_activation") else "—"

    text = (
        f"<b>📊 Статистика</b>\n\n"
        f"👥 Всего в базе: <b>{len(users)}</b>\n"
        f"✅ Активировано: <b>{active}</b>\n"
        f"🔴 Заблокировано: <b>{banned}</b>\n"
        f"🔑 Всего активаций: <b>{s['total_activations']}</b>\n"
        f"🕐 Последняя активация: <b>{last}</b>"
    )
    await edit_with_menu(call.message.chat.id, call.message.message_id, text, back_menu())


@router.callback_query(F.data == "btn_search")
async def btn_search(call: CallbackQuery):
    await call.answer()
    search_state[call.from_user.id] = True
    await call.message.reply(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите username или ID для поиска.\n\n"
        "Отмена: /cancel",
        parse_mode="HTML",
        reply_markup=ForceReply()
    )


def user_detail_text(u: dict) -> str:
    username = u.get("username") or "—"
    tid = u["telegram_id"]
    activated = "✅ Активирован" if u.get("activated") else "❌ Не активирован"
    banned = "🔴 Заблокирован" if u.get("banned") else "🟢 Не заблокирован"
    last_seen = u.get("last_seen")
    if last_seen:
        ago = int(time.time()) - last_seen
        if ago < 60:
            seen = f"{ago} сек назад"
        elif ago < 3600:
            seen = f"{ago // 60} мин назад"
        elif ago < 86400:
            seen = f"{ago // 3600} ч назад"
        else:
            seen = f"{ago // 86400} дн назад"
    else:
        seen = "—"
    created = datetime.fromtimestamp(u.get("created_at") or 0).strftime("%d.%m.%Y") if u.get("created_at") else "—"

    return (
        f"<b>👤 {username}</b>\n\n"
        f"ID: <code>{tid}</code>\n"
        f"Статус: {activated}\n"
        f"Бан: {banned}\n"
        f"Активность: {seen}\n"
        f"Регистрация: {created}"
    )


@router.callback_query(F.data.startswith("info_"))
async def btn_info(call: CallbackQuery):
    await call.answer()
    user_id = call.data[5:]
    user = await db.get_user_by_telegram_id(user_id)
    if not user:
        await call.answer("Пользователь не найден", show_alert=True)
        return
    text = user_detail_text(user)
    buttons = []
    if user.get("activated"):
        buttons.append([InlineKeyboardButton(
            text="⚠️ Кикнуть",
            callback_data=f"kick_{user_id}"
        )])
    if user.get("banned"):
        buttons.append([InlineKeyboardButton(
            text="🟢 Разблокировать",
            callback_data=f"unban_{user_id}"
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="🔴 Заблокировать",
            callback_data=f"ban_{user_id}"
        )])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="btn_users")])
    await edit_with_menu(
        call.message.chat.id, call.message.message_id, text,
        InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("kick_"))
async def btn_kick(call: CallbackQuery):
    user_id = call.data[5:]
    user = await db.get_user_by_telegram_id(user_id)
    await db.deactivate_user(user_id)
    await call.answer(f"⚠️ Пользователь {user.get('username') or user_id} кикнут", show_alert=True)
    await btn_info(call)


@router.callback_query(F.data == "btn_users")
async def btn_users(call: CallbackQuery):
    await call.answer()
    users = await db.get_all_users()

    if not users:
        text = "📭 Пока никто не логинился."
        await edit_with_menu(call.message.chat.id, call.message.message_id, text, back_menu())
        return

    lines = []
    now = int(time.time())
    for u in users:
        username = u.get("username") or "—"
        banned = u.get("banned")
        last_seen = u.get("last_seen") or 0
        online = (now - last_seen) < 60

        if banned:
            status = "🔴"
            online_ico = ""
        elif online:
            status = "🟢"
            online_ico = " 🟢"
        else:
            status = "⚪"
            online_ico = " ⚪"

        lines.append(f"{status} <b>{username}</b>{online_ico} — <code>{u['telegram_id']}</code>")

    text = f"<b>👥 Пользователи ({len(users)})</b>\n\n" + "\n".join(lines)
    text += "\n\n🟢 = онлайн  ⚪ = оффлайн  🔴 = заблокирован"
    await edit_with_menu(call.message.chat.id, call.message.message_id, text, back_menu())


@router.callback_query(F.data == "btn_broadcast")
async def btn_broadcast(call: CallbackQuery):
    await call.answer()
    broadcast_state[call.from_user.id] = True
    await call.message.reply(
        "📢 <b>Рассылка</b>\n\n"
        "Введите сообщение — оно будет отправлено всем активированным пользователям.\n\n"
        "Отмена: /cancel",
        parse_mode="HTML",
        reply_markup=ForceReply()
    )


@router.callback_query(F.data == "btn_broadcast_cancel")
async def btn_broadcast_cancel(call: CallbackQuery):
    await call.answer()
    broadcast_state.pop(call.from_user.id, None)
    await call.message.delete()
    await call.message.answer(
        "❌ Рассылка отменена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ В меню", callback_data="btn_back")]
        ])
    )


@router.callback_query(F.data.startswith("ban_"))
async def btn_ban(call: CallbackQuery):
    user_id = call.data[4:]
    user = await db.get_user_by_telegram_id(user_id)
    await db.ban_user(user_id, True)
    await call.answer(f"🔴 Заблокирован: {user.get('username') or user_id}", show_alert=True)
    await btn_bans(call)


@router.callback_query(F.data.startswith("unban_"))
async def btn_unban(call: CallbackQuery):
    user_id = call.data[7:]
    user = await db.get_user_by_telegram_id(user_id)
    await db.ban_user(user_id, False)
    await call.answer(f"🟢 Разблокирован: {user.get('username') or user_id}", show_alert=True)
    await btn_bans(call)


# === Остальные текстовые сообщения (в конце) ===

@router.message(F.text)
async def any_text(msg: Message):
    # Рассылка — если админ в режиме ввода
    if broadcast_state.get(msg.from_user.id) and msg.from_user.id == ADMIN_ID:
        broadcast_state.pop(msg.from_user.id)
        await delete_msg(msg)

        users = await db.get_all_users()
        activated = [u for u in users if u.get("activated")]
        sent = 0
        failed = 0

        for u in activated:
            try:
                await bot.send_message(int(u["telegram_id"]), msg.text, parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1

        await msg.answer(
            f"✅ <b>Рассылка завершена</b>\n\n"
            f"📤 Отправлено: <b>{sent}</b>\n"
            f"❌ Не доставлено: <b>{failed}</b>",
            parse_mode="HTML"
        )
        return

    # Поиск — если админ в режиме поиска
    if search_state.get(msg.from_user.id) and msg.from_user.id == ADMIN_ID:
        search_state.pop(msg.from_user.id)
        await delete_msg(msg)

        users = await db.search_users(msg.text.strip())
        if not users:
            await msg.answer(
                "🔍 <b>Поиск</b>\n\nНичего не найдено по запросу «<b>{}</b>»".format(msg.text),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀ Назад", callback_data="btn_back")]
                ])
            )
            return

        now = int(time.time())
        lines = []
        for u in users:
            username = u.get("username") or "—"
            banned = u.get("banned")
            last_seen = u.get("last_seen") or 0
            online = (now - last_seen) < 60

            if banned:
                status = "🔴"
                online_ico = ""
            elif online:
                status = "🟢"
                online_ico = " 🟢"
            else:
                status = "⚪"
                online_ico = " ⚪"

            lines.append(f"{status} <b>{username}</b>{online_ico} — <code>{u['telegram_id']}</code>")

        text = f"🔍 <b>Результаты поиска ({len(users)})</b>\n\n" + "\n".join(lines)
        buttons = []
        for u in users:
            username = u.get("username") or u["telegram_id"]
            buttons.append([InlineKeyboardButton(
                text=f"{'🔴' if u.get('banned') else '🟢'} {username}",
                callback_data=f"info_{u['telegram_id']}"
            )])
        buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="btn_back")])

        await msg.answer(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        return

    # Отмена рассылки
    if msg.text == "/cancel" and (broadcast_state.get(msg.from_user.id) or search_state.get(msg.from_user.id)):
        broadcast_state.pop(msg.from_user.id)
        search_state.pop(msg.from_user.id)
        await delete_msg(msg)
        text = "<b>⚙️ Админ-панель NEXUS</b>\n\nВыберите действие:"
        await msg.answer(text, parse_mode="HTML", reply_markup=admin_menu())
        return

    await delete_msg(msg)
    await msg.answer("Напишите /start чтобы получить код активации.")


async def main():
    await db.init_db()
    dp.include_router(router)
    logger.info("Бот запущен v2")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
