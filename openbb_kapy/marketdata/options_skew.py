"""BTC options 25-delta IV skew helper.

Source strategy:
- Sharpe API when SHARPE_API_KEY or OPENBB_SHARPE_API_KEY is set.
- Deribit public option chain fallback, explicitly labeled as a proxy.
"""

from __future__ import annotations

import asyncio
import math
import os
from datetime import date, datetime, timezone
from typing import Any

from openbb_kapy.utils.deribit_client import DeribitClient

from .http import get_json


SHARPE_BASE_URL = "https://www.sharpe.ai/api/v1"


class OptionsSkewFetchError(RuntimeError):
    """Raised when no options skew row can be produced."""


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(spot: float, strike: float, iv: float, years: float, option_type: str) -> float | None:
    if spot <= 0 or strike <= 0 or iv <= 0 or years <= 0:
        return None
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * years) / (iv * math.sqrt(years))
    if option_type == "call":
        return _norm_cdf(d1)
    if option_type == "put":
        return _norm_cdf(d1) - 1.0
    return None


def _row(metric_name: str, value: float, provider: str, raw: dict[str, Any], obs_date: date | None = None) -> dict[str, Any]:
    return {
        "symbol": "BTC",
        "metric_name": metric_name,
        "date": obs_date or datetime.now(timezone.utc).date(),
        "value": value,
        "provider": provider,
        "raw": raw,
    }


def _fetch_sharpe_25d_skew_1m() -> dict[str, Any] | None:
    api_key = os.getenv("SHARPE_API_KEY") or os.getenv("OPENBB_SHARPE_API_KEY")
    if not api_key:
        return None

    payload = get_json(
        f"{SHARPE_BASE_URL}/options/data",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"chart": "vol-skew", "coin": "BTC", "timeframe": "1M", "exchanges": "Deribit"},
        timeout=20,
    )
    body = payload.get("data") if isinstance(payload, dict) else {}
    points = body.get("data") if isinstance(body, dict) else []
    if not isinstance(points, list) or not points:
        raise OptionsSkewFetchError("Sharpe options vol-skew response has no data points")

    latest = max(
        (p for p in points if isinstance(p, dict)),
        key=lambda p: _parse_dt(p.get("fetched_at")) or datetime.min.replace(tzinfo=timezone.utc),
        default=None,
    )
    if not latest:
        raise OptionsSkewFetchError("Sharpe options vol-skew response has no usable data points")

    value = _as_float(latest.get("skew_1m"))
    if value is None:
        raise OptionsSkewFetchError("Sharpe options vol-skew response missing skew_1m")

    fetched_at = _parse_dt(latest.get("fetched_at"))
    return _row(
        metric_name="options_25d_skew_1m",
        value=value,
        provider="sharpe",
        obs_date=fetched_at.date() if fetched_at else None,
        raw={
            "source": "sharpe",
            "endpoint": "/v1/options/data",
            "chart": "vol-skew",
            "source_field": "skew_1m",
            "definition": "put_iv_25d_minus_call_iv_25d; IV absolute decimal",
            "latest_point": latest,
            "meta": payload.get("meta") if isinstance(payload, dict) else None,
        },
    )


async def _fetch_deribit_chain(currency: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    instruments, books = await asyncio.gather(
        DeribitClient.get_instruments(currency),
        DeribitClient.get_book_summary_by_currency(currency),
    )
    return instruments, books


def _chain_records(
    instruments: list[dict[str, Any]],
    books: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    book_by_name = {b.get("instrument_name"): b for b in books if isinstance(b, dict)}
    records: list[dict[str, Any]] = []

    for ins in instruments:
        if not isinstance(ins, dict):
            continue
        name = ins.get("instrument_name")
        option_type = ins.get("option_type")
        if not name or option_type not in {"call", "put"}:
            continue
        book = book_by_name.get(name)
        if not book:
            continue

        mark_iv_pct = _as_float(book.get("mark_iv"))
        strike = _as_float(ins.get("strike"))
        spot = _as_float(book.get("underlying_price"))
        exp_ts = _as_float(ins.get("expiration_timestamp"))
        if mark_iv_pct is None or strike is None or spot is None or exp_ts is None:
            continue

        exp_dt = datetime.fromtimestamp(exp_ts / 1000.0, tz=timezone.utc)
        dte = (exp_dt.date() - now.date()).days
        if dte <= 0:
            continue

        greeks = book.get("greeks") if isinstance(book.get("greeks"), dict) else {}
        delta = _as_float(greeks.get("delta") or book.get("delta"))
        delta_source = "deribit_greeks" if delta is not None else None
        if delta is None:
            delta = _bs_delta(spot, strike, mark_iv_pct / 100.0, max(dte / 365.25, 1e-6), option_type)
            delta_source = "black_scholes_mark_iv" if delta is not None else None

        records.append(
            {
                "instrument_name": name,
                "option_type": option_type,
                "expiry": exp_dt.date().isoformat(),
                "dte": dte,
                "strike": strike,
                "underlying_price": spot,
                "mark_iv": mark_iv_pct / 100.0,
                "delta": delta,
                "delta_source": delta_source,
                "bid_price": book.get("bid_price"),
                "ask_price": book.get("ask_price"),
                "mark_price": book.get("mark_price"),
                "open_interest": book.get("open_interest"),
                "volume": book.get("volume"),
            }
        )

    return records


def _select_expiry(records: list[dict[str, Any]], target_dte: int) -> tuple[str, int]:
    expiries: dict[str, int] = {}
    for r in records:
        dte = int(r["dte"])
        if dte >= 7:
            expiries[r["expiry"]] = dte
    if not expiries:
        for r in records:
            expiries[r["expiry"]] = int(r["dte"])
    if not expiries:
        raise OptionsSkewFetchError("Deribit option chain has no live expiries")
    expiry, dte = min(expiries.items(), key=lambda item: (abs(item[1] - target_dte), item[1]))
    return expiry, dte


def _leg_payload(leg: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "instrument_name",
        "option_type",
        "expiry",
        "dte",
        "strike",
        "underlying_price",
        "mark_iv",
        "delta",
        "delta_source",
        "bid_price",
        "ask_price",
        "mark_price",
        "open_interest",
        "volume",
    ]
    return {k: leg.get(k) for k in keys}


def _select_delta_legs(expiry_records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    calls = [r for r in expiry_records if r["option_type"] == "call" and r.get("delta") is not None]
    puts = [r for r in expiry_records if r["option_type"] == "put" and r.get("delta") is not None]
    if not calls or not puts:
        return None
    call = min(calls, key=lambda r: abs(float(r["delta"]) - 0.25))
    put = min(puts, key=lambda r: abs(float(r["delta"]) + 0.25))
    return put, call


def _select_moneyness_legs(expiry_records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    spot = next((r.get("underlying_price") for r in expiry_records if r.get("underlying_price")), None)
    if spot is None:
        raise OptionsSkewFetchError("Deribit option chain missing underlying_price for moneyness proxy")
    calls = [r for r in expiry_records if r["option_type"] == "call"]
    puts = [r for r in expiry_records if r["option_type"] == "put"]
    if not calls or not puts:
        raise OptionsSkewFetchError("Deribit option chain missing put/call legs")
    call = min(calls, key=lambda r: abs(float(r["strike"]) - float(spot) * 1.05))
    put = min(puts, key=lambda r: abs(float(r["strike"]) - float(spot) * 0.95))
    return put, call


def _fetch_deribit_proxy_1m() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    instruments, books = asyncio.run(_fetch_deribit_chain("BTC"))
    records = _chain_records(instruments, books, now)
    if not records:
        raise OptionsSkewFetchError("Deribit option chain produced no IV records")

    expiry, dte = _select_expiry(records, target_dte=30)
    expiry_records = [r for r in records if r["expiry"] == expiry]

    legs = _select_delta_legs(expiry_records)
    method = "deribit_delta_bucket_proxy"
    if legs is None:
        legs = _select_moneyness_legs(expiry_records)
        method = "deribit_moneyness_proxy"
    put, call = legs

    value = float(put["mark_iv"]) - float(call["mark_iv"])
    return _row(
        metric_name="options_25d_skew_proxy_1m",
        value=value,
        provider="deribit",
        obs_date=now.date(),
        raw={
            "source": "deribit",
            "definition": "put_iv_25d_minus_call_iv_25d; IV absolute decimal",
            "method": method,
            "target_dte": 30,
            "selected_expiry": expiry,
            "selected_dte": dte,
            "target_delta": {"put": -0.25, "call": 0.25},
            "put_leg": _leg_payload(put),
            "call_leg": _leg_payload(call),
            "chain_counts": {
                "instruments": len(instruments),
                "book_summaries": len(books),
                "usable_records": len(records),
                "expiry_records": len(expiry_records),
            },
            "generated_at": now.isoformat(),
        },
    )


def fetch_btc_options_skew_1m() -> list[dict[str, Any]]:
    """Return one normalized BTC options skew row.

    The exact metric is emitted only when Sharpe provides a 25-delta skew.
    Deribit fallback is always emitted as a proxy metric.
    """
    sharpe_error: str | None = None
    try:
        sharpe_row = _fetch_sharpe_25d_skew_1m()
        if sharpe_row is not None:
            return [sharpe_row]
    except Exception as exc:
        sharpe_error = str(exc)

    row = _fetch_deribit_proxy_1m()
    if sharpe_error:
        row["raw"]["sharpe_error"] = sharpe_error
    return [row]


__all__ = ["OptionsSkewFetchError", "fetch_btc_options_skew_1m"]
