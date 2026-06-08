"""On-chain realized profit indicator fetchers.

Source:
- BGeometrics free API (daily SOPR family endpoints)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .http import get_json


BGEOMETRICS_BASE_URL = "https://api.bgeometrics.com/v1"
BGEOMETRICS_PROVIDER = "kapy.bgeometrics"

BGEOMETRICS_METRICS: dict[str, dict[str, str]] = {
    "sopr": {"endpoint": "sopr", "value_key": "sopr"},
    "asopr": {"endpoint": "asopr", "value_key": "asopr"},
    "sth_sopr": {"endpoint": "sth-sopr", "value_key": "sth_sopr"},
    "lth_sopr": {"endpoint": "lth-sopr", "value_key": "lth_sopr"},
    "mvrv_ratio": {"endpoint": "mvrv", "value_key": "mvrv"},
    "mvrv_zscore": {"endpoint": "mvrv-zscore", "value_key": "mvrvZscore"},
    "puell_multiple": {"endpoint": "puell-multiple", "value_key": "puellMultiple"},
    "nupl": {"endpoint": "nupl", "value_key": "nupl"},
}

_DATE_KEYS = ("d", "date", "time", "timestamp")
_SKIP_VALUE_KEYS = {"d", "date", "time", "timestamp", "unixTs", "unix_ts"}


class OnchainIndicatorFetchError(RuntimeError):
    """Raised when on-chain indicator fetch fails."""


def _parse_date(item: dict[str, Any]) -> date:
    for key in _DATE_KEYS:
        value = item.get(key)
        if not value:
            continue
        if isinstance(value, str):
            return datetime.fromisoformat(value[:10]).date()
        if isinstance(value, (int, float)):
            ts = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(ts, tz=timezone.utc).date()

    unix_ts = item.get("unixTs") or item.get("unix_ts")
    if isinstance(unix_ts, (int, float)):
        ts = unix_ts / 1000 if unix_ts > 10_000_000_000 else unix_ts
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()

    raise ValueError(f"cannot parse BGeometrics date from item: {item}")


def _value_candidates(metric_name: str, endpoint: str, value_key: str) -> list[str]:
    camel = "".join(part.capitalize() if idx else part for idx, part in enumerate(endpoint.split("-")))
    return [
        value_key,
        metric_name,
        metric_name.replace("_", "-"),
        metric_name.replace("_", ""),
        endpoint,
        endpoint.replace("-", "_"),
        endpoint.replace("-", ""),
        camel,
    ]


def _parse_value(item: dict[str, Any], metric_name: str, endpoint: str, value_key: str) -> float | None:
    for key in _value_candidates(metric_name, endpoint, value_key):
        value = item.get(key)
        if value is None:
            continue
        return float(value)

    for key, value in item.items():
        if key in _SKIP_VALUE_KEYS or value is None:
            continue
        if isinstance(value, (int, float, str)):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _sort_key(item: dict[str, Any]) -> tuple[str, float]:
    unix_ts = item.get("unixTs") or item.get("unix_ts") or 0
    try:
        ts = float(unix_ts)
    except (TypeError, ValueError):
        ts = 0.0
    return (_parse_date(item).isoformat(), ts)


def fetch_bgeometrics_indicator(
    metric_name: str,
    api_key: str | None = None,
    proxies: dict | None = None,
) -> list[dict[str, Any]]:
    """Fetch one BGeometrics indicator and normalize it to daily records."""
    if metric_name not in BGEOMETRICS_METRICS:
        raise ValueError(f"unsupported BGeometrics metric: {metric_name}")

    spec = BGEOMETRICS_METRICS[metric_name]
    endpoint = spec["endpoint"]
    url = f"{BGEOMETRICS_BASE_URL}/{endpoint}"
    headers = {"x-api-key": api_key} if api_key else None
    payload = get_json(url, timeout=30, headers=headers, proxies=proxies)
    if not isinstance(payload, list):
        raise OnchainIndicatorFetchError(f"BGeometrics {endpoint} payload is not a list")

    latest_by_date: dict[date, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        obs_date = _parse_date(item)
        value = _parse_value(item, metric_name, endpoint, spec["value_key"])
        if value is None:
            continue

        current = latest_by_date.get(obs_date)
        if current is None or _sort_key(item) >= _sort_key(current["raw_item"]):
            latest_by_date[obs_date] = {
                "symbol": "BTC",
                "metric_name": metric_name,
                "date": obs_date,
                "value": value,
                "provider": BGEOMETRICS_PROVIDER,
                "raw": {
                    "endpoint": endpoint,
                    "url": url,
                    "item": item,
                },
                "raw_item": item,
            }

    records = []
    for obs_date in sorted(latest_by_date):
        record = dict(latest_by_date[obs_date])
        record.pop("raw_item", None)
        records.append(record)
    return records


def fetch_bgeometrics_indicators(metric_names: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Fetch multiple BGeometrics indicators keyed by metric name."""
    names = metric_names or list(BGEOMETRICS_METRICS)
    return {name: fetch_bgeometrics_indicator(name) for name in names}


def fetch_latest_bgeometrics_indicator(metric_name: str = "sopr") -> dict[str, Any]:
    """Fetch one indicator and return its latest normalized daily record."""
    records = fetch_bgeometrics_indicator(metric_name)
    if not records:
        raise OnchainIndicatorFetchError(f"BGeometrics {metric_name} returned no records")
    return records[-1]
