import sqlite3
from datetime import datetime

conn = sqlite3.connect("users.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    notify_time TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_date TEXT NOT NULL,         -- YYYY-MM-DD (дата сессии)
    q_index INTEGER NOT NULL,           -- 1..4
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)
""")

conn.commit()


def upsert_user(user_id: int, notify_time: str | None, is_active: int):
    cur.execute(
        """
        INSERT INTO users (user_id, notify_time, is_active, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            notify_time=excluded.notify_time,
            is_active=excluded.is_active,
            updated_at=excluded.updated_at
        """,
        (user_id, notify_time, is_active, datetime.utcnow().isoformat())
    )
    conn.commit()


def get_user(user_id: int):
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_active_users():
    cur.execute("SELECT user_id, notify_time FROM users WHERE is_active=1 AND notify_time IS NOT NULL")
    return [(r["user_id"], r["notify_time"]) for r in cur.fetchall()]


def save_answer(user_id: int, session_date: str, q_index: int, question: str, answer: str):
    cur.execute(
        """
        INSERT INTO answers (user_id, session_date, q_index, question, answer, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, session_date, q_index, question, answer, datetime.utcnow().isoformat())
    )
    conn.commit()
