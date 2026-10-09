"""Read-only YouTube REST client; no upload, edit or comment APIs."""
from datetime import datetime, timedelta
import httpx
from services.ruhun_config import CHANNEL_ID

METRICS = ('views', 'engagedViews', 'estimatedMinutesWatched', 'averageViewDuration',
           'averageViewPercentage', 'likes', 'comments', 'shares', 'subscribersGained')
SCOPES = ('https://www.googleapis.com/auth/youtube.readonly',
          'https://www.googleapis.com/auth/yt-analytics.readonly')

class YouTubeError(RuntimeError):
    pass

def rows_to_dicts(response):
    headers = [item['name'] for item in response.get('columnHeaders', [])]
    rows = response.get('rows', [])
    if rows and (not headers or any(len(row) != len(headers) for row in rows)):
        raise YouTubeError('Analiz yanıtının sütunları tutarsız.')
    return [dict(zip(headers, row)) for row in rows]

class YouTube:
    def __init__(self, config, transport=None):
        self.config, self.transport = config, transport
        self.access_token = None

    async def request(self, url, params):
        async with httpx.AsyncClient(timeout=40, transport=self.transport) as client:
            response = await client.get(url, params=params, headers={'Authorization': f'Bearer {self.access_token}'})
        if response.status_code != 200:
            raise YouTubeError(f'YouTube isteği başarısız (HTTP {response.status_code}); bağlantı/kota kontrolü gerekiyor.')
        return response.json()

    async def verify(self):
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.post('https://oauth2.googleapis.com/token', data={
                'client_id': self.config.youtube_client_id, 'client_secret': self.config.youtube_client_secret,
                'refresh_token': self.config.youtube_refresh_token, 'grant_type': 'refresh_token'})
        if response.status_code != 200:
            raise YouTubeError('YouTube oturumu yenilenemedi; yeniden yetkilendirme gerekiyor.')
        payload = response.json()
        if not set(SCOPES).issubset(set(payload.get('scope', '').split())):
            raise YouTubeError('Salt okunur YouTube ve Analytics izinleri doğrulanamadı.')
        if set(payload['scope'].split()) - set(SCOPES):
            raise YouTubeError('Bu oturum gereğinden geniş izin içeriyor; salt okunur bağlantı kurun.')
        self.access_token = payload['access_token']
        channels = await self.request('https://www.googleapis.com/youtube/v3/channels',
                                      {'part': 'snippet,contentDetails', 'mine': 'true'})
        items = channels.get('items', [])
        if len(items) != 1 or items[0]['id'] != CHANNEL_ID:
            raise YouTubeError('Bağlanan hesap Ruhun Sükûnu kanalına ait değil.')
        return items[0]

    async def list_videos(self, channel, now):
        cutoff = now - timedelta(days=90)
        playlist = channel['contentDetails']['relatedPlaylists']['uploads']
        page, result = None, []
        while True:
            params = {'part': 'contentDetails', 'playlistId': playlist, 'maxResults': 50}
            if page:
                params['pageToken'] = page
            data = await self.request('https://www.googleapis.com/youtube/v3/playlistItems', params)
            ids = [item['contentDetails']['videoId'] for item in data.get('items', [])]
            if ids:
                videos = await self.request('https://www.googleapis.com/youtube/v3/videos',
                                           {'part': 'snippet,contentDetails,status', 'id': ','.join(ids)})
                for video in videos.get('items', []):
                    published = datetime.fromisoformat(video['snippet']['publishedAt'].replace('Z', '+00:00'))
                    if published >= cutoff and video['status']['privacyStatus'] == 'public':
                        result.append({'id': video['id'], 'title': video['snippet']['title'],
                                       'published_at': published.isoformat(),
                                       'duration_iso': video['contentDetails']['duration']})
            page = data.get('nextPageToken')
            if not page:
                return result

    async def query(self, video_id, start, end, metrics=METRICS, dimensions=None):
        params = {'ids': f'channel=={CHANNEL_ID}', 'startDate': str(start), 'endDate': str(end),
                  'metrics': ','.join(metrics), 'filters': f'video=={video_id}'}
        if dimensions:
            params['dimensions'] = dimensions
        data = await self.request('https://youtubeanalytics.googleapis.com/v2/reports', params)
        return rows_to_dicts(data)

    async def content_type(self, video_id, start, end):
        rows = await self.query(video_id, start, end, ('views',), 'day,creatorContentType')
        kinds = {row['creatorContentType'] for row in rows}
        return 'SHORTS' if kinds == {'SHORTS'} else ('OTHER' if kinds else 'UNKNOWN')
