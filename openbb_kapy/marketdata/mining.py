"""BTC mining snapshot fetcher (provider-style helper).

Source: mempool.space public API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


class MiningFetchError(RuntimeError):
    """Raised when mining snapshot fetch fails."""


def _get_json(url: str) -> Any:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 KapyProvider/1.0"}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_mining_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "mempool.space",
        "data": {},
    }
    data = out["data"]

    # Hashrate + difficulty
    hash_diff = _get_json("https://mempool.space/api/v1/mining/hashrate/1m")
    data["current_hashrate"] = (hash_diff.get("currentHashrate") or 0) / 1e18
    data["current_difficulty"] = (hash_diff.get("currentDifficulty") or 0) / 1e12

    rates = hash_diff.get("hashrates") or []
    if rates:
        month_ago = (rates[0].get("avgHashrate") or 0) / 1e18
        if month_ago:
            data["hashrate_1m_change"] = ((data["current_hashrate"] - month_ago) / month_ago) * 100.0

    # Pools
    pools = _get_json("https://mempool.space/api/v1/mining/pools/24h")
    block_count = pools.get("blockCount") or 0
    rows = []
    for p in (pools.get("pools") or [])[:10]:
        b = p.get("blockCount") or 0
        rows.append({
            "name": p.get("name"),
            "blocks": b,
            "share": (b / block_count * 100.0) if block_count else None,
        })
    data["pools"] = rows

    # Avg fee rate 24h
    fee_rows = _get_json("https://mempool.space/api/v1/mining/blocks/fee-rates/24h")
    if isinstance(fee_rows, list) and fee_rows:
        vals = [float(x.get("avgFee_10") or 0.0) for x in fee_rows]
        if vals:
            data["avg_fee_rate_24h"] = sum(vals) / len(vals)

    if not data.get("current_hashrate") and not data.get("pools"):
        raise MiningFetchError("empty mining payload")

    out["_source"] = "kapy-provider:mempool"
    return out
