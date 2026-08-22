import os
import sqlite3
import time
from pathlib import Path

_default_db = Path(__file__).parent.parent / "data.db"
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(_default_db)))


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
                teams_chat_id TEXT,
                teams_message_id TEXT NOT NULL,
                last_message_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_tokens (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_group_state (
                wa_chat_id TEXT PRIMARY KEY,
                last_activity_at INTEGER NOT NULL DEFAULT 0,
                window_open INTEGER NOT NULL DEFAULT 0,
                window_opened_at INTEGER,
                window_customer_number TEXT,
                window_customer_name TEXT,
                window_notified INTEGER NOT NULL DEFAULT 0,
                last_our_response_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS ai_customer_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_chat_id TEXT NOT NULL,
                sender_number TEXT NOT NULL,
                sender_name TEXT,
                text TEXT,
                created_at INTEGER NOT NULL DEFAULT (unixepoch())
            );

            CREATE INDEX IF NOT EXISTS idx_ai_customer_messages_lookup
                ON ai_customer_messages (wa_chat_id, sender_number, created_at);
        """)
        try:
            conn.execute("ALTER TABLE chat_threads ADD COLUMN teams_chat_id TEXT")
        except Exception:
            pass


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


def save_refresh_token(token: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO auth_tokens (key, value) VALUES ('refresh_token', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (token,),
        )


def get_refresh_token() -> str | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM auth_tokens WHERE key = 'refresh_token'"
        ).fetchone()
        return row["value"] if row else None


_THREAD_TTL = 86400  # 24 horas em segundos


def get_active_thread(chat_id: str) -> dict | None:
    """Retorna a thread ativa se a última mensagem foi há menos de 24h."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM chat_threads WHERE chat_id = ? AND last_message_at > ?",
            (chat_id, int(time.time()) - _THREAD_TTL),
        ).fetchone()
        return dict(row) if row else None


def get_most_recent_thread() -> dict | None:
    """Retorna a thread WA com atividade mais recente nas últimas 24h."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM chat_threads WHERE last_message_at > ? ORDER BY last_message_at DESC LIMIT 1",
            (int(time.time()) - _THREAD_TTL,),
        ).fetchone()
        return dict(row) if row else None


def save_thread(chat_id: str, teams_message_id: str, teams_chat_id: str = "") -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO chat_threads (chat_id, teams_chat_id, teams_message_id, last_message_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                teams_chat_id = excluded.teams_chat_id,
                teams_message_id = excluded.teams_message_id,
                last_message_at = excluded.last_message_at
            """,
            (chat_id, teams_chat_id, teams_message_id, int(time.time())),
        )


def seed_chat_threads(jid_mappings: dict[str, str]) -> None:
    """Insere mapeamentos teams_chat_id→wa_jid vindos do config, sem sobrescrever entradas reais."""
    for teams_chat_id, wa_jid in jid_mappings.items():
        if not wa_jid:
            continue
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO chat_threads (chat_id, teams_chat_id, teams_message_id, last_message_at)
                VALUES (?, ?, 'seed', 0)
                ON CONFLICT(chat_id) DO UPDATE SET
                    teams_chat_id = excluded.teams_chat_id
                WHERE teams_chat_id IS NULL OR teams_chat_id = ''
                """,
                (wa_jid, teams_chat_id),
            )
        print(f"[DB] Seed: {wa_jid[:30]} → {teams_chat_id[:40]}")


def find_wa_jid_by_teams_chat(teams_chat_id: str) -> str | None:
    """Retorna o JID WA mais recente mapeado ao chat Teams, sem restrição de tempo."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT chat_id FROM chat_threads WHERE teams_chat_id = ?"
            " ORDER BY last_message_at DESC LIMIT 1",
            (teams_chat_id,),
        ).fetchone()
        return row["chat_id"] if row else None


def update_thread_timestamp(chat_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE chat_threads SET last_message_at = ? WHERE chat_id = ?",
            (int(time.time()), chat_id),
        )


# ─────────────────────────────────────────────
# Camada de IA
# ─────────────────────────────────────────────

def _ensure_ai_state(conn: sqlite3.Connection, wa_chat_id: str) -> None:
    conn.execute(
        "INSERT INTO ai_group_state (wa_chat_id, last_activity_at) VALUES (?, 0) "
        "ON CONFLICT(wa_chat_id) DO NOTHING",
        (wa_chat_id,),
    )


def get_ai_state(wa_chat_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM ai_group_state WHERE wa_chat_id = ?", (wa_chat_id,)
        ).fetchone()
        return dict(row) if row else None


def touch_ai_activity(wa_chat_id: str, now: int) -> None:
    with _conn() as conn:
        _ensure_ai_state(conn, wa_chat_id)
        conn.execute(
            "UPDATE ai_group_state SET last_activity_at = ? WHERE wa_chat_id = ?",
            (now, wa_chat_id),
        )


def open_ai_window(wa_chat_id: str, now: int, customer_number: str, customer_name: str) -> None:
    with _conn() as conn:
        _ensure_ai_state(conn, wa_chat_id)
        conn.execute(
            """
            UPDATE ai_group_state SET
                window_open = 1,
                window_opened_at = ?,
                window_customer_number = ?,
                window_customer_name = ?,
                window_notified = 0
            WHERE wa_chat_id = ?
            """,
            (now, customer_number, customer_name, wa_chat_id),
        )


def mark_window_notified(wa_chat_id: str, now: int) -> None:
    """Fecha a janela após a IA ter efetivamente enviado uma mensagem ao grupo."""
    with _conn() as conn:
        conn.execute(
            """
            UPDATE ai_group_state SET
                window_open = 0,
                window_notified = 1,
                last_activity_at = ?
            WHERE wa_chat_id = ?
            """,
            (now, wa_chat_id),
        )


def close_ai_window(wa_chat_id: str) -> None:
    """Fecha a janela sem que a IA tenha enviado mensagem alguma (não altera last_activity_at,
    pois nenhuma atividade real ocorreu no grupo)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE ai_group_state SET window_open = 0, window_notified = 1 WHERE wa_chat_id = ?",
            (wa_chat_id,),
        )


def mark_our_response(wa_chat_id: str, now: int) -> None:
    with _conn() as conn:
        _ensure_ai_state(conn, wa_chat_id)
        conn.execute(
            """
            UPDATE ai_group_state SET
                last_our_response_at = ?,
                last_activity_at = ?,
                window_open = 0,
                window_notified = 0
            WHERE wa_chat_id = ?
            """,
            (now, now, wa_chat_id),
        )


def log_ai_customer_message(wa_chat_id: str, sender_number: str, sender_name: str, text: str, now: int) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO ai_customer_messages (wa_chat_id, sender_number, sender_name, text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (wa_chat_id, sender_number, sender_name, text, now),
        )


def get_ai_customer_messages_since(wa_chat_id: str, sender_number: str, since_ts: int) -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT text FROM ai_customer_messages
            WHERE wa_chat_id = ? AND sender_number = ? AND created_at >= ?
            ORDER BY created_at ASC
            """,
            (wa_chat_id, sender_number, since_ts),
        ).fetchall()
        return [row["text"] for row in rows if row["text"]]


def get_due_ai_windows(timeout_seconds: int) -> list[dict]:
    now = int(time.time())
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM ai_group_state
            WHERE window_open = 1
              AND window_notified = 0
              AND window_opened_at IS NOT NULL
              AND (? - window_opened_at) >= ?
            """,
            (now, timeout_seconds),
        ).fetchall()
        return [dict(row) for row in rows]


