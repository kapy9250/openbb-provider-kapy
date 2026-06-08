"""Forex snapshot fetcher (provider-style helper).

Provides:
- DXY estimate (from DX-Y.NYB latest close)
- EUR/USD spot proxy (from EURUSD=X latest close)
- USD/JPY spot proxy (from USDJPY=X latest close)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import yfinance as yf


class ForexFetchError(RuntimeError):
    """Raised when forex snapshot fetch fails."""


def _yfinance_last_close(ticker: str) -> tuple[float | None, date | None]:
    try:
        df = yf.download(
            ticker,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception:
        return None, None
    if df.empty or "Close" not in df:
        return None, None

    close = df["Close"]
    if hasattr(close, "columns"):
        close = close[ticker] if ticker in close.columns else close.iloc[:, 0]
    close = close.dropna()
    if close.empty:
        return None, None

    last_index = close.index[-1]
    if hasattr(last_index, "date"):
        obs_date = last_index.date()
    else:
        obs_date = datetime.now(timezone.utc).date()

    try:
        return float(close.iloc[-1]), obs_date
    except Exception:
        return None, None


def fetch_forex_snapshot() -> dict[str, Any]:
    dxy, dxy_date = _yfinance_last_close("DX-Y.NYB")
    eurusd, eurusd_date = _yfinance_last_close("EURUSD=X")
    usdjpy, usdjpy_date = _yfinance_last_close("USDJPY=X")
    if dxy is None and eurusd is None and usdjpy is None:
        raise ForexFetchError("DXY, EURUSD and USDJPY all unavailable")

    latest_date = max(d for d in (dxy_date, eurusd_date, usdjpy_date) if d is not None)

    return {
        "timestamp": latest_date.isoformat(),
        "dxy_estimate": dxy,
        "eur_usd": eurusd,
        "usd_jpy": usdjpy,
        "_source": "kapy-provider:yfinance",
    }
