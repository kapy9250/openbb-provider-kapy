"""ETF flow snapshot fetcher (provider-style helper).

Data source:
- https://btcetffundflow.com/us (Next.js __NEXT_DATA__ payload)

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
import re
from datetime import datetime, timezone
from typing import Any

import requests


UA = "Mozilla/5.0 KapyProvider/1.0"


class EtfFlowFetchError(RuntimeError):
    """Raised when ETF flow fetch fails."""


def _fetch_next_data(url: str = "https://btcetffundflow.com/us") -> dict[str, Any]:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    html = resp.text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise EtfFlowFetchError("__NEXT_DATA__ not found")
    return json.loads(m.group(1))


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def fetch_etf_flow_snapshot() -> dict[str, Any]:
    raw = _fetch_next_data()

    try:
        data = raw["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["data"]
    except Exception as e:
        raise EtfFlowFetchError(f"unexpected payload structure: {e}") from e

    providers = data.get("providers") or {}
    flows = data.get("flows") or []  # USD flow
    flows2 = data.get("flows2") or []  # BTC flow
    chart3 = data.get("chart3") or []  # BTC holdings timeline

    if not chart3:
        raise EtfFlowFetchError("chart3 empty; cannot derive btc holdings")

    latest = chart3[-1]
    ts = latest.get("ts")
    updated_date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if isinstance(ts, (int, float)) else None
    btc_price = _safe_float(latest.get("price"))
    btc_holdings = _safe_float(latest.get("0"))  # provider 0 => TOTAL

    usd_by_provider = {str(x.get("provider")): _safe_float(x.get("value")) for x in flows if isinstance(x, dict)}
    btc_by_provider = {str(x.get("provider")): _safe_float(x.get("value")) for x in flows2 if isinstance(x, dict)}

    top_flows: list[dict[str, Any]] = []
    for pid, btc_flow in btc_by_provider.items():
        if pid == "0":
            continue  # TOTAL kept separately
        if btc_flow is None:
            continue
        label = str(providers.get(pid) or pid)
        ticker = label.split(" ")[0].replace("(", "").replace(")", "").upper()
        top_flows.append(
            {
                "ticker": ticker,
                "flow_btc": btc_flow,
                "flow_usd_million": usd_by_provider.get(pid),
            }
        )

    # Sort by abs flow and keep top 5 (consistent with old behavior)
    top_flows = sorted(top_flows, key=lambda x: abs(x.get("flow_btc") or 0), reverse=True)[:5]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "kapy-provider:btcetffundflow",
        "updated_date": updated_date,
        "btc_holdings": btc_holdings,
        "btc_price": btc_price,
        "trends": {},
        "top_flows": top_flows,
        "raw_providers": providers,
    }
