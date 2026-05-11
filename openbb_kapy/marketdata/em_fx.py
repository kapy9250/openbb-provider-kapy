"""EM FX basket rates and stress index via yfinance."""
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

# USDXXX=X — higher value means EM currency weaker (more stress)
EM_PAIRS: dict[str, str] = {
    "USDTRY": "USDTRY=X",
    "USDBRL": "USDBRL=X",
    "USDZAR": "USDZAR=X",
    "USDMXN": "USDMXN=X",
    "USDINR": "USDINR=X",
    "USDEGP": "USDEGP=X",
    "USDPKR": "USDPKR=X",
    "USDARS": "USDARS=X",
}

STRESS_WINDOW = 30  # trading days


def _download(tickers: list[str], start: str, end: str | None = None) -> pd.DataFrame:
    kw = dict(start=start, auto_adjust=True, progress=False)
    if end:
        kw["end"] = end
    raw = yf.download(list(tickers), **kw)
    close = raw["Close"] if "Close" in raw else raw
    if isinstance(close.columns, pd.MultiIndex):
        close = close.droplevel(0, axis=1)
    ticker_to_pair = {v: k for k, v in EM_PAIRS.items()}
    close = close.rename(columns=ticker_to_pair)
    close.index = pd.to_datetime(close.index).normalize()
    return close


def fetch_em_fx_snapshot(lookback_days: int = 55) -> dict:
    """Fetch recent EM FX rates and compute the 30-day stress index."""
    today = datetime.now(timezone.utc).date()
    start = str(today - timedelta(days=lookback_days))

    df = _download(list(EM_PAIRS.values()), start=start)
    if df.empty:
        raise ValueError("yfinance returned no EM FX data")

    # Latest non-null rates
    latest_ts = df.index[-1]
    latest_date = latest_ts.date() if hasattr(latest_ts, "date") else latest_ts

    rates: dict[str, float] = {}
    for pair in EM_PAIRS:
        if pair in df.columns:
            s = df[pair].dropna()
            if not s.empty:
                rates[pair] = float(s.iloc[-1])

    # 30-day rolling pct change (positive = EM currency weakened = stress)
    pct_30d: dict[str, float] = {}
    for pair in EM_PAIRS:
        if pair not in df.columns:
            continue
        s = df[pair].dropna()
        if len(s) >= STRESS_WINDOW:
            chg = float(s.iloc[-1] / s.iloc[-STRESS_WINDOW] - 1)
            if not math.isnan(chg):
                pct_30d[pair] = chg

    stress = float(pd.Series(list(pct_30d.values())).mean()) if pct_30d else None

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": str(latest_date),
        "rates": rates,
        "pct_30d": pct_30d,
        "em_fx_stress": stress,
    }


def fetch_em_fx_history(start: str = "2000-01-01") -> pd.DataFrame:
    """Fetch full daily history for all EM pairs. Returns DataFrame indexed by date."""
    df = _download(list(EM_PAIRS.values()), start=start)
    df.index = [ts.date() if hasattr(ts, "date") else ts for ts in df.index]
    return df


def compute_stress_series(df: pd.DataFrame) -> pd.Series:
    """Compute daily 30-trading-day EM FX stress index from a history DataFrame."""
    pct = df.pct_change(periods=STRESS_WINDOW)
    stress = pct[[c for c in EM_PAIRS if c in pct.columns]].mean(axis=1, skipna=True)
    stress.index = [ts.date() if hasattr(ts, "date") else ts for ts in stress.index]
    return stress
