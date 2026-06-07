"""Forex snapshot fetcher (provider-style helper).

Provides:
- DXY estimate (from DX-Y.NYB latest close)
- EUR/USD spot proxy (from EURUSD=X latest close)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .http import get_text


class ForexFetchError(RuntimeError):
    """Raised when forex snapshot fetch fails."""


def _stooq_last_close(symbol: str) -> float | None:
    url = f"https://stooq.com/q/l/?s={symbol}&i=d"
    try:
        text = get_text(url, timeout=15)
    except Exception:
        return None
    parts = [p.strip() for p in text.strip().split(",")]
    if len(parts) < 7:
        return None
    close = parts[6]
    if close.upper() == "N/D" or close == "":
        return None
    try:
        return float(close)
    except Exception:
        return None


def fetch_forex_snapshot() -> dict[str, Any]:
    # DX.F approximates DXY futures close; EURUSD and USDJPY from spot pairs.
    dxy = _stooq_last_close("dx.f")
    eurusd = _stooq_last_close("eurusd")
    usdjpy = _stooq_last_close("usdjpy")
    if dxy is None and eurusd is None and usdjpy is None:
        raise ForexFetchError("DXY, EURUSD and USDJPY all unavailable")

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "dxy_estimate": dxy,
        "eur_usd": eurusd,
        "usd_jpy": usdjpy,
        "_source": "kapy-provider:stooq",
    }
