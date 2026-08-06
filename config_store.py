"""Load / save config.json (local secrets — never exported to data.js)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from parser import CATEGORY_KEYWORDS

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

BUDGET_CATEGORIES = sorted(set(CATEGORY_KEYWORDS.keys()) | {"other", "loans"})


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or CONFIG_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    p = path or CONFIG_PATH
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def dashboard_url(cfg: dict[str, Any] | None = None) -> str:
    c = cfg if cfg is not None else load_config()
    return (c.get("dashboard_url") or "").strip().rstrip("/")
