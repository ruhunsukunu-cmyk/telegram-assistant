"""Loopback OAuth helper: no credentials printed; secrets go to a protected local file."""
import asyncio
import base64
import hashlib
import json
import secrets
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.ruhun_config import Config, CHANNEL_ID
from services.ruhun_youtube import SCOPES, YouTube

def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python tools/connect_youtube.py ABSOLUTE_OAUTH_CLIENT_JSON')
    path = Path(sys.argv[1]).resolve(strict=True)
    settings = json.loads(path.read_text('utf-8'))
    client = settings.get('installed')
    if not client:
        raise SystemExit('Desktop OAuth client JSON required.')
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    outcome = {}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            data = parse_qs(urlparse(self.path).query)
            if data.get('state', [''])[0] != state:
                self.send_error(400); return
            outcome.update({key: values[0] for key, values in data.items()})
            self.send_response(200); self.end_headers()
            self.wfile.write(b'Authorization received. Return to the terminal. Channel verification pending.')
    server = HTTPServer(('127.0.0.1', 0), Callback)
    server.timeout = 180
    redirect = f'http://127.0.0.1:{server.server_port}/'
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': client['client_id'], 'redirect_uri': redirect, 'response_type': 'code',
        'scope': ' '.join(SCOPES), 'access_type': 'offline', 'prompt': 'consent', 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256'})
    webbrowser.open(url)
    server.handle_request(); server.server_close()
    if 'code' not in outcome:
        raise SystemExit('Authorization missing or declined; no secrets written.')
    async def exchange():
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.post('https://oauth2.googleapis.com/token', data={
                'client_id': client['client_id'], 'client_secret': client['client_secret'],
                'code': outcome['code'], 'code_verifier': verifier, 'redirect_uri': redirect,
                'grant_type': 'authorization_code'})
        if response.status_code != 200:
            raise RuntimeError('Token exchange failed; no secrets written.')
        token = response.json().get('refresh_token')
        if not token:
            raise RuntimeError('Offline refresh token missing.')
        cfg = Config(youtube_client_id=client['client_id'], youtube_client_secret=client['client_secret'], youtube_refresh_token=token)
        await YouTube(cfg).verify()
        return {'RUHUN_YT_CLIENT_ID': client['client_id'], 'RUHUN_YT_CLIENT_SECRET': client['client_secret'], 'RUHUN_YT_REFRESH_TOKEN': token}
    values = asyncio.run(exchange())
    output = Path(__file__).resolve().parents[1] / '.ruhun-youtube-secrets.json'
    # New file only; never silently overwrite an existing connection.
    with output.open('x', encoding='utf-8') as file:
        json.dump(values, file)
    print(f'Channel verified: {CHANNEL_ID}. Secrets saved locally to ignored file; transfer to Railway variables without printing.')

if __name__ == '__main__':
    main()
