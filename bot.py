import os, asyncio, uuid
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from database import Database
from locales import t
from html import escape
from datetime import datetime


load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

db = Database()
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router = Router()
MEDIA = Path(__file__).resolve().parent / "media"
MEDIA.mkdir(exist_ok=True)

# Картинки можно заменить своими файлами с теми же именами:
GENERATION_IMAGE = MEDIA / "generation.jpg"
PROFILE_IMAGE = MEDIA / "profile.jpg"
BUY_IMAGE = MEDIA / "buy.jpg"
MAIN_MENU = MEDIA / "general.jpg"

async def send_asset(message, image_path: Path, text: str, reply_markup=None):
    if image_path.exists():
        await message.answer_photo(
            photo=FSInputFile(str(image_path)),
            caption=text,
            reply_markup=reply_markup
        )
    else:
        await message.answer(text, reply_markup=reply_markup)



def menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang,"photo"), callback_data="test:photo"), InlineKeyboardButton(text=t(lang,"video"), callback_data="test:video")],
        [InlineKeyboardButton(text=t(lang,"profile"), callback_data="profile"), InlineKeyboardButton(text=t(lang,"buy"), callback_data="buy")],
        [InlineKeyboardButton(text=t(lang,"support"), url="https://t.me/beIosheeev_kyc")]])


@router.message(CommandStart())
async def start(m: Message):
    old = db.get_user(m.from_user.id)
    db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    db.add_message(m.from_user.id, m.message_id, "incoming", "text", "/start")
    if not old:
        db.add_action(m.from_user.id, "start", "Первый вход; выдано 5 тикетов")
    else:
        db.add_action(m.from_user.id, "start", "Повторный запуск")
    u = db.get_user(m.from_user.id); lang = u["language"] or "ru"
    await m.answer(t(lang,"welcome"), reply_markup=menu(lang))


@router.callback_query(F.data == "profile")
async def profile(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.add_action(c.from_user.id, "profile", "Открыт профиль")
    text = (f"👤 <b>Профиль</b>\n\n🆔 ID: <code>{u['telegram_id']}</code>\n"
            f"👋 Username: {'@'+u['username'] if u['username'] else '—'}\n"
            f"🌐 Язык: {lang.upper()}\n🎫 Баланс: <b>{u['tickets']}</b>\n📱 Телефон: {u['phone'] or '—'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang,"phone"), callback_data="phone")],
        [InlineKeyboardButton(text=t(lang,"buy"), callback_data="buy")],
        [InlineKeyboardButton(text=t(lang,"back"), callback_data="back")]])
    try:
        await c.message.delete()
    except Exception:
        pass
    await send_asset(c.message, PROFILE_IMAGE, text, kb)
    await c.answer()


@router.callback_query(F.data == "phone")
async def phone(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    if u["phone_verified"]:
        await c.answer("Бонус уже получен.", show_alert=True); return
    db.add_action(c.from_user.id, "phone_request", "Запрошен контакт")
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t(lang,"share"), request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await c.message.answer("📱 Нажми кнопку ниже и отправь свой номер.", reply_markup=kb); await c.answer()


@router.message(F.content_type == ContentType.CONTACT)
async def contact(m: Message):
    u = db.get_user(m.from_user.id)
    if not u: return
    db.add_message(m.from_user.id, m.message_id, "incoming", "contact", m.contact.phone_number)
    if m.contact.user_id != m.from_user.id:
        db.add_action(m.from_user.id, "phone_rejected", "Контакт другого пользователя")
        await m.answer("Отправь свой контакт через кнопку Telegram."); return
    if db.verify_phone(m.from_user.id, m.contact.phone_number):
        db.add_action(m.from_user.id, "phone_verified", "Подтверждён номер; начислено 10 тикетов")
        await m.answer("🎁 Номер подтверждён. Начислено <b>10 тикетов</b>.", reply_markup=menu(u["language"] or "ru"))
    else:
        await m.answer("Бонус уже получен.")


@router.callback_query(F.data == "buy")
async def buy(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.add_action(c.from_user.id, "buy_open", "Открыт раздел покупки")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟️ 5 тикетов — $2 (ТЕСТ)", callback_data="buy:test")],
        [InlineKeyboardButton(text=t(lang,"back"), callback_data="back")]])
    try:
        await c.message.delete()
    except Exception:
        pass
    await send_asset(
        c.message,
        BUY_IMAGE,
        "🎫 <b>Покупка тикетов</b>\n\n5 тикетов — $2.\n\n⚠️ Тестовый режим: кнопка начисляет 5 тикетов.",
        kb
    )
    await c.answer()


@router.callback_query(F.data == "buy:test")
async def buytest(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.change_tickets(c.from_user.id, 5)
    db.add_action(c.from_user.id, "ticket_purchase_demo", "Тестовая покупка: +5")
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.message.answer("✅ Тестовая покупка: <b>+5 тикетов</b>.", reply_markup=menu(lang))
    await c.answer()


@router.callback_query(F.data == "back")
async def back(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.add_action(c.from_user.id, "menu", "Возврат в главное меню")
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.message.answer(t(lang, "welcome"), reply_markup=menu(lang))
    await c.answer()


@router.callback_query(F.data == "test:photo")
async def photo_test(c: CallbackQuery):
    db.add_action(c.from_user.id, "photo_generation_test", "Нажата кнопка фото")
    await c.answer()

    u = db.get_user(c.from_user.id)
    lang = u["language"] or "ru"
    await send_asset(
        c.message,
        GENERATION_IMAGE,
        "📸 <b>Генерация по фото</b>\n\n⏳ Ваше фото генерируется, пожалуйста, подождите 10 секунд...",
    )
    await asyncio.sleep(10)
    # После 10 секунд ничего не отправляем.


@router.callback_query(F.data == "test:video")
async def video_test(c: CallbackQuery):
    db.add_action(c.from_user.id, "video_generation_test", "Нажата кнопка видео")
    await c.answer()

    u = db.get_user(c.from_user.id)
    lang = u["language"] or "ru"
    await send_asset(
        c.message,
        GENERATION_IMAGE,
        "🎬 <b>Генерация видео</b>\n\n⏳ Ваше видео генерируется, пожалуйста, подождите 10 секунд...",
    )
    await asyncio.sleep(10)
    # После 10 секунд ничего не отправляем.


@router.message(F.photo)
async def photo(m: Message):
    db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    p = m.photo[-1]; folder = MEDIA / str(m.from_user.id); folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + ".jpg")
    await bot.download(p, destination=path)
    photo_id = db.add_photo(m.from_user.id, p.file_id, p.file_unique_id, str(path), m.caption or "", m.message_id, "incoming")
    db.add_message(m.from_user.id, m.message_id, "incoming", "photo", m.caption or "")
    db.add_action(m.from_user.id, "photo_received", f"Фото #{photo_id} сохранено; message_id={m.message_id}")
    await m.answer("🧪 Фото получено и сохранено в истории. Генерация пока отключена.")


@router.message(F.video)
async def video(m: Message):
    db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    v = m.video
    folder = MEDIA / str(m.from_user.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + ".mp4")
    try:
        await bot.download(v, destination=path)
        local_path = str(path)
    except Exception:
        local_path = ""
    video_id = db.add_video(m.from_user.id, v.file_id, v.file_unique_id, local_path, m.caption or "", m.message_id, "incoming")
    db.add_message(m.from_user.id, m.message_id, "incoming", "video", m.caption or "")
    db.add_action(m.from_user.id, "video_received", f"Видео #{video_id} сохранено; message_id={m.message_id}")
    await m.answer("🧪 Видео получено и сохранено в истории. Генерация пока отключена.")


@router.message()
async def any_message(m: Message):
    if not db.get_user(m.from_user.id):
        db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    text = m.text or m.caption or ""
    ctype = str(m.content_type)
    db.add_message(m.from_user.id, m.message_id, "incoming", ctype, text[:4000])
    db.add_action(m.from_user.id, "message", f"type={ctype}; {text[:1000]}")


# =========================
# Telegram admin panel
# =========================
ADMIN_ID = 7628243006
ADMIN_PAGE_SIZE = 8
OSINT_BOT_URL = "https://t.me/VPNuniversalYourbot"


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def fmt_time(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except Exception:
        return str(value)[:16]


def fmt_date(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(value)[:19]


def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users:0")],
        [InlineKeyboardButton(text="📸 Фото", callback_data="adm:photos") , InlineKeyboardButton(text="🎥 Видео", callback_data="adm:videos")],
        [InlineKeyboardButton(text="💬 Сообщения", callback_data="adm:messages"), InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="🔎 OSINT", url=OSINT_BOT_URL)],
    ])


def admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админку", callback_data="adm:home")]])


def user_display(u):
    username = f"@{u['username']}" if u["username"] else (u["first_name"] or "Без username")
    return username[:35]


def users_kb(users, page):
    rows = []
    start = page * ADMIN_PAGE_SIZE
    for u in users[start:start + ADMIN_PAGE_SIZE]:
        rows.append([InlineKeyboardButton(
            text=f"{user_display(u)} · {fmt_time(u['last_seen_at'])} · {u['telegram_id']}",
            callback_data=f"adm:user:{u['telegram_id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:users:{page-1}"))
    if start + ADMIN_PAGE_SIZE < len(users):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:users:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Фото", callback_data=f"adm:userphotos:{uid}:0"), InlineKeyboardButton(text="🎥 Видео", callback_data=f"adm:uservideos:{uid}:0")],
        [InlineKeyboardButton(text="💬 Сообщения", callback_data=f"adm:usermessages:{uid}:0")],
        [InlineKeyboardButton(text="ℹ️ Инфо", callback_data=f"adm:userinfo:{uid}"), InlineKeyboardButton(text="🎫 Тикеты", callback_data=f"adm:usertickets:{uid}")],
        [InlineKeyboardButton(text="🔎 OSINT", url=OSINT_BOT_URL)],
        [InlineKeyboardButton(text="⬅️ Пользователи", callback_data="adm:users:0")],
    ])


async def admin_guard_message(m: Message):
    if not is_admin(m.from_user.id):
        return False
    return True


async def admin_guard_callback(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Нет доступа", show_alert=True)
        return False
    return True


@router.message(F.text == "/admin")
async def admin_command(m: Message):
    if not await admin_guard_message(m):
        return
    await m.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm:home")
async def admin_home(c: CallbackQuery):
    if not await admin_guard_callback(c):
        return
    await c.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())
    await c.answer()


@router.callback_query(F.data.startswith("adm:users:"))
async def admin_users(c: CallbackQuery):
    if not await admin_guard_callback(c):
        return
    page = int(c.data.rsplit(":", 1)[1])
    users = db.users()
    text = f"👥 <b>Пользователи</b> — {len(users)}\n\nНажми на пользователя. Показаны username, время последней активности и Telegram ID."
    await c.message.edit_text(text, reply_markup=users_kb(users, page))
    await c.answer()


@router.callback_query(F.data.startswith("adm:user:"))
async def admin_user(c: CallbackQuery):
    if not await admin_guard_callback(c):
        return
    uid = int(c.data.split(":")[-1])
    u = db.get_user(uid)
    if not u:
        await c.answer("Пользователь не найден", show_alert=True)
        return
    name = " ".join(x for x in [u["first_name"], u["last_name"]] if x) or "—"
    username = f"@{u['username']}" if u["username"] else "—"
    text = (
        f"👤 <b>{escape(name)}</b>\n\n"
        f"Username: {escape(username)}\n"
        f"🆔 Telegram ID: <code>{u['telegram_id']}</code>\n"
        f"📱 Телефон: <code>{escape(u['phone'])}</code>" if u["phone"] else
        f"👤 <b>{escape(name)}</b>\n\nUsername: {escape(username)}\n🆔 Telegram ID: <code>{u['telegram_id']}</code>\n📱 Телефон: —"
    )
    text += f"\n🎫 Тикеты: <b>{u['tickets']}</b>\n🕒 Последняя активность: {fmt_date(u['last_seen_at'])}\n📅 Регистрация: {fmt_date(u['created_at'])}"
    await c.message.edit_text(text, reply_markup=user_kb(uid))
    await c.answer()


@router.callback_query(F.data.startswith("adm:userinfo:"))
async def admin_user_info(c: CallbackQuery):
    if not await admin_guard_callback(c):
        return
    uid = int(c.data.split(":")[-1]); u = db.get_user(uid)
    if not u:
        await c.answer("Пользователь не найден", show_alert=True); return
    acts = db.actions(uid, 10)
    lines = ["ℹ️ <b>Последние действия</b>"]
    if not acts:
        lines.append("Нет действий.")
    else:
        for a in acts:
            detail = escape((a["details"] or "")[:180])
            lines.append(f"• {fmt_date(a['created_at'])} — <b>{escape(a['action_type'])}</b> {detail}")
    await c.message.edit_text("\n".join(lines), reply_markup=user_kb(uid))
    await c.answer()


@router.callback_query(F.data.startswith("adm:usertickets:"))
async def admin_user_tickets(c: CallbackQuery):
    if not await admin_guard_callback(c):
        return
    uid = int(c.data.split(":")[-1]); u = db.get_user(uid)
    if not u:
        await c.answer("Пользователь не найден", show_alert=True); return
    await c.message.edit_text(f"🎫 <b>Тикеты пользователя</b>\n\nID: <code>{uid}</code>\nБаланс: <b>{u['tickets']}</b>", reply_markup=user_kb(uid))
    await c.answer()


async def admin_media_list(c: CallbackQuery, uid: int, kind: str, page: int):
    if kind == "photo":
        items = db.photos(uid, 200)
        title = "📸 Фото"
        prefix = "adm:userphotos"
    else:
        items = db.videos(uid, 200)
        title = "🎥 Видео"
        prefix = "adm:uservideos"
    start = page * ADMIN_PAGE_SIZE
    chunk = items[start:start + ADMIN_PAGE_SIZE]
    lines = [f"{title} пользователя <code>{uid}</code> — всего {len(items)}"]
    if not chunk:
        lines.append("\nНет сохранённых файлов.")
    else:
        for i, item in enumerate(chunk, start=start + 1):
            caption = escape((item["caption"] or "")[:100])
            lines.append(f"\n<b>#{i}</b> {fmt_date(item['created_at'])} {caption}")
    rows = []
    for item in chunk:
        rows.append([InlineKeyboardButton(text=f"▶️ Открыть #{items.index(item)+1}", callback_data=f"adm:send{kind}:{item['id']}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{uid}:{page-1}"))
    if start + ADMIN_PAGE_SIZE < len(items): nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{uid}:{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К пользователю", callback_data=f"adm:user:{uid}")])
    await c.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()


@router.callback_query(F.data.startswith("adm:userphotos:"))
async def admin_user_photos(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    _, _, uid, page = c.data.split(":")
    await admin_media_list(c, int(uid), "photo", int(page))


@router.callback_query(F.data.startswith("adm:uservideos:"))
async def admin_user_videos(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    _, _, uid, page = c.data.split(":")
    await admin_media_list(c, int(uid), "video", int(page))


@router.callback_query(F.data.startswith("adm:sendphoto:"))
async def admin_send_photo(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    pid = int(c.data.split(":")[-1]); item = db.get_photo(pid)
    if not item:
        await c.answer("Фото не найдено", show_alert=True); return
    try:
        await c.message.answer_photo(item["telegram_file_id"], caption=f"📸 Фото #{pid}\nID пользователя: {item['telegram_id']}\n{item['caption'] or ''}")
        await c.answer("Отправлено")
    except Exception as e:
        await c.answer("Не удалось отправить фото", show_alert=True)


@router.callback_query(F.data.startswith("adm:sendvideo:"))
async def admin_send_video(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    vid = int(c.data.split(":")[-1]); item = db.get_video(vid)
    if not item:
        await c.answer("Видео не найдено", show_alert=True); return
    try:
        await c.message.answer_video(item["telegram_file_id"], caption=f"🎥 Видео #{vid}\nID пользователя: {item['telegram_id']}\n{item['caption'] or ''}")
        await c.answer("Отправлено")
    except Exception:
        await c.answer("Не удалось отправить видео", show_alert=True)


@router.callback_query(F.data.startswith("adm:usermessages:"))
async def admin_user_messages(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    _, _, uid, page = c.data.split(":"); uid=int(uid); page=int(page)
    items=db.messages(uid, 200); start=page*ADMIN_PAGE_SIZE; chunk=items[start:start+ADMIN_PAGE_SIZE]
    lines=[f"💬 <b>Сообщения</b> пользователя <code>{uid}</code> — всего {len(items)}"]
    for item in chunk:
        direction="⬅️" if item["direction"]=="incoming" else "➡️"
        body=escape((item["text"] or "")[:500]) or "(без текста)"
        lines.append(f"\n{direction} {fmt_date(item['created_at'])} · {escape(item['content_type'] or '')}\n{body}")
    if not chunk: lines.append("\nНет сообщений.")
    rows=[]; nav=[]
    if page>0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:usermessages:{uid}:{page-1}"))
    if start+ADMIN_PAGE_SIZE<len(items): nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:usermessages:{uid}:{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К пользователю", callback_data=f"adm:user:{uid}")])
    await c.message.edit_text("".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()


@router.callback_query(F.data == "adm:stats")
async def admin_stats(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    s=db.stats()
    text=("📊 <b>Статистика</b>\n\n"
          f"👥 Пользователи: <b>{s['users']}</b>\n"
          f"💬 Сообщения: <b>{s['messages']}</b>\n"
          f"📸 Фото: <b>{s['photos']}</b>\n"
          f"🎥 Видео: <b>{s['videos']}</b>\n"
          f"⚡ Действия: <b>{s['actions']}</b>\n"
          f"🎫 Всего тикетов на балансах: <b>{s['tickets']}</b>")
    await c.message.edit_text(text, reply_markup=admin_back_kb()); await c.answer()


@router.callback_query(F.data == "adm:photos")
async def admin_photos(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    users=db.users(); total=sum(len(db.photos(u["telegram_id"], 200)) for u in users)
    await c.message.edit_text(f"📸 <b>Фото</b>\n\nВсего сохранённых фото: <b>{total}</b>\n\nОткрывай пользователя → 📸 Фото, чтобы просматривать файлы.", reply_markup=admin_back_kb()); await c.answer()


@router.callback_query(F.data == "adm:videos")
async def admin_videos(c: CallbackQuery):
    if not await admin_guard_callback(c): return
    users=db.users(); total=sum(len(db.videos(u["telegram_id"], 200)) for u in users)
    await c.message.edit_text(f"🎥 <b>Видео</b>\n\nВсего сохранённых видео: <b>{total}</b>\n\nОткрывай пользователя → 🎥 Видео, чтобы просматривать файлы.", reply_markup=admin_back_kb()); await c.answer()


async def run_bot():
    dp = Dispatcher(); dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
