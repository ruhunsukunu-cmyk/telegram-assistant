import asyncio
import copy
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx

from services.ruhun_config import Config, CHANNEL_ID
from services.ruhun_store import Store
from services.ruhun_reporting import (first_window, periods, duration_group, normalized_metrics,
                                     subscriber_rate, validate_bundle, build_report, markdown)
from services.ruhun_youtube import YouTube, YouTubeError, METRICS, SCOPES, rows_to_dicts
from services.ruhun_ai import evaluate, validate_result, fingerprint, context_for
from services.gemini import generate_text, GeminiError
from services.ruhun_tracker import Tracker
from tools.reset_legacy import inventory, reset
from ruhun_bot import authorized, build_application, schedule, initialize, help_message, callbacks
from ruhun_bot import main as bot_main

NOW = datetime(2026, 10, 12, 8, tzinfo=timezone.utc)
CONFIG = Config(token='123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi', owner_id=7, chat_id=7,
                youtube_client_id='id', youtube_client_secret='secret', youtube_refresh_token='refresh')
MEASURES = dict(zip(METRICS, [100, 50, 20, 24, 80, 5, 2, 1, 3]))

class TestArea:
    def __init__(self):
        root = Path(__file__).resolve().parents[1] / 'work' / 'tests'
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / uuid.uuid4().hex
        self.path.mkdir()
        self.name = str(self.path)
    def cleanup(self):
        for name in ('test.db', 'test.db-wal', 'test.db-shm', 'test.db-journal'):
            (self.path / name).unlink(missing_ok=True)
        self.path.rmdir()

def fixture(store, count=5):
    for i in range(count):
        vid = f'video{i:06d}'
        video = {'id': vid, 'title': f'Kıssa {i}', 'published_at': '2026-09-28T08:00:00+00:00',
                 'duration_seconds': 30, 'content_type': 'SHORTS', 'active': True}
        store.put('videos', vid, video)
        ranges = [first_window(video['published_at']), *periods(NOW)]
        for start, end in ranges:
            store.put('summaries', f'{vid}:{start}:{end}', {'status': 'available', 'metrics': MEASURES})
    return build_report(store, NOW)

class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = TestArea()
        self.path = str(Path(self.temp.name) / 'test.db')
        self.store = Store(self.path, url=''); self.store.init()
    def tearDown(self):
        self.temp.cleanup()
    def test_maintenance_never_builds_bot_or_database(self):
        with patch.dict('os.environ', {'RUHUN_MAINTENANCE': 'true'}), \
             patch('tools.maintenance_server.main') as quiet, \
             patch('ruhun_bot.build_application') as build:
            bot_main()
            quiet.assert_called_once()
            build.assert_not_called()
    def test_upsert_restart(self):
        self.store.put('daily', 'v:d', {'views': 1}); self.store.put('daily', 'v:d', {'views': 2})
        second = Store(self.path, url=''); second.init()
        self.assertEqual(second.all('daily'), {'v:d': {'views': 2}})
    def test_lock_expiry_and_exclusion(self):
        self.assertTrue(self.store.claim('run', 10, now=100))
        self.assertFalse(Store(self.path, url='').claim('run', 10, now=105))
        self.assertTrue(self.store.claim('run', 10, now=110))
    def test_first_window_pacific_and_dst(self):
        a, b = first_window('2026-11-01T06:30:00Z')
        self.assertEqual(str(a), '2026-11-01'); self.assertEqual(str(b), '2026-11-07')
    def test_period_cutoff(self):
        current, prev = periods(NOW)
        self.assertEqual((str(current[0]), str(current[1])), ('2026-10-03', '2026-10-09'))
        self.assertEqual((str(prev[0]), str(prev[1])), ('2026-09-26', '2026-10-02'))
    def test_zero_missing_and_denominator(self):
        self.assertEqual(normalized_metrics({'views': 0})['views'], 0)
        self.assertIsNone(normalized_metrics({})['views'])
        self.assertIsNone(subscriber_rate({'engagedViews': 0, 'subscribersGained': 3}))
        self.assertEqual(subscriber_rate(MEASURES), 60)
        with self.assertRaises(ValueError): normalized_metrics({'views': float('nan')})
        self.assertEqual(normalized_metrics({'likes': -1})['likes'], -1)
        with self.assertRaises(ValueError): normalized_metrics({'views': -1})
    def test_small_sample_and_other_format(self):
        report = fixture(self.store, 4)
        self.store.put('videos', 'long', {'id': 'long', 'content_type': 'OTHER'})
        text = markdown(build_report(self.store, NOW))
        self.assertIn('Küçük örneklem', text); self.assertEqual(len(report['eligible_videos']), 4)
        self.assertEqual(duration_group(30), '0–30 sn'); self.assertEqual(duration_group(60), '31–60 sn')
    def test_missing_period_suppresses_percent(self):
        fixture(self.store, 1)
        start, end = periods(NOW)[0]
        self.store.put('summaries', f'video000000:{start}:{end}', {'status': 'missing'})
        report = build_report(self.store, NOW)
        self.assertFalse(report['periods'][0]['complete'])
        self.assertIn('yüzde karşılaştırması yapılmadı', markdown(report))
    def test_endpoint_average_used(self):
        report = fixture(self.store, 1)
        self.store.put('daily', 'v:date', {'metrics': {'averageViewPercentage': 10}})
        self.assertEqual(report['eligible_videos'][0]['metrics']['averageViewPercentage'], 80)
    def test_import_validation_and_atomic_write(self):
        data = {'schema_version': 1, 'channel_id': CHANNEL_ID, 'videos': [{'video_id': 'v', 'hook': 'Bir karar.'}], 'experiments': []}
        videos, experiments = validate_bundle(data, {'v'})
        self.store.import_bundle(videos, experiments)
        self.assertEqual(self.store.get('production', 'v')['hook'], 'Bir karar.')
        for bad in ({**data, 'channel_id': 'other'}, {**data, 'secret': 'key'}, {**data, 'videos': [{'video_id': 'unknown'}]}):
            with self.assertRaises(ValueError): validate_bundle(bad, {'v'})
    def test_reset_only_known_legacy_and_no_restore(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE notes(user_id INT,content TEXT)')
            conn.execute('CREATE TABLE reminders(user_id INT,chat_id INT,message TEXT,due_at TEXT)')
            conn.execute('CREATE TABLE app_metadata(key TEXT,value TEXT)')
            conn.execute('CREATE TABLE another_app(id INT)')
            conn.execute("INSERT INTO notes VALUES(7,'sensitive test fixture')")
            conn.commit()
            before = inventory(conn)
            self.assertEqual(before['row_counts']['notes'], 1)
            cleaned = reset(conn, apply=True)
            self.assertEqual(cleaned['remaining_legacy_tables'], [])
            self.assertIn('another_app', cleaned['preserved_tables'])
        self.store.init(); self.store.init()
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertNotIn('notes', {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")})
    def test_reset_rejects_similar_foreign_schema(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE notes(id INT,foreign_data TEXT)')
            with self.assertRaises(ValueError): reset(conn, apply=True)

class AsyncCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TestArea()
        self.store = Store(str(Path(self.temp.name) / 'test.db'), url=''); self.store.init()
    async def asyncTearDown(self):
        self.temp.cleanup()
    async def test_unverified_ai_never_called(self):
        report = fixture(self.store)
        with patch('services.ruhun_ai.generate_text', new_callable=AsyncMock) as call:
            result, status = await evaluate(replace(CONFIG, gemini_key='paid-or-unknown'), report)
            call.assert_not_called(); self.assertEqual(status, 'disabled_unverified')
    async def test_truncated_or_blocked_ai_never_published(self):
        for reason in ('MAX_TOKENS', 'SAFETY', None):
            transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
                'candidates': [{'finishReason': reason, 'content': {'parts': [{'text': '{}'}]}}]}))
            with self.assertRaises(GeminiError):
                await generate_text('fixture', '{}', 'fixture', transport=transport)
    async def test_ai_schema_and_reference_rejection(self):
        good = {'observations': [{'text': 'Açılış yönünü sınamak yararlı olabilir.', 'video_ids': ['v']}],
                'uncertainties': ['Konu ve dağıtım etkisini ayıramıyoruz.'], 'experiment': None}
        self.assertEqual(validate_result(good, {'v'}), good)
        bad = copy.deepcopy(good); bad['observations'][0]['video_ids'] = ['foreign']
        with self.assertRaises(ValueError): validate_result(bad, {'v'})
        bad = copy.deepcopy(good); bad['observations'][0]['text'] = 'Yüzde 99 başarı.'
        with self.assertRaises(ValueError): validate_result(bad, {'v'})
    async def test_ai_failure_fallback_and_only_one_retry(self):
        fixture(self.store)
        tracker = Tracker(CONFIG, self.store)
        with patch('services.ruhun_tracker.evaluate', new_callable=AsyncMock, return_value=(None, 'failed')) as call:
            first = await tracker.weekly(NOW)
            again = await tracker.weekly(NOW)
            self.assertEqual(first, again); self.assertEqual(call.await_count, 1)
            await tracker.weekly(NOW.replace(day=13), retry=True)
            await tracker.weekly(NOW.replace(day=13), retry=True)
            self.assertEqual(call.await_count, 2)
    async def test_report_view_no_model_call(self):
        fixture(self.store)
        tracker = Tracker(CONFIG, self.store)
        with patch('services.ruhun_tracker.evaluate', new_callable=AsyncMock) as call:
            report = tracker.latest_report(NOW); tracker.cached_ai(report); markdown(report)
            call.assert_not_called()
    async def test_uncertain_delivery_not_retried_after_restart(self):
        report = fixture(self.store)
        record = {'week': '2026-W42', 'report': report}
        send = AsyncMock(side_effect=TimeoutError)
        self.assertEqual(await Tracker(CONFIG, self.store).deliver_once(record, send), 'unknown')
        self.assertEqual(await Tracker(CONFIG, self.store).deliver_once(record, send), 'already_attempted')
        self.assertEqual(send.await_count, 1)
    async def test_owner_only_private_chat(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=7), effective_chat=SimpleNamespace(id=7, type='private'))
        self.assertTrue(authorized(update, CONFIG))
        update.effective_chat.type = 'group'; self.assertFalse(authorized(update, CONFIG))
        update.effective_chat.type = 'private'; update.effective_user.id = 8
        self.assertFalse(authorized(update, CONFIG))
        self.assertFalse(authorized(update, replace(CONFIG, owner_id=0)))
    async def test_jobs_only_new_and_monday(self):
        app = build_application(replace(CONFIG, jobs_enabled=True), self.store)
        schedule(app)
        names = {j.name for j in app.job_queue.jobs()}
        self.assertEqual(names, {'ruhun-collection', 'ruhun-weekly', 'ruhun-ai-retry'})
        weekly = app.job_queue.get_jobs_by_name('ruhun-weekly')[0]
        self.assertIn('mon', str(weekly.job.trigger))
        app.job_queue.scheduler.remove_all_jobs()
    async def test_unconfigured_owner_has_no_jobs(self):
        app = build_application(replace(CONFIG, owner_id=0, jobs_enabled=True), self.store)
        schedule(app); self.assertEqual(app.job_queue.jobs(), ())
    async def test_legacy_command_and_button_never_model_call(self):
        update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=AsyncMock()),
                                 callback_query=SimpleNamespace(answer=AsyncMock(), data='voc:start', message=SimpleNamespace(reply_text=AsyncMock())))
        with patch('services.gemini.generate_text', new_callable=AsyncMock) as call:
            await help_message(update, None); await callbacks(update, None); call.assert_not_called()
            update.callback_query.message.reply_text.assert_awaited_once()
    async def test_youtube_wrong_channel_rejected(self):
        def handler(request):
            if request.url.host == 'oauth2.googleapis.com':
                return httpx.Response(200, json={'access_token': 'access', 'scope': ' '.join(SCOPES)})
            return httpx.Response(200, json={'items': [{'id': 'wrong'}]})
        with self.assertRaises(YouTubeError): await YouTube(CONFIG, httpx.MockTransport(handler)).verify()
    async def test_broad_oauth_rejected(self):
        def handler(request):
            return httpx.Response(200, json={'access_token': 'access', 'scope': ' '.join(SCOPES) + ' https://www.googleapis.com/auth/youtube'})
        with self.assertRaises(YouTubeError): await YouTube(CONFIG, httpx.MockTransport(handler)).verify()
    async def test_live_content_type_values_and_ambiguity(self):
        youtube = YouTube(CONFIG)
        for values, expected in [(['shorts'], 'SHORTS'), (['SHORTS'], 'SHORTS'),
                                 (['videoOnDemand'], 'OTHER'), (['VIDEO_ON_DEMAND'], 'OTHER'),
                                 (['UNSPECIFIED'], 'UNKNOWN'), (['shorts', 'videoOnDemand'], 'UNKNOWN'),
                                 ([], 'UNKNOWN')]:
            youtube.query = AsyncMock(return_value=[{'creatorContentType': value} for value in values])
            self.assertEqual(await youtube.content_type('v', '2026-09-01', '2026-10-01'), expected)
    async def test_collection_failure_preserves_previous(self):
        self.store.put('meta', 'collection', {'last_success': 'earlier'})
        youtube = SimpleNamespace(verify=AsyncMock(side_effect=YouTubeError('invalid')))
        result = await Tracker(CONFIG, self.store, youtube).collection(NOW)
        self.assertEqual(result, 'failed'); self.assertEqual(self.store.get('meta', 'collection')['last_success'], 'earlier')
    async def test_collection_missing_does_not_erase_snapshot(self):
        video = {'id': 'v', 'title': 'Kıssa', 'published_at': '2026-09-28T08:00:00+00:00', 'duration_iso': 'PT30S'}
        first = first_window(video['published_at'])
        key = f'v:{first[0]}:{first[1]}'
        self.store.put('summaries', key, {'status': 'available', 'metrics': MEASURES})
        youtube = SimpleNamespace(content_type=AsyncMock(return_value='SHORTS'), query=AsyncMock(return_value=[]))
        await Tracker(CONFIG, self.store, youtube).collect_video(video, NOW)
        self.assertEqual(self.store.get('summaries', key)['metrics'], MEASURES)
    async def test_headers_not_positional_assumptions(self):
        value = rows_to_dicts({'columnHeaders': [{'name': 'likes'}, {'name': 'views'}], 'rows': [[1, 0]]})
        self.assertEqual(value, [{'likes': 1, 'views': 0}])

if __name__ == '__main__': unittest.main()
