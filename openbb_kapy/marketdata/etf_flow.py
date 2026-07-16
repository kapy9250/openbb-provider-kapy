"""ETF flow snapshot fetcher (provider-style helper).

Data source:
- https://btcetfdata.com/v1/current.json

Returns normalized structure aligned with previous `latest-simple.json` format:
{
  timestamp,
  source,
  updated_date,
  btc_holdings,
  btc_price,
  trends,
  top_flows: [{ticker, flow_btc, flow_usd_million?}]
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .http import get_json


class EtfFlowFetchError(RuntimeError):
    """Raised when ETF flow fetch fails."""

def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None

def fetch_etf_flow_snapshot() -> dict[str, Any]:
    # 1. Fetch ETF data
    try:
        payload = get_json("https://btcetfdata.com/v1/current.json", timeout=15)
    except Exception as e:
        raise EtfFlowFetchError(f"Failed to fetch btcetfdata: {e}") from e

    # 2. Fetch BTC price to allow downstream USD calculations
    try:
        btc_price = _safe_float(get_json("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10).get("price"))
    except Exception:
        btc_price = None

    data = payload.get("data", {})
    if not data:
        raise EtfFlowFetchError("Empty data returned from btcetfdata")

    # Sort out the dates to find the most recent 'updated_date' (dt) across all entries
    dates = [item["dt"] for item in data.values() if "dt" in item and item["dt"]]
    updated_date = max(dates) if dates else datetime.utcnow().strftime("%Y-%m-%d")

    # Calculate Total holdings
    btc_holdings = sum((_safe_float(item.get("holdings")) or 0) for item in data.values())

    top_flows: list[dict[str, Any]] = []
    for ticker, item in data.items():
        flow_btc = _safe_float(item.get("change"))
        if flow_btc is None:
            continue

        flow_usd_million = None
        if btc_price is not None:
            flow_usd_million = (flow_btc * btc_price) / 1_000_000.0

        top_flows.append({
            "ticker": ticker.upper(),
            "flow_btc": flow_btc,
            "flow_usd_million": flow_usd_million,
            # 各基金 holdings 快照的 as-of 日各不相同（同一时刻可能混杂 3 个日期），
            # 逐项透传 dt 供下游按真实归属日落库，勿用顶层 updated_date（=max(dt)）代替
            "dt": item.get("dt"),
        })

    # Sort top flows by absolute BTC flow, taking top 5 (consistent with old behavior)
    top_flows = sorted(top_flows, key=lambda x: abs(x.get("flow_btc") or 0), reverse=True)[:5]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "kapy-provider:btcetfdata.com",
        "updated_date": updated_date,
        "btc_holdings": btc_holdings,
        "btc_price": btc_price,
        "trends": {},
        "top_flows": top_flows,
        "raw_providers": list(data.keys()),
    }
