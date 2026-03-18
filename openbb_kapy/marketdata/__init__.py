"""Market-data fetch helpers for Kapy provider-style ingestion."""

from .defi import fetch_defi_snapshot
from .derivatives import fetch_derivatives_snapshot
from .etf_flow import fetch_etf_flow_snapshot
from .etf_source import fetch_etf_source_snapshot
from .etf_volume import fetch_etf_volume_snapshot
from .exchange_balance import fetch_exchange_balance_snapshot
from .forex import fetch_forex_snapshot
from .mining import fetch_mining_snapshot
from .onchain import fetch_onchain_snapshot
from .sentiment import fetch_sentiment_snapshot
from .stablecoins_usde import fetch_stablecoins_usde_snapshot
from .volume import fetch_volume_snapshot

__all__ = [
    "fetch_defi_snapshot",
    "fetch_derivatives_snapshot",
    "fetch_etf_flow_snapshot",
    "fetch_etf_source_snapshot",
    "fetch_etf_volume_snapshot",
    "fetch_exchange_balance_snapshot",
    "fetch_forex_snapshot",
    "fetch_mining_snapshot",
    "fetch_onchain_snapshot",
    "fetch_sentiment_snapshot",
    "fetch_stablecoins_usde_snapshot",
    "fetch_volume_snapshot",
]
