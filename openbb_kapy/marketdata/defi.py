"""DeFi snapshot fetcher (provider-style helper).

Sources:
- https://api.llama.fi/overview/fees
- https://stablecoins.llama.fi/stablecoins
- https://api.llama.fi/v2/chains
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .http import get_json


class DefiFetchError(RuntimeError):
    """Raised when DeFi snapshot fetch fails."""


def fetch_defi_snapshot() -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    fees_raw = get_json("https://api.llama.fi/overview/fees", timeout=25)
    stable_raw = get_json("https://stablecoins.llama.fi/stablecoins", timeout=25)
    chains_raw = get_json("https://api.llama.fi/v2/chains", timeout=25)

    top_protocols = sorted(
        [p for p in (fees_raw.get("protocols") or []) if (p.get("total24h") or 0) > 0],
        key=lambda x: x.get("total24h") or 0,
        reverse=True,
    )[:20]

    pegged = stable_raw.get("peggedAssets") or []
    total_circ = sum((x.get("circulating") or {}).get("peggedUSD") or 0 for x in pegged)
    total_prev_day = sum((x.get("circulatingPrevDay") or {}).get("peggedUSD") or 0 for x in pegged)
    total_prev_week = sum((x.get("circulatingPrevWeek") or {}).get("peggedUSD") or 0 for x in pegged)
    total_prev_month = sum((x.get("circulatingPrevMonth") or {}).get("peggedUSD") or 0 for x in pegged)

    top_stable = sorted(
        pegged,
        key=lambda x: (x.get("circulating") or {}).get("peggedUSD") or 0,
        reverse=True,
    )[:15]

    chains_sorted = sorted(chains_raw or [], key=lambda x: x.get("tvl") or 0, reverse=True)
    total_tvl = sum((x.get("tvl") or 0) for x in (chains_raw or []))

    data = {
        "timestamp": now,
        "fees": {
            "total": {
                "fees_24h": fees_raw.get("total24h"),
                "fees_7d": fees_raw.get("total7d"),
                "fees_30d": fees_raw.get("total30d"),
                "change_1d": fees_raw.get("change_1d"),
                "change_7d": fees_raw.get("change_7d"),
            },
            "top_protocols": [
                {
                    "name": p.get("name"),
                    "displayName": p.get("displayName"),
                    "fees_24h": p.get("total24h"),
                    "fees_7d": p.get("total7d"),
                    "fees_30d": p.get("total30d"),
                    "change_1d": p.get("change_1d"),
                    "category": p.get("category"),
                }
                for p in top_protocols
            ],
        },
        "stablecoins": {
            "total": {
                "circulating": total_circ,
                "change_24h": total_circ - total_prev_day,
                "change_7d": total_circ - total_prev_week,
                "change_30d": total_circ - total_prev_month,
            },
            "top_stablecoins": [
                {
                    "name": s.get("name"),
                    "symbol": s.get("symbol"),
                    "circulating": (s.get("circulating") or {}).get("peggedUSD"),
                }
                for s in top_stable
            ],
        },
        "chains": {
            "total_tvl": total_tvl,
            "chains": [
                {
                    "name": c.get("name"),
                    "tvl": c.get("tvl"),
                }
                for c in chains_sorted[:20]
            ],
        },
    }

    # lightweight sanity
    if data["fees"]["total"]["fees_24h"] is None and data["chains"]["total_tvl"] is None:
        raise DefiFetchError("defi snapshot core fields missing")

    return {
        "timestamp": now,
        "data": data,
        "_source": "kapy-provider:defillama",
    }
