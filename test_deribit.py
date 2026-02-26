import asyncio
from openbb_kapy.utils.deribit_client import DeribitClient

async def test():
    print("Testing get_instruments BTC...")
    instruments = await DeribitClient.get_instruments("BTC")
    print(f"Got {len(instruments)} BTC options.")
    if instruments:
        print("Sample instrument:", instruments[0])
    
    print("\nTesting get_book_summary_by_currency BTC...")
    book = await DeribitClient.get_book_summary_by_currency("BTC")
    print(f"Got {len(book)} book summaries.")
    if book:
        print("Sample book summary:", [b for b in book if b.get('instrument_name') == instruments[0]['instrument_name']][:1])

asyncio.run(test())
