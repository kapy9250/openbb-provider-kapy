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


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _source_global(source: str, url: str, values: dict[str, Any]) -> dict[str, Any]:
    out = {
        "source": source,
        "url": url,
        "total_24h_volume_usd": _as_float(values.get("total_24h_volume_usd")),
        "total_market_cap_usd": _as_float(values.get("total_market_cap_usd")),
        "btc_dominance": _as_float(values.get("btc_dominance")),
        "eth_dominance": _as_float(values.get("eth_dominance")),
        "raw_updated_at": values.get("raw_updated_at"),
    }
    return {k: v for k, v in out.items() if v is not None}


def _coinpaprika_global() -> dict[str, Any]:
    url = "https://api.coinpaprika.com/v1/global"
    try:
        d = _get_json(url) or {}
        return _source_global(
            "coinpaprika",
            url,
            {
                "total_24h_volume_usd": d.get("volume_24h_usd"),
                "total_market_cap_usd": d.get("market_cap_usd"),
                "btc_dominance": d.get("bitcoin_dominance_percentage"),
                "raw_updated_at": d.get("last_updated"),
            },
        )
    except Exception:
        return {}


def _coingecko_global() -> dict[str, Any]:
    url = "https://api.coingecko.com/api/v3/global"
    try:
        d = _get_json(url).get("data") or {}
        return _source_global(
            "coingecko",
            url,
            {
                "total_24h_volume_usd": ((d.get("total_volume") or {}).get("usd")),
                "total_market_cap_usd": ((d.get("total_market_cap") or {}).get("usd")),
                "btc_dominance": ((d.get("market_cap_percentage") or {}).get("btc")),
                "eth_dominance": ((d.get("market_cap_percentage") or {}).get("eth")),
                "raw_updated_at": d.get("updated_at"),
            },
        )
    except Exception:
        return {}


def _coinlore_global() -> dict[str, Any]:
    url = "https://api.coinlore.net/api/global/"
    try:
        payload = _get_json(url) or []
        d = payload[0] if isinstance(payload, list) and payload else {}
        return _source_global(
            "coinlore",
            url,
            {
                "total_24h_volume_usd": d.get("total_volume"),
                "total_market_cap_usd": d.get("total_mcap"),
                "btc_dominance": d.get("btc_d"),
                "eth_dominance": d.get("eth_d"),
            },
        )
    except Exception:
        return {}


def _pct_diff(a: Any, b: Any) -> float | None:
    x = _as_float(a)
    y = _as_float(b)
    if x is None or y is None or y == 0:
        return None
    return (x - y) / abs(y)


def _crypto_global() -> dict[str, Any]:
    sources = {
        row["source"]: row
        for row in (_coinpaprika_global(), _coingecko_global(), _coinlore_global())
        if row.get("source")
    }
    if not sources:
        return {}

    # Keep CoinGecko as primary to preserve historical continuity in
    # daily_volume_metrics; CoinPaprika/CoinLore are fallback and validation.
    priority = ("coingecko", "coinpaprika", "coinlore")
    fields = (
        "total_24h_volume_usd",
        "total_market_cap_usd",
        "btc_dominance",
        "eth_dominance",
    )
    selected: dict[str, Any] = {"sources": sources, "field_sources": {}}
    for field in fields:
        for source in priority:
            value = sources.get(source, {}).get(field)
            if value is not None:
                selected[field] = value
                selected["field_sources"][field] = source
                break

    selected["source"] = selected["field_sources"].get("total_market_cap_usd") or next(iter(sources))
    selected["validation"] = {
        "coinpaprika_vs_coingecko_total_market_cap_pct": _pct_diff(
            sources.get("coinpaprika", {}).get("total_market_cap_usd"),
            sources.get("coingecko", {}).get("total_market_cap_usd"),
        ),
        "coinpaprika_vs_coingecko_total_24h_volume_pct": _pct_diff(
            sources.get("coinpaprika", {}).get("total_24h_volume_usd"),
            sources.get("coingecko", {}).get("total_24h_volume_usd"),
        ),
        "coinpaprika_vs_coingecko_btc_dominance_pct": _pct_diff(
            sources.get("coinpaprika", {}).get("btc_dominance"),
            sources.get("coingecko", {}).get("btc_dominance"),
        ),
    }
    selected["validation"] = {k: v for k, v in selected["validation"].items() if v is not None}
    return {"global": selected}


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
            **_crypto_global(),
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
        "_source": "kapy-provider:etf+crypto-global-fallback+defillama",
    }
