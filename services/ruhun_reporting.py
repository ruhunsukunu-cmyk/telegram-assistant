"""Deterministic calculations, portable exports and strict production imports."""
import json
import math
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from services.ruhun_config import CHANNEL_ID
from services.ruhun_youtube import METRICS

PACIFIC = ZoneInfo('America/Los_Angeles')
LOCAL = ZoneInfo('Europe/Istanbul')
COUNT_METRICS = ('views', 'engagedViews', 'likes', 'comments', 'shares', 'subscribersGained', 'estimatedMinutesWatched')

def duration_seconds(value):
    match = re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', value)
    if not match or not any(match.groups()):
        raise ValueError('Geçersiz video süresi.')
    return sum(float(n or 0) * scale for n, scale in zip(match.groups(), (3600, 60, 1)))

def duration_group(seconds):
    return '0–30 sn' if seconds <= 30 else ('31–60 sn' if seconds <= 60 else '>60 sn')

def first_window(published_at):
    day = datetime.fromisoformat(published_at.replace('Z', '+00:00')).astimezone(PACIFIC).date()
    return day + timedelta(days=1), day + timedelta(days=7)

def periods(now):
    end = now.astimezone(PACIFIC).date() - timedelta(days=3)
    return [(end - timedelta(days=6), end), (end - timedelta(days=13), end - timedelta(days=7))]

def normalized_metrics(row):
    result = {}
    for name in METRICS:
        value = row.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value < 0):
            raise ValueError('Analiz ölçümü geçersiz.')
        result[name] = value
    return result

def subscriber_rate(metrics):
    views, subs = metrics.get('engagedViews'), metrics.get('subscribersGained')
    return 1000 * subs / views if views and subs is not None else None

def validate_bundle(data, known_ids):
    if not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('channel_id') != CHANNEL_ID:
        raise ValueError('Şema sürümü veya kanal kimliği uyuşmuyor.')
    if set(data) - {'schema_version', 'channel_id', 'videos', 'experiments'}:
        raise ValueError('İçe aktarımda bilinmeyen alan var.')
    videos, experiments = data.get('videos', []), data.get('experiments', [])
    if not isinstance(videos, list) or not isinstance(experiments, list) or len(videos) > 100 or len(experiments) > 100:
        raise ValueError('İçe aktarım listeleri geçersiz.')
    seen_videos, seen_experiments = set(), set()
    for item in videos:
        allowed = {'video_id', 'topic', 'hook', 'narration', 'visual_style', 'source_urls'}
        if not isinstance(item, dict) or set(item) - allowed or item.get('video_id') not in known_ids:
            raise ValueError('Video kaydı geçersiz veya kanalda henüz doğrulanmamış.')
        if item['video_id'] in seen_videos:
            raise ValueError('Tekrarlanan video kaydı.')
        seen_videos.add(item['video_id'])
        for field in allowed - {'video_id', 'source_urls'}:
            if field in item and (not isinstance(item[field], str) or len(item[field]) > 2000):
                raise ValueError('Üretim notu geçersiz.')
        urls = item.get('source_urls', [])
        if not isinstance(urls, list) or len(urls) > 20 or any(not isinstance(u, str) or not u.startswith('https://') or len(u) > 2000 for u in urls):
            raise ValueError('Kaynak bağlantıları geçersiz.')
    for item in experiments:
        allowed = {'id', 'hypothesis', 'variable', 'video_ids', 'metric', 'window_days', 'status'}
        if not isinstance(item, dict) or set(item) != allowed:
            raise ValueError('Deney alanları eksik veya geçersiz.')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', str(item['id'])) or item['id'] in seen_experiments:
            raise ValueError('Deney kimliği geçersiz veya tekrarlı.')
        seen_experiments.add(item['id'])
        for field in ('hypothesis', 'variable'):
            if not isinstance(item[field], str) or not 1 <= len(item[field]) <= 2000:
                raise ValueError('Deney açıklaması geçersiz.')
        if not isinstance(item['video_ids'], list) or not item['video_ids'] or any(v not in known_ids for v in item['video_ids']):
            raise ValueError('Deney video kimlikleri doğrulanmamış.')
        if item['metric'] not in METRICS or item['window_days'] != 7 or item['status'] not in ('draft', 'active', 'closed'):
            raise ValueError('Deney ölçümü/penceresi/durumu geçersiz.')
    # Also rejects NaN supplied by Python's permissive JSON parser.
    json.dumps(data, allow_nan=False)
    return videos, experiments

def build_report(store, now):
    ps = periods(now)
    videos = store.all('videos')
    production = store.all('production')
    snapshots, groups = [], {}
    for video in videos.values():
        if video.get('content_type') != 'SHORTS' or not video.get('active', True):
            continue
        start, end = first_window(video['published_at'])
        period = store.get('summaries', f"{video['id']}:{start}:{end}")
        if not period or period['status'] != 'available' or end > ps[0][1]:
            continue
        item = dict(video_id=video['id'], title=video['title'], duration_group=duration_group(video['duration_seconds']),
                    start=str(start), end=str(end), metrics=period['metrics'], production=production.get(video['id'], {}))
        item['subscribers_per_1000_engaged_views'] = subscriber_rate(item['metrics'])
        snapshots.append(item)
        groups.setdefault(item['duration_group'], []).append(item)
    for items in groups.values():
        if len(items) >= 5:
            items.sort(key=lambda item: (item['metrics'].get('averageViewPercentage') is not None,
                                        item['metrics'].get('averageViewPercentage') or 0), reverse=True)
    totals = []
    for start, end in ps:
        entries, missing = [], []
        for video in videos.values():
            if video.get('content_type') != 'SHORTS' or not video.get('active', True):
                continue
            published = datetime.fromisoformat(video['published_at']).astimezone(PACIFIC).date()
            if published > end:
                continue
            entry = store.get('summaries', f"{video['id']}:{start}:{end}")
            if entry and entry['status'] == 'available':
                entries.append(entry)
            else:
                missing.append(video['id'])
        sums = {name: (sum(e['metrics'][name] for e in entries)
                       if entries and all(e['metrics'].get(name) is not None for e in entries) else None)
                for name in COUNT_METRICS}
        totals.append({'start': str(start), 'end': str(end), 'metrics': sums,
                       'missing_video_ids': missing, 'available_videos': len(entries), 'complete': bool(entries) and not missing})
    return {'schema_version': 1, 'channel_id': CHANNEL_ID, 'generated_at': now.isoformat(),
            'scope': 'Son 90 günde yayımlanan, doğrulanmış Shorts; kanalın tüm tarihi değildir.',
            'analytics_timezone': 'America/Los_Angeles', 'periods': totals, 'duration_groups': groups,
            'eligible_videos': sorted(snapshots, key=lambda v: v['end'], reverse=True),
            'pending_video_ids': [v['id'] for v in videos.values() if v.get('content_type') == 'UNKNOWN' and v.get('active', True)],
            'production': production, 'experiments': store.all('experiments'),
            'last_collection': store.get('meta', 'collection'),
            'caveats': ['Eksik analiz sıfır değildir.', 'Günler Pasifik saatidir; ilk 168 saat değildir.',
                        'Son günler gecikmeli olabilir.', 'Kaynak bağlantısı dinî doğrulama değildir.',
                        'Feed gösterimi ve kaydırma oranı bu raporda yoktur.']}

def fmt(value, decimals=1):
    if value is None:
        return 'eksik'
    return str(int(value)) if isinstance(value, int) or float(value).is_integer() else f'{value:.{decimals}f}'

def markdown(report, ai=None):
    def safe(text):
        return str(text).replace('|', '/').replace('\n', ' ').replace('`', "'")
    lines = ['# Ruhun Sükûnu · Shorts raporu', '', report['scope'],
             f"Hazırlandı: {report['generated_at']}", 'Analiz günleri: Pasifik saati.', '', '## Dönemler', '']
    for period in report['periods']:
        m = period['metrics']
        lines.append(f"- {period['start']}–{period['end']}: izlenme {fmt(m['views'])}; etkileşimli izlenme {fmt(m['engagedViews'])}; kazanılan abone {fmt(m['subscribersGained'])}. Eksik video: {len(period['missing_video_ids'])}.")
    current, previous = report['periods']
    if current['complete'] and previous['complete']:
        lines.extend(['', 'Karşılaştırma:'])
        for name in ('views', 'engagedViews', 'subscribersGained'):
            a, b = current['metrics'][name], previous['metrics'][name]
            if a is not None and b is not None:
                change = f'{100 * (a - b) / b:+.1f}%' if b else 'önceki dönem sıfır; yüzde hesaplanmadı'
                lines.append(f'- {name}: {change}')
    else:
        lines.append('Eksik dönemler nedeniyle dönemler arası yüzde karşılaştırması yapılmadı.')
    for group, entries in report['duration_groups'].items():
        lines.extend(['', f'## {group} · örnek sayısı {len(entries)}',
                      'Sıralama: izlenme yüzdesi.' if len(entries) >= 5 else 'Küçük örneklem; sıralama yapılmadı.', '',
                      '| Video | İzlenme | Etkileşimli | Ort. sn | Ort. % | Abone / bin etkileşimli |', '|---|---:|---:|---:|---:|---:|'])
        for item in entries:
            m = item['metrics']
            lines.append(f"| {safe(item['title'])} ({item['video_id']}) | {fmt(m['views'])} | {fmt(m['engagedViews'])} | {fmt(m['averageViewDuration'])} | {fmt(m['averageViewPercentage'])} | {fmt(item['subscribers_per_1000_engaged_views'])} |")
    lines.extend(['', '## Sınırlar', ''] + ['- ' + x for x in report['caveats']])
    lines.append(f"- Sınıflandırma bekleyen video: {len(report['pending_video_ids'])}.")
    if ai:
        lines.extend(['', '## AI değerlendirmesi · uygulanmamış taslak', ''])
        for observation in ai['observations']:
            lines.append('- ' + safe(observation['text']) + ' · ' + ', '.join(observation['video_ids']))
        lines.extend(['', 'Belirsizlikler:'] + ['- ' + safe(t) for t in ai['uncertainties']])
        if ai['experiment']:
            e = ai['experiment']
            lines.extend(['', 'Deney taslağı:', '- Hipotez: ' + safe(e['hypothesis']), '- Tek değişiklik: ' + safe(e['variable']),
                          '- Ölçüm: ' + e['metric'], '- Gözlem: yayından sonraki yedi tam API günü.'])
    else:
        lines.extend(['', 'AI değerlendirmesi yok veya bekliyor; sayısal rapor kullanılabilir.'])
    return '\n'.join(lines) + '\n'
