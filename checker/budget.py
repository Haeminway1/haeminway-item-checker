"""Spending cap for the paid model.

Every call is priced from the usage the API returns and added to a ledger on
disk. Before a call, the service checks the month and day totals; once either
cap is reached the checker keeps working with rule checks only.

The owner's ceiling is 50,000 KRW per month. At a conservative 1,450 KRW/USD
that is about 34.5 USD; the cap below leaves headroom for exchange-rate moves
and price changes, and the day cap stops one bad day from spending the month.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

MODEL = "gpt-6-luna"
# USD per 1M tokens, OpenAI pricing page (checked 2026-09-27)
PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.10, 0.01, 0.50
MONTH_CAP_USD = float(os.environ.get("CHECKER_MONTH_CAP_USD", "30"))
DAY_CAP_USD = float(os.environ.get("CHECKER_DAY_CAP_USD", "1.5"))
LEDGER = Path(os.environ.get("CHECKER_LEDGER", str(Path.home() / ".local/state/haeminway-checker/budget.json")))
_lock = threading.Lock()


def _now():
    t = time.localtime()
    return f"{t.tm_year:04d}-{t.tm_mon:02d}", f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"


def _read() -> dict:
    try:
        return json.loads(LEDGER.read_text())
    except Exception:
        return {}


def _write(d: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, LEDGER)


def state() -> dict:
    month, day = _now()
    d = _read()
    return {"month": month, "month_usd": d.get("months", {}).get(month, 0.0),
            "day": day, "day_usd": d.get("days", {}).get(day, 0.0),
            "month_cap": MONTH_CAP_USD, "day_cap": DAY_CAP_USD, "calls": d.get("calls", {}).get(month, 0)}


def allowed(estimate_usd: float = 0.002) -> bool:
    s = state()
    return s["month_usd"] + estimate_usd <= MONTH_CAP_USD and s["day_usd"] + estimate_usd <= DAY_CAP_USD


def charge(usage: dict) -> float:
    """Add one call's cost from an OpenAI usage object; returns its USD cost."""
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    cached = int(details.get("cached_tokens") or 0)
    out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    cost = ((prompt - cached) * PRICE_IN + cached * PRICE_CACHED + out * PRICE_OUT) / 1_000_000
    month, day = _now()
    with _lock:
        d = _read()
        d.setdefault("months", {})[month] = round(d.get("months", {}).get(month, 0.0) + cost, 6)
        days = d.setdefault("days", {})
        days[day] = round(days.get(day, 0.0) + cost, 6)
        for k in sorted(days)[:-40]:  # keep ~40 days
            days.pop(k)
        d.setdefault("calls", {})[month] = d.get("calls", {}).get(month, 0) + 1
        _write(d)
    return cost
