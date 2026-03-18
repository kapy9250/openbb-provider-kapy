"""USDe stablecoin snapshot fetcher (provider-style helper).

Sources:
- CoinGecko simple price (USDe / sUSDe)
- DefiLlama protocol TVL (Ethena)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


class StablecoinUsdeFetchError(RuntimeError):
    """Raised when USDe snapshot fetch fails."""


def _get_json(url: str) -> Any:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 KapyProvider/1.0"}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_stablecoins_usde_snapshot() -> dict[str, Any]:
    price_url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=ethena-usde,ethena-staked-usde&vs_currencies=usd&include_24hr_change=true"
    )
    p = _get_json(price_url)

    usde_price = ((p.get("ethena-usde") or {}).get("usd"))
    susde_price = ((p.get("ethena-staked-usde") or {}).get("usd"))

    tvl = None
    try:
        ethena = _get_json("https://api.llama.fi/protocol/ethena")
        tvl = (ethena.get("currentChainTvls") or {}).get("Ethereum")
        if tvl is None:
            hist = ethena.get("tvl") or []
            if hist:
                tvl = (hist[-1] or {}).get("totalLiquidityUSD")
    except Exception:
        tvl = None

    if usde_price is None:
        raise StablecoinUsdeFetchError("USDe price unavailable")

    peg_dev = (float(usde_price) - 1.0) * 100.0

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price": float(usde_price),
        "susde_price": float(susde_price) if susde_price is not None else None,
        "peg_deviation_pct": peg_dev,
        "ethena": {"tvl": float(tvl) if tvl is not None else None},
        "_source": "kapy-provider:coingecko+defillama",
    }
