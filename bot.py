"""
Telegram bot for the personal expense tracker.

Reads token + budgets from config.json. Every logged message is parsed,
stored in SQLite, then data.js is regenerated for the offline dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
import export as exporter
from config_store import BUDGET_CATEGORIES, dashboard_url, load_config, save_config
from parser import parse

ROOT = Path(__file__).resolve().parent

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("expense-bot")


def _currency() -> str:
    return load_config().get("currency", "₹")


def _fmt(amount: float) -> str:
    """Indian-style grouping: ₹12,34,567.50"""
    cur = _currency()
    negative = amount < 0
    amount = abs(amount)
    whole = int(amount)
    frac = round(amount - whole, 2)
    s = str(whole)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while rest:
            parts.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(reversed(parts)) + "," + last3
    if frac:
        result = f"{cur}{grouped}.{int(round(frac * 100)):02d}"
    else:
        result = f"{cur}{grouped}"
    return f"-{result}" if negative else result


def _progress_bar(spent: float, budget: float, width: int = 12) -> str:
    if budget <= 0:
        return "░" * width
    ratio = max(0.0, min(1.0, spent / budget))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _month_label(month: str | None = None) -> str:
    m = month or _current_month()
    dt = datetime.strptime(m + "-01", "%Y-%m-%d")
    return dt.strftime("%B %Y")


def _with_dashboard(text: str) -> str:
    url = dashboard_url()
    if url:
        return f"{text}\n\n📱 Dashboard\n{url}"
    return (
        f"{text}\n\n📱 Dashboard\n"
        "Not set yet — /setdashboard https://your-app.vercel.app"
    )


def _publish() -> None:
    exporter.export_and_publish()


def _parse_amount_arg(raw: str) -> float:
    return float(raw.replace(",", "").replace("_", ""))


def _confirm_line(result: dict) -> str:
    amt = result["amount"]
    t = result["type"]
    labels = {
        "income": f"✅ Income +{_fmt(amt)}",
        "expense": f"✅ Logged −{_fmt(amt)}",
        "lend": f"🤝 Lent −{_fmt(amt)}",
        "borrow": f"🤝 Borrowed +{_fmt(amt)}",
        "collect": f"🤝 Collected +{_fmt(amt)}",
        "repay": f"🤝 Repaid −{_fmt(amt)}",
    }
    return labels.get(t, f"✅ Saved {_fmt(amt)}")


def _undo_sign(txn_type: str) -> str:
    if txn_type in ("income", "borrow", "collect"):
        return "+"
    return "−"


# ── Commands ───────────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        _with_dashboard(
            "Expense tracker online.\n\n"
            "Just text me what you spent or earned:\n"
            "  • spent 500 on ola\n"
            "  • swiggy 420 dinner\n"
            "  • got salary 75000\n"
            "  • lent 500 to Rahul\n\n"
            "Commands:\n"
            "  /help — show usage and commands\n"
            "  /total — monthly spending summary\n"
            "  /undo — undo last entry\n"
            "  /budget — view budgets and caps\n"
            "  /loans — show friend loan balances\n"
            "  /setbudget <amount> — set monthly budget\n"
            "  /setcap <category> <amount> — set category cap\n"
            "  /setdashboard <url> — set dashboard URL\n"
            "  /setsync on|off — toggle GitHub sync"
        )
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cats = ", ".join(BUDGET_CATEGORIES)
    await update.message.reply_text(
        _with_dashboard(
            "HOW TO LOG\n"
            "──────────\n"
            "Plain message + amount → category auto-detected.\n\n"
            "Amounts: 500 · 1.5k · 2l · ₹800 · rs 500\n\n"
            f"Categories: {cats}\n\n"
            "Friend loans:\n"
            "  lent 500 to Rahul · borrowed 2k from Amit\n"
            "  Rahul paid back 500 · paid Rahul back 500\n\n"
            "COMMANDS\n"
            "/total /undo /budget /loans\n"
            "/setbudget 50000 — monthly cap\n"
            "/setcap food 8000 — category cap\n"
            "/setdashboard <url> — mobile dashboard link\n"
            "/setsync on|off — auto-push data to GitHub"
        )
    )


async def cmd_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = load_config()
    month = _current_month()
    spent = db.month_total(month, "expense")
    income = db.month_total(month, "income")
    budget = float(cfg.get("monthlyBudget", 0))
    pct = (spent / budget * 100) if budget else 0
    bar = _progress_bar(spent, budget)
    remaining = budget - spent

    lines = [
        f"📊 {_month_label(month)}",
        f"Spent   {_fmt(spent)} / {_fmt(budget)}  ({pct:.0f}%)",
        f"[{bar}]",
        f"Left    {_fmt(remaining)}",
        f"Income  {_fmt(income)}",
    ]
    await update.message.reply_text(_with_dashboard("\n".join(lines)))


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    deleted = db.undo_last(chat_id)
    if deleted is None:
        await update.message.reply_text(_with_dashboard("Nothing to undo."))
        return
    _publish()
    sign = _undo_sign(deleted["type"])
    await update.message.reply_text(
        _with_dashboard(
            f"Undone: {sign}{_fmt(deleted['amount'])} "
            f"[{deleted['type']}/{deleted['category']}] {deleted['note']}"
        )
    )


async def cmd_loans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    balances = db.loan_balances()
    if not balances:
        await update.message.reply_text(
            _with_dashboard(
                "No open friend loans.\n\n"
                "Examples:\n"
                "  lent 500 to Rahul\n"
                "  borrowed 2k from Amit"
            )
        )
        return

    lines = ["🤝 Friend ledger", ""]
    total_rec = 0.0
    total_pay = 0.0
    for row in balances:
        name = row["name"]
        rec = float(row["receivable"])
        pay = float(row["payable"])
        if rec > 0.01:
            lines.append(f"{name} owes you  {_fmt(rec)}")
            total_rec += rec
        if pay > 0.01:
            lines.append(f"You owe {name}  {_fmt(pay)}")
            total_pay += pay
    lines.append("")
    if total_rec > 0:
        lines.append(f"Total receivable  {_fmt(total_rec)}")
    if total_pay > 0:
        lines.append(f"Total payable     {_fmt(total_pay)}")
    await update.message.reply_text(_with_dashboard("\n".join(lines)))


async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = load_config()
    month = _current_month()
    budgets: dict = cfg.get("budgets", {})
    monthly = float(cfg.get("monthlyBudget", 0))

    lines = [f"📋 Budgets — {_month_label(month)}", f"Monthly  {_fmt(monthly)}", ""]
    for cat, cap in budgets.items():
        spent = 0.0
        for row in db.all_rows():
            if (
                row["type"] == "expense"
                and row["category"] == cat
                and row["date"][:7] == month
            ):
                spent += row["amount"]
        flag = " ⚠" if spent > float(cap) else ""
        bar = _progress_bar(spent, float(cap), width=8)
        lines.append(
            f"{cat:<12} [{bar}] {_fmt(spent)} / {_fmt(float(cap))}{flag}"
        )
    lines.append("\nChange: /setbudget · /setcap food 8000")
    await update.message.reply_text(_with_dashboard("\n".join(lines)))


async def cmd_setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            _with_dashboard("Usage: /setbudget 50000")
        )
        return
    try:
        amount = _parse_amount_arg(context.args[0])
    except ValueError:
        await update.message.reply_text(_with_dashboard("Invalid amount."))
        return
    if amount <= 0:
        await update.message.reply_text(_with_dashboard("Budget must be > 0."))
        return
    cfg = load_config()
    cfg["monthlyBudget"] = amount
    save_config(cfg)
    _publish()
    await update.message.reply_text(
        _with_dashboard(f"Monthly budget set to {_fmt(amount)}.")
    )


async def cmd_setcap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) != 2:
        cats = ", ".join(BUDGET_CATEGORIES)
        await update.message.reply_text(
            _with_dashboard(f"Usage: /setcap food 8000\nCategories: {cats}")
        )
        return
    cat = context.args[0].lower()
    try:
        amount = _parse_amount_arg(context.args[1])
    except ValueError:
        await update.message.reply_text(_with_dashboard("Invalid amount."))
        return
    if amount < 0:
        await update.message.reply_text(_with_dashboard("Cap must be ≥ 0."))
        return
    cfg = load_config()
    budgets = cfg.setdefault("budgets", {})
    budgets[cat] = amount
    save_config(cfg)
    _publish()
    await update.message.reply_text(
        _with_dashboard(f"Cap for {cat} set to {_fmt(amount)}.")
    )


async def cmd_setdashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        url = dashboard_url()
        await update.message.reply_text(
            _with_dashboard(
                f"Current URL: {url or '(not set)'}\n\n"
                "Usage: /setdashboard https://your-app.vercel.app"
            )
        )
        return
    url = context.args[0].strip().rstrip("/")
    if not url.startswith("https://") and not url.startswith("http://"):
        await update.message.reply_text(
            _with_dashboard("URL must start with https://")
        )
        return
    cfg = load_config()
    cfg["dashboard_url"] = url
    save_config(cfg)
    await update.message.reply_text(
        _with_dashboard(f"Dashboard link saved.\nI'll send this after every message:\n{url}")
    )


async def cmd_setsync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].lower() not in ("on", "off", "true", "false"):
        cfg = load_config()
        state = "on" if cfg.get("github_sync") else "off"
        await update.message.reply_text(
            _with_dashboard(
                f"github_sync is {state}.\n\n"
                "Usage: /setsync on — push data.js to GitHub after each log\n"
                "       /setsync off"
            )
        )
        return
    on = context.args[0].lower() in ("on", "true")
    cfg = load_config()
    cfg["github_sync"] = on
    save_config(cfg)
    await update.message.reply_text(
        _with_dashboard(
            f"GitHub sync {'enabled' if on else 'disabled'}.\n"
            "When on, each log commits data.js so Vercel redeploys."
        )
    )


# ── Free-text logging ──────────────────────────────────────────────────────


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return

    result = parse(text)
    if result is None:
        await update.message.reply_text(
            _with_dashboard(
                "Couldn't find an amount. Try:\n"
                "  spent 500 on ola\n"
                "  swiggy 420 dinner"
            )
        )
        return

    chat_id = update.effective_chat.id
    row_id = db.add(
        amount=result["amount"],
        category=result["category"],
        note=result["note"],
        txn_type=result["type"],
        chat_id=chat_id,
    )
    _publish()

    cfg = load_config()
    month = _current_month()
    spent = db.month_total(month, "expense")
    budget = float(cfg.get("monthlyBudget", 0))
    pct = (spent / budget * 100) if budget else 0
    bar = _progress_bar(spent, budget)

    head = _confirm_line(result)

    extra = ""
    if result["type"] in ("lend", "borrow", "collect", "repay"):
        bal = db.loan_balances()
        person = (result["note"] or "").strip().title()
        for row in bal:
            if row["name"].lower() == person.lower():
                if float(row["receivable"]) > 0.01:
                    extra = f"\n{row['name']} still owes you {_fmt(row['receivable'])}"
                elif float(row["payable"]) > 0.01:
                    extra = f"\nYou still owe {row['name']} {_fmt(row['payable'])}"
                else:
                    extra = f"\nSettled with {row['name']} ✓"
                break

    reply = (
        f"{head}\n"
        f"[{result['category']}] {result['note']}\n"
        f"#{row_id}{extra}\n\n"
        f"{_month_label(month)}  {_fmt(spent)} / {_fmt(budget)}  ({pct:.0f}%)\n"
        f"[{bar}]"
    )
    await update.message.reply_text(_with_dashboard(reply))


def main() -> None:
    cfg = load_config()
    token = cfg.get("telegram_token", "")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit(
            "Set telegram_token in config.json (get one from @BotFather)."
        )

    db.init_db()
    exporter.export_and_publish()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("total", cmd_total))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("budget", cmd_budget))
    app.add_handler(CommandHandler("loans", cmd_loans))
    app.add_handler(CommandHandler("setbudget", cmd_setbudget))
    app.add_handler(CommandHandler("setcap", cmd_setcap))
    app.add_handler(CommandHandler("setdashboard", cmd_setdashboard))
    app.add_handler(CommandHandler("setsync", cmd_setsync))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Bot starting — dashboard at %s", ROOT / "dashboard.html")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
