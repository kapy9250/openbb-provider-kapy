"""Provider-style derivatives snapshot model/fetcher.

Lightweight fetcher abstraction used by decision pipeline migration.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from openbb_core.provider.abstract.data import Data
from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.abstract.query_params import QueryParams

from openbb_kapy.marketdata.derivatives import fetch_derivatives_snapshot


class KapyDerivativesQueryParams(QueryParams):
    """Derivatives query params."""

    date: date | None = None


class KapyDerivativesData(Data):
    """Derivatives normalized metric row."""

    symbol: str
    metric_name: str
    value: float | None = None
    snapshot_date: date | None = None


class KapyDerivativesFetcher(Fetcher[KapyDerivativesQueryParams, list[KapyDerivativesData]]):
    """Derivatives snapshot fetcher."""

    @staticmethod
    def transform_query(params: dict[str, Any]) -> KapyDerivativesQueryParams:
        return KapyDerivativesQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: KapyDerivativesQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return fetch_derivatives_snapshot()

    @staticmethod
    def transform_data(
        query: KapyDerivativesQueryParams,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> list[KapyDerivativesData]:
        rows: list[KapyDerivativesData] = []
        snap_date = query.date

        funding = ((data.get("binance") or {}).get("btc_funding") or [])
        if funding:
            latest = funding[-1]
            sym = latest.get("symbol") or "BTCUSDT"
            if latest.get("fundingRate") is not None:
                rows.append(KapyDerivativesData(symbol=sym, metric_name="funding_rate", value=float(latest.get("fundingRate")), snapshot_date=snap_date))
            if latest.get("markPrice") is not None:
                rows.append(KapyDerivativesData(symbol=sym, metric_name="mark_price", value=float(latest.get("markPrice")), snapshot_date=snap_date))

        ls = ((data.get("binance") or {}).get("long_short") or [])
        if ls:
            latest = ls[-1]
            for k in ["longShortRatio", "longAccount", "shortAccount"]:
                if latest.get(k) is not None:
                    rows.append(
                        KapyDerivativesData(
                            symbol="BTCUSDT",
                            metric_name={
                                "longShortRatio": "long_short_ratio",
                                "longAccount": "long_account",
                                "shortAccount": "short_account",
                            }[k],
                            value=float(latest.get(k)),
                            snapshot_date=snap_date,
                        )
                    )

        for item in ((data.get("coinalyze") or {}).get("oi") or []):
            if item.get("symbol") and item.get("value") is not None:
                rows.append(
                    KapyDerivativesData(
                        symbol=str(item.get("symbol")),
                        metric_name="open_interest",
                        value=float(item.get("value")),
                        snapshot_date=snap_date,
                    )
                )

        return rows
