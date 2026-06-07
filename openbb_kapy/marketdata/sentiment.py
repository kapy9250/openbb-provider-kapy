"""Sentiment snapshot fetcher (provider-style helper).

Current source strategy:
- Alternative.me Fear & Greed Index (crypto)

Returns a normalized payload aligned with pipeline shape so downstream
sync scripts can ingest directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .http import get_json


class SentimentFetchError(RuntimeError):
    """Raised when sentiment fetch fails."""


def _safe_int(val: Any) -> int | None:
    """Convert value to int, returning None on failure."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def fetch_sentiment_snapshot() -> dict[str, Any]:
    """Fetch Fear & Greed Index (last 7 days) and normalize structure."""
    now = datetime.now(timezone.utc).isoformat()

    try:
        raw = get_json("https://api.alternative.me/fng/?limit=7")
    except Exception as e:
        raise SentimentFetchError(f"fear_greed fetch failed: {e}") from e

    data_list = raw.get("data")
    if not isinstance(data_list, list) or not data_list:
        raise SentimentFetchError("fear_greed response has no data array")

    fear_greed = []
    for item in data_list:
        if not isinstance(item, dict):
            continue
        value = _safe_int(item.get("value"))
        timestamp = _safe_int(item.get("timestamp"))
        if value is None or timestamp is None:
            continue
        fear_greed.append({
            "value": value,
            "classification": item.get("value_classification", ""),
            "timestamp": timestamp,
        })

    if not fear_greed:
        raise SentimentFetchError("fear_greed parsed 0 valid entries")

    return {
        "timestamp": now,
        "fear_greed": fear_greed,
        "_source": "kapy-provider:alternative.me",
    }
