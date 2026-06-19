import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS message_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_group_id TEXT NOT NULL,
                wa_group_name TEXT,
                wa_sender_name TEXT,
                wa_sender_number TEXT,
                wa_message_id TEXT NOT NULL,
                wa_message_text TEXT,
                teams_message_id TEXT NOT NULL UNIQUE,
                created_at INTEGER DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS teams_subscription (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id TEXT UNIQUE NOT NULL,
                expiration_datetime TEXT NOT NULL,
                resource TEXT,
                updated_at INTEGER DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS chat_threads (
                chat_id TEXT PRIMARY KEY,
                teams_message_id TEXT NOT NULL,
                last_message_at INTEGER NOT NULL
            );
        """)


def save_message_map(entry: dict) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO message_map
                (wa_group_id, wa_group_name, wa_sender_name, wa_sender_number,
                 wa_message_id, wa_message_text, teams_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["wa_group_id"],
                entry["wa_group_name"],
                entry["wa_sender_name"],
                entry["wa_sender_number"],
                entry["wa_message_id"],
                entry["wa_message_text"],
                entry["teams_message_id"],
            ),
        )


def find_by_teams_message_id(teams_message_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM message_map WHERE teams_message_id = ?",
            (teams_message_id,),
        ).fetchone()
        return dict(row) if row else None


def save_subscription(sub: dict) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO teams_subscription (subscription_id, expiration_datetime, resource)
            VALUES (?, ?, ?)
            ON CONFLICT(subscription_id) DO UPDATE SET
                expiration_datetime = excluded.expiration_datetime,
                updated_at = unixepoch()
            """,
            (sub["subscription_id"], sub["expiration_datetime"], sub["resource"]),
        )


def get_subscription() -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM teams_subscription ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def delete_subscription(subscription_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM teams_subscription WHERE subscription_id = ?",
            (subscription_id,),
        )


_THREAD_TTL = 86400  # 24 horas em segundos


def get_active_thread(chat_id: str) -> dict | None:
    """Retorna a thread ativa se a última mensagem foi há menos de 24h."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM chat_threads WHERE chat_id = ? AND last_message_at > ?",
            (chat_id, int(time.time()) - _THREAD_TTL),
        ).fetchone()
        return dict(row) if row else None


def save_thread(chat_id: str, teams_message_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO chat_threads (chat_id, teams_message_id, last_message_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                teams_message_id = excluded.teams_message_id,
                last_message_at = excluded.last_message_at
            """,
            (chat_id, teams_message_id, int(time.time())),
        )


def update_thread_timestamp(chat_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE chat_threads SET last_message_at = ? WHERE chat_id = ?",
            (int(time.time()), chat_id),
        )
