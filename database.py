import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "assistant.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                is_done INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


# --- NOTLAR ---
def add_note(user_id: int, content: str) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notes (user_id, content) VALUES (?, ?)",
            (user_id, content.strip())
        )
        conn.commit()
        return cursor.lastrowid


def get_notes(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        return cursor.fetchall()


def delete_note(note_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM notes WHERE id = ? AND user_id = ?",
            (note_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


# --- GÖREVLER (TODO) ---
def add_task(user_id: int, title: str) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (user_id, title, is_done) VALUES (?, ?, 0)",
            (user_id, title.strip())
        )
        conn.commit()
        return cursor.lastrowid


def get_tasks(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, is_done, created_at FROM tasks WHERE user_id = ? ORDER BY is_done ASC, id DESC",
            (user_id,)
        )
        return cursor.fetchall()


def complete_task(task_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET is_done = 1 WHERE id = ? AND user_id = ?",
            (task_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_task(task_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
