"""Provider-style ETF flow snapshot model/fetcher.

This model is intentionally lightweight and can be consumed directly by
pipeline scripts while preserving OpenBB provider coding style.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from openbb_core.provider.abstract.data import Data
from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.abstract.query_params import QueryParams

from openbb_kapy.marketdata.etf_flow import fetch_etf_flow_snapshot


class KapyEtfFlowQueryParams(QueryParams):
    """ETF flow query params."""

    date: date | None = None


class KapyEtfFlowData(Data):
    """ETF flow snapshot data row."""

    ticker: str
    flow_btc: float | None = None
    flow_usd: float | None = None
    holdings_btc: float | None = None
    snapshot_date: date | None = None


class KapyEtfFlowFetcher(Fetcher[KapyEtfFlowQueryParams, list[KapyEtfFlowData]]):
    """ETF flow snapshot fetcher."""

    @staticmethod
    def transform_query(params: dict[str, Any]) -> KapyEtfFlowQueryParams:
        return KapyEtfFlowQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: KapyEtfFlowQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return fetch_etf_flow_snapshot()

    @staticmethod
    def transform_data(
        query: KapyEtfFlowQueryParams,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> list[KapyEtfFlowData]:
        rows: list[KapyEtfFlowData] = []
        snap_date = query.date or (date.fromisoformat(data.get("updated_date")) if data.get("updated_date") else None)

        if data.get("btc_holdings") is not None:
            rows.append(
                KapyEtfFlowData(
                    ticker="TOTAL",
                    holdings_btc=float(data.get("btc_holdings")),
                    snapshot_date=snap_date,
                )
            )

        for item in data.get("top_flows") or []:
            rows.append(
                KapyEtfFlowData(
                    ticker=str(item.get("ticker") or "").upper(),
                    flow_btc=float(item.get("flow_btc")) if item.get("flow_btc") is not None else None,
                    flow_usd=float(item.get("flow_usd_million")) * 1_000_000 if item.get("flow_usd_million") is not None else None,
                    snapshot_date=snap_date,
                )
            )
        return rows
