"""ETF source flow snapshot fetcher (provider-style helper).

Source:
- https://btcetffundflow.com/us (__NEXT_DATA__)

Produces legacy-compatible shape expected by sync_marketdata_etf_source.py:
{
  timestamp,
  source,
  daily_flows: [{date,total,ibit,fbtc,gbtc}]
}
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import requests


class EtfSourceFetchError(RuntimeError):
    """Raised when ETF source flow fetch fails."""


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _next_data(url: str = "https://btcetffundflow.com/us") -> dict[str, Any]:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 KapyProvider/1.0"}, timeout=25)
    resp.raise_for_status()
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.S)
    if not m:
        raise EtfSourceFetchError("__NEXT_DATA__ not found")
    return json.loads(m.group(1))


def fetch_etf_source_snapshot() -> dict[str, Any]:
    raw = _next_data()
    try:
        data = raw["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["data"]
    except Exception as e:
        raise EtfSourceFetchError(f"unexpected payload: {e}") from e

    providers: dict[str, str] = data.get("providers") or {}
    chart4 = data.get("chart4") or []  # btc flow history
    if not chart4:
        raise EtfSourceFetchError("chart4 empty")

    # provider id map (ticker -> provider index key)
    pid_total = "0"
    pid_ibit = next((k for k, v in providers.items() if str(v).upper().startswith("IBIT")), None)
    pid_fbtc = next((k for k, v in providers.items() if str(v).upper().startswith("FBTC")), None)
    pid_gbtc = next((k for k, v in providers.items() if str(v).upper().startswith("GBTC")), None)

    rows: list[dict[str, Any]] = []
    for x in chart4[-120:]:  # keep recent window
        ts = x.get("ts")
        if not isinstance(ts, (int, float)):
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        rows.append(
            {
                "date": d,
                "total": _safe_float(x.get(pid_total)) if pid_total else None,
                "ibit": _safe_float(x.get(pid_ibit)) if pid_ibit else None,
                "fbtc": _safe_float(x.get(pid_fbtc)) if pid_fbtc else None,
                "gbtc": _safe_float(x.get(pid_gbtc)) if pid_gbtc else None,
            }
        )

    if not rows:
        raise EtfSourceFetchError("no daily flow rows")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "kapy-provider:btcetffundflow",
        "daily_flows": rows,
    }
