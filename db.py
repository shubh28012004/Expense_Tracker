"""
SQLite storage for expense / income transactions.

Single table `txns`. Database file lives next to this module (expenses.db).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).resolve().parent / "expenses.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS txns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT    NOT NULL,
    category   TEXT    NOT NULL,
    amount     REAL    NOT NULL,
    note       TEXT    NOT NULL DEFAULT '',
    type       TEXT    NOT NULL DEFAULT 'expense',
    chat_id    INTEGER,
    created_at TEXT    NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def add(
    amount: float,
    category: str,
    note: str = "",
    txn_type: str = "expense",
    chat_id: Optional[int] = None,
    date: Optional[str] = None,
) -> int:
    """Insert a transaction. Returns the new row id."""
    init_db()
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO txns (date, category, amount, note, type, chat_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (date, category, float(amount), note or "", txn_type, chat_id, created_at),
        )
        return int(cur.lastrowid)


def undo_last(chat_id: int) -> Optional[dict[str, Any]]:
    """Delete the most recent txn for this chat. Returns the deleted row or None."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM txns
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM txns WHERE id = ?", (row["id"],))
        return dict(row)


def all_rows() -> list[dict[str, Any]]:
    """Return every transaction, oldest first."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM txns ORDER BY date ASC, id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def month_total(month: str, txn_type: str = "expense") -> float:
    """
    Sum amounts for a calendar month.

    `month` is 'YYYY-MM'. Only rows whose `type` matches are included.
    """
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM txns
            WHERE type = ?
              AND substr(date, 1, 7) = ?
            """,
            (txn_type, month),
        ).fetchone()
        return float(row["total"])


def delete_all() -> None:
    """Wipe the table (used by tests)."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM txns")


def _person_key(note: str) -> str:
    name = (note or "").strip()
    if not name or name == "—":
        return "Unknown"
    return name.title()


def loan_balances() -> list[dict[str, Any]]:
    """
    Per-friend loan ledger.

    receivable = they owe you (lent − collected back)
    payable    = you owe them (borrowed − repaid)
    """
    people: dict[str, dict[str, float]] = {}
    for row in all_rows():
        t = row["type"]
        if t not in ("lend", "borrow", "collect", "repay"):
            continue
        key = _person_key(row["note"])
        bucket = people.setdefault(key, {"receivable": 0.0, "payable": 0.0})
        amt = float(row["amount"])
        if t == "lend":
            bucket["receivable"] += amt
        elif t == "collect":
            bucket["receivable"] -= amt
        elif t == "borrow":
            bucket["payable"] += amt
        elif t == "repay":
            bucket["payable"] -= amt

    out: list[dict[str, Any]] = []
    for name, bal in sorted(people.items()):
        rec = round(bal["receivable"], 2)
        pay = round(bal["payable"], 2)
        if abs(rec) < 0.01 and abs(pay) < 0.01:
            continue
        out.append({"name": name, "receivable": rec, "payable": pay})
    return out
