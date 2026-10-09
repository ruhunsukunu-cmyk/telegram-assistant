"""Ruhun-only JSON records and transactional leases; no legacy restoration."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

class Store:
    def __init__(self, path=None, url=None):
        self.path = path or os.getenv('DB_PATH', str(Path(__file__).parent.parent / 'ruhun.db'))
        self.url = url if url is not None else os.getenv('DATABASE_URL', '').strip()

    @contextmanager
    def connect(self):
        if self.url:
            from psycopg import connect
            conn = connect(self.url)
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=15)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def sql(self, text):
        return text.replace('?', '%s') if self.url else text

    def init(self):
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS ruhun_records (namespace TEXT NOT NULL, record_key TEXT NOT NULL, payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL, PRIMARY KEY(namespace, record_key))')
            conn.execute('CREATE TABLE IF NOT EXISTS ruhun_leases (name TEXT PRIMARY KEY, expires_at DOUBLE PRECISION NOT NULL)')

    def get(self, namespace, key, default=None):
        with self.connect() as conn:
            row = conn.execute(self.sql('SELECT payload FROM ruhun_records WHERE namespace=? AND record_key=?'), (namespace, key)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, namespace, key, value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
        with self.connect() as conn:
            conn.execute(self.sql('INSERT INTO ruhun_records(namespace,record_key,payload,updated_at) VALUES(?,?,?,?) ON CONFLICT(namespace,record_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at'), (namespace, key, payload, time.time()))

    def all(self, namespace):
        with self.connect() as conn:
            rows = conn.execute(self.sql('SELECT record_key,payload FROM ruhun_records WHERE namespace=? ORDER BY record_key'), (namespace,)).fetchall()
        return {key: json.loads(payload) for key, payload in rows}

    def claim(self, name, seconds=1800, now=None):
        now = time.time() if now is None else now
        with self.connect() as conn:
            result = conn.execute(self.sql('INSERT INTO ruhun_leases(name,expires_at) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET expires_at=excluded.expires_at WHERE ruhun_leases.expires_at<=?'), (name, now + seconds, now))
            return result.rowcount == 1

    def release(self, name):
        with self.connect() as conn:
            conn.execute(self.sql('DELETE FROM ruhun_leases WHERE name=?'), (name,))

    def import_bundle(self, videos, experiments):
        with self.connect() as conn:
            for namespace, entries, field in [('production', videos, 'video_id'), ('experiments', experiments, 'id')]:
                for item in entries:
                    conn.execute(self.sql('INSERT INTO ruhun_records(namespace,record_key,payload,updated_at) VALUES(?,?,?,?) ON CONFLICT(namespace,record_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at'), (namespace, item[field], json.dumps(item, ensure_ascii=False, allow_nan=False), time.time()))
