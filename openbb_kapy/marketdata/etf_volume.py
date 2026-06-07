"""ETF volume snapshot fetcher (provider-style helper).

Source: Yahoo Finance chart API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .http import get_json


ETF_CONFIG: dict[str, dict[str, str]] = {
    "SPY": {"category": "us_equity"},
    "QQQ": {"category": "us_equity"},
    "IWM": {"category": "us_equity"},
    "DIA": {"category": "us_equity"},
    "TLT": {"category": "us_bonds"},
    "IEF": {"category": "us_bonds"},
    "SHY": {"category": "us_bonds"},
    "BND": {"category": "us_bonds"},
    "TIP": {"category": "us_bonds"},
    "HYG": {"category": "us_bonds"},
    "LQD": {"category": "us_bonds"},
    "GLD": {"category": "gold"},
    "IAU": {"category": "gold"},
    "USO": {"category": "oil"},
    "BNO": {"category": "oil"},
    "DBC": {"category": "commodities"},
    "GSG": {"category": "commodities"},
    "UUP": {"category": "forex"},
    "FXE": {"category": "forex"},
    "EEM": {"category": "em_equity"},
    "VWO": {"category": "em_equity"},
}


class EtfVolumeFetchError(RuntimeError):
    """Raised when ETF volume fetch fails."""


def _fetch_quote(symbol: str) -> dict[str, Any] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    obj = get_json(url, timeout=20)
    result = (((obj.get("chart") or {}).get("result") or [None])[0])
    if not result:
        return None

    meta = result.get("meta") or {}
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    timestamps = result.get("timestamp") or []
    if not timestamps:
        return None
    last_idx = len(timestamps) - 1

    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    volume_list = quote.get("volume") or []
    volume = volume_list[last_idx] if last_idx < len(volume_list) else None

    if price is None or prev_close in (None, 0) or volume in (None, 0):
        return None

    price = float(price)
    prev_close = float(prev_close)
    volume = float(volume)

    return {
        "price": price,
        "volume": volume,
        "change_pct": ((price / prev_close) - 1.0) * 100.0,
        "dollar_volume": price * volume,
    }


def fetch_etf_volume_snapshot() -> dict[str, Any]:
    etfs: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for ticker, cfg in ETF_CONFIG.items():
        try:
            q = _fetch_quote(ticker)
            if not q:
                continue
            etfs[ticker] = {
                "category": cfg.get("category"),
                "price": q["price"],
                "volume": q["volume"],
                "dollar_volume": q["dollar_volume"],
                "change_pct": q["change_pct"],
            }
        except Exception as e:  # pragma: no cover
            errors.append(f"{ticker}: {e}")

    if not etfs:
        raise EtfVolumeFetchError("no etf quote extracted")

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "etfs": etfs,
        "_source": "kapy-provider:yahoo-chart",
    }
    if errors:
        out["_warnings"] = errors
    return out
