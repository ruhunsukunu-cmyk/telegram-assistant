"""Inventory-first, exact-table deletion of the former assistant's data. No backups."""
import argparse
import json
import os
import sqlite3
from pathlib import Path

# Only tables from the former repository's database.init_db are eligible.
LEGACY = {
    'notes': {'user_id', 'content'}, 'tasks': {'user_id', 'title', 'is_done'},
    'reminders': {'user_id', 'chat_id', 'message', 'due_at'},
    'user_settings': {'user_id', 'default_city'}, 'task_metadata': {'task_id', 'priority'},
    'reminder_rules': {'reminder_id', 'recurrence'}, 'habits': {'user_id', 'name'},
    'habit_logs': {'habit_id', 'log_date'}, 'expenses': {'user_id', 'amount', 'category'},
    'calendar_events': {'user_id', 'starts_at'}, 'user_preferences': {'user_id', 'timezone'},
    'daily_summaries': {'user_id', 'chat_id', 'send_time'}, 'budgets': {'user_id', 'monthly_limit'},
    'app_metadata': {'key', 'value'}, 'calendar_notifications': {'event_key', 'offset_minutes'},
    'assistant_alerts': {'user_id', 'kind', 'ref_key'}, 'assistant_feedback': {'user_id', 'action'},
    'task_activity': {'user_id', 'task_id', 'action'},
    'notification_preferences': {'user_id', 'kind', 'enabled'}, 'user_onboarding': {'user_id', 'seen_at'},
}

def inventory(conn, postgres=False):
    if postgres:
        tables = {r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE'")}
        columns = lambda name: {r[0] for r in conn.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s', (name,))}
    else:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = lambda name: {r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')}
    matched = []
    for name, required in LEGACY.items():
        if name in tables:
            if not required <= columns(name):
                raise ValueError(f'{name}: eski uygulama şeması uyuşmuyor; silme durduruldu.')
            matched.append(name)
    if matched and not {'notes', 'reminders', 'app_metadata'} <= set(matched):
        raise ValueError('Eski uygulamanın üç ana tablo imzası doğrulanamadı; silme durduruldu.')
    return {'matched_tables': sorted(matched), 'preserved_tables': sorted(tables - set(matched)),
            'row_counts': {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in matched}}

def reset(conn, postgres=False, apply=False):
    info = inventory(conn, postgres)
    if apply:
        if not postgres:
            conn.execute('PRAGMA secure_delete=ON')
        # No CASCADE: dependencies outside this application must cause a stop.
        for name in reversed(info['matched_tables']):
            conn.execute(f'DROP TABLE "{name}"')
        conn.commit()
        if not postgres:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            conn.execute('VACUUM')
        info['remaining_legacy_tables'] = inventory(conn, postgres)['matched_tables']
    info['applied'] = apply
    return info

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', type=Path, help='Exact absolute SQLite target; never a directory.')
    parser.add_argument('--postgres', action='store_true', help='Use DATABASE_URL without displaying it.')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--stopped', action='store_true', help='Operator has verified all legacy writers stopped.')
    parser.add_argument('--confirm', default='')
    args = parser.parse_args()
    if bool(args.sqlite) == args.postgres:
        parser.error('Select exactly one explicit target.')
    if args.apply and (not args.stopped or args.confirm != 'DELETE_LEGACY_NO_BACKUP'):
        parser.error('Destructive run requires --stopped --confirm DELETE_LEGACY_NO_BACKUP.')
    if args.postgres:
        from psycopg import connect
        conn = connect(os.environ['DATABASE_URL'])
    else:
        target = args.sqlite.resolve(strict=True)
        if not args.sqlite.is_absolute() or not target.is_file() or target.suffix not in ('.db', '.sqlite', '.sqlite3'):
            parser.error('Absolute existing database file required.')
        conn = sqlite3.connect(f'file:{target.as_posix()}?mode=rw', uri=True)
    try:
        print(json.dumps(reset(conn, args.postgres, args.apply), ensure_ascii=False, indent=2))
    finally:
        conn.close()

if __name__ == '__main__':
    main()
