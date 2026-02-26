import asyncio
import aiohttp
from typing import Dict, Any

class DeribitClient:
    BASE_URL = "https://deribit.com/api/v2/public"

    @classmethod
    async def get_book_summary_by_currency(cls, currency: str) -> Dict[str, Any]:
        """Fetch book summary for a currency (e.g. BTC, ETH), optionally filtering by kind."""
        url = f"{cls.BASE_URL}/get_book_summary_by_currency"
        params = {"currency": currency.upper(), "kind": "option"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                if "error" in data:
                    raise Exception(f"Deribit API error: {data['error']}")
                return data.get("result", [])

    @classmethod
    async def get_instruments(cls, currency: str) -> Dict[str, Any]:
        """Fetch all option instruments for a given currency."""
        url = f"{cls.BASE_URL}/get_instruments"
        params = {"currency": currency.upper(), "kind": "option", "expired": "false"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                if "error" in data:
                    raise Exception(f"Deribit API error: {data['error']}")
                return data.get("result", [])
