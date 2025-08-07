import asyncio, sys
import logging
import aiohttp
try: from CobraRouter.CobraRouter.router._swaps import CobraSwaps # type: ignore
except: from .router._swaps import CobraSwaps
try: from CobraRouter.CobraRouter.router import Router # type: ignore
except: from .router import Router
try: from CobraRouter.CobraRouter.router import Cleaner # type: ignore
except: from .router import Cleaner
from solders.keypair import Keypair # type: ignore
from solders.message import VersionedMessage # type: ignore
from solana.rpc.async_api import AsyncClient
try: from CobraRouter.CobraRouter.router.libutils.colors import * # type: ignore
except: from .router.libutils.colors import *
try: from CobraRouter.CobraRouter.detect import CobraDetector # type: ignore
except: from .detect import CobraDetector

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format=f'{cc.LIGHT_MAGENTA}[CobraRouter] {cc.WHITE}%(message)s{cc.RESET}',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)

class CobraRouter:
    def __init__(self, rpc_url: str, session: aiohttp.ClientSession):
        self.async_client = AsyncClient(rpc_url)
        self.router = Router(self.async_client, session)
        self.detector = CobraDetector(self.router, rpc_url)
        self.swaps = CobraSwaps(self.router, self.async_client, aiohttp.ClientSession(), rpc_url)
        self.cleaner = Cleaner()

    async def get_priority_fee(self, msg: VersionedMessage | None = None):
        return await self.swaps.priority_fee_levels(msg)

    async def detect(self, mint: str, **kwargs):
        """
            Returns:
              tuple:
                dex: str
                pool: str
        """
        exclude_pools = kwargs.get("exclude_pools", [])
        dex, pool = await self.detector._detect(mint, exclude_pools=exclude_pools)
        return dex, pool
    
    async def swap(self, action: str, mint: str, pool: str, slippage: float, priority_level: str, dex: str, keypair: Keypair, sell_pct: int = 100, sol_amount_in: float = 0.0001):
        """
            Returns:
                tuple: (sig: str, ok: str)
        """
        if action == "buy":
            sig, ok = await self.swaps.buy(mint, pool, keypair, sol_amount_in, slippage, priority_level, dex)
            return (sig, ok)
        elif action == "sell":
            sig, ok = await self.swaps.sell(mint, pool, keypair, sell_pct, slippage, priority_level, dex)
            return (sig, ok)
        else:
            raise ValueError(f"Invalid action: {action}")

    async def close(self):
        try:
            cprint(f"Closing CobraRouter...")
            await self.router.close()
            await self.async_client.close()
            await self.detector.async_client.close()
            await self.swaps.close()
            return True
        except Exception as e:
            print(f"Error closing CobraRouter: {e}")
            return False