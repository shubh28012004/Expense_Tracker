"""End-to-end tests for parser + SQLite storage + export (no Telegram)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure local imports resolve
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import db
import export as exporter
from parser import parse


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_parser() -> None:
    cases = [
        ("spent 500 on ola", 500, "travel", "expense"),
        ("swiggy 420 dinner", 420, "food", "expense"),
        ("1.5k myntra shirt", 1500, "clothes", "expense"),
        ("got salary 75000", 75000, "other", "income"),
        ("2l rent", 200000, "rent", "expense"),
        ("rs 1,250 blinkit", 1250, "groceries", "expense"),
        ("₹800 netflix", 800, "luxuries", "expense"),
        ("paid 300rs for chai", 300, "food", "expense"),
        ("refund 200 from amazon", 200, "other", "income"),
        ("sip 5000 groww", 5000, "investments", "expense"),
        ("zepto 890 groceries", 890, "groceries", "expense"),
        ("cashback 50", 50, "other", "income"),
        ("doctor 1200 checkup", 1200, "health", "expense"),
        ("udemy 499 course", 499, "education", "expense"),
        ("lent 500 to Rahul", 500, "loans", "lend"),
        ("borrowed 2k from Amit", 2000, "loans", "borrow"),
        ("Rahul paid back 500", 500, "loans", "collect"),
        ("paid Rahul back 500", 500, "loans", "repay"),
    ]
    for msg, amount, category, txn_type in cases:
        r = parse(msg)
        check(r is not None, f"parse failed for {msg!r}")
        check(r["amount"] == amount, f"{msg!r}: amount {r['amount']} != {amount}")
        check(r["category"] == category, f"{msg!r}: category {r['category']} != {category}")
        check(r["type"] == txn_type, f"{msg!r}: type {r['type']} != {txn_type}")
        check(isinstance(r["note"], str) and len(r["note"]) > 0, f"{msg!r}: empty note")

    check(parse("hello there") is None, "should reject messages with no amount")
    check(parse("") is None, "should reject empty")
    print("parser: OK (%d cases)" % len(cases))


def test_db_and_export() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db.DB_PATH = tmp_path / "test.db"
        data_js = tmp_path / "data.js"

        # Point export at a temp config + data.js
        cfg = {
            "telegram_token": "SECRET_TOKEN_DO_NOT_LEAK",
            "currency": "₹",
            "monthlyBudget": 50000,
            "budgets": {"food": 8000, "travel": 5000},
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        exporter.CONFIG_PATH = cfg_path
        exporter.DATA_JS_PATH = data_js

        db.init_db()
        db.delete_all()

        id1 = db.add(500, "travel", "ola", "expense", chat_id=42, date="2026-08-01")
        id2 = db.add(420, "food", "swiggy dinner", "expense", chat_id=42, date="2026-08-02")
        id3 = db.add(75000, "other", "salary", "income", chat_id=42, date="2026-08-01")
        check(id1 > 0 and id2 > 0 and id3 > 0, "ids should be positive")

        rows = db.all_rows()
        check(len(rows) == 3, f"expected 3 rows, got {len(rows)}")

        spent = db.month_total("2026-08", "expense")
        check(spent == 920, f"month expense total {spent} != 920")
        income = db.month_total("2026-08", "income")
        check(income == 75000, f"month income {income} != 75000")

        deleted = db.undo_last(42)
        check(deleted is not None and deleted["id"] == id3, "undo should remove last row")
        check(len(db.all_rows()) == 2, "should have 2 rows after undo")
        check(db.undo_last(999) is None, "undo other chat should be None")

        out = exporter.export(data_js)
        text = out.read_text(encoding="utf-8")
        check("window.EXPENSE_DATA" in text, "data.js missing EXPENSE_DATA")
        check("window.EXPENSE_CONFIG" in text, "data.js missing EXPENSE_CONFIG")
        check("SECRET_TOKEN_DO_NOT_LEAK" not in text, "token leaked into data.js!")
        check("telegram_token" not in text, "telegram_token key leaked into data.js!")
        check('"currency": "₹"' in text or '"currency":"₹"' in text, "currency missing")

        # Execute-ish sanity: JSON extracts
        check("ola" in text and "swiggy dinner" in text, "notes missing from export")

        db.add(500, "loans", "Rahul", "lend", chat_id=42)
        db.add(200, "loans", "Rahul", "collect", chat_id=42)
        db.add(1000, "loans", "Amit", "borrow", chat_id=42)
        bal = db.loan_balances()
        rahul = next(b for b in bal if b["name"] == "Rahul")
        amit = next(b for b in bal if b["name"] == "Amit")
        check(rahul["receivable"] == 300, f"Rahul receivable {rahul['receivable']}")
        check(amit["payable"] == 1000, f"Amit payable {amit['payable']}")

        print("db + export: OK")


if __name__ == "__main__":
    test_parser()
    test_db_and_export()
    print("\nAll end-to-end tests passed.")
