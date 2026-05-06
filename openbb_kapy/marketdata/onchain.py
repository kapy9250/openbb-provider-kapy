"""On-chain BTC snapshot fetcher (provider-style helper).

Sources:
- blockchain.info/stats
- mempool.space/api/mempool
- mempool.space/api/v1/blocks
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


class OnchainFetchError(RuntimeError):
    """Raised when on-chain snapshot fetch fails."""


def _get_json(url: str) -> Any:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 KapyProvider/1.0"}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_onchain_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "btc": {},
        "errors": [],
        "_source": "kapy-provider:blockchain+mempool",
    }

    btc = out["btc"]

    try:
        stats = _get_json("https://blockchain.info/stats?format=json")
        btc["market_price_usd"] = stats.get("market_price_usd")
        btc["total_btc"] = (stats.get("totalbc") or 0) / 1e8 if stats.get("totalbc") is not None else None
        btc["blocks_size"] = stats.get("blocks_size")
        btc["miners_revenue_usd"] = stats.get("miners_revenue_usd")
        btc["total_fees_btc"] = (stats.get("total_fees_btc") or 0) / 1e8 if stats.get("total_fees_btc") is not None else None
        btc["n_tx"] = stats.get("n_tx")
        btc["estimated_transaction_volume_usd"] = stats.get("estimated_transaction_volume_usd")
    except Exception as e:  # pragma: no cover
        out["errors"].append({"source": "blockchain.info/stats", "error": str(e)})

    try:
        mempool = _get_json("https://mempool.space/api/mempool")
        btc["mempool"] = {
            "count": mempool.get("count"),
            "vsize": mempool.get("vsize"),
            "total_fee": ((mempool.get("total_fee") or 0) / 1e8) if mempool.get("total_fee") is not None else None,
            "fee_histogram": (mempool.get("fee_histogram") or [])[:10],
        }
    except Exception as e:  # pragma: no cover
        out["errors"].append({"source": "mempool.space/mempool", "error": str(e)})

    try:
        charts = _get_json(
            "https://api.blockchain.info/charts/n-unique-addresses"
            "?timespan=2days&format=json&sampled=false"
        )
        values = charts.get("values") or []
        if values:
            btc["active_addresses"] = values[-1].get("y")
    except Exception as e:  # pragma: no cover
        out["errors"].append({"source": "blockchain.info/charts/n-unique-addresses", "error": str(e)})

    try:
        blocks = _get_json("https://mempool.space/api/v1/blocks")
        if isinstance(blocks, list) and blocks:
            b = blocks[0]
            btc["latest_block"] = {
                "height": b.get("height"),
                "timestamp": b.get("timestamp"),
                "tx_count": b.get("tx_count"),
                "size": b.get("size"),
                "weight": b.get("weight"),
            }
    except Exception as e:  # pragma: no cover
        out["errors"].append({"source": "mempool.space/blocks", "error": str(e)})

    if not btc:
        raise OnchainFetchError("onchain payload empty")

    return out
