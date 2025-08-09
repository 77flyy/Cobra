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
from solders.pubkey import Pubkey # type: ignore
from solana.rpc.types import TokenAccountOpts # type: ignore
from solana.rpc.commitment import Processed # type: ignore
try: from CobraRouter.CobraRouter.router.libutils._common import TOKEN_2022, TOKEN_PROGRAM_ID # type: ignore
except: from .router.libutils._common import TOKEN_2022, TOKEN_PROGRAM_ID # type: ignore

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
        self.detector = CobraDetector(self.router, self.async_client)
        self.swaps = CobraSwaps(self.router, self.async_client, session, rpc_url)
        self.cleaner = Cleaner()
        self.warmed_up = False # warming up RPC cache to avoid cold-start overhead

    async def list_mints(self, pubkey: str | Pubkey) -> list[str]:
        """
        List all mints owned by a given address.

        Args:
            pubkey: str | Pubkey
        Returns:
            list[str]: list of mint addresses
        """
        try:
            owner = Pubkey.from_string(pubkey) if isinstance(pubkey, str) else pubkey

            resp1 = await self.async_client.get_token_accounts_by_owner_json_parsed(
                owner,
                TokenAccountOpts(program_id=TOKEN_PROGRAM_ID),
                Processed,
            )
            resp2 = await self.async_client.get_token_accounts_by_owner_json_parsed(
                owner,
                TokenAccountOpts(program_id=TOKEN_2022),
                Processed,
            )

            def extract_mints(response) -> list[str]:
                mints: list[str] = []
                value = getattr(response, "value", []) or []
                for item in value:
                    mint: str | None = None
                    try:
                        parsed = item.account.data.parsed
                        if isinstance(parsed, dict):
                            mint = parsed.get("info", {}).get("mint")
                        else:
                            mint = getattr(getattr(parsed, "info", {}), "mint", None)
                    except Exception:
                        try:
                            mint = item["account"]["data"]["parsed"]["info"]["mint"]
                        except Exception:
                            mint = None
                    if isinstance(mint, str) and len(mint) > 0:
                        mints.append(mint)
                return mints

            all_mints = extract_mints(resp1) + extract_mints(resp2)

            seen: set[str] = set()
            unique_mints: list[str] = []
            for m in all_mints:
                if m not in seen:
                    seen.add(m)
                    unique_mints.append(m)
            return unique_mints
        except Exception as e:
            logging.error(f"Error listing mints: {e}")
            return []

    async def ping(self) -> bool:
        """
        Ping the RPC to warm up the cache.
        """
        try:
            resp = await self.async_client.get_latest_blockhash()
            if resp is None:
                raise Exception("ping: Failed to get latest blockhash")
            self.warmed_up = True
            logging.info("RPC cache warmed up.")
            return True
        except Exception as e:
            logging.error(f"Error pinging router: {e}")
            return False

    async def get_priority_fee(self, msg: VersionedMessage | None = None):
        """
        Get priority fee levels.
            Args:
                msg: VersionedMessage | None
            Returns:
                dict:
                    low: float
                    medium: float
                    high: float
                    turbo: float
        """
        while not self.warmed_up:
            logging.info("Warming up RPC cache...")
            if not await self.ping():
                await asyncio.sleep(0.5)
                continue
            else:
                break
        return await self.swaps.priority_fee_levels(msg)

    async def get_decimals(self, mint: str | Pubkey):
        """
        Get decimals of a mint.
        """
        try:
            decimals = await self.router.get_decimals(mint)
            return decimals
        except Exception as e:
            logging.error(f"Error getting decimals: {e}")
            return None

    async def get_price(self, mint: str, **kwargs):
        """
        Get price of a mint.
        """
        try:
            dex, pool = await self.detect(mint, **kwargs)
            if not dex or not pool:
                raise ValueError(f"No pool found for mint: {mint}")
            return await self.swaps.get_price(mint, pool, dex)
        except Exception as e:
            logging.error(f"Error getting price: {e}")
            return None

    async def detect(self, mint: str, **kwargs):
        """
            Returns:
              tuple:
                dex: str
                pool: str
        """
        while not self.warmed_up:
            logging.info("Warming up RPC cache...")
            if not await self.ping():
                await asyncio.sleep(0.5)
                continue
            else:
                break
        use_cache = kwargs.get("use_cache", False)
        exclude_pools = kwargs.get("exclude_pools", [])
        dex, pool = await self.detector._detect(mint, exclude_pools=exclude_pools, use_cache=use_cache)
        return dex, pool
    
    async def swap(self, action: str, mint: str, pool: str, slippage: float, priority_level: str, dex: str, keypair: Keypair, sell_pct: int = 100, sol_amount_in: float = 0.0001):
        """
            Returns:
                tuple: (sig: str, ok: str)
        """
        while not self.warmed_up:
            logging.info("Warming up RPC cache...")
            if not await self.ping():
                await asyncio.sleep(0.5)
                continue
            else:
                break
        if action == "buy":
            sig, ok = await self.swaps.buy(mint, pool, keypair, sol_amount_in, slippage, priority_level, dex)
            return (sig, ok)
        elif action == "sell":
            sig, ok = await self.swaps.sell(mint, pool, keypair, sell_pct, slippage, priority_level, dex)
            return (sig, ok)
        else:
            raise ValueError(f"Invalid action: {action}")

    async def close(self):
        """
        Close the CobraRouter.
        """
        try:
            cprint(f"Closing CobraRouter...")
            await self.router.close()
            await self.async_client.close()
            await self.detector.async_client.close()
            await self.swaps.close()
            return True
        except Exception as e:
            logging.info(f"Error closing CobraRouter: {e}")
            return False