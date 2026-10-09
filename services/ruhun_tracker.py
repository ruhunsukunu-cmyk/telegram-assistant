"""Collection, cached weekly reports and durable delivery state."""
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from services.ruhun_youtube import YouTube, METRICS, YouTubeError
from services.ruhun_reporting import (PACIFIC, LOCAL, duration_seconds, first_window, periods,
                                      normalized_metrics, build_report)
from services.ruhun_ai import evaluate, context_for, fingerprint

def utcnow():
    return datetime.now(timezone.utc)

class Tracker:
    def __init__(self, config, store, youtube=None):
        self.config, self.store = config, store
        self.youtube = youtube or YouTube(config)

    async def collection(self, now=None):
        now = now or utcnow()
        if not self.config.youtube_ready:
            return 'unconfigured'
        if not self.store.claim('collection'):
            return 'busy'
        try:
            async with asyncio.timeout(900):
                channel = await self.youtube.verify()
                self.store.put('meta', 'channel', {'id': channel['id'], 'title': channel['snippet']['title'], 'verified_at': now.isoformat()})
                videos = await self.youtube.list_videos(channel, now)
                ids = {v['id'] for v in videos}
                for old in self.store.all('videos').values():
                    if old['id'] not in ids:
                        old['active'] = False
                        self.store.put('videos', old['id'], old)
                for video in videos:
                    await self.collect_video(video, now)
                self.store.put('meta', 'collection', {'status': 'available', 'last_success': now.isoformat(), 'video_count': len(videos)})
                return 'available'
        except (YouTubeError, ValueError, TimeoutError, httpx.HTTPError):
            old = self.store.get('meta', 'collection', {})
            self.store.put('meta', 'collection', {**old, 'status': 'failed', 'last_failure': now.isoformat()})
            return 'failed'
        finally:
            self.store.release('collection')

    async def collect_video(self, video, now):
        published = datetime.fromisoformat(video['published_at']).astimezone(PACIFIC).date()
        today = now.astimezone(PACIFIC).date()
        old = self.store.get('videos', video['id'])
        video['duration_seconds'] = duration_seconds(video['duration_iso'])
        video['active'] = True
        video['content_type'] = await self.youtube.content_type(video['id'], published, today)
        self.store.put('videos', video['id'], video)
        if video['content_type'] != 'SHORTS':
            return
        start = max(published, today - timedelta(days=27)) if old and self.store.get('meta', 'backfill:' + video['id']) else published
        daily = await self.youtube.query(video['id'], start, today, dimensions='day')
        for row in daily:
            self.store.put('daily', video['id'] + ':' + row['day'], {'video_id': video['id'], 'day': row['day'],
                           'metrics': normalized_metrics(row), 'collected_at': now.isoformat()})
        self.store.put('meta', 'backfill:' + video['id'], {'at': now.isoformat()})
        windows = list(periods(now))
        first = first_window(video['published_at'])
        if first[1] <= periods(now)[0][1]:
            windows.append(first)
        for start, end in set(windows):
            if published > end:
                continue
            key = f"{video['id']}:{start}:{end}"
            rows = await self.youtube.query(video['id'], start, end)
            # Missing rows never overwrite the last successful nonzero/zero values.
            if rows:
                self.store.put('summaries', key, {'status': 'available', 'metrics': normalized_metrics(rows[0]),
                               'start': str(start), 'end': str(end), 'collected_at': now.isoformat(),
                               'source': 'YouTube Analytics aggregate; recent data may be delayed'})
            elif not self.store.get('summaries', key):
                self.store.put('summaries', key, {'status': 'missing', 'metrics': None, 'start': str(start), 'end': str(end)})

    def latest_report(self, now=None):
        return build_report(self.store, now or utcnow())

    async def weekly(self, now=None, retry=False):
        now = now or utcnow()
        local = now.astimezone(LOCAL)
        week = f'{local.isocalendar().year}-W{local.isocalendar().week:02d}'
        if not self.store.claim('weekly'):
            return None
        try:
            record = self.store.get('reports', week)
            if retry and not record:
                return None
            if record and (not retry or record['ai_status'] != 'failed' or record['attempts'] >= 2):
                return record
            if record and retry and (now.date() - datetime.fromisoformat(record['created_at']).date()).days != 1:
                return record
            report = record['report'] if record else self.latest_report(now)
            cached = self.store.get('ai', fingerprint(context_for(report)))
            if cached:
                result, status = cached, 'available'
            else:
                result, status = await evaluate(self.config, report)
            record = {'week': week, 'created_at': record['created_at'] if record else now.isoformat(),
                      'report': report, 'ai': result, 'ai_status': status,
                      'attempts': (record['attempts'] if record else 0) + 1}
            if result:
                self.store.put('ai', fingerprint(context_for(report)), result)
            self.store.put('reports', week, record)
            self.store.put('meta', 'latest_week', week)
            return record
        finally:
            self.store.release('weekly')

    def cached_ai(self, report):
        return self.store.get('ai', fingerprint(context_for(report)))

    async def deliver_once(self, record, send):
        key = 'weekly:' + record['week']
        if not self.store.claim('delivery'):
            return 'busy'
        try:
            if self.store.get('deliveries', key):
                return 'already_attempted'
            signature = fingerprint(context_for(record['report']))
            if self.store.get('meta', 'last_delivery_signature') == signature:
                self.store.put('deliveries', key, {'state': 'unchanged'})
                return 'unchanged'
            # Record before the call: a timeout or crash must never cause an automatic duplicate.
            self.store.put('deliveries', key, {'state': 'sending', 'at': utcnow().isoformat()})
            try:
                message_id = await send(record)
            except Exception:
                self.store.put('deliveries', key, {'state': 'unknown', 'at': utcnow().isoformat()})
                return 'unknown'
            self.store.put('deliveries', key, {'state': 'sent', 'message_id': message_id})
            self.store.put('meta', 'last_delivery_signature', signature)
            return 'sent'
        finally:
            self.store.release('delivery')
