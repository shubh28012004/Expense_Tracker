"""
Parse plain-English expense/income messages into structured records.

Edit CATEGORY_KEYWORDS and INCOME_KEYWORDS below to customise matching.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Easy-to-edit keyword maps  (add synonyms freely)
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "travel": [
        "ola", "uber", "rapido", "metro", "train", "flight", "taxi", "cab",
        "petrol", "diesel", "fuel", "parking", "toll", "bus", "auto",
        "irctc", "makemytrip", "mmt", "indigo", "airindia", "goibibo",
        "commute", "travel", "trip", "fare",
    ],
    "food": [
        "swiggy", "zomato", "chai", "coffee", "tea", "lunch", "dinner",
        "breakfast", "restaurant", "cafe", "pizza", "burger", "biryani",
        "food", "meal", "snack", "mcdonalds", "dominos", "kfc", "starbucks",
        "barista", "juice", "icecream", "dessert", "dhaba", "canteen",
    ],
    "groceries": [
        "blinkit", "zepto", "bigbasket", "instamart", "grocery", "groceries",
        "milk", "vegetables", "veggies", "fruits", "kirana", "supermarket",
        "dmart", "reliance fresh", "nature basket", "provisions",
    ],
    "clothes": [
        "myntra", "ajio", "fashion", "shirt", "pants", "jeans", "shoes",
        "clothes", "clothing", "dress", "kurta", "saree", "nike", "adidas",
        "zara", "h&m", "uniqlo", "meesho", "flipkart fashion",
    ],
    "rent": [
        "rent", "house rent", "pg", "hostel", "lease", "deposit",
        "maintenance", "society",
    ],
    "bills": [
        "electricity", "water bill", "gas", "wifi", "internet", "broadband",
        "phone bill", "recharge", "mobile", "jio", "airtel", "vi ",
        "utility", "bill", "emi", "loan emi", "insurance premium",
    ],
    "luxuries": [
        "netflix", "spotify", "prime", "hotstar", "disney", "gym", "movie",
        "cinema", "pvr", "inox", "concert", "party", "club", "spa",
        "salon", "gaming", "playstation", "xbox", "steam", "luxury",
        "perfume", "watch", "jewellery", "jewelry",
    ],
    "investments": [
        "sip", "etf", "stocks", "mutual fund", "mf", "nps", "ppf", "fd",
        "investment", "invest", "shares", "crypto", "bitcoin", "gold",
        "zerodha", "groww", "upstox", "kuvera", "fixed deposit",
    ],
    "health": [
        "doctor", "hospital", "medicine", "pharmacy", "medical", "clinic",
        "dental", "dentist", "lab test", "health", "apollo", "1mg",
        "pharmeasy", "netmeds", "consultation", "checkup",
    ],
    "education": [
        "course", "tuition", "school", "college", "books", "udemy",
        "coursera", "education", "exam", "fees", "fee", "coaching",
        "training", "workshop", "certification",
    ],
}

INCOME_KEYWORDS: list[str] = [
    "salary", "refund", "cashback", "received", "credited", "income",
    "got paid", "paycheck", "bonus", "dividend", "interest received",
    "freelance", "client paid", "reimbursement", "stipend", "got salary",
]

# Friend loans — edit these lists to match how you text
LOAN_LEND_KEYWORDS: list[str] = [
    "lent ", "lent to", "loan to", "loaned to", "gave loan", "udhari diya",
]
LOAN_BORROW_KEYWORDS: list[str] = [
    "borrowed", "borrow from", "borrowed from", "loan from", "loaned from",
    "took from", "took loan", "udhari liya",
]

FILLER_WORDS: set[str] = {
    "spent", "spend", "spending", "paid", "pay", "bought", "buy", "on",
    "for", "rs", "inr", "rupees", "rupee", "of", "a", "an", "the", "to",
    "from", "via", "with", "my", "got", "was", "is", "at", "and",
    "lent", "loan", "loaned", "borrowed", "borrow", "friend", "back",
    "repaid", "returned", "gave", "took", "udhari", "diya", "liya",
    "settled", "collected", "collect",
}

# Amount patterns: 1.5k, 2l, 2.5cr, ₹1,250, rs 500, 500rs, plain 500
# Comma form requires at least one comma so "75000" is not split into "750"+"00".
# Suffix must be glued to the number (1.5k / 2l) so "500 lunch" is not 500 lakh.
_AMOUNT_RE = re.compile(
    r"""
    (?:₹|rs\.?\s*|inr\s*)?              # optional currency prefix
    (?P<num>
          \d{1,3}(?:,\d{2,3})+(?:\.\d+)?  # 1,250 or 12,34,567
        | \d+(?:\.\d+)?                    # 500, 75000, 1.5
    )
    (?P<suffix>[kKlL]|[cC][rR])?         # glued k / l / cr
    (?:\s*(?:rs\.?|inr|₹))?             # optional currency suffix
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _parse_amount(text: str) -> Optional[tuple[float, str]]:
    """Return (amount, matched_substring) or None."""
    best: Optional[tuple[float, str]] = None

    for m in _AMOUNT_RE.finditer(text):
        raw = m.group("num").replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue

        suffix = (m.group("suffix") or "").lower()
        if suffix == "k":
            value *= 1_000
        elif suffix == "l":
            value *= 100_000
        elif suffix == "cr":
            value *= 10_000_000

        if value <= 0:
            continue

        matched = m.group(0)
        # Prefer the match that yields the larger amount; tie-break on longer text
        if best is None or value > best[0] or (
            value == best[0] and len(matched) > len(best[1])
        ):
            best = (value, matched)

    if best is None:
        return None
    return best


def _detect_type(text: str) -> str:
    lower = text.lower()

    # Settlements (check before generic income/expense)
    if any(k in lower for k in ("paid back to", "returned to", "repaid ")):
        return "repay"
    if re.search(r"\bpaid\s+\w+\s+back\b", lower):
        return "repay"
    if re.search(r"\w+\s+paid\s+back\b", lower) or "got back" in lower:
        return "collect"
    if "paid back" in lower and " from " in lower:
        return "collect"

    for kw in LOAN_BORROW_KEYWORDS:
        if kw in lower:
            return "borrow"
    for kw in LOAN_LEND_KEYWORDS:
        if kw in lower:
            return "lend"
    if lower.startswith("lent"):
        return "lend"

    for kw in INCOME_KEYWORDS:
        if kw in lower:
            return "income"
    return "expense"


def _detect_category(text: str) -> str:
    lower = text.lower()
    # Score by longest keyword match so "mutual fund" beats "fund"-less noise
    best_cat = "other"
    best_len = 0
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower and len(kw) > best_len:
                best_cat = cat
                best_len = len(kw)
    return best_cat


def _build_note(text: str, amount_match: str) -> str:
    # Remove the amount substring (first occurrence, case-insensitive)
    note = re.sub(re.escape(amount_match), " ", text, count=1, flags=re.IGNORECASE)
    # Strip currency leftovers and punctuation noise
    note = re.sub(r"[₹]", " ", note)
    words = re.split(r"\s+", note.strip())
    kept = []
    for w in words:
        cleaned = w.strip(".,!?;:\"'()[]{}").lower()
        if not cleaned or cleaned in FILLER_WORDS:
            continue
        # Drop bare currency tokens
        if cleaned in ("rs", "rs.", "inr"):
            continue
        kept.append(w.strip(".,!?;:\"'()[]{}"))
    return " ".join(kept).strip() or "—"


def parse(message: str) -> Optional[dict]:
    """
    Turn a free-text message into
        {amount, category, note, type: expense|income|lend|borrow|collect|repay}
    or None if no amount can be found.
    """
    if not message or not message.strip():
        return None

    text = message.strip()
    amount_info = _parse_amount(text)
    if amount_info is None:
        return None

    amount, matched = amount_info
    txn_type = _detect_type(text)
    if txn_type in ("lend", "borrow", "collect", "repay"):
        category = "loans"
    else:
        category = _detect_category(text)
    # Income without a clear category stays "other"
    if txn_type == "income" and category == "other":
        # Try a light income-side categorisation
        lower = text.lower()
        if any(k in lower for k in ("salary", "paycheck", "stipend", "bonus")):
            category = "other"
        elif any(k in lower for k in ("dividend", "sip", "stocks", "interest")):
            category = "investments"

    note = _build_note(text, matched)

    return {
        "amount": round(amount, 2),
        "category": category,
        "note": note,
        "type": txn_type,
    }


if __name__ == "__main__":
    samples = [
        "spent 500 on ola",
        "swiggy 420 dinner",
        "1.5k myntra shirt",
        "got salary 75000",
        "2l rent deposit",
        "rs 1,250 blinkit",
        "₹800 netflix",
        "paid 300rs for chai",
        "refund 200 from amazon",
        "sip 5000 groww",
        "lent 500 to Rahul",
        "borrowed 2k from Amit",
        "Rahul paid back 500",
    ]
    for s in samples:
        print(f"{s!r:40s} → {parse(s)}")
