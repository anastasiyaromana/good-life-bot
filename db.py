import sqlite3
from datetime import datetime

conn = sqlite3.connect("users.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()


def _has_column(table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(r["name"] == col for r in cur.fetchall())


def migrate():
    # базовая users (может быть старой)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        notify_time TEXT
    )
    """)

    # новые поля
    if not _has_column("users", "timezone_group"):
        cur.execute("ALTER TABLE users ADD COLUMN timezone_group TEXT")
    if not _has_column("users", "is_active"):
        cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if not _has_column("users", "updated_at"):
        cur.execute("ALTER TABLE users ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")

    # тихое правило
    if not _has_column("users", "last_activity_at"):
        cur.execute("ALTER TABLE users ADD COLUMN last_activity_at TEXT")
    if not _has_column("users", "last_nudge_at"):
        cur.execute("ALTER TABLE users ADD COLUMN last_nudge_at TEXT")

    # пропуск дня
    if not _has_column("users", "skip_date"):
        cur.execute("ALTER TABLE users ADD COLUMN skip_date TEXT")

    # заполним updated_at
    cur.execute(
        "UPDATE users SET updated_at=? WHERE updated_at IS NULL OR updated_at=''",
        (datetime.utcnow().isoformat(),)
    )

    # answers
    cur.execute("""
    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        session_date TEXT NOT NULL,         -- YYYY-MM-DD (локальная дата пользователя)
        q_index INTEGER NOT NULL,           -- 1..4
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    conn.commit()


migrate()


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat()


def upsert_user(user_id: int, notify_time: str | None, timezone_group: str | None, is_active: int):
    cur.execute(
        """
        INSERT INTO users (user_id, notify_time, timezone_group, is_active, updated_at, last_activity_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            notify_time=excluded.notify_time,
            timezone_group=excluded.timezone_group,
            is_active=excluded.is_active,
            updated_at=excluded.updated_at
        """,
        (user_id, notify_time, timezone_group, is_active, now_utc_iso(), now_utc_iso())
    )
    conn.commit()


def get_user(user_id: int):
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def set_active(user_id: int, is_active: int):
    cur.execute(
        "UPDATE users SET is_active=?, updated_at=? WHERE user_id=?",
        (is_active, now_utc_iso(), user_id)
    )
    conn.commit()


def update_timezone_group(user_id: int, timezone_group: str):
    u = get_user(user_id)
    if u is None:
        upsert_user(user_id, None, timezone_group, 1)
        return
    cur.execute(
        "UPDATE users SET timezone_group=?, updated_at=? WHERE user_id=?",
        (timezone_group, now_utc_iso(), user_id)
    )
    conn.commit()


def update_notify_time(user_id: int, notify_time: str):
    u = get_user(user_id)
    if u is None:
        upsert_user(user_id, notify_time, "Москва", 1)
        return
    cur.execute(
        "UPDATE users SET notify_time=?, is_active=1, updated_at=? WHERE user_id=?",
        (notify_time, now_utc_iso(), user_id)
    )
    conn.commit()


def touch_activity(user_id: int):
    u = get_user(user_id)
    if u is None:
        upsert_user(user_id, None, "Москва", 1)
        return
    cur.execute(
        "UPDATE users SET last_activity_at=?, updated_at=? WHERE user_id=?",
        (now_utc_iso(), now_utc_iso(), user_id)
    )
    conn.commit()


def set_skip_date(user_id: int, skip_date: str):
    u = get_user(user_id)
    if u is None:
        upsert_user(user_id, None, "Москва", 1)
    cur.execute(
        "UPDATE users SET skip_date=?, updated_at=? WHERE user_id=?",
        (skip_date, now_utc_iso(), user_id)
    )
    conn.commit()


def clear_skip_date(user_id: int):
    cur.execute(
        "UPDATE users SET skip_date=NULL, updated_at=? WHERE user_id=?",
        (now_utc_iso(), user_id)
    )
    conn.commit()


def save_nudge_sent(user_id: int):
    cur.execute(
        "UPDATE users SET last_nudge_at=?, updated_at=? WHERE user_id=?",
        (now_utc_iso(), now_utc_iso(), user_id)
    )
    conn.commit()


def get_active_users_for_schedule():
    cur.execute("""
        SELECT user_id, notify_time, timezone_group, skip_date
        FROM users
        WHERE is_active=1 AND notify_time IS NOT NULL
    """)
    return [dict(r) for r in cur.fetchall()]


def get_users_for_nudge():
    cur.execute("""
        SELECT user_id, is_active, last_activity_at, last_nudge_at
        FROM users
        WHERE is_active=1
    """)
    return [dict(r) for r in cur.fetchall()]


def save_answer(user_id: int, session_date: str, q_index: int, question: str, answer: str):
    cur.execute(
        """
        INSERT INTO answers (user_id, session_date, q_index, question, answer, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, session_date, q_index, question, answer, now_utc_iso())
    )
    conn.commit()
