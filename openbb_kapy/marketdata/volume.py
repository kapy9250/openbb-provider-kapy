"""Global volume snapshot fetcher (provider-style helper).

A practical subset replacement for legacy market-data volume aggregator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from .etf_volume import ETF_CONFIG, fetch_etf_volume_snapshot


class VolumeFetchError(RuntimeError):
    """Raised when volume snapshot fetch fails."""


def _get_json(url: str) -> Any:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 KapyProvider/1.0"}, timeout=25)
    resp.raise_for_status()
    return resp.json()


def _coingecko_global() -> dict[str, Any]:
    try:
        d = _get_json("https://api.coingecko.com/api/v3/global").get("data") or {}
        return {
            "global": {
                "total_24h_volume_usd": ((d.get("total_volume") or {}).get("usd")),
                "total_market_cap_usd": ((d.get("total_market_cap") or {}).get("usd")),
                "btc_dominance": ((d.get("market_cap_percentage") or {}).get("btc")),
                "eth_dominance": ((d.get("market_cap_percentage") or {}).get("eth")),
            }
        }
    except Exception:
        return {}


def _tokenized_gold() -> dict[str, Any]:
    try:
        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=tether-gold,pax-gold&vs_currencies=usd"
            "&include_market_cap=true&include_24hr_vol=true"
        )
        d = _get_json(url)
        x = d.get("tether-gold") or {}
        p = d.get("pax-gold") or {}
        return {
            "tokenized_gold": {
                "total_market_cap": (x.get("usd_market_cap") or 0) + (p.get("usd_market_cap") or 0),
                "total_volume_24h": (x.get("usd_24h_vol") or 0) + (p.get("usd_24h_vol") or 0),
            }
        }
    except Exception:
        return {}


def _dex_volume() -> dict[str, Any]:
    try:
        d = _get_json(
            "https://api.llama.fi/overview/dexs?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
        )
        return {
            "total_24h": d.get("total24h"),
            "total_7d": d.get("total7d"),
            "change_1d": d.get("change_1d"),
        }
    except Exception:
        return {}


def _etf_by_category(etfs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, dict[str, Any]] = {}
    for ticker, row in etfs.items():
        cat = row.get("category") or (ETF_CONFIG.get(ticker) or {}).get("category")
        if not cat:
            continue
        out.setdefault(cat, {"total_volume": 0.0, "total_dollar_volume": 0.0})
        out[cat]["total_volume"] += float(row.get("volume") or 0.0)
        out[cat]["total_dollar_volume"] += float(row.get("dollar_volume") or 0.0)
    return out


def fetch_volume_snapshot() -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    etf = fetch_etf_volume_snapshot()
    etf_rows = etf.get("etfs") or {}

    data = {
        "timestamp": now,
        "date": now.split("T")[0],
        "fed_liquidity": {},
        "etf_volumes": {
            "by_category": _etf_by_category(etf_rows),
        },
        "futures": {"by_category": {}},
        "crypto_volume": {
            **_coingecko_global(),
            **_tokenized_gold(),
        },
        "dex_volume": _dex_volume(),
    }

    # compatibility flatten (legacy script also had these shortcuts)
    g = (data.get("crypto_volume") or {}).get("global") or {}
    if g:
        data["crypto_volume"]["total_24h_volume_usd"] = g.get("total_24h_volume_usd")
        data["crypto_volume"]["total_market_cap_usd"] = g.get("total_market_cap_usd")
        data["crypto_volume"]["btc_dominance"] = g.get("btc_dominance")
        data["crypto_volume"]["eth_dominance"] = g.get("eth_dominance")

    # sanity: at least one major block should exist
    has_any = bool(
        data["etf_volumes"].get("by_category")
        or data["dex_volume"].get("total_24h")
        or (data["crypto_volume"].get("global") or {}).get("total_24h_volume_usd")
    )
    if not has_any:
        raise VolumeFetchError("volume snapshot empty")

    return {
        "timestamp": now,
        "data": data,
        "_source": "kapy-provider:etf+coingecko+defillama",
    }
