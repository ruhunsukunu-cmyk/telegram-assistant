import os
import sys
import logging
import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Windows konsolunda emoji karakterlerinin hata vermesini engelle
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()
from telegram import (
    BotCommand,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.helpers import escape_markdown


from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database as db
from services.weather import get_weather
from services.finance import get_market_rates

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# httpx logs full request URLs. Telegram embeds the bot token in that URL, so
# INFO-level request logging would leak the credential to Render logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Istanbul")
LOCAL_TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Europe/Istanbul"))
WEBHOOK_BASE_URL = (
    os.getenv("WEBHOOK_URL", "").strip()
    or os.getenv("RENDER_EXTERNAL_URL", "").strip()
)

MAIN_MENU_TEXT = (
    "✨ *Kişisel Asistan Paneli*\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "Bugün ne yapmak istersin?\n\n"
    "🌤️ Güncel bilgi  •  📋 Planlama\n"
    "📝 Notlar             •  ⏰ Hatırlatıcılar"
)


def get_main_keyboard():
    """Ana menü interaktif butonları"""
    keyboard = [
        [
            InlineKeyboardButton("🌤️ Hava", callback_data="btn_weather"),
            InlineKeyboardButton("💹 Piyasalar", callback_data="btn_finance"),
        ],
        [
            InlineKeyboardButton("📋 Görevler", callback_data="btn_tasks"),
            InlineKeyboardButton("📝 Notlar", callback_data="btn_notes"),
        ],
        [
            InlineKeyboardButton("➕ Hızlı ekle", callback_data="btn_quick_add"),
            InlineKeyboardButton("⏰ Hatırlatıcılar", callback_data="btn_reminders"),
        ],
        [
            InlineKeyboardButton("❓ Yardım ve komutlar", callback_data="btn_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")]])


def get_cancel_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Vazgeç", callback_data="cancel_input"),
    ]])


def parse_quick_reminder(text):
    """'15 Su iç' biçimindeki hızlı hatırlatıcı girişini doğrula."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        minutes = float(parts[0].replace(",", "."))
    except ValueError:
        return None
    message = parts[1].strip()
    if not 0 < minutes <= 525_600 or not message:
        return None
    return minutes, message


def get_webhook_config(token=TOKEN, base_url=WEBHOOK_BASE_URL):
    """Tokenı URL'ye koymadan güvenli webhook adresi ve doğrulama anahtarı üret."""
    if not base_url:
        return None
    secret = hashlib.sha256(token.encode("utf-8")).hexdigest()
    path = "telegram"
    return {
        "url_path": path,
        "webhook_url": f"{base_url.rstrip('/')}/{path}",
        "secret_token": secret,
    }


async def show_panel(update, text, reply_markup=None, parse_mode="Markdown"):
    """Komutlarda yeni mesaj, menü gezinmesinde aynı mesajı günceller."""
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text, parse_mode=parse_mode, reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text=text, parse_mode=parse_mode, reply_markup=reply_markup
        )


# ─────────────────────────────────────────
# KOMUTLAR
# ─────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start komutu: Kullanıcıyı karşılar ve kontrol panelini sunar."""
    user = update.effective_user
    name = user.first_name if user else "Dostum"

    welcome_text = f"👋 Merhaba *{escape_markdown(name)}*!\n\n{MAIN_MENU_TEXT}"
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_panel(update, MAIN_MENU_TEXT, get_main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help komutu: Tüm komutların detaylı kullanım kılavuzu."""
    help_text = (
        "❓ *Yardım merkezi*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "`/hava Ankara` — hava durumu\n"
        "`/piyasa` — döviz ve kripto\n"
        "`/gorev Kitap oku` — görev ekle\n"
        "`/gorevler` — görevleri görüntüle\n"
        "`/not Fikir metni` — not kaydet\n"
        "`/notlar` — notları görüntüle\n"
        "`/hatirlat 15 Su iç` — hatırlatıcı kur\n"
        "`/hatirlaticilar` — bekleyen hatırlatıcılar\n"
        "`/menu` — ana paneli aç"
    )
    await show_panel(update, help_text, get_back_keyboard())


# ─── HAVA DURUMU ───
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hava <şehir> komutu"""
    city = " ".join(context.args).strip() if context.args else DEFAULT_CITY
    progress = await update.message.reply_text("🌤️ Hava durumu hazırlanıyor…")
    result = await get_weather(city)
    await progress.edit_text(result, parse_mode="Markdown", reply_markup=get_back_keyboard())


# ─── FİNANS & KURLAR ───
async def finance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/piyasa komutu"""
    progress = await update.message.reply_text("💹 Piyasa özeti hazırlanıyor…")
    result = await get_market_rates()
    await progress.edit_text(result, parse_mode="Markdown", reply_markup=get_back_keyboard())


# ─── NOT YÖNETİMİ ───
async def add_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/not <not içeriği>"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Lütfen kaydedilecek notu yazın.\n*Örnek:* `/not Toplantı yarın 14:00'te`",
            parse_mode="Markdown"
        )
        return

    content = " ".join(context.args)
    user_id = update.effective_user.id
    note_id = db.add_note(user_id, content)
    await update.message.reply_text(
        f"✅ *Not kaydedildi*\n\n{escape_markdown(content)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📝 Notlarımı aç", callback_data="btn_notes"),
            InlineKeyboardButton("⌂ Menü", callback_data="btn_home"),
        ]]),
    )


async def list_notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/notlar"""
    user_id = update.effective_user.id
    notes = db.get_notes(user_id)

    if not notes:
        text = "📝 *Notların*\n━━━━━━━━━━━━━━━━━━━━━\nHenüz notun yok.\n\nEklemek için: `/not <metin>`"
        await show_panel(update, text, get_back_keyboard())
        return

    msg = f"📝 *Notların*  ·  _{len(notes)} kayıt_\n━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for index, n in enumerate(notes[:10], 1):
        dt = str(n["created_at"]).split()[0] if n["created_at"] else ""
        msg += f"\n*{index}.* {escape_markdown(n['content'])}\n   _{dt}_\n"
        keyboard.append([
            InlineKeyboardButton(f"🗑️ {index}. notu sil", callback_data=f"ask_del_note_{n['id']}")
        ])
    keyboard.append([InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")])
    await show_panel(update, msg, InlineKeyboardMarkup(keyboard))


# ─── GÖREV YÖNETİMİ (TODO) ───
async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gorev <görev metni>"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Lütfen görev açıklamasını yazın.\n*Örnek:* `/gorev Kitap oku 30 sayfa`",
            parse_mode="Markdown"
        )
        return

    title = " ".join(context.args)
    user_id = update.effective_user.id
    task_id = db.add_task(user_id, title)
    await update.message.reply_text(
        f"✅ *Görev eklendi*\n\n{escape_markdown(title)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Görevlerimi aç", callback_data="btn_tasks"),
            InlineKeyboardButton("⌂ Menü", callback_data="btn_home"),
        ]]),
    )


async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gorevler"""
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id)

    if not tasks:
        text = "📋 *Görevlerin*\n━━━━━━━━━━━━━━━━━━━━━\n🎉 Bekleyen görevin yok.\n\nEklemek için: `/gorev <iş>`"
        await show_panel(update, text, get_back_keyboard())
        return

    pending_count = sum(not t["is_done"] for t in tasks)
    msg = f"📋 *Görevlerin*  ·  _{pending_count} bekliyor_\n━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for index, t in enumerate(tasks[:15], 1):
        status_emoji = "✅" if t["is_done"] else "⬜"
        msg += f"\n{status_emoji} *{index}.* {escape_markdown(t['title'])}\n"

        if not t["is_done"]:
            keyboard.append([
                InlineKeyboardButton(f"✅ {index}. Tamamla", callback_data=f"done_task_{t['id']}"),
                InlineKeyboardButton("🗑️ Sil", callback_data=f"ask_del_task_{t['id']}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(f"🗑️ {index}. görevi temizle", callback_data=f"ask_del_task_{t['id']}")
            ])
    keyboard.append([InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")])
    await show_panel(update, msg, InlineKeyboardMarkup(keyboard))


# ─── HATIRLATICI (JOB QUEUE) ───
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    """Zamanı gelen hatırlatmayı kullanıcıya iletir"""
    job = context.job
    chat_id = job.chat_id
    reminder_id = job.data["id"]
    message_text = job.data["message"]

    alarm_msg = (
        "⏰ *DİKKAT! HATIRLATMA ZAMANI!*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 *Hatırlatıcı:* {escape_markdown(message_text)}\n"
        f"🕒 *Zaman:* {datetime.now().strftime('%H:%M')}"
    )
    await context.bot.send_message(chat_id=chat_id, text=alarm_msg, parse_mode="Markdown")
    db.mark_reminder_sent(reminder_id)


def _as_utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def restore_reminders(app):
    """Yeniden başlatmadan sonra bekleyen hatırlatıcıları tekrar sıraya al."""
    now = datetime.now(timezone.utc)
    restored = 0
    for reminder in db.get_pending_reminders():
        due_at = _as_utc(reminder["due_at"])
        app.job_queue.run_once(
            reminder_callback,
            when=max((due_at - now).total_seconds(), 1),
            chat_id=reminder["chat_id"],
            data={"id": reminder["id"], "message": reminder["message"]},
            name=f"reminder-{reminder['id']}",
        )
        restored += 1
    if restored:
        logger.info("%s bekleyen hatırlatıcı yeniden yüklendi.", restored)


async def initialize_app(app):
    """Telegram komut menüsünü kur ve kalıcı hatırlatıcıları geri yükle."""
    await app.bot.set_my_commands([
        BotCommand("menu", "Ana paneli aç"),
        BotCommand("gorev", "Yeni görev ekle"),
        BotCommand("gorevler", "Görevlerini görüntüle"),
        BotCommand("not", "Yeni not kaydet"),
        BotCommand("notlar", "Notlarını görüntüle"),
        BotCommand("hatirlat", "Dakika bazlı hatırlatıcı kur"),
        BotCommand("hatirlaticilar", "Bekleyen hatırlatıcılarını görüntüle"),
        BotCommand("hava", "Şehir hava durumunu göster"),
        BotCommand("piyasa", "Döviz ve kripto özetini göster"),
        BotCommand("help", "Yardım merkezini aç"),
    ])
    await restore_reminders(app)


def schedule_reminder(context, user_id, chat_id, minutes, message):
    seconds = max(1, int(minutes * 60))
    due_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    reminder_id = db.add_reminder(user_id, chat_id, message, due_at)
    context.job_queue.run_once(
        reminder_callback,
        when=seconds,
        chat_id=chat_id,
        data={"id": reminder_id, "message": message},
        name=f"reminder-{reminder_id}",
    )
    return reminder_id


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hatirlat <dakika> <mesaj>"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Hatalı kullanım!\n"
            "*Kullanım:* `/hatirlat <dakika> <mesaj>`\n"
            "*Örnek:* `/hatirlat 10 Çayı ocaktan al`\n"
            "*Örnek:* `/hatirlat 45 Almanca tekrarını bitir`",
            parse_mode="Markdown"
        )
        return

    try:
        minutes = float(context.args[0])
        if minutes <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ Lütfen geçerli bir pozitif dakika girin (Örn: 5, 15, 60).")
        return

    remind_text = " ".join(context.args[1:])
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    schedule_reminder(context, user_id, chat_id, minutes, remind_text)

    await update.message.reply_text(
        f"⏰ *Hatırlatıcı kuruldu*\n\n"
        f"*{minutes:g} dakika sonra:* {escape_markdown(remind_text)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bekleyen hatırlatıcıları göster ve iptal etmeyi kolaylaştır."""
    user_id = update.effective_user.id
    reminders = db.get_pending_reminders(user_id)

    if not reminders:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Hatırlatıcı oluştur", callback_data="btn_remind_help")],
            [InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")],
        ])
        await show_panel(
            update,
            "⏰ *Hatırlatıcıların*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Bekleyen hatırlatıcın yok.",
            keyboard,
        )
        return

    text = f"⏰ *Hatırlatıcıların*  ·  _{len(reminders)} bekliyor_\n━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for index, reminder in enumerate(reminders[:15], 1):
        due_at = _as_utc(reminder["due_at"]).astimezone(LOCAL_TIMEZONE)
        text += (
            f"\n*{index}.* {escape_markdown(reminder['message'])}\n"
            f"   _{due_at.strftime('%d.%m.%Y · %H:%M')}_\n"
        )
        keyboard.append([
            InlineKeyboardButton(
                f"✕ {index}. hatırlatıcıyı iptal et",
                callback_data=f"ask_cancel_reminder_{reminder['id']}",
            )
        ])
    keyboard.extend([
        [InlineKeyboardButton("➕ Yeni hatırlatıcı", callback_data="btn_remind_help")],
        [InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")],
    ])
    await show_panel(update, text, InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────
# BUTON ETKİLEŞİMLERİ (CALLBACK QUERY)
# ─────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "btn_home":
        context.user_data.pop("pending_action", None)
        await show_panel(update, MAIN_MENU_TEXT, get_main_keyboard())

    elif data == "cancel_input":
        context.user_data.pop("pending_action", None)
        await show_panel(update, "İşlem iptal edildi.\n\n" + MAIN_MENU_TEXT, get_main_keyboard())

    elif data == "btn_weather":
        await query.edit_message_text("🌤️ Hava durumu hazırlanıyor…")
        res = await get_weather(DEFAULT_CITY)
        await query.edit_message_text(res, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif data == "btn_finance":
        await query.edit_message_text("💹 Piyasa özeti hazırlanıyor…")
        res = await get_market_rates()
        await query.edit_message_text(res, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif data == "btn_tasks":
        await list_tasks_command(update, context)

    elif data == "btn_notes":
        await list_notes_command(update, context)

    elif data == "btn_reminders":
        await list_reminders_command(update, context)

    elif data == "btn_remind_help":
        context.user_data["pending_action"] = "reminder"
        await show_panel(
            update,
            "⏰ *Hatırlatıcı oluştur*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Kaç dakika sonra ve neyi hatırlatayım?\n\n"
            "Örnek: `20 Mola ver`",
            get_cancel_keyboard(),
        )

    elif data == "btn_quick_add":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Görev ekle", callback_data="quick_task")],
            [InlineKeyboardButton("📝 Not ekle", callback_data="quick_note")],
            [InlineKeyboardButton("⏰ Hatırlatıcı kur", callback_data="btn_remind_help")],
            [InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")],
        ])
        await show_panel(
            update,
            "➕ *Hızlı ekle*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Eklemek istediğin kayıt türünü seç.",
            keyboard,
        )

    elif data == "quick_task":
        context.user_data["pending_action"] = "task"
        await show_panel(
            update,
            "📋 *Yeni görev*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Görevini bir sonraki mesajda yaz.",
            get_cancel_keyboard(),
        )

    elif data == "quick_note":
        context.user_data["pending_action"] = "note"
        await show_panel(
            update,
            "📝 *Yeni not*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Notunu bir sonraki mesajda yaz.",
            get_cancel_keyboard(),
        )

    elif data == "btn_help":
        await help_command(update, context)

    elif data.startswith("done_task_"):
        task_id = int(data.replace("done_task_", ""))
        user_id = query.from_user.id
        db.complete_task(task_id, user_id)
        await list_tasks_command(update, context)

    elif data.startswith("ask_del_task_"):
        task_id = int(data.replace("ask_del_task_", ""))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Evet, sil", callback_data=f"confirm_del_task_{task_id}"),
            InlineKeyboardButton("Vazgeç", callback_data="btn_tasks"),
        ]])
        await show_panel(update, "🗑️ *Bu görevi silmek istediğine emin misin?*", keyboard)

    elif data.startswith("confirm_del_task_"):
        task_id = int(data.replace("confirm_del_task_", ""))
        user_id = query.from_user.id
        db.delete_task(task_id, user_id)
        await list_tasks_command(update, context)

    elif data.startswith("ask_del_note_"):
        note_id = int(data.replace("ask_del_note_", ""))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Evet, sil", callback_data=f"confirm_del_note_{note_id}"),
            InlineKeyboardButton("Vazgeç", callback_data="btn_notes"),
        ]])
        await show_panel(update, "🗑️ *Bu notu silmek istediğine emin misin?*", keyboard)

    elif data.startswith("confirm_del_note_"):
        note_id = int(data.replace("confirm_del_note_", ""))
        user_id = query.from_user.id
        db.delete_note(note_id, user_id)
        await list_notes_command(update, context)

    elif data.startswith("ask_cancel_reminder_"):
        reminder_id = int(data.replace("ask_cancel_reminder_", ""))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Evet, iptal et", callback_data=f"confirm_cancel_reminder_{reminder_id}"),
            InlineKeyboardButton("Vazgeç", callback_data="btn_reminders"),
        ]])
        await show_panel(update, "⏰ *Bu hatırlatıcıyı iptal etmek istediğine emin misin?*", keyboard)

    elif data.startswith("confirm_cancel_reminder_"):
        reminder_id = int(data.replace("confirm_cancel_reminder_", ""))
        user_id = query.from_user.id
        if db.cancel_reminder(reminder_id, user_id):
            for job in context.job_queue.get_jobs_by_name(f"reminder-{reminder_id}"):
                job.schedule_removal()
        await list_reminders_command(update, context)


# ─── SERBEST METİN YANITLAYICI ───
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı buton veya slash komut yerine direkt metin yazarsa akıllı yanıt verir."""
    raw_text = (update.message.text or "").strip()
    text = raw_text.lower()
    pending_action = context.user_data.get("pending_action")

    if pending_action and text in {"iptal", "vazgeç", "vazgec", "cancel"}:
        context.user_data.pop("pending_action", None)
        await update.message.reply_text("İşlem iptal edildi.", reply_markup=get_main_keyboard())
        return

    if pending_action == "task":
        context.user_data.pop("pending_action", None)
        db.add_task(update.effective_user.id, raw_text[:500])
        await update.message.reply_text(
            f"✅ *Görev eklendi*\n\n{escape_markdown(raw_text[:500])}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Görevlerimi aç", callback_data="btn_tasks"),
                InlineKeyboardButton("⌂ Menü", callback_data="btn_home"),
            ]]),
        )
        return

    if pending_action == "note":
        context.user_data.pop("pending_action", None)
        db.add_note(update.effective_user.id, raw_text[:2000])
        await update.message.reply_text(
            f"✅ *Not kaydedildi*\n\n{escape_markdown(raw_text[:2000])}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📝 Notlarımı aç", callback_data="btn_notes"),
                InlineKeyboardButton("⌂ Menü", callback_data="btn_home"),
            ]]),
        )
        return

    if pending_action == "reminder":
        parsed = parse_quick_reminder(raw_text)
        if not parsed:
            await update.message.reply_text(
                "Bu formatı anlayamadım. Örneğin `20 Mola ver` yazabilirsin.",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard(),
            )
            return
        context.user_data.pop("pending_action", None)
        minutes, reminder_text = parsed
        schedule_reminder(
            context,
            update.effective_user.id,
            update.effective_chat.id,
            minutes,
            reminder_text,
        )
        await update.message.reply_text(
            f"⏰ *Hatırlatıcı kuruldu*\n\n"
            f"*{minutes:g} dakika sonra:* {escape_markdown(reminder_text)}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        return

    if any(w in text for w in ["hava", "hava durumu", "hava nasıl"]):
        await weather_command(update, context)
    elif any(w in text for w in ["dolar", "euro", "piyasa", "kurlar", "borsa", "bitcoin", "btc"]):
        await finance_command(update, context)
    elif text in ["görev", "görevler", "gorev", "yapılacaklar", "todo"]:
        await list_tasks_command(update, context)
    elif text in ["not", "notlar", "notlarım"]:
        await list_notes_command(update, context)
    elif text in ["menü", "menu", "ana menü", "ana menu"]:
        await menu_command(update, context)
    elif text in ["yardım", "help", "komutlar", "neler yapabilirsin"]:
        await help_command(update, context)
    else:
        await update.message.reply_text(
            f"🤔 '{update.message.text}' mesajını aldım!\n"
            f"Hızlı işlem yapmak için aşağıdaki menüyü kullanabilir veya `/help` yazabilirsin.",
            reply_markup=get_main_keyboard()
        )


# ─────────────────────────────────────────
# UYGULAMA BAŞLATICI
# ─────────────────────────────────────────
def main():
    # Veritabanını hazırla
    db.init_db()

    if not TOKEN or TOKEN == "BURAYA_BOT_TOKENINI_YAPISTIR":
        print("\n" + "=" * 60)
        print("⚠️  DİKKAT: TELEGRAM BOT TOKEN BULUNAMADI!")
        print("=" * 60)
        print("Botu çalıştırmak için bir Telegram Bot Token'ına ihtiyacınız var.")
        print("Nasıl alınır? (Tamamen ücretsizdir ve 30 saniye sürer):")
        print("1. Telegram'ı açın ve @BotFather aratın.")
        print("2. /newbot komutunu gönderin.")
        print("3. Botunuza bir isim ve kullanıcı adı verin.")
        print("4. Size verilen HTTP API Token'ı kopyalayın.")
        print("5. '.env' dosyasını açıp TELEGRAM_BOT_TOKEN alanına yapıştırın.")
        print("=" * 60 + "\n")
        sys.exit(1)

    print("🚀 Telegram Asistan Botu başlatılıyor...")
    app = ApplicationBuilder().token(TOKEN).post_init(initialize_app).build()

    # Komut yöneticileri
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("hava", weather_command))
    app.add_handler(CommandHandler("piyasa", finance_command))
    app.add_handler(CommandHandler("gorev", add_task_command))
    app.add_handler(CommandHandler("gorevler", list_tasks_command))
    app.add_handler(CommandHandler("not", add_note_command))
    app.add_handler(CommandHandler("notlar", list_notes_command))
    app.add_handler(CommandHandler("hatirlat", remind_command))
    app.add_handler(CommandHandler("hatirlaticilar", list_reminders_command))

    # Callback & Metin yöneticileri
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    webhook = get_webhook_config()
    if webhook:
        port = int(os.getenv("PORT", "10000"))
        logger.info("Telegram webhook modu başlatılıyor: %s", webhook["webhook_url"])
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook["url_path"],
            webhook_url=webhook["webhook_url"],
            secret_token=webhook["secret_token"],
            drop_pending_updates=False,
        )
    else:
        logger.info("Yerel polling modu başlatılıyor.")
        app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
