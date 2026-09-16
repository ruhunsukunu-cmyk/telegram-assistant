import os
import sys
import logging
from datetime import datetime

# Windows konsolunda emoji karakterlerinin hata vermesini engelle
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.helpers import escape_markdown


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Bulut sunucularının (Render, Koyeb vb.) botu canlı görmesi için HTTP yanıtı"""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "online", "service": "telegram-assistant-bot"}')

    def log_message(self, format, *args):
        pass  # Gereksiz konsol kirliliğini engelle


def start_health_server(port: int):
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"🌐 Bulut sağlık kontrolü sunucusu port {port} üzerinde hazır.")
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

# Ortam değişkenlerini yükle
load_dotenv()

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


def get_main_keyboard():
    """Ana menü interaktif butonları"""
    keyboard = [
        [
            InlineKeyboardButton("🌤️ Hava Durumu", callback_data="btn_weather"),
            InlineKeyboardButton("💹 Finans & Kurlar", callback_data="btn_finance"),
        ],
        [
            InlineKeyboardButton("📋 Görevlerim", callback_data="btn_tasks"),
            InlineKeyboardButton("📝 Notlarım", callback_data="btn_notes"),
        ],
        [
            InlineKeyboardButton("⏰ Hatırlatıcı Nasıl Kurulur?", callback_data="btn_remind_help"),
            InlineKeyboardButton("❓ Yardım & Komutlar", callback_data="btn_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ─────────────────────────────────────────
# KOMUTLAR
# ─────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start komutu: Kullanıcıyı karşılar ve kontrol panelini sunar."""
    user = update.effective_user
    name = user.first_name if user else "Dostum"

    welcome_text = (
        f"👋 Merhaba *{escape_markdown(name)}*! Ben senin kişisel *Telegram Asistanınım*.\n\n"
        f"Günlük işlerinde, hatırlatmalarında, notlarında ve piyasa/hava takibinde "
        f"sana yardımcı olmak için 7/24 buradayım.\n\n"
        f"Aşağıdaki butonları kullanarak hızlıca işlem yapabilirsin 👇"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help komutu: Tüm komutların detaylı kullanım kılavuzu."""
    help_text = (
        "🤖 *Kişisel Asistan Komut Listesi:*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🌤️ *Hava Durumu:* `/hava <şehir>` (Örn: `/hava ankara`)\n"
        "💹 *Piyasa / Kurlar:* `/piyasa` (Dolar, Euro, BTC, ETH)\n"
        "📋 *Görev Ekle:* `/gorev <yapılacak iş>` (Örn: `/gorev Almanca çalış`)\n"
        "📋 *Görevleri Gör:* `/gorevler`\n"
        "📝 *Hızlı Not Al:* `/not <not içeriği>`\n"
        "📝 *Notları Gör:* `/notlar`\n"
        "⏰ *Hatırlatıcı Kur:* `/hatirlat <dakika> <mesaj>`\n"
        "   └ *Örnek:* `/hatirlat 15 Çayı ocaktan al`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *İpucu:* Menü butonlarını kullanarak da tek tıkla işlem yapabilirsin!"
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(help_text, parse_mode="Markdown")


# ─── HAVA DURUMU ───
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hava <şehir> komutu"""
    city = " ".join(context.args).strip() if context.args else DEFAULT_CITY
    await update.message.reply_text("⏳ Hava durumu alınıyor...")
    result = await get_weather(city)
    await update.message.reply_text(result, parse_mode="Markdown")


# ─── FİNANS & KURLAR ───
async def finance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/piyasa komutu"""
    await update.message.reply_text("⏳ Piyasa kurları çekiliyor...")
    result = await get_market_rates()
    await update.message.reply_text(result, parse_mode="Markdown")


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
        f"✅ Not kaydedildi (ID: `{note_id}`):\n\n_{escape_markdown(content)}_",
        parse_mode="Markdown"
    )


async def list_notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/notlar"""
    user_id = update.effective_user.id
    notes = db.get_notes(user_id)

    if not notes:
        text = "📝 Henüz kaydedilmiş bir notunuz yok.\nEklemek için: `/not <metin>`"
        if update.message:
            await update.message.reply_text(text, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode="Markdown")
        return

    msg = "📝 *Kaydedilen Notlarınız:*\n━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for n in notes[:10]:  # Son 10 not
        dt = n["created_at"].split()[0] if n["created_at"] else ""
        msg += f"• `{escape_markdown(n['content'])}` _({dt})_\n"
        keyboard.append([
            InlineKeyboardButton(f"🗑️ Sil: {n['content'][:20]}...", callback_data=f"del_note_{n['id']}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)


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
        f"📋 Görev listene eklendi (ID: `{task_id}`):\n\n_{escape_markdown(title)}_",
        parse_mode="Markdown"
    )


async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gorevler"""
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id)

    if not tasks:
        text = "🎉 Harika! Bekleyen hiçbir göreviniz yok.\nYeni görev için: `/gorev <iş>`"
        if update.message:
            await update.message.reply_text(text, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode="Markdown")
        return

    msg = "📋 *Görev Listeniz:*\n━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for t in tasks:
        status_emoji = "✅" if t["is_done"] else "⬜"
        msg += f"{status_emoji} *{escape_markdown(t['title'])}*\n"

        if not t["is_done"]:
            keyboard.append([
                InlineKeyboardButton(f"✅ Tamamla: {t['title'][:18]}", callback_data=f"done_task_{t['id']}"),
                InlineKeyboardButton("🗑️ Sil", callback_data=f"del_task_{t['id']}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(f"🗑️ Temizle: {t['title'][:20]}", callback_data=f"del_task_{t['id']}")
            ])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)


# ─── HATIRLATICI (JOB QUEUE) ───
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    """Zamanı gelen hatırlatmayı kullanıcıya iletir"""
    job = context.job
    chat_id = job.chat_id
    message_text = job.data

    alarm_msg = (
        "⏰ *DİKKAT! HATIRLATMA ZAMANI!*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 *Hatırlatıcı:* {escape_markdown(message_text)}\n"
        f"🕒 *Zaman:* {datetime.now().strftime('%H:%M')}"
    )
    await context.bot.send_message(chat_id=chat_id, text=alarm_msg, parse_mode="Markdown")


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
    seconds = int(minutes * 60)
    chat_id = update.effective_chat.id

    context.job_queue.run_once(
        reminder_callback,
        when=seconds,
        chat_id=chat_id,
        data=remind_text
    )

    await update.message.reply_text(
        f"⏳ Anlaşıldı! *{minutes} dakika* sonra sana şunu hatırlatacağım:\n\n"
        f"🔔 _{escape_markdown(remind_text)}_",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────
# BUTON ETKİLEŞİMLERİ (CALLBACK QUERY)
# ─────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "btn_weather":
        await query.message.reply_text("⏳ Hava durumu alınıyor...")
        res = await get_weather(DEFAULT_CITY)
        await query.message.reply_text(res, parse_mode="Markdown")

    elif data == "btn_finance":
        await query.message.reply_text("⏳ Piyasa kurları çekiliyor...")
        res = await get_market_rates()
        await query.message.reply_text(res, parse_mode="Markdown")

    elif data == "btn_tasks":
        await list_tasks_command(update, context)

    elif data == "btn_notes":
        await list_notes_command(update, context)

    elif data == "btn_remind_help":
        await query.message.reply_text(
            "⏰ *Hatırlatıcı Nasıl Kurulur?*\n\n"
            "Mesaj alanına şu komutu yazıp göndermen yeterli:\n"
            "`/hatirlat <dakika> <hatırlatılacak şey>`\n\n"
            "*Örnekler:*\n"
            "• `/hatirlat 5 Fırını kapat`\n"
            "• `/hatirlat 30 Toplantıya katıl`\n"
            "• `/hatirlat 60 Mola ver su iç`",
            parse_mode="Markdown"
        )

    elif data == "btn_help":
        await help_command(update, context)

    elif data.startswith("done_task_"):
        task_id = int(data.replace("done_task_", ""))
        user_id = query.from_user.id
        db.complete_task(task_id, user_id)
        await query.message.reply_text(f"🎉 Görev tamamlandı olarak işaretlendi!")

    elif data.startswith("del_task_"):
        task_id = int(data.replace("del_task_", ""))
        user_id = query.from_user.id
        db.delete_task(task_id, user_id)
        await query.message.reply_text(f"🗑️ Görev silindi.")

    elif data.startswith("del_note_"):
        note_id = int(data.replace("del_note_", ""))
        user_id = query.from_user.id
        db.delete_note(note_id, user_id)
        await query.message.reply_text(f"🗑️ Not silindi.")


# ─── SERBEST METİN YANITLAYICI ───
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı buton veya slash komut yerine direkt metin yazarsa akıllı yanıt verir."""
    text = (update.message.text or "").strip().lower()

    if any(w in text for w in ["hava", "hava durumu", "hava nasıl"]):
        await weather_command(update, context)
    elif any(w in text for w in ["dolar", "euro", "piyasa", "kurlar", "borsa", "bitcoin", "btc"]):
        await finance_command(update, context)
    elif text in ["görev", "görevler", "gorev", "yapılacaklar", "todo"]:
        await list_tasks_command(update, context)
    elif text in ["not", "notlar", "notlarım"]:
        await list_notes_command(update, context)
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

    # Bulut ortamı (Render, Koyeb vb.) portu verdiyse HTTP sunucusunu başlat
    port = os.getenv("PORT")
    if port:
        try:
            start_health_server(int(port))
        except Exception as e:
            logger.warning(f"Sağlık sunucusu başlatılamadı: {e}")

    print("🚀 Telegram Asistan Botu başlatılıyor...")
    app = ApplicationBuilder().token(TOKEN).build()

    # Komut yöneticileri
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("hava", weather_command))
    app.add_handler(CommandHandler("piyasa", finance_command))
    app.add_handler(CommandHandler("gorev", add_task_command))
    app.add_handler(CommandHandler("gorevler", list_tasks_command))
    app.add_handler(CommandHandler("not", add_note_command))
    app.add_handler(CommandHandler("notlar", list_notes_command))
    app.add_handler(CommandHandler("hatirlat", remind_command))

    # Callback & Metin yöneticileri
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot hazır ve mesajları dinliyor! Telegram'dan botunuzu başlatabilirsiniz.")
    app.run_polling()


if __name__ == "__main__":
    main()
