"""All SQL lives here. Nothing else imports psycopg.

Rules: values only via %s placeholders; Postgres types converted here to JSON-safe values.
The only f-strings interpolate hardcoded column names, never user input.
"""

from importlib.resources import files

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

pool = ConnectionPool(
    DATABASE_URL, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
)
SQL_DIR = files("support_bot") / "sql"


def open_pool(wait: bool = True, timeout: float = 10.0):
    pool.open(wait=wait, timeout=timeout)


def close_pool():
    pool.close()


def init_db(seed: bool = True):
    names = ("schema.sql", "seed.sql") if seed else ("schema.sql",)
    with pool.connection() as conn:
        for name in names:
            conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))


# --- sessions --------------------------------------------------------------

_SESSION_FIELDS = {
    "verified_order_id", "failed_attempts", "locked", "pending_action",
    "pending_turn", "last_decision", "last_reason", "action_taken",
}


def get_session(session_id):
    """Fetch the session row, creating it on first use."""
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id) VALUES (%s) ON CONFLICT DO NOTHING", (session_id,)
        )
        return conn.execute(
            "SELECT *, session_id::text AS session_id FROM sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()


def update_session(session_id, **fields):
    unknown = set(fields) - _SESSION_FIELDS
    if unknown:
        raise ValueError(f"Unknown session fields: {unknown}")
    if not fields:
        return
    sets = ", ".join(f"{name} = %s" for name in fields)
    with pool.connection() as conn:
        conn.execute(
            f"UPDATE sessions SET {sets} WHERE session_id = %s", (*fields.values(), session_id)
        )


def bump_user_turn(session_id):
    with pool.connection() as conn:
        return conn.execute(
            "UPDATE sessions SET user_turns = user_turns + 1 WHERE session_id = %s "
            "RETURNING user_turns",
            (session_id,),
        ).fetchone()["user_turns"]


def record_failed_attempt(session_id, max_attempts):
    """Atomic increment; locks the session when the limit is reached."""
    with pool.connection() as conn:
        return conn.execute(
            """
            UPDATE sessions
               SET failed_attempts = failed_attempts + 1,
                   locked = (failed_attempts + 1 >= %s)
             WHERE session_id = %s
            RETURNING failed_attempts, locked
            """,
            (max_attempts, session_id),
        ).fetchone()


# --- orders ----------------------------------------------------------------

_ORDER_COLUMNS = """
    o.order_id,
    o.status,
    o.total_amount::float                          AS total_amount,
    o.placed_at::date::text                        AS placed_at,
    o.delivered_at::date::text                     AS delivered_at,
    EXTRACT(DAY FROM now() - o.delivered_at)::int  AS days_since_delivery
"""


def find_order_id(order_id, contact):
    """Return the canonical order_id if contact (email OR phone) matches; else None.

    One answer for 'no such order' and 'wrong contact', so IDs can't be enumerated.
    Phones compare digits only and need at least 7 digits.
    """
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT o.order_id
              FROM orders o JOIN customers c ON c.customer_id = o.customer_id
             WHERE upper(o.order_id) = upper(%s)
               AND (
                    lower(c.email) = lower(%s)
                 OR (length(regexp_replace(%s, '[^0-9]', '', 'g')) >= 7
                     AND regexp_replace(coalesce(c.phone, ''), '[^0-9]', '', 'g')
                         = regexp_replace(%s, '[^0-9]', '', 'g'))
               )
            """,
            (order_id, contact, contact, contact),
        ).fetchone()
        return row["order_id"] if row else None


def get_order(order_id):
    with pool.connection() as conn:
        order = conn.execute(
            f"SELECT {_ORDER_COLUMNS} FROM orders o WHERE o.order_id = %s", (order_id,)
        ).fetchone()
        if order is None:
            return None
        order["items"] = conn.execute(
            "SELECT name, quantity, unit_price::float AS unit_price FROM order_items "
            "WHERE order_id = %s ORDER BY item_id",
            (order_id,),
        ).fetchall()
        return order


def cancel_order(order_id):
    """Idempotent: a second call reports already_cancelled instead of failing."""
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE orders SET status = 'cancelled' "
            "WHERE order_id = %s AND status = 'processing' RETURNING order_id",
            (order_id,),
        ).fetchone()
        if row:
            return {"cancelled": True, "already_cancelled": False}
        status = conn.execute(
            "SELECT status FROM orders WHERE order_id = %s", (order_id,)
        ).fetchone()
        if status and status["status"] == "cancelled":
            return {"cancelled": True, "already_cancelled": True}
        return {"cancelled": False, "already_cancelled": False}


def refund_order(session_id, order_id, amount):
    """Idempotent by UNIQUE(order_id): calling twice can never refund twice."""
    with pool.connection() as conn:  # one transaction
        row = conn.execute(
            "INSERT INTO refunds (order_id, session_id, amount) VALUES (%s, %s, %s) "
            "ON CONFLICT (order_id) DO NOTHING RETURNING refund_id::text",
            (order_id, session_id, amount),
        ).fetchone()
        if row is None:
            existing = conn.execute(
                "SELECT refund_id::text, amount::float AS amount FROM refunds WHERE order_id = %s",
                (order_id,),
            ).fetchone()
            return {**existing, "already_refunded": True}
        conn.execute("UPDATE orders SET status = 'refunded' WHERE order_id = %s", (order_id,))
        return {"refund_id": row["refund_id"], "amount": amount, "already_refunded": False}


def refund_exists(order_id):
    with pool.connection() as conn:
        return conn.execute(
            "SELECT 1 FROM refunds WHERE order_id = %s", (order_id,)
        ).fetchone() is not None


def get_order_status(order_id):
    with pool.connection() as conn:
        row = conn.execute("SELECT status FROM orders WHERE order_id = %s", (order_id,)).fetchone()
        return row["status"] if row else None


# --- escalations, audit, messages, cases -----------------------------------

def create_escalation(session_id, order_id, reason):
    with pool.connection() as conn:
        return conn.execute(
            "INSERT INTO escalations (session_id, order_id, reason) VALUES (%s, %s, %s) "
            "RETURNING escalation_id::text",
            (session_id, order_id, reason),
        ).fetchone()["escalation_id"]


def has_escalation(session_id):
    with pool.connection() as conn:
        return conn.execute(
            "SELECT 1 FROM escalations WHERE session_id = %s", (session_id,)
        ).fetchone() is not None


def log_action(session_id, tool, tool_input, result, ok):
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO actions (session_id, tool, input, result, ok) VALUES (%s, %s, %s, %s, %s)",
            (session_id, tool, Jsonb(tool_input), Jsonb(result), ok),
        )


def tools_called(session_id):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT tool FROM actions WHERE session_id = %s", (session_id,)
        ).fetchall()
        return {r["tool"] for r in rows}


def insert_message(session_id, role, content):
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
            (session_id, role, Jsonb(content)),
        )


def load_history(session_id):
    """Rebuild API-shaped history. tool_result rows go back to the API as role=user."""
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = %s ORDER BY message_id",
            (session_id,),
        ).fetchall()
    return [
        {"role": "user" if r["role"] == "tool_result" else r["role"], "content": r["content"]}
        for r in rows
    ]


def insert_case(session_id, order_id, issue_type, action_taken, outcome, reason):
    with pool.connection() as conn:
        return conn.execute(
            """
            INSERT INTO cases (session_id, order_id, issue_type, action_taken, outcome, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING case_id::text, session_id::text, order_id, issue_type, action_taken,
                      outcome, reason, created_at::text AS timestamp
            """,
            (session_id, order_id, issue_type, action_taken, outcome, reason),
        ).fetchone()
