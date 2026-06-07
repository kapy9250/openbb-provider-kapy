"""Derivatives snapshot fetcher (provider-style helper).

Current source strategy:
- Binance public API (funding / long-short / open-interest)
- Coinalyze API (liquidations)

Returns a normalized payload aligned with legacy market-data shape so downstream
pipeline migration can be incremental.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .http import get_json


class DerivativesFetchError(RuntimeError):
    """Raised when derivatives fetch fails."""


def fetch_derivatives_snapshot() -> dict[str, Any]:
    """Fetch derivatives snapshot from Binance and normalize structure."""
    now = datetime.now(timezone.utc).isoformat()

    out: dict[str, Any] = {
        "timestamp": now,
        "binance": {"btc_funding": [], "long_short": [], "top_account": [], "top_position": [], "taker_ratio": []},
        "coinalyze": {"oi": [], "funding": [], "predicted_funding": [], "liquidations": []},
        "deribit": {"btc_dvol": []},
        "coinglass": {},
    }

    errors: list[str] = []

    # 1) Funding (BTC)
    try:
        funding = get_json("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=5", timeout=15)
        if isinstance(funding, list):
            out["binance"]["btc_funding"] = [
                {
                    "symbol": x.get("symbol"),
                    "fundingRate": float(x.get("fundingRate")) if x.get("fundingRate") is not None else None,
                    "fundingTime": int(x.get("fundingTime")) if x.get("fundingTime") is not None else None,
                    "markPrice": float(x.get("markPrice")) if x.get("markPrice") is not None else None,
                }
                for x in funding
                if isinstance(x, dict)
            ]
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"funding: {e}")

    # 2) Global long/short ratio (all accounts)
    try:
        ls = get_json(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1d&limit=1",
            timeout=15,
        )
        if isinstance(ls, list) and ls:
            x = ls[0]
            out["binance"]["long_short"] = [
                {
                    "timestamp": int(x.get("timestamp")) if x.get("timestamp") is not None else None,
                    "longAccount": float(x.get("longAccount")) if x.get("longAccount") is not None else None,
                    "shortAccount": float(x.get("shortAccount")) if x.get("shortAccount") is not None else None,
                    "longShortRatio": float(x.get("longShortRatio")) if x.get("longShortRatio") is not None else None,
                }
            ]
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"long_short: {e}")

    # 2b) Top trader long/short ratio (accounts)
    try:
        ta = get_json(
            "https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=1d&limit=1",
            timeout=15,
        )
        if isinstance(ta, list) and ta:
            x = ta[0]
            out["binance"]["top_account"] = [
                {
                    "timestamp": int(x.get("timestamp")) if x.get("timestamp") is not None else None,
                    "longAccount": float(x.get("longAccount")) if x.get("longAccount") is not None else None,
                    "shortAccount": float(x.get("shortAccount")) if x.get("shortAccount") is not None else None,
                    "longShortRatio": float(x.get("longShortRatio")) if x.get("longShortRatio") is not None else None,
                }
            ]
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"top_account: {e}")

    # 2c) Top trader long/short ratio (positions)
    try:
        tp = get_json(
            "https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=1d&limit=1",
            timeout=15,
        )
        if isinstance(tp, list) and tp:
            x = tp[0]
            out["binance"]["top_position"] = [
                {
                    "timestamp": int(x.get("timestamp")) if x.get("timestamp") is not None else None,
                    "longAccount": float(x.get("longAccount")) if x.get("longAccount") is not None else None,
                    "shortAccount": float(x.get("shortAccount")) if x.get("shortAccount") is not None else None,
                    "longShortRatio": float(x.get("longShortRatio")) if x.get("longShortRatio") is not None else None,
                }
            ]
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"top_position: {e}")

    # 2d) Taker buy/sell ratio
    try:
        tr = get_json(
            "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=1d&limit=1",
            timeout=15,
        )
        if isinstance(tr, list) and tr:
            x = tr[0]
            out["binance"]["taker_ratio"] = [
                {
                    "timestamp": int(x.get("timestamp")) if x.get("timestamp") is not None else None,
                    "buySellRatio": float(x.get("buySellRatio")) if x.get("buySellRatio") is not None else None,
                    "buyVol": float(x.get("buyVol")) if x.get("buyVol") is not None else None,
                    "sellVol": float(x.get("sellVol")) if x.get("sellVol") is not None else None,
                }
            ]
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"taker_ratio: {e}")

    # 3) Open interest (BTC/ETH)
    try:
        btc_oi = get_json("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT", timeout=15)
        if isinstance(btc_oi, dict) and btc_oi.get("openInterest") is not None:
            out["coinalyze"]["oi"].append(
                {
                    "symbol": "BTCUSDT_PERP.BINANCE",
                    "value": float(btc_oi.get("openInterest")),
                    "source": "binance_open_interest",
                }
            )
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"btc_oi: {e}")

    try:
        eth_oi = get_json("https://fapi.binance.com/fapi/v1/openInterest?symbol=ETHUSDT", timeout=15)
        if isinstance(eth_oi, dict) and eth_oi.get("openInterest") is not None:
            out["coinalyze"]["oi"].append(
                {
                    "symbol": "ETHUSDT_PERP.BINANCE",
                    "value": float(eth_oi.get("openInterest")),
                    "source": "binance_open_interest",
                }
            )
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"eth_oi: {e}")

    # 4) Liquidations (Coinalyze)
    try:
        coinalyze_key = os.environ.get("OPENBB_COINALYZE_API_KEY", "")
        if coinalyze_key:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            liq = get_json(
                "https://api.coinalyze.net/v1/liquidation-history",
                params={"symbols": "BTCUSD_PERP.A", "interval": "daily", "from": str(now_ts - 86400), "to": str(now_ts)},
                headers={"api_key": coinalyze_key},
                timeout=15,
            )
            if isinstance(liq, list):
                for item in liq:
                    history = item.get("history") or []
                    for h in history:
                        out["coinalyze"]["liquidations"].append({
                            "symbol": item.get("symbol", "BTCUSD_PERP.A"),
                            "timestamp": h.get("t"),
                            "long": h.get("l"),
                            "short": h.get("s"),
                        })
        else:
            errors.append("liquidations: OPENBB_COINALYZE_API_KEY not set")
    except Exception as e:  # pragma: no cover - network dependent
        errors.append(f"liquidations: {e}")

    has_core = bool(out["binance"]["btc_funding"] or out["binance"]["long_short"] or out["coinalyze"]["oi"])
    if not has_core:
        raise DerivativesFetchError("derivatives snapshot empty; " + "; ".join(errors or ["unknown error"]))

    if errors:
        out["_warnings"] = errors

    out["_source"] = "kapy-provider:binance"
    return out
