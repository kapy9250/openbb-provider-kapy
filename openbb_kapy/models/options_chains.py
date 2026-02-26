"""Kapy options chains fetcher.

Supported modes:
- Commodity proxy mapping via yfinance
  - GC=F -> GLD
  - CL=F -> USO
- Crypto options via Deribit
  - BTC-USD / ETH-USD
"""

from datetime import datetime, timezone
from typing import Any

from openbb_core.provider.abstract.annotated_result import AnnotatedResult
from openbb_core.provider.standard_models.options_chains import (
    OptionsChainsData,
    OptionsChainsQueryParams,
)
from openbb_yfinance.models.options_chains import YFinanceOptionsChainsFetcher

from openbb_kapy.utils.deribit_client import DeribitClient


class KapyOptionsChainsQueryParams(OptionsChainsQueryParams):
    """Kapy Options Chains Query Parameters."""


class KapyOptionsChainsData(OptionsChainsData):
    """Kapy Options Chains Data."""


class KapyOptionsChainsFetcher(YFinanceOptionsChainsFetcher):
    """Kapy Options Chains Fetcher."""

    SYMBOL_MAP = {"GC=F": "GLD", "CL=F": "USO"}
    CRYPTO_MAP = {"BTC-USD": "BTC", "ETH-USD": "ETH"}

    @staticmethod
    def transform_query(params: dict[str, Any]) -> KapyOptionsChainsQueryParams:
        return KapyOptionsChainsQueryParams(**params)

    @staticmethod
    async def _extract_from_deribit(query_symbol: str, currency: str) -> dict:
        instruments = await DeribitClient.get_instruments(currency)
        books = await DeribitClient.get_book_summary_by_currency(currency)
        book_by_name = {b.get("instrument_name"): b for b in books}

        now = datetime.now(timezone.utc)
        records: list[dict[str, Any]] = []

        for ins in instruments:
            name = ins.get("instrument_name")
            if not name:
                continue
            book = book_by_name.get(name, {})

            exp_ts = ins.get("expiration_timestamp")
            exp_dt = (
                datetime.fromtimestamp(exp_ts / 1000, tz=timezone.utc)
                if isinstance(exp_ts, (int, float))
                else None
            )
            dte = (exp_dt.date() - now.date()).days if exp_dt else None

            mark = book.get("mark_price")
            bid = book.get("bid_price")
            ask = book.get("ask_price")
            volume = book.get("volume")
            oi = book.get("open_interest")

            option_type = ins.get("option_type")
            if option_type == "call":
                option_type = "call"
            elif option_type == "put":
                option_type = "put"
            else:
                continue

            records.append(
                {
                    "underlying_symbol": query_symbol,
                    "underlying_price": book.get("underlying_price"),
                    "contract_symbol": name,
                    "expiration": exp_dt.strftime("%Y-%m-%d") if exp_dt else None,
                    "dte": dte,
                    "strike": ins.get("strike"),
                    "option_type": option_type,
                    "contract_size": ins.get("contract_size"),
                    "open_interest": oi if oi is not None else 0,
                    "volume": volume if volume is not None else 0,
                    "last_trade_price": book.get("last"),
                    "bid": bid,
                    "ask": ask,
                    "mark": mark,
                    "implied_volatility": (
                        (book.get("mark_iv") / 100)
                        if isinstance(book.get("mark_iv"), (int, float))
                        else None
                    ),
                }
            )

        underlying = {
            "symbol": query_symbol,
            "name": f"{currency} Options (Deribit)",
            "exchange": "Deribit",
            "currency": currency,
            "last_price": books[0].get("underlying_price") if books else None,
            "kapy_requested_symbol": query_symbol,
            "kapy_mapped_symbol": currency,
            "kapy_source": "deribit",
        }

        return {"underlying": underlying, "chains": records}

    @staticmethod
    async def aextract_data(
        query: KapyOptionsChainsQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> dict:
        requested = query.symbol.upper()

        # Crypto path: Deribit
        if requested in KapyOptionsChainsFetcher.CRYPTO_MAP:
            currency = KapyOptionsChainsFetcher.CRYPTO_MAP[requested]
            return await KapyOptionsChainsFetcher._extract_from_deribit(requested, currency)

        # Default path: yfinance (with optional commodity proxy mapping)
        mapped = KapyOptionsChainsFetcher.SYMBOL_MAP.get(requested, requested)
        upstream_query = KapyOptionsChainsQueryParams(symbol=mapped)
        data = await YFinanceOptionsChainsFetcher.aextract_data(upstream_query, credentials, **kwargs)
        data.setdefault("underlying", {})
        data["underlying"]["kapy_requested_symbol"] = requested
        data["underlying"]["kapy_mapped_symbol"] = mapped
        data["underlying"]["kapy_source"] = "yfinance"
        return data

    @staticmethod
    def transform_data(
        query: KapyOptionsChainsQueryParams,
        data: dict,
        **kwargs: Any,
    ) -> AnnotatedResult[KapyOptionsChainsData]:
        requested = query.symbol.upper()
        source = data.get("underlying", {}).get("kapy_source", "yfinance")

        if source == "deribit":
            from pandas import DataFrame

            df = DataFrame(data.get("chains", []))
            if df.empty:
                validated = KapyOptionsChainsData.model_validate(
                    {
                        "underlying_symbol": [],
                        "contract_symbol": [],
                        "expiration": [],
                        "strike": [],
                        "option_type": [],
                    }
                )
                metadata = {
                    "kapy_requested_symbol": requested,
                    "kapy_mapped_symbol": data.get("underlying", {}).get("kapy_mapped_symbol"),
                    "kapy_source": "deribit",
                }
                return AnnotatedResult(result=validated, metadata=metadata)

            # ensure required columns exist
            for col in [
                "underlying_symbol",
                "contract_symbol",
                "expiration",
                "strike",
                "option_type",
            ]:
                if col not in df.columns:
                    df[col] = None

            payload = df.where(df.notna(), None).to_dict("list")
            validated = KapyOptionsChainsData.model_validate(payload)
            metadata = {
                "kapy_requested_symbol": requested,
                "kapy_mapped_symbol": data.get("underlying", {}).get("kapy_mapped_symbol"),
                "kapy_source": "deribit",
                "exchange": "Deribit",
            }
            return AnnotatedResult(result=validated, metadata=metadata)

        # yfinance transform path
        result = YFinanceOptionsChainsFetcher.transform_data(query, data, **kwargs)
        mapped = data.get("underlying", {}).get("kapy_mapped_symbol", requested)

        if mapped != requested:
            payload = result.result.model_dump()
            if isinstance(payload, list):
                from pandas import DataFrame

                payload_df = DataFrame(payload)
                if "underlying_symbol" in payload_df.columns:
                    payload_df["underlying_symbol"] = requested
                payload = payload_df.to_dict("list")
            elif "underlying_symbol" in payload and isinstance(payload["underlying_symbol"], list):
                payload["underlying_symbol"] = [requested for _ in payload["underlying_symbol"]]
            result.result = KapyOptionsChainsData.model_validate(payload)

        metadata = dict(result.metadata or {})
        metadata["kapy_requested_symbol"] = requested
        metadata["kapy_mapped_symbol"] = mapped
        metadata["kapy_source"] = "yfinance"

        return AnnotatedResult(result=result.result, metadata=metadata)
