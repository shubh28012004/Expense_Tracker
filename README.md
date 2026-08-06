# Personal Expense Tracker (Telegram → SQLite → Offline Dashboard)

Log spending in plain English via Telegram. Everything stays on your machine: a local SQLite database and a double-click HTML dashboard. No cloud, no web server, no paid apps.

## Setup (5 steps)

1. **Create a bot token**  
   Open Telegram, talk to [@BotFather](https://t.me/BotFather), run `/newbot`, and copy the token.

2. **Put the token in `config.json`**  
   Replace `YOUR_BOT_TOKEN_HERE` with your token. Adjust `monthlyBudget`, `currency`, and per-category `budgets` as you like.

3. **Install the dependency**
   ```bash
   pip install -r requirements.txt
   ```
   (or: `pip install python-telegram-bot`)

4. **Start the bot**
   ```bash
   python bot.py
   ```
   Leave this terminal open. Message your bot on Telegram.

5. **Open the dashboard**  
   Double-click `dashboard.html` (or open it in any browser). It reads `data.js` via a `<script>` tag — no server needed. After every log, the bot regenerates `data.js` so a refresh shows fresh numbers.

## Example messages

| You type | What happens |
|---|---|
| `spent 500 on ola` | −₹500 · travel |
| `swiggy 420 dinner` | −₹420 · food |
| `1.5k myntra shirt` | −₹1,500 · clothes |
| `rs 1,250 blinkit` | −₹1,250 · groceries |
| `2l rent` | −₹2,00,000 · rent |
| `got salary 75000` | +₹75,000 · income |
| `refund 200 from amazon` | +₹200 · income |
| `sip 5000 groww` | −₹5,000 · investments |
| `lent 500 to Rahul` | Loan given · Rahul owes you |
| `borrowed 2k from Amit` | Loan taken · you owe Amit |
| `Rahul paid back 500` | Friend repaid you |
| `paid Rahul back 500` | You repaid a friend |

Amounts understand: `500`, `1,250`, `1.5k`, `2l`, `₹500`, `rs 500`, `500rs`.

Friend loans are **not** counted in your monthly expense budget. Use `/loans` to see who owes whom.

## Bot commands

- `/start` `/help` — how to use
- `/total` — this month’s spend vs budget (with a progress bar)
- `/undo` — delete your last entry
- `/budget` — show category caps and progress
- `/loans` — friend loan ledger

## Files

| File | Role |
|---|---|
| `parser.py` | Message → `{amount, category, note, type}` |
| `db.py` | SQLite (`expenses.db`) helpers |
| `export.py` | Writes `data.js` (never includes the bot token) |
| `bot.py` | Telegram bot |
| `config.json` | Token, currency, budgets |
| `dashboard.html` | Offline charts (inline SVG) |
| `data.js` | Auto-generated; loaded by the dashboard |

## Customise

- **Categories / keywords** — edit `CATEGORY_KEYWORDS`, `INCOME_KEYWORDS`, and `LOAN_*_KEYWORDS` at the top of `parser.py`.
- **Currency & caps** — edit `config.json` (`currency`, `monthlyBudget`, `budgets`).
- **Database** — single file `expenses.db` next to the scripts. Delete it to start fresh.

## Privacy

Nothing leaves your machine except the messages you send to Telegram’s API so the bot can reply. All stored data is local SQLite + `data.js`. The bot token is never written into browser-facing files.
