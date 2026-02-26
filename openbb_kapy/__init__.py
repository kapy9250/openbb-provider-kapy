from openbb_core.provider.abstract.provider import Provider
from openbb_kapy.models.options_chains import KapyOptionsChainsFetcher

kapy_provider = Provider(
    name="kapy",
    website="https://github.com",
    description="Kapy Custom Provider for Crypto and Proxy Options.",
    fetcher_dict={
        "OptionsChains": KapyOptionsChainsFetcher,
    },
    repr_name="Kapy Custom",
)
