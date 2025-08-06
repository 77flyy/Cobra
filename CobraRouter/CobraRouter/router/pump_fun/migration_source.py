import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from solders.pubkey import Pubkey # type: ignore
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import MemcmpOpts
from solana.exceptions import SolanaRpcException
from solana.rpc.commitment import Confirmed

PUMPSWAP_AMM_ID   = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
BASE_MINT_OFFSET  = 43
QUOTE_MINT_OFFSET = 75

RAYDIUM_POOL_INFO = "https://api-v3.raydium.io/pools/info/mint"

async def find_pumpswap_pools(
    client: AsyncClient,
    base_mint: str,
    quote_mint: Optional[str] = None,
    retry: bool = False
) -> List[Dict[str, Any]]:
    try:
        """On-chain lookup of PumpSwapAMM pools for base (and optional quote)."""
        base_pk = Pubkey.from_string(base_mint) if isinstance(base_mint, str) else base_mint
        filters = [MemcmpOpts(offset=BASE_MINT_OFFSET, bytes=str(base_pk))]
        if quote_mint:
            quote_pk = Pubkey.from_string(quote_mint) if isinstance(quote_mint, str) else quote_mint
            filters.append(MemcmpOpts(offset=QUOTE_MINT_OFFSET,
                                    bytes=str(quote_pk)))
        resp = await client.get_program_accounts(
            pubkey=PUMPSWAP_AMM_ID,
            commitment=Confirmed,
            encoding="base64",
            filters=filters,
        )
        return [{"pubkey": str(acc.pubkey), "account": acc.account}
                for acc in resp.value]
    except SolanaRpcException as e:
        print(f"Couldn't find a pumpswap pool for {base_mint}: {e}")
        if not retry:
            return await find_pumpswap_pools(client, base_mint, quote_mint, retry=True)
        else:
            return []

async def find_raydium_pools(
    session: aiohttp.ClientSession,
    base_mint: str
) -> Dict[str, Any]:
    """HTTP lookup of Raydium v3 pools for base mint."""
    params = {"mint1": base_mint,
              "poolType": "all",
              "poolSortField": "default",
              "sortType": "desc",
              "pageSize": 100,
              "page": 1}
    async with session.get(RAYDIUM_POOL_INFO, params=params) as resp:
        resp.raise_for_status()
        return await resp.json()

async def find_migration_source(
    ctx: AsyncClient,
    base_mint: str,
    quote_mint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    1) Try PumpSwap on-chain.
    2) If it finds at least one pool, return that.
    3) Otherwise fall back to Raydium HTTP.
    """
    ps_pools = await find_pumpswap_pools(ctx, base_mint, quote_mint)

    if ps_pools:
        return {"source": "pumpswap", "result": ps_pools}

    async with aiohttp.ClientSession() as session:
        ry = await find_raydium_pools(session, base_mint)

    data = ry.get("data", {})
    if data.get("count", 0) > 0:
        return {"source": "raydium", "result": ry}

    return {"source": "none", "result": {"pumpswap": ps_pools, "raydium": ry}}