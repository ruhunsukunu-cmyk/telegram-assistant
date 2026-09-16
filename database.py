import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "assistant.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def _uses_postgres():
    return bool(DATABASE_URL)


@contextmanager
def get_db():
    if _uses_postgres():
        from psycopg import connect
        from psycopg.rows import dict_row
        conn = connect(DATABASE_URL, row_factory=dict_row)
    else:
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
        conn.commit()


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
    return _change("UPDATE tasks SET is_done = 1 WHERE id = ? AND user_id = ?", (task_id, user_id))


def delete_task(task_id, user_id):
    return _change("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))


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


def mark_reminder_sent(reminder_id):
    return _change("UPDATE reminders SET sent_at = CURRENT_TIMESTAMP WHERE id = ? AND sent_at IS NULL", (reminder_id,))


def cancel_reminder(reminder_id, user_id):
    """Yalnızca sahibine ait ve henüz gönderilmemiş hatırlatıcıyı iptal et."""
    return _change(
        "DELETE FROM reminders WHERE id = ? AND user_id = ? AND sent_at IS NULL",
        (reminder_id, user_id),
    )


def _change(query, params):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(_sql(query), params)
        conn.commit()
        return cursor.rowcount > 0
