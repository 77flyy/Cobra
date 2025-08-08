import asyncio, argparse
try: from router import Router
except: from .router import Router
from solders.keypair import Keypair # type: ignore
from solana.rpc.async_api import AsyncClient
try: from router.libutils.colors import *
except: from .router.libutils.colors import *

class CobraDetector:
    def __init__(self, router: Router, async_client: AsyncClient):
        self.async_client = async_client
        self.router = router

    async def _detect(self, mint: str, exclude_pools: list[str] = [], use_cache: bool = False):
        dex, pool = await self.router.find_best_market_for_mint_race(mint, exclude_pools=exclude_pools, use_cache=use_cache)
        return (dex, pool)