"""Single-owner Ruhun Sükûnu bot. No personal-assistant handlers or legacy jobs."""
import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, time as walltime
from io import BytesIO
from dotenv import load_dotenv
from telegram import (BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats,
                      BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, InputFile)
from telegram.ext import (ApplicationBuilder, ApplicationHandlerStop, CallbackQueryHandler,
                          CommandHandler, MessageHandler, TypeHandler, filters)
from telegram import Update
from services.ruhun_config import Config, CHANNEL_ID
from services.ruhun_store import Store
from services.ruhun_tracker import Tracker, utcnow
from services.ruhun_reporting import LOCAL, markdown, validate_bundle

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
log = logging.getLogger('ruhun')
HELP = ('Ruhun Sükûnu · Shorts takipçisi\n\n'
        '/ruhun — Bağlantı ve veri durumu\n/ruhun_rapor — Sonuçları göster\n'
        '/ruhun_disaaktar — Sohbete aktarılabilir Markdown/JSON\n'
        '/ruhun_aktar — Üretim ve deney JSON dosyası yükle\n\n'
        'Veriler her gün 10.00’da sessizce toplanır. Haftalık rapor pazartesi 11.00’de gelir. '
        'Saatler Türkiye saatidir. AI önerileri uygulanmamış taslaktır.')

def authorized(update, config):
    return bool(config.owner_id and config.chat_id and update.effective_user and update.effective_chat
                and update.effective_user.id == config.owner_id
                and update.effective_chat.id == config.chat_id and update.effective_chat.type == 'private')

def keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton('Durum', callback_data='ruhun:status'),
                                  InlineKeyboardButton('Rapor', callback_data='ruhun:report')],
                                 [InlineKeyboardButton('Dışa aktar', callback_data='ruhun:export')]])

def parts(context):
    return context.application.bot_data['config'], context.application.bot_data['tracker']

async def guard(update, context):
    config, _ = parts(context)
    if not authorized(update, config):
        if update.callback_query:
            await update.callback_query.answer('Bu bot özel kullanım içindir.')
        raise ApplicationHandlerStop

async def start(update, context):
    await update.effective_message.reply_text(HELP, reply_markup=keyboard())

async def status(update, context):
    config, tracker = parts(context)
    last = tracker.store.get('meta', 'collection', {})
    channel = tracker.store.get('meta', 'channel')
    ai = 'Free Tier doğrulandı; haftalık değerlendirme açık.' if config.ai_ready else 'Kapalı; ücretsiz proje/anahtar doğrulaması bekliyor.'
    text = (f'Ruhun Sükûnu\nKanal: {CHANNEL_ID}\n'
            f"Kanal doğrulaması: {channel['verified_at'] if channel else 'bekliyor'}\n"
            f"Son başarılı toplama: {last.get('last_success', 'henüz yok')}\n"
            f"Toplama durumu: {last.get('status', 'bekliyor')}\n"
            f"Zamanlayıcı: {'açık' if config.jobs_enabled else 'kapalı'}\nGemini: {ai}")
    await update.effective_message.reply_text(text, reply_markup=keyboard())

async def send_report(message, tracker):
    report = await asyncio.to_thread(tracker.latest_report)
    ai = tracker.cached_ai(report)
    text = markdown(report, ai)
    await message.reply_document(document=InputFile(text.encode('utf-8'), filename='Ruhun-Sukunu-Rapor.md'),
                                 caption='Sayısal rapor; varsa AI bölümü uygulanmamış öneridir.')
    if not ai:
        week = tracker.store.get('meta', 'latest_week')
        record = tracker.store.get('reports', week) if week else None
        if record and record['ai']:
            previous = markdown(record['report'], record['ai'])
            await message.reply_document(InputFile(previous.encode('utf-8'), filename='Ruhun-Sukunu-Son-Haftalik.md'),
                                         caption='Son haftalık AI değerlendirmesi; kendi rapor dönemine aittir.')

async def report_command(update, context):
    _, tracker = parts(context)
    await send_report(update.effective_message, tracker)

async def export_command(update, context):
    _, tracker = parts(context)
    report = await asyncio.to_thread(tracker.latest_report)
    report['ai'] = tracker.cached_ai(report)
    await update.effective_message.reply_document(InputFile(markdown(report, report['ai']).encode('utf-8'), filename='Ruhun-Sukunu-Rapor.md'))
    await update.effective_message.reply_document(InputFile(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'), filename='Ruhun-Sukunu-Veriler.json'))

async def import_command(update, context):
    context.user_data['import_until'] = time.time() + 300
    await update.effective_message.reply_text('Beş dakika içinde schema_version=1 ve doğru channel_id içeren üretim/deney JSON dosyasını gönder. Bilinmeyen video kimlikleri önce kanaldan doğrulanmalıdır.')

async def import_document(update, context):
    _, tracker = parts(context)
    if context.user_data.pop('import_until', 0) < time.time():
        await update.effective_message.reply_text('Önce /ruhun_aktar yaz.')
        return
    doc = update.effective_message.document
    if not doc.file_name or not doc.file_name.lower().endswith('.json') or not doc.file_size or doc.file_size > 256000:
        await update.effective_message.reply_text('En fazla 256 KB bir JSON dosyası gerekiyor.')
        return
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    try:
        payload = json.loads(data.decode('utf-8-sig'))
        videos, experiments = validate_bundle(payload, set(tracker.store.all('videos')))
        await asyncio.to_thread(tracker.store.import_bundle, videos, experiments)
    except (ValueError, TypeError, KeyError, UnicodeError):
        await update.effective_message.reply_text('Dosya şeması, kanal/video kimliği veya alanları geçersiz. Hiçbir kayıt aktarılmadı.')
        return
    await update.effective_message.reply_text(f'{len(videos)} üretim notu ve {len(experiments)} deney kaydı aktarıldı. Kaynak bağlantıları doğrulama yapılmış sayılmaz.')

async def callbacks(update, context):
    q = update.callback_query
    await q.answer()
    action = {'ruhun:status': status, 'ruhun:report': report_command, 'ruhun:export': export_command}.get(q.data)
    if action:
        await action(update, context)
    else:
        await q.message.reply_text('Bu eski düğme artık kullanılmıyor. /menu ile Ruhun Sükûnu ekranını aç.')

async def help_message(update, context):
    await update.effective_message.reply_text('Bu bot yalnız Ruhun Sükûnu için çalışıyor. /menu ile rapor ve durum ekranını aç.')

async def notify_once(app, key, text):
    config, tracker = app.bot_data['config'], app.bot_data['tracker']
    if tracker.store.get('alerts', key):
        return
    tracker.store.put('alerts', key, {'state': 'attempted'})
    try:
        await app.bot.send_message(config.chat_id, text)
    except Exception:
        log.warning('Durum bildiriminin teslimi doğrulanamadı.')

async def collection_job(context):
    tracker = context.application.bot_data['tracker']
    result = await tracker.collection()
    if result == 'failed':
        await notify_once(context.application, 'collection-failed', 'YouTube veri toplama başarısız. /ruhun ile durumu kontrol et; son başarılı veriler korunuyor.')
    elif result == 'available':
        tracker.store.put('alerts', 'collection-failed', None)

async def weekly_job(context):
    app = context.application
    tracker, config = app.bot_data['tracker'], app.bot_data['config']
    # Reuse daily collected data; do not make another collection or model call on view.
    record = await tracker.weekly()
    if not record or not record['report']['eligible_videos']:
        return
    async def send(value):
        body = markdown(value['report'], value['ai'])
        message = await app.bot.send_document(config.chat_id, InputFile(body.encode('utf-8'), filename='Ruhun-Sukunu-Haftalik.md'),
                                              caption='Ruhun Sükûnu haftalık raporu · AI önerileri taslaktır.')
        return message.message_id
    state = await tracker.deliver_once(record, send)
    if state == 'unknown':
        log.warning('Haftalık rapor teslimi belirsiz; otomatik tekrar yapılmayacak.')

async def ai_retry_job(context):
    # Tracker permits exactly one retry on the day after the original failed report.
    await context.application.bot_data['tracker'].weekly(retry=True)

def schedule(app):
    config = app.bot_data['config']
    if not config.jobs_enabled or not config.owner_id or not config.chat_id or not config.youtube_ready:
        return
    options = {'job_kwargs': {'max_instances': 1, 'coalesce': True, 'misfire_grace_time': 1800}}
    app.job_queue.run_daily(collection_job, walltime(10, tzinfo=LOCAL), name='ruhun-collection', **options)
    # python-telegram-bot 21 days: Sunday=0, Monday=1.
    app.job_queue.run_daily(weekly_job, walltime(11, tzinfo=LOCAL), days=(1,), name='ruhun-weekly', **options)
    # Also covers an initial setup report created on a day other than Monday.
    # Tracker makes no model call except one retry on the next day.
    app.job_queue.run_daily(ai_retry_job, walltime(11, 15, tzinfo=LOCAL), name='ruhun-ai-retry', **options)

async def initialize(app):
    config = app.bot_data['config']
    commands = [BotCommand(c, d) for c, d in [('menu', 'Ruhun Sükûnu ana ekranı'), ('ruhun', 'Kanal ve bağlantı durumu'),
                ('ruhun_rapor', 'Shorts sonuçları'), ('ruhun_disaaktar', 'Raporu indir'), ('ruhun_aktar', 'Üretim ve deney kaydı ekle'), ('help', 'Kısa yardım')]]
    for scope in (BotCommandScopeDefault(), BotCommandScopeAllPrivateChats()):
        await app.bot.delete_my_commands(scope=scope)
        await app.bot.set_my_commands(commands, scope=scope)
    if config.chat_id:
        await app.bot.delete_my_commands(scope=BotCommandScopeChat(config.chat_id))
    await app.bot.set_my_description('Ruhun Sükûnu Shorts sonuçlarını takip eder. Haftalık rapor ve deney taslakları sunar.')
    await app.bot.set_my_short_description('Ruhun Sükûnu · Shorts takipçisi')
    schedule(app)

async def on_error(update, context):
    # Avoid exception repr: network errors can contain credential-bearing URLs.
    log.error('Bot işlem hatası: %s', type(context.error).__name__)

def build_application(config, store=None):
    store = store or Store()
    store.init()
    app = ApplicationBuilder().token(config.token).post_init(initialize).build()
    app.bot_data.update(config=config, tracker=Tracker(config, store))
    app.add_handler(TypeHandler(Update, guard), group=-1)
    for command in ('start', 'menu', 'help'):
        app.add_handler(CommandHandler(command, start))
    for command, fn in [('ruhun', status), ('ruhun_rapor', report_command), ('ruhun_disaaktar', export_command), ('ruhun_aktar', import_command)]:
        app.add_handler(CommandHandler(command, fn))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.Document.ALL, import_document))
    app.add_handler(MessageHandler(filters.TEXT, help_message))
    app.add_error_handler(on_error)
    return app

def main():
    if os.getenv('RUHUN_MAINTENANCE', '').lower() in ('1', 'true', 'yes'):
        from tools.maintenance_server import main as maintenance
        maintenance()
        return
    config = Config.from_env()
    if not config.token:
        raise SystemExit('TELEGRAM_BOT_TOKEN gerekli.')
    app = build_application(config)
    url = os.getenv('WEBHOOK_URL', '').strip()
    if url:
        secret = hashlib.sha256(config.token.encode()).hexdigest()
        path = 'ruhun-' + secret[:24]
        app.run_webhook(listen='0.0.0.0', port=int(os.getenv('PORT', '8080')), url_path=path,
                        webhook_url=url.rstrip('/') + '/' + path, secret_token=secret,
                        drop_pending_updates=config.drop_pending)
    else:
        app.run_polling(drop_pending_updates=config.drop_pending)

if __name__ == '__main__':
    main()
