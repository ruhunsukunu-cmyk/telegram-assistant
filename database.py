import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from datetime import datetime, timezone

DB_PATH = os.getenv(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "assistant.db")
).strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

MIGRATION_TABLES = (
    "notes", "tasks", "reminders", "user_settings", "task_metadata",
    "reminder_rules", "habits", "habit_logs", "expenses", "calendar_events",
    "user_preferences", "daily_summaries", "budgets", "calendar_notifications",
    "assistant_alerts", "assistant_feedback", "task_activity", "notification_preferences",
    "user_onboarding",
)


def _uses_postgres():
    return bool(DATABASE_URL)


def storage_label():
    if _uses_postgres():
        return "PostgreSQL"
    if os.getenv("DB_PATH", "").strip():
        return "kalıcı SQLite"
    return "yerel SQLite"


@contextmanager
def get_db():
    if _uses_postgres():
        from psycopg import connect
        from psycopg.rows import dict_row
        conn = connect(DATABASE_URL, row_factory=dict_row)
    else:
        db_directory = os.path.dirname(DB_PATH)
        if db_directory:
            os.makedirs(db_directory, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _sql(query):
    return query.replace("?", "%s") if _uses_postgres() else query


def _insert_and_get_id(conn, query, params):
    cursor = conn.cursor()
    if _uses_postgres():
        cursor.execute(_sql(query) + " RETURNING id", params)
        row_id = cursor.fetchone()["id"]
    else:
        cursor.execute(query, params)
        row_id = cursor.lastrowid
    conn.commit()
    return row_id


def init_db():
    id_column = "BIGSERIAL PRIMARY KEY" if _uses_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"CREATE TABLE IF NOT EXISTS notes (id {id_column}, user_id BIGINT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS tasks (id {id_column}, user_id BIGINT NOT NULL, title TEXT NOT NULL, is_done INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS reminders (id {id_column}, user_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, message TEXT NOT NULL, due_at TIMESTAMP NOT NULL, sent_at TIMESTAMP NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_settings (user_id BIGINT PRIMARY KEY, default_city TEXT NOT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS task_metadata (task_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, priority TEXT NOT NULL DEFAULT 'normal', due_at TIMESTAMP NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS reminder_rules (reminder_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, recurrence TEXT NULL)")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS habits (id {id_column}, user_id BIGINT NOT NULL, name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS habit_logs (habit_id BIGINT NOT NULL, user_id BIGINT NOT NULL, log_date DATE NOT NULL, PRIMARY KEY (habit_id, log_date))")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS expenses (id {id_column}, user_id BIGINT NOT NULL, amount NUMERIC NOT NULL, currency TEXT NOT NULL DEFAULT 'TRY', category TEXT NOT NULL, note TEXT, spent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS calendar_events (id {id_column}, user_id BIGINT NOT NULL, title TEXT NOT NULL, starts_at TIMESTAMP NOT NULL, ends_at TIMESTAMP NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_preferences (user_id BIGINT PRIMARY KEY, timezone TEXT NOT NULL DEFAULT 'Europe/Istanbul', summary_time TEXT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS daily_summaries (user_id BIGINT PRIMARY KEY, chat_id BIGINT NOT NULL, send_time TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT 'Europe/Istanbul')")
        cursor.execute("CREATE TABLE IF NOT EXISTS budgets (user_id BIGINT PRIMARY KEY, monthly_limit NUMERIC NOT NULL, currency TEXT NOT NULL DEFAULT 'TRY')")
        cursor.execute("CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS calendar_notifications (event_key TEXT NOT NULL, offset_minutes INTEGER NOT NULL, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (event_key, offset_minutes))")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS assistant_alerts (id {id_column}, user_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, kind TEXT NOT NULL, ref_key TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, kind, ref_key))")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS assistant_feedback (id {id_column}, user_id BIGINT NOT NULL, alert_id BIGINT NULL, action TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS task_activity (id {id_column}, user_id BIGINT NOT NULL, task_id BIGINT NOT NULL, action TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS notification_preferences (user_id BIGINT NOT NULL, kind TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (user_id, kind))")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_onboarding (user_id BIGINT PRIMARY KEY, seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()


def migrate_postgres_to_sqlite(source_url):
    """Render PostgreSQL verilerini boş Railway Volume'a bir kez kopyala."""
    source_url = source_url.strip()
    if not source_url or _uses_postgres():
        return 0

    with get_db() as target:
        marker = target.execute(
            "SELECT value FROM app_metadata WHERE key = ?", ("postgres_migration_v1",)
        ).fetchone()
        if marker:
            return 0

        from psycopg import connect
        from psycopg.rows import dict_row

        copied = 0
        with connect(source_url, row_factory=dict_row) as source:
            existing_tables = {
                row["table_name"]
                for row in source.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                ).fetchall()
            }
            for table in (name for name in MIGRATION_TABLES if name in existing_tables):
                rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                for row in rows:
                    columns = tuple(row.keys())
                    placeholders = ", ".join("?" for _ in columns)
                    names = ", ".join(f'"{name}"' for name in columns)
                    values = tuple(_sqlite_value(row[name]) for name in columns)
                    target.execute(
                        f'INSERT OR IGNORE INTO "{table}" ({names}) VALUES ({placeholders})',
                        values,
                    )
                    copied += 1
        target.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, CURRENT_TIMESTAMP)",
            ("postgres_migration_v1",),
        )
        target.commit()
        return copied


def _sqlite_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def add_note(user_id, content):
    with get_db() as conn:
        return _insert_and_get_id(conn, "INSERT INTO notes (user_id, content) VALUES (?, ?)", (user_id, content.strip()))


def get_notes(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT id, content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC"), (user_id,))
        return cursor.fetchall()


def delete_note(note_id, user_id):
    return _change("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))


def add_task(user_id, title):
    with get_db() as conn:
        return _insert_and_get_id(conn, "INSERT INTO tasks (user_id, title, is_done) VALUES (?, ?, 0)", (user_id, title.strip()))


def get_tasks(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT id, title, is_done, created_at FROM tasks WHERE user_id = ? ORDER BY is_done ASC, id DESC"), (user_id,))
        return cursor.fetchall()


def complete_task(task_id, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("UPDATE tasks SET is_done = 1 WHERE id = ? AND user_id = ? AND is_done = 0"),
            (task_id, user_id),
        )
        changed = cursor.rowcount > 0
        if changed:
            cursor.execute(
                _sql("INSERT INTO task_activity (user_id, task_id, action) VALUES (?, ?, 'completed')"),
                (user_id, task_id),
            )
        conn.commit()
        return changed


def delete_task(task_id, user_id):
    return _change("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))


def clear_completed_tasks(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("DELETE FROM tasks WHERE user_id = ? AND is_done = 1"), (user_id,))
        conn.commit()
        return cursor.rowcount


def add_reminder(user_id, chat_id, message, due_at: datetime):
    due_at = due_at.astimezone(timezone.utc).replace(tzinfo=None)
    due_value = due_at if _uses_postgres() else due_at.isoformat(sep=" ")
    with get_db() as conn:
        return _insert_and_get_id(conn, "INSERT INTO reminders (user_id, chat_id, message, due_at) VALUES (?, ?, ?, ?)", (user_id, chat_id, message.strip(), due_value))


def get_pending_reminders(user_id=None):
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT id, user_id, chat_id, message, due_at FROM reminders WHERE sent_at IS NULL"
        params = ()
        if user_id is not None:
            query += " AND user_id = ?"
            params = (user_id,)
        query += " ORDER BY due_at"
        cursor.execute(_sql(query), params)
        return cursor.fetchall()


def get_reminder(reminder_id, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("SELECT id, user_id, chat_id, message, due_at, sent_at FROM reminders WHERE id = ? AND user_id = ?"),
            (reminder_id, user_id),
        )
        return cursor.fetchone()


def mark_reminder_sent(reminder_id):
    return _change("UPDATE reminders SET sent_at = CURRENT_TIMESTAMP WHERE id = ? AND sent_at IS NULL", (reminder_id,))


def cancel_reminder(reminder_id, user_id):
    """Yalnızca sahibine ait ve henüz gönderilmemiş hatırlatıcıyı iptal et."""
    return _change(
        "DELETE FROM reminders WHERE id = ? AND user_id = ? AND sent_at IS NULL",
        (reminder_id, user_id),
    )


def set_reminder_recurrence(reminder_id, user_id, recurrence):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("INSERT INTO reminder_rules (reminder_id, user_id, recurrence) VALUES (?, ?, ?) ON CONFLICT(reminder_id) DO UPDATE SET recurrence = excluded.recurrence"),
            (reminder_id, user_id, recurrence),
        )
        conn.commit()


def get_reminder_recurrence(reminder_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT recurrence FROM reminder_rules WHERE reminder_id = ?"), (reminder_id,))
        row = cursor.fetchone()
        return row["recurrence"] if row else None


def set_default_city(user_id, city):
    city = city.strip()[:100]
    with get_db() as conn:
        cursor = conn.cursor()
        if _uses_postgres():
            cursor.execute(
                "INSERT INTO user_settings (user_id, default_city) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET default_city = EXCLUDED.default_city",
                (user_id, city),
            )
        else:
            cursor.execute(
                "INSERT INTO user_settings (user_id, default_city) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET default_city = excluded.default_city",
                (user_id, city),
            )
        conn.commit()


def get_default_city(user_id, fallback="Istanbul"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT default_city FROM user_settings WHERE user_id = ?"), (user_id,))
        row = cursor.fetchone()
        return row["default_city"] if row else fallback


def search_user_content(user_id, term, limit=10):
    pattern = f"%{term.strip()}%"
    operator = "ILIKE" if _uses_postgres() else "LIKE"
    results = []
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql(f"SELECT id, title AS content, is_done FROM tasks WHERE user_id = ? AND title {operator} ? ORDER BY id DESC LIMIT ?"),
            (user_id, pattern, limit),
        )
        results.extend({"type": "task", **dict(row)} for row in cursor.fetchall())
        cursor.execute(
            _sql(f"SELECT id, content FROM notes WHERE user_id = ? AND content {operator} ? ORDER BY id DESC LIMIT ?"),
            (user_id, pattern, limit),
        )
        results.extend({"type": "note", **dict(row)} for row in cursor.fetchall())
    return results[:limit]


def set_task_metadata(task_id, user_id, priority="normal", due_at=None):
    due_value = _datetime_value(due_at) if due_at else None
    with get_db() as conn:
        cursor = conn.cursor()
        sql = (
            "INSERT INTO task_metadata (task_id, user_id, priority, due_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET priority = excluded.priority, due_at = excluded.due_at"
        )
        cursor.execute(_sql(sql), (task_id, user_id, priority, due_value))
        conn.commit()


def get_enriched_tasks(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("""
            SELECT t.id, t.title, t.is_done, t.created_at,
                   COALESCE(m.priority, 'normal') AS priority, m.due_at
            FROM tasks t LEFT JOIN task_metadata m ON m.task_id = t.id
            WHERE t.user_id = ?
            ORDER BY t.is_done ASC,
                     CASE COALESCE(m.priority, 'normal') WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                     m.due_at ASC, t.id DESC
        """), (user_id,))
        return cursor.fetchall()


def add_habit(user_id, name):
    with get_db() as conn:
        return _insert_and_get_id(conn, "INSERT INTO habits (user_id, name) VALUES (?, ?)", (user_id, name.strip()))


def get_habits(user_id, day=None):
    day = day or datetime.now(timezone.utc).date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("""
            SELECT h.id, h.name,
                   CASE WHEN l.habit_id IS NULL THEN 0 ELSE 1 END AS done_today,
                   (SELECT COUNT(*) FROM habit_logs x WHERE x.habit_id = h.id) AS total_days
            FROM habits h LEFT JOIN habit_logs l ON l.habit_id = h.id AND l.log_date = ?
            WHERE h.user_id = ? ORDER BY h.id
        """), (day, user_id))
        return cursor.fetchall()


def check_habit(habit_id, user_id, day=None):
    day = day or datetime.now(timezone.utc).date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        sql = "INSERT INTO habit_logs (habit_id, user_id, log_date) SELECT ?, ?, ? WHERE EXISTS (SELECT 1 FROM habits WHERE id = ? AND user_id = ?) ON CONFLICT(habit_id, log_date) DO NOTHING"
        cursor.execute(_sql(sql), (habit_id, user_id, day, habit_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def add_expense(user_id, amount, category, note="", currency="TRY"):
    with get_db() as conn:
        return _insert_and_get_id(conn, "INSERT INTO expenses (user_id, amount, currency, category, note) VALUES (?, ?, ?, ?, ?)", (user_id, amount, currency, category, note.strip()))


def get_expense_summary(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT category, currency, SUM(amount) AS total FROM expenses WHERE user_id = ? GROUP BY category, currency ORDER BY total DESC"), (user_id,))
        return cursor.fetchall()


def get_expenses(user_id, limit=1000):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT id, amount, currency, category, note, spent_at FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT ?"), (user_id, limit))
        return cursor.fetchall()


def set_budget(user_id, monthly_limit, currency="TRY"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("INSERT INTO budgets (user_id, monthly_limit, currency) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET monthly_limit = excluded.monthly_limit, currency = excluded.currency"), (user_id, monthly_limit, currency))
        conn.commit()


def get_budget(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT monthly_limit, currency FROM budgets WHERE user_id = ?"), (user_id,))
        return cursor.fetchone()


def get_habit_log_dates(habit_id, user_id, limit=30):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT log_date FROM habit_logs WHERE habit_id = ? AND user_id = ? ORDER BY log_date DESC LIMIT ?"), (habit_id, user_id, limit))
        return [str(row["log_date"]) for row in cursor.fetchall()]


def add_calendar_event(user_id, title, starts_at, ends_at=None):
    with get_db() as conn:
        return _insert_and_get_id(conn, "INSERT INTO calendar_events (user_id, title, starts_at, ends_at) VALUES (?, ?, ?, ?)", (user_id, title.strip(), _datetime_value(starts_at), _datetime_value(ends_at) if ends_at else None))


def get_upcoming_events(user_id, after=None, limit=10):
    after = after or datetime.now(timezone.utc)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT id, title, starts_at, ends_at FROM calendar_events WHERE user_id = ? AND starts_at >= ? ORDER BY starts_at LIMIT ?"), (user_id, _datetime_value(after), limit))
        return cursor.fetchall()


def was_calendar_notification_sent(event_key, offset_minutes):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("SELECT 1 FROM calendar_notifications WHERE event_key = ? AND offset_minutes = ?"),
            (event_key, offset_minutes),
        )
        return cursor.fetchone() is not None


def mark_calendar_notification_sent(event_key, offset_minutes):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("INSERT INTO calendar_notifications (event_key, offset_minutes) VALUES (?, ?) ON CONFLICT(event_key, offset_minutes) DO NOTHING"),
            (event_key, offset_minutes),
        )
        conn.commit()
        return cursor.rowcount > 0


def create_assistant_alert(user_id, chat_id, kind, ref_key, title):
    """Create an actionable alert once and return its stable database id."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("INSERT INTO assistant_alerts (user_id, chat_id, kind, ref_key, title) VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, kind, ref_key) DO NOTHING"),
            (user_id, chat_id, kind, ref_key, title[:500]),
        )
        conn.commit()
        cursor.execute(
            _sql("SELECT id, user_id, chat_id, kind, ref_key, title, status FROM assistant_alerts WHERE user_id = ? AND kind = ? AND ref_key = ?"),
            (user_id, kind, ref_key),
        )
        return cursor.fetchone()


def get_assistant_alert(alert_id, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("SELECT id, user_id, chat_id, kind, ref_key, title, status FROM assistant_alerts WHERE id = ? AND user_id = ?"),
            (alert_id, user_id),
        )
        return cursor.fetchone()


def resolve_assistant_alert(alert_id, user_id, status, action=None):
    """Close/snooze an alert and retain lightweight feedback for later personalization."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("UPDATE assistant_alerts SET status = ? WHERE id = ? AND user_id = ?"),
            (status, alert_id, user_id),
        )
        changed = cursor.rowcount > 0
        if changed and action:
            cursor.execute(
                _sql("INSERT INTO assistant_feedback (user_id, alert_id, action) VALUES (?, ?, ?)"),
                (user_id, alert_id, action),
            )
        conn.commit()
        return changed


def get_feedback_summary(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("SELECT action, COUNT(*) AS total FROM assistant_feedback WHERE user_id = ? GROUP BY action"),
            (user_id,),
        )
        return {row["action"]: row["total"] for row in cursor.fetchall()}


def count_completed_tasks_since(user_id, since):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("SELECT COUNT(*) AS total FROM task_activity WHERE user_id = ? AND action = 'completed' AND created_at >= ?"),
            (user_id, _datetime_value(since)),
        )
        return cursor.fetchone()["total"]


DEFAULT_NOTIFICATION_PREFERENCES = {
    "morning": True,
    "calendar": True,
    "midday": False,
    "evening": False,
    "weekly": False,
    "followup": False,
}


def notification_enabled(user_id, kind):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("SELECT enabled FROM notification_preferences WHERE user_id = ? AND kind = ?"),
            (user_id, kind),
        )
        row = cursor.fetchone()
        if row:
            return bool(row["enabled"])
        return DEFAULT_NOTIFICATION_PREFERENCES.get(kind, True)


def set_notification_enabled(user_id, kind, enabled):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("INSERT INTO notification_preferences (user_id, kind, enabled) VALUES (?, ?, ?) ON CONFLICT(user_id, kind) DO UPDATE SET enabled = excluded.enabled"),
            (user_id, kind, int(bool(enabled))),
        )
        conn.commit()


def has_seen_onboarding(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("SELECT 1 FROM user_onboarding WHERE user_id = ?"), (user_id,))
        return cursor.fetchone() is not None


def mark_onboarding_seen(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("INSERT INTO user_onboarding (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING"),
            (user_id,),
        )
        conn.commit()


def export_user_data(user_id):
    data = {}
    with get_db() as conn:
        cursor = conn.cursor()
        for name, query in {
            "notes": "SELECT id, content, created_at FROM notes WHERE user_id = ?",
            "tasks": "SELECT id, title, is_done, created_at FROM tasks WHERE user_id = ?",
            "reminders": "SELECT id, message, due_at, sent_at FROM reminders WHERE user_id = ?",
            "habits": "SELECT id, name, created_at FROM habits WHERE user_id = ?",
            "expenses": "SELECT id, amount, currency, category, note, spent_at FROM expenses WHERE user_id = ?",
            "calendar_events": "SELECT id, title, starts_at, ends_at FROM calendar_events WHERE user_id = ?",
            "assistant_feedback": "SELECT action, created_at FROM assistant_feedback WHERE user_id = ?",
            "task_activity": "SELECT task_id, action, created_at FROM task_activity WHERE user_id = ?",
            "notification_preferences": "SELECT kind, enabled FROM notification_preferences WHERE user_id = ?",
            "user_onboarding": "SELECT seen_at FROM user_onboarding WHERE user_id = ?",
        }.items():
            cursor.execute(_sql(query), (user_id,))
            data[name] = [dict(row) for row in cursor.fetchall()]
    return data


def delete_user_data(user_id):
    """Kullanıcıya ait tüm verileri tek işlemde kaldır."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql("DELETE FROM habit_logs WHERE user_id = ?"), (user_id,))
        cursor.execute(_sql("DELETE FROM task_metadata WHERE user_id = ?"), (user_id,))
        cursor.execute(_sql("DELETE FROM reminder_rules WHERE user_id = ?"), (user_id,))
        cursor.execute(_sql("DELETE FROM assistant_feedback WHERE user_id = ?"), (user_id,))
        cursor.execute(_sql("DELETE FROM assistant_alerts WHERE user_id = ?"), (user_id,))
        cursor.execute(_sql("DELETE FROM task_activity WHERE user_id = ?"), (user_id,))
        cursor.execute(_sql("DELETE FROM notification_preferences WHERE user_id = ?"), (user_id,))
        cursor.execute(_sql("DELETE FROM user_onboarding WHERE user_id = ?"), (user_id,))
        for table in ("notes", "tasks", "reminders", "habits", "expenses", "calendar_events", "user_settings", "user_preferences", "daily_summaries", "budgets"):
            cursor.execute(_sql(f"DELETE FROM {table} WHERE user_id = ?"), (user_id,))
        conn.commit()


def set_daily_summary(user_id, chat_id, send_time, timezone_name="Europe/Istanbul"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            _sql("INSERT INTO daily_summaries (user_id, chat_id, send_time, timezone) VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET chat_id = excluded.chat_id, send_time = excluded.send_time, timezone = excluded.timezone"),
            (user_id, chat_id, send_time, timezone_name),
        )
        conn.commit()


def delete_daily_summary(user_id):
    return _change("DELETE FROM daily_summaries WHERE user_id = ?", (user_id,))


def get_daily_summaries():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, chat_id, send_time, timezone FROM daily_summaries")
        return cursor.fetchall()


def _datetime_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value if _uses_postgres() else value.isoformat(sep=" ")


def _change(query, params):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql(query), params)
        conn.commit()
        return cursor.rowcount > 0
