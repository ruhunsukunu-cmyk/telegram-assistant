import os
import sys
import logging
import hashlib
import json
import csv
from io import BytesIO, StringIO
from datetime import date, datetime, timedelta, timezone
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
    InputFile,
    WebAppInfo,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.helpers import escape_markdown


from telegram.ext import (
    ApplicationHandlerStop,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    TypeHandler,
    ContextTypes,
    filters,
)

import database as db
from services.weather import get_weather
from services.finance import get_market_rates
from services.natural_language import extract_future_datetime, parse_datetime, parse_expense_text

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
MINI_APP_URL = os.getenv("MINI_APP_URL", "").strip()
ALLOWED_USER_IDS = {
    int(value) for value in os.getenv("ALLOWED_USER_IDS", "").split(",") if value.strip().isdigit()
}
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()

MAIN_MENU_TEXT = (
    "✨ *Kişisel Asistan*\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "Gününü planla, takip et ve tek yerden yönet.\n\n"
    "Aşağıdan yapmak istediğin işlemi seç 👇"
)


def get_main_keyboard():
    """Ana menü interaktif butonları"""
    keyboard = [
        [InlineKeyboardButton("☀️ Bugün", callback_data="btn_today")],
        [
            InlineKeyboardButton("📋 Görevler", callback_data="btn_tasks"),
            InlineKeyboardButton("⏰ Hatırlatıcılar", callback_data="btn_reminders"),
        ],
        [
            InlineKeyboardButton("🎯 Alışkanlıklar", callback_data="btn_habits"),
            InlineKeyboardButton("💳 Harcamalar", callback_data="btn_expenses"),
        ],
        [
            InlineKeyboardButton("📝 Notlar", callback_data="btn_notes"),
            InlineKeyboardButton("📅 Takvim", callback_data="btn_calendar"),
        ],
        [
            InlineKeyboardButton("🌤️ Hava", callback_data="btn_weather"),
            InlineKeyboardButton("💹 Piyasalar", callback_data="btn_finance"),
        ],
        [InlineKeyboardButton("➕ Hızlı ekle", callback_data="btn_quick_add")],
        [
            InlineKeyboardButton("✨ Bu bot ne işe yarar?", callback_data="btn_about"),
            InlineKeyboardButton("❓ Yardım", callback_data="btn_help"),
        ]
    ]
    if MINI_APP_URL:
        keyboard.append([InlineKeyboardButton("📱 Görsel panel", web_app=WebAppInfo(MINI_APP_URL))])
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
        "En sık kullanılan örnekler:\n\n"
        "`/gorev Kitap oku` — görev ekle\n"
        "`/hatirlat 15 Su iç` — hatırlatıcı kur\n"
        "`/not Fikir metni` — not kaydet\n"
        "`/harcama 250 market` — harcama kaydet\n"
        "`/etkinlik yarın 14:00 | Doktor` — etkinlik ekle\n"
        "`/aliskanlik ekle Kitap oku` — alışkanlık başlat\n"
        "`/ara toplantı` — görev ve notlarında ara\n\n"
        "💡 Komut ezberlemek zorunda değilsin; `/menu` yazıp butonları kullanabilir "
        "veya _yarın saat 10 doktoru hatırlat_ gibi doğal bir cümle gönderebilirsin."
    )
    await show_panel(update, help_text, get_back_keyboard())


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "✨ *Bu bot ne işe yarar?*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Günlük hayatını Telegram'dan yönetmen için hazırlanmış kişisel asistandır.\n\n"
        "📋 *Planlama*\n"
        "• Görev ekler, tamamlar ve önceliklendirir\n"
        "• Son tarihli görevleri ve günlük özeti gösterir\n"
        "• Notlarını kaydeder ve tüm kayıtlarda arama yapar\n\n"
        "⏰ *Hatırlatıcılar ve takvim*\n"
        "• Dakikalık, tarihli, günlük ve haftalık hatırlatıcı kurar\n"
        "• Türkçe cümleleri anlar: _yarın saat 10 doktoru hatırlat_\n"
        "• Etkinlikleri takip eder, Google/Outlook uyumlu takvim dosyası verir\n\n"
        "🎯 *Rutinler ve finans*\n"
        "• Alışkanlıklarını günlük işaretler ve haftalık oranı hesaplar\n"
        "• Harcamalarını kategorilere ayırır, bütçeni ve kalan tutarı gösterir\n"
        "• Harcamaları Excel uyumlu CSV olarak indirir\n\n"
        "🌤️ *Güncel bilgiler*\n"
        "• Seçtiğin şehrin hava durumunu gösterir\n"
        "• Döviz ve kripto piyasalarını özetler\n\n"
        "🔐 *Verilerin*\n"
        "• Tüm verilerini JSON olarak indirebilir veya tamamen silebilirsin\n"
        "• Her kullanıcının kayıtları birbirinden ayrıdır"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Hemen bir şey ekle", callback_data="btn_quick_add")],
        [InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")],
    ])
    await show_panel(update, text, keyboard)


# ─── HAVA DURUMU ───
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hava <şehir> komutu"""
    city = " ".join(context.args).strip() if context.args else db.get_default_city(update.effective_user.id, DEFAULT_CITY)
    progress = await update.message.reply_text("🌤️ Hava durumu hazırlanıyor…")
    result = await get_weather(city)
    await progress.edit_text(result, parse_mode="Markdown", reply_markup=get_back_keyboard())


async def city_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        city = db.get_default_city(update.effective_user.id, DEFAULT_CITY)
        await update.message.reply_text(
            f"📍 Varsayılan şehrin: *{escape_markdown(city)}*\n\n"
            "Değiştirmek için: `/sehir Ankara`",
            parse_mode="Markdown",
        )
        return
    city = " ".join(context.args).strip()[:100]
    db.set_default_city(update.effective_user.id, city)
    await update.message.reply_text(
        f"✅ Varsayılan şehir *{escape_markdown(city)}* olarak kaydedildi.",
        parse_mode="Markdown",
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    term = " ".join(context.args).strip()
    if len(term) < 2:
        await update.message.reply_text(
            "🔎 Aramak istediğin en az iki harfi yaz.\nÖrnek: `/ara toplantı`",
            parse_mode="Markdown",
        )
        return
    results = db.search_user_content(update.effective_user.id, term)
    if not results:
        await update.message.reply_text(
            f"🔎 *{escape_markdown(term)}* için görev veya not bulunamadı.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        return
    lines = []
    for item in results:
        icon = "✅" if item["type"] == "task" and item.get("is_done") else "📋" if item["type"] == "task" else "📝"
        lines.append(f"{icon} {escape_markdown(item['content'])}")
    await update.message.reply_text(
        f"🔎 *Arama sonuçları* · _{len(results)} kayıt_\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


# ─── FİNANS & KURLAR ───
async def finance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/piyasa komutu"""
    progress = await update.message.reply_text("💹 Piyasa özeti hazırlanıyor…")
    result = await get_market_rates()
    await progress.edit_text(result, parse_mode="Markdown", reply_markup=get_back_keyboard())


async def build_today_summary(user_id):
    city = db.get_default_city(user_id, DEFAULT_CITY)
    weather = await get_weather(city)
    tasks = [task for task in db.get_tasks(user_id) if not task["is_done"]]
    reminders = db.get_pending_reminders(user_id)

    task_lines = [f"• {escape_markdown(task['title'])}" for task in tasks[:3]]
    task_text = "\n".join(task_lines) if task_lines else "_Bekleyen görev yok_"
    if reminders:
        next_reminder = reminders[0]
        due_at = _as_utc(next_reminder["due_at"]).astimezone(LOCAL_TIMEZONE)
        reminder_text = (
            f"{escape_markdown(next_reminder['message'])}\n"
            f"_{due_at.strftime('%d.%m · %H:%M')}_"
        )
    else:
        reminder_text = "_Bekleyen hatırlatıcı yok_"

    return (
        "☀️ *Bugünün özeti*\n\n"
        f"{weather}\n\n"
        f"📋 *Görevler* · {len(tasks)} bekliyor\n{task_text}\n\n"
        f"⏰ *Sıradaki hatırlatıcı*\n{reminder_text}"
    )


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress = await update.message.reply_text("☀️ Günün özeti hazırlanıyor…")
    summary = await build_today_summary(update.effective_user.id)
    await progress.edit_text(summary, parse_mode="Markdown", reply_markup=get_back_keyboard())


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


async def add_detailed_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args).strip()
    parts = [part.strip() for part in raw.split("|", 2)]
    priority_map = {"yüksek": "high", "yuksek": "high", "normal": "normal", "düşük": "low", "dusuk": "low"}
    if len(parts) != 3 or parts[0].lower() not in priority_map:
        await update.message.reply_text("Örnek: `/gorevdetay yüksek | yarın 18:00 | Raporu bitir`", parse_mode="Markdown")
        return
    due_at = parse_datetime(parts[1])
    if not due_at or not parts[2]:
        await update.message.reply_text("Görev tarihi veya açıklaması anlaşılamadı.")
        return
    task_id = db.add_task(update.effective_user.id, parts[2][:500])
    db.set_task_metadata(task_id, update.effective_user.id, priority_map[parts[0].lower()], due_at)
    await update.message.reply_text("✅ Tarihli görev eklendi.", reply_markup=get_main_keyboard())


async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gorevler"""
    user_id = update.effective_user.id
    tasks = db.get_enriched_tasks(user_id)

    if not tasks:
        text = "📋 *Görevlerin*\n━━━━━━━━━━━━━━━━━━━━━\n🎉 Bekleyen görevin yok.\n\nEklemek için: `/gorev <iş>`"
        await show_panel(update, text, get_back_keyboard())
        return

    pending_count = sum(not t["is_done"] for t in tasks)
    msg = f"📋 *Görevlerin*  ·  _{pending_count} bekliyor_\n━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for index, t in enumerate(tasks[:15], 1):
        priority_emoji = {"high": "🔴", "normal": "🟡", "low": "🟢"}.get(t["priority"], "🟡")
        status_emoji = "✅" if t["is_done"] else "⬜"
        due_text = ""
        if t["due_at"]:
            due_text = f" · _{_as_utc(t['due_at']).astimezone(LOCAL_TIMEZONE).strftime('%d.%m %H:%M')}_"
        msg += f"\n{status_emoji} {priority_emoji} *{index}.* {escape_markdown(t['title'])}{due_text}\n"

        if not t["is_done"]:
            keyboard.append([
                InlineKeyboardButton(f"✅ {index}. Tamamla", callback_data=f"done_task_{t['id']}"),
                InlineKeyboardButton("🗑️ Sil", callback_data=f"ask_del_task_{t['id']}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(f"🗑️ {index}. görevi temizle", callback_data=f"ask_del_task_{t['id']}")
            ])
    if any(t["is_done"] for t in tasks):
        keyboard.append([
            InlineKeyboardButton("🧹 Tamamlananları temizle", callback_data="ask_clear_completed")
        ])
    keyboard.append([InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")])
    await show_panel(update, msg, InlineKeyboardMarkup(keyboard))


async def clear_completed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    completed = sum(task["is_done"] for task in db.get_tasks(update.effective_user.id))
    if not completed:
        await update.message.reply_text("🧹 Temizlenecek tamamlanmış görev yok.")
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Evet, temizle", callback_data="confirm_clear_completed"),
        InlineKeyboardButton("Vazgeç", callback_data="btn_tasks"),
    ]])
    await update.message.reply_text(
        f"🧹 *{completed} tamamlanmış görev silinsin mi?*",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


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
    if not job.data.get("recurrence"):
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
        recurrence = db.get_reminder_recurrence(reminder["id"])
        data = {"id": reminder["id"], "message": reminder["message"], "recurrence": recurrence}
        if recurrence == "daily" or (recurrence and recurrence.startswith("weekly:")):
            local_due = due_at.astimezone(LOCAL_TIMEZONE)
            kwargs = {}
            if recurrence.startswith("weekly:"):
                kwargs["days"] = (int(recurrence.split(":", 1)[1]),)
            app.job_queue.run_daily(reminder_callback, time=local_due.timetz(), chat_id=reminder["chat_id"], data=data, name=f"reminder-{reminder['id']}", **kwargs)
        else:
            app.job_queue.run_once(
                reminder_callback, when=max((due_at - now).total_seconds(), 1),
                chat_id=reminder["chat_id"], data=data, name=f"reminder-{reminder['id']}",
            )
        restored += 1
    if restored:
        logger.info("%s bekleyen hatırlatıcı yeniden yüklendi.", restored)


async def daily_summary_callback(context: ContextTypes.DEFAULT_TYPE):
    summary = await build_today_summary(context.job.data["user_id"])
    await context.bot.send_message(
        chat_id=context.job.chat_id, text=summary, parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


def restore_daily_summaries(app):
    for item in db.get_daily_summaries():
        hour, minute = map(int, item["send_time"].split(":"))
        timezone_info = ZoneInfo(item["timezone"])
        send_at = datetime.now(timezone_info).replace(hour=hour, minute=minute, second=0, microsecond=0).timetz()
        app.job_queue.run_daily(
            daily_summary_callback, time=send_at, chat_id=item["chat_id"],
            data={"user_id": item["user_id"]}, name=f"daily-summary-{item['user_id']}",
        )


async def initialize_app(app):
    """Telegram komut menüsünü kur ve kalıcı hatırlatıcıları geri yükle."""
    await app.bot.set_my_commands([
        BotCommand("menu", "Ana paneli aç"),
        BotCommand("bugun", "Kişisel günlük özetini göster"),
        BotCommand("gorev", "Yeni görev ekle"),
        BotCommand("gorevdetay", "Öncelikli ve tarihli görev ekle"),
        BotCommand("gorevler", "Görevlerini görüntüle"),
        BotCommand("not", "Yeni not kaydet"),
        BotCommand("notlar", "Notlarını görüntüle"),
        BotCommand("hatirlat", "Dakika bazlı hatırlatıcı kur"),
        BotCommand("hatirlaticilar", "Bekleyen hatırlatıcılarını görüntüle"),
        BotCommand("tekrarla", "Her gün tekrarlanan hatırlatıcı kur"),
        BotCommand("hava", "Şehir hava durumunu göster"),
        BotCommand("sehir", "Varsayılan şehrini değiştir"),
        BotCommand("piyasa", "Döviz ve kripto özetini göster"),
        BotCommand("ara", "Görev ve notlarında ara"),
        BotCommand("temizle", "Tamamlanan görevleri temizle"),
        BotCommand("aliskanlik", "Alışkanlık ekle veya takip et"),
        BotCommand("harcama", "Yeni harcama kaydet"),
        BotCommand("harcamalar", "Harcama özetini göster"),
        BotCommand("butce", "Aylık harcama bütçesi belirle"),
        BotCommand("harcamaindir", "Harcamaları CSV olarak indir"),
        BotCommand("disaaktar", "Kişisel verilerini indir"),
        BotCommand("etkinlik", "Takvime etkinlik ekle"),
        BotCommand("takvim", "Yaklaşan etkinlikleri göster"),
        BotCommand("takvimindir", "Takvimi ICS olarak indir"),
        BotCommand("durum", "Botun çalışma durumunu göster"),
        BotCommand("ozetsaat", "Otomatik günlük özet saatini ayarla"),
        BotCommand("verilerimisil", "Tüm kişisel verilerini sil"),
        BotCommand("hakkinda", "Botun yapabildiği her şeyi göster"),
        BotCommand("help", "Yardım merkezini aç"),
    ])
    await restore_reminders(app)
    restore_daily_summaries(app)


async def daily_summary_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for job in context.job_queue.get_jobs_by_name(f"daily-summary-{user_id}"):
        job.schedule_removal()
    value = " ".join(context.args).strip().lower()
    if value in {"kapat", "off", "iptal"}:
        db.delete_daily_summary(user_id)
        await update.message.reply_text("Günlük otomatik özet kapatıldı.")
        return
    import re
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        await update.message.reply_text("Örnek: `/ozetsaat 08:00` veya `/ozetsaat kapat`", parse_mode="Markdown")
        return
    db.set_daily_summary(user_id, update.effective_chat.id, value, str(LOCAL_TIMEZONE))
    hour, minute = map(int, value.split(":"))
    send_at = datetime.now(LOCAL_TIMEZONE).replace(hour=hour, minute=minute, second=0, microsecond=0).timetz()
    context.job_queue.run_daily(
        daily_summary_callback, time=send_at, chat_id=update.effective_chat.id,
        data={"user_id": user_id}, name=f"daily-summary-{user_id}",
    )
    await update.message.reply_text(f"☀️ Günlük özet saati {value} olarak ayarlandı.")


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


async def recurring_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args).strip()
    if "|" not in raw:
        await update.message.reply_text("Örnek: `/tekrarla 08:00 | Su iç`", parse_mode="Markdown")
        return
    time_text, message = (part.strip() for part in raw.split("|", 1))
    day_map = {"pazar": 0, "pazartesi": 1, "salı": 2, "sali": 2, "çarşamba": 3, "carsamba": 3, "perşembe": 4, "persembe": 4, "cuma": 5, "cumartesi": 6}
    time_parts = time_text.lower().split()
    recurrence = "daily"
    days = None
    if time_parts and time_parts[0] in day_map:
        recurrence = f"weekly:{day_map[time_parts[0]]}"
        days = (day_map[time_parts[0]],)
        time_text = " ".join(time_parts[1:])
    parsed = parse_datetime(time_text)
    if not parsed or not message:
        await update.message.reply_text("Saat veya mesaj anlaşılamadı.")
        return
    now_local = datetime.now(LOCAL_TIMEZONE)
    first = now_local.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
    if days:
        target_python_weekday = (days[0] - 1) % 7
        day_delta = (target_python_weekday - now_local.weekday()) % 7
        if day_delta == 0 and first <= now_local:
            day_delta = 7
        first += timedelta(days=day_delta)
    elif first <= now_local:
        first += timedelta(days=1)
    reminder_id = db.add_reminder(update.effective_user.id, update.effective_chat.id, message, first)
    db.set_reminder_recurrence(reminder_id, update.effective_user.id, recurrence)
    kwargs = {"days": days} if days else {}
    context.job_queue.run_daily(
        reminder_callback, time=first.timetz(), chat_id=update.effective_chat.id,
        data={"id": reminder_id, "message": message, "recurrence": recurrence},
        name=f"reminder-{reminder_id}", **kwargs,
    )
    label = time_parts[0].capitalize() if days else "Her gün"
    await update.message.reply_text(f"🔁 {label} {first.strftime('%H:%M')} için hatırlatıcı kuruldu.")


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


async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].lower() == "ekle":
        name = " ".join(context.args[1:]).strip()
        if not name:
            await update.message.reply_text("Örnek: `/aliskanlik ekle Kitap oku`", parse_mode="Markdown")
            return
        db.add_habit(update.effective_user.id, name[:200])
    await show_habits(update)


async def show_habits(update):
    habits = db.get_habits(update.effective_user.id)
    if not habits:
        await show_panel(
            update,
            "🎯 *Alışkanlıkların*\n━━━━━━━━━━━━━━━━━━━━━\nHenüz kayıt yok.\n\n"
            "`/aliskanlik ekle Kitap oku`",
            get_back_keyboard(),
        )
        return
    text = "🎯 *Bugünkü alışkanlıkların*\n━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for habit in habits:
        icon = "✅" if habit["done_today"] else "⬜"
        recent_dates = set(db.get_habit_log_dates(habit["id"], update.effective_user.id, 7))
        last_week = {(datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat() for i in range(7)}
        weekly = round(len(recent_dates & last_week) / 7 * 100)
        text += f"\n{icon} {escape_markdown(habit['name'])} · _7 gün %{weekly} · toplam {habit['total_days']}_"
        if not habit["done_today"]:
            keyboard.append([InlineKeyboardButton(
                f"✓ {habit['name'][:30]}", callback_data=f"check_habit_{habit['id']}"
            )])
    keyboard.append([InlineKeyboardButton("‹ Ana menü", callback_data="btn_home")])
    await show_panel(update, text, InlineKeyboardMarkup(keyboard))


async def expense_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Örnek: `/harcama 250 market Haftalık alışveriş`", parse_mode="Markdown"
        )
        return
    try:
        amount = float(context.args[0].replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Tutar pozitif bir sayı olmalı.")
        return
    category = context.args[1].lower()[:50]
    note = " ".join(context.args[2:])[:500]
    db.add_expense(update.effective_user.id, amount, category, note)
    await update.message.reply_text(
        f"✅ *Harcama kaydedildi*\n{amount:,.2f} TL · {escape_markdown(category)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


async def expenses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = db.get_expense_summary(update.effective_user.id)
    if not summary:
        text = "💳 *Harcamaların*\n━━━━━━━━━━━━━━━━━━━━━\nHenüz kayıt yok.\n\n`/harcama 250 market`"
    else:
        total = sum(float(row["total"]) for row in summary if row["currency"] == "TRY")
        lines = [f"• {escape_markdown(row['category'])}: *{float(row['total']):,.2f} {row['currency']}*" for row in summary]
        budget = db.get_budget(update.effective_user.id)
        budget_text = ""
        if budget:
            remaining = float(budget["monthly_limit"]) - total
            budget_text = f"\nBütçeden kalan: *{remaining:,.2f} {budget['currency']}*"
        text = f"💳 *Harcama özeti*\n━━━━━━━━━━━━━━━━━━━━━\nToplam: *{total:,.2f} TL*{budget_text}\n\n" + "\n".join(lines)
    await show_panel(update, text, get_back_keyboard())


async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Örnek: `/butce 10000`", parse_mode="Markdown")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Bütçe pozitif bir sayı olmalı.")
        return
    db.set_budget(update.effective_user.id, amount)
    await update.message.reply_text(f"💳 Aylık bütçe {amount:,.2f} TL olarak ayarlandı.")


async def expense_export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["tutar", "para_birimi", "kategori", "not", "tarih"])
    for row in db.get_expenses(update.effective_user.id):
        writer.writerow([row["amount"], row["currency"], row["category"], row["note"], row["spent_at"]])
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    await update.message.reply_document(
        document=InputFile(BytesIO(content), filename="harcamalar.csv"),
        caption="💳 Harcama kayıtların hazır.",
    )


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = db.export_user_data(update.effective_user.id)
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")
    await update.message.reply_document(
        document=InputFile(BytesIO(content), filename="telegram-asistan-verilerim.json"),
        caption="📦 Verilerinin dışa aktarımı hazır.",
    )


async def delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Tüm verilerimi sil", callback_data="confirm_delete_all_data"),
        InlineKeyboardButton("Vazgeç", callback_data="btn_home"),
    ]])
    await update.message.reply_text(
        "⚠️ *Tüm notların, görevlerin, hatırlatıcıların, alışkanlıkların, "
        "harcamaların ve etkinliklerin kalıcı olarak silinecek.*",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage = "PostgreSQL" if db.DATABASE_URL else "geçici SQLite"
    mode = "webhook" if get_webhook_config() else "polling"
    await update.message.reply_text(
        f"🟢 Bot çalışıyor\n• Bağlantı: {mode}\n• Veri deposu: {storage}\n"
        f"• Saat: {datetime.now(LOCAL_TIMEZONE).strftime('%d.%m.%Y %H:%M')}"
    )


async def event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args).strip()
    if "|" not in raw:
        await update.message.reply_text(
            "Örnek: `/etkinlik yarın 14:00 | Doktor randevusu`", parse_mode="Markdown"
        )
        return
    date_text, title = (part.strip() for part in raw.split("|", 1))
    starts_at = parse_datetime(date_text)
    if not starts_at or not title:
        await update.message.reply_text("Tarih veya etkinlik adı anlaşılamadı.")
        return
    db.add_calendar_event(update.effective_user.id, title[:300], starts_at)
    local_time = starts_at.astimezone(LOCAL_TIMEZONE)
    await update.message.reply_text(
        f"📅 *Etkinlik eklendi*\n{escape_markdown(title[:300])}\n"
        f"_{local_time.strftime('%d.%m.%Y · %H:%M')}_",
        parse_mode="Markdown",
    )


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = db.get_upcoming_events(update.effective_user.id)
    if not events:
        text = "📅 *Takvimin*\n━━━━━━━━━━━━━━━━━━━━━\nYaklaşan etkinlik yok.\n\n`/etkinlik yarın 14:00 | Doktor`"
    else:
        lines = []
        for event in events:
            starts_at = _as_utc(event["starts_at"]).astimezone(LOCAL_TIMEZONE)
            lines.append(f"• *{escape_markdown(event['title'])}*\n  _{starts_at.strftime('%d.%m.%Y · %H:%M')}_")
        text = "📅 *Yaklaşan etkinlikler*\n━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(lines)
    await show_panel(update, text, get_back_keyboard())


async def calendar_export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = db.get_upcoming_events(update.effective_user.id, datetime(1970, 1, 1, tzinfo=timezone.utc), 1000)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Telegram Assistant//TR"]
    for event in events:
        start = _as_utc(event["starts_at"]).strftime("%Y%m%dT%H%M%SZ")
        title = str(event["title"]).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
        lines.extend(["BEGIN:VEVENT", f"UID:{event['id']}@telegram-assistant", f"DTSTART:{start}", f"SUMMARY:{title}", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    content = "\r\n".join(lines).encode("utf-8")
    await update.message.reply_document(
        document=InputFile(BytesIO(content), filename="telegram-asistan-takvim.ics"),
        caption="📅 Takvim dosyan hazır. Google veya Outlook Takvim'e aktarabilirsin.",
    )


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
        city = db.get_default_city(query.from_user.id, DEFAULT_CITY)
        res = await get_weather(city)
        await query.edit_message_text(res, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif data == "btn_today":
        await query.edit_message_text("☀️ Günün özeti hazırlanıyor…")
        summary = await build_today_summary(query.from_user.id)
        await query.edit_message_text(summary, parse_mode="Markdown", reply_markup=get_back_keyboard())

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

    elif data == "btn_habits":
        await show_habits(update)

    elif data == "btn_expenses":
        await expenses_command(update, context)

    elif data == "btn_calendar":
        await calendar_command(update, context)

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
            [
                InlineKeyboardButton("📋 Görev", callback_data="quick_task"),
                InlineKeyboardButton("📝 Not", callback_data="quick_note"),
            ],
            [InlineKeyboardButton("⏰ Hatırlatıcı kur", callback_data="btn_remind_help")],
            [
                InlineKeyboardButton("🎯 Alışkanlık", callback_data="btn_habits"),
                InlineKeyboardButton("💳 Harcama", callback_data="btn_expenses"),
            ],
            [InlineKeyboardButton("📅 Takvimi aç", callback_data="btn_calendar")],
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

    elif data == "btn_about":
        await about_command(update, context)

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

    elif data == "ask_clear_completed":
        completed = sum(task["is_done"] for task in db.get_tasks(query.from_user.id))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Evet, temizle", callback_data="confirm_clear_completed"),
            InlineKeyboardButton("Vazgeç", callback_data="btn_tasks"),
        ]])
        await show_panel(update, f"🧹 *{completed} tamamlanmış görev silinsin mi?*", keyboard)

    elif data == "confirm_clear_completed":
        db.clear_completed_tasks(query.from_user.id)
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

    elif data.startswith("check_habit_"):
        habit_id = int(data.replace("check_habit_", ""))
        db.check_habit(habit_id, query.from_user.id)
        await show_habits(update)

    elif data == "confirm_delete_all_data":
        user_id = query.from_user.id
        for reminder in db.get_pending_reminders(user_id):
            for job in context.job_queue.get_jobs_by_name(f"reminder-{reminder['id']}"):
                job.schedule_removal()
        db.delete_user_data(user_id)
        context.user_data.clear()
        await show_panel(update, "✅ Tüm kişisel verilerin silindi.", get_main_keyboard())


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

    if "hatırlat" in text or "hatirlat" in text:
        parsed_datetime = extract_future_datetime(raw_text)
        if parsed_datetime:
            due_at, reminder_text = parsed_datetime
            if reminder_text and due_at > datetime.now(due_at.tzinfo):
                minutes = (due_at.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 60
                schedule_reminder(context, update.effective_user.id, update.effective_chat.id, minutes, reminder_text)
                await update.message.reply_text(
                    f"⏰ *Hatırlatıcı kuruldu*\n{escape_markdown(reminder_text)}\n"
                    f"_{due_at.astimezone(LOCAL_TIMEZONE).strftime('%d.%m.%Y · %H:%M')}_",
                    parse_mode="Markdown",
                )
                return

    if text.startswith("alışkanlık ekle ") or text.startswith("aliskanlik ekle "):
        name = raw_text.split(" ", 2)[2].strip()
        db.add_habit(update.effective_user.id, name[:200])
        await update.message.reply_text(f"🎯 Alışkanlık eklendi: {name[:200]}")
        return

    if any(marker in text for marker in [" tl ", " try ", "₺"]):
        expense = parse_expense_text(raw_text)
        if expense:
            db.add_expense(update.effective_user.id, **expense)
            await update.message.reply_text(
                f"💳 {expense['amount']:,.2f} TL · {expense['category']} kaydedildi."
            )
            return

    if "takvime ekle" in text:
        parsed_event = extract_future_datetime(raw_text)
        if parsed_event:
            starts_at, title = parsed_event
            if title:
                db.add_calendar_event(update.effective_user.id, title[:300], starts_at)
                await update.message.reply_text(
                    f"📅 Etkinlik eklendi: {title[:300]} · "
                    f"{starts_at.astimezone(LOCAL_TIMEZONE).strftime('%d.%m.%Y %H:%M')}"
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


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        payload = json.loads(update.effective_message.web_app_data.data)
    except (TypeError, ValueError, json.JSONDecodeError):
        await update.effective_message.reply_text("Panel isteği anlaşılamadı.")
        return
    action = payload.get("action")
    if action == "tasks":
        await list_tasks_command(update, context)
    elif action == "habits":
        await show_habits(update)
    elif action == "expenses":
        await expenses_command(update, context)
    elif action == "today":
        await today_command(update, context)
    else:
        await update.effective_message.reply_text("Bilinmeyen panel işlemi.")


async def error_handler(update, context):
    logger.exception("Telegram güncellemesi işlenirken hata oluştu", exc_info=context.error)
    message = getattr(update, "effective_message", None)
    if message:
        try:
            await message.reply_text("⚠️ İşlem tamamlanamadı. Lütfen biraz sonra tekrar dene.")
        except Exception:
            logger.exception("Kullanıcıya hata mesajı gönderilemedi")
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                int(ADMIN_CHAT_ID),
                f"🚨 Bot hatası: {type(context.error).__name__}",
            )
        except Exception:
            logger.exception("Yönetici hata bildirimi gönderilemedi")


async def access_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ALLOWED_USER_IDS or not update.effective_user:
        return
    if update.effective_user.id not in ALLOWED_USER_IDS:
        if update.effective_message:
            await update.effective_message.reply_text("Bu bot özel kullanım için yapılandırılmış.")
        raise ApplicationHandlerStop


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
    app.add_handler(TypeHandler(Update, access_guard), group=-1)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("hakkinda", about_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("hava", weather_command))
    app.add_handler(CommandHandler("sehir", city_command))
    app.add_handler(CommandHandler("ara", search_command))
    app.add_handler(CommandHandler("piyasa", finance_command))
    app.add_handler(CommandHandler("bugun", today_command))
    app.add_handler(CommandHandler("gorev", add_task_command))
    app.add_handler(CommandHandler("gorevdetay", add_detailed_task_command))
    app.add_handler(CommandHandler("gorevler", list_tasks_command))
    app.add_handler(CommandHandler("temizle", clear_completed_command))
    app.add_handler(CommandHandler("aliskanlik", habits_command))
    app.add_handler(CommandHandler("harcama", expense_command))
    app.add_handler(CommandHandler("harcamalar", expenses_command))
    app.add_handler(CommandHandler("butce", budget_command))
    app.add_handler(CommandHandler("harcamaindir", expense_export_command))
    app.add_handler(CommandHandler("disaaktar", export_command))
    app.add_handler(CommandHandler("etkinlik", event_command))
    app.add_handler(CommandHandler("takvim", calendar_command))
    app.add_handler(CommandHandler("takvimindir", calendar_export_command))
    app.add_handler(CommandHandler("durum", status_command))
    app.add_handler(CommandHandler("ozetsaat", daily_summary_time_command))
    app.add_handler(CommandHandler("verilerimisil", delete_data_command))
    app.add_handler(CommandHandler("not", add_note_command))
    app.add_handler(CommandHandler("notlar", list_notes_command))
    app.add_handler(CommandHandler("hatirlat", remind_command))
    app.add_handler(CommandHandler("hatirlaticilar", list_reminders_command))
    app.add_handler(CommandHandler("tekrarla", recurring_reminder_command))

    # Callback & Metin yöneticileri
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

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
