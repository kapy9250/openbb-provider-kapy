"""Exchange-balance snapshot helper (transitional bridge).

NOTE:
- Coinglass balance endpoint is JS-rendered and currently not exposed via a stable
  unauthenticated JSON endpoint in this runtime.
- As an interim migration step, this helper bridges legacy normalized raw output
  from market-data (`raw/exchange-balance/latest.json`) into provider namespace.

This keeps pipeline call-sites provider-first while preserving fallback behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ExchangeBalanceFetchError(RuntimeError):
    """Raised when exchange balance fetch fails."""


DEFAULT_RAW_PATH = Path("/workspace/market-data/raw/exchange-balance/latest.json")


def fetch_exchange_balance_snapshot(raw_path: Path | None = None) -> dict[str, Any]:
    path = raw_path or DEFAULT_RAW_PATH
    if not path.exists():
        raise ExchangeBalanceFetchError(f"legacy raw exchange-balance file missing: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["_source"] = "kapy-provider:legacy-raw-bridge"
    return payload
