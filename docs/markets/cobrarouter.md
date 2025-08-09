## CobraRouter

High-level async client for routing price lookups and swaps across supported Solana DEXes. It wraps a low-level `Router`, a `CobraDetector` for pool detection, and `CobraSwaps` for transaction building/sending. Also exposes a `Cleaner` utility to close token accounts and unwrap WSOL.

### Quickstart

```python
import asyncio, aiohttp
from solders.keypair import Keypair
from CobraRouter.CobraRouter.main import CobraRouter

RPC_URL = "https://api.mainnet-beta.solana.com"

async def main():
    async with aiohttp.ClientSession() as session:
        router = CobraRouter(RPC_URL, session)

        # Warm-up RPC (fills cache used by fee estimation etc.)
        await router.ping()

        # Detect market and pool
        mint = "MINT_ADDRESS_HERE"  # example
        dex, pool = await router.detect(mint, use_cache=True)
        print("route:", dex, pool)

        # Get price
        price = await router.get_price(mint)
        print("price:", price)

        # # Get priority fee levels (SOL)
        # fees = await router.get_priority_fee()
        # print("fees:", fees)

        # Buy/Sell
        keypair = Keypair()  # load your own
        if dex and pool:
            sig, ok = await router.swap(
                action="buy",
                mint=mint,
                pool=str(pool),
                slippage=10,
                priority_level="medium",
                dex=dex,
                keypair=keypair,
                sol_amount_in=0.001,
            )
            print("buy:", sig, ok)

        await router.close()

asyncio.run(main())
```

### Supported concepts

- **DEX coverage**: PumpFun, PumpSwap, Meteora (DBC, DAMM v1/v2, DLMM), Raydium (AMM v4, CLMM, CPMM), Launchpad.
- **Routing**: The router “races” multiple probes concurrently and returns the first viable `(dex, pool)`.
- **Priority fees**: Recent prioritization fees on the blockchain are sampled and converted into SOL budgets for compute units.

## Routing and priority fee

- Routing: `Router.find_best_market_for_mint_race` races PumpFun/Launchpad/Believe, PumpSwap, Raydium (AMM/CLMM/CPMM), Meteora (DBC/DAMM/DLMM). Short-circuits when mint authority maps to a known platform.
- Exclusions and caching: pass `exclude_pools` and `use_cache=True` to reuse a prior `(dex,pool)`.
- Priority fees: `CobraSwaps.priority_fee_levels(msg)` calls `getRecentPrioritizationFees`, computes quantiles (25/50/75/99) and converts to SOL budgets for `_DEFAULT_CU` compute units. 

Common kwargs
- `return_instructions=True` returns instruction list to batch or sign elsewhere
- `slippage` is a percentage, per DEX adapter semantics
- `priority_level` one of: `low | medium | high | turbo`

## API Reference

### CobraRouter

Purpose
- High-level facade that warms RPC, detects routes, estimates priority fees, fetches prices, and executes swaps.

```python
import aiohttp
from typing import Optional
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.message import VersionedMessage
from solana.rpc.async_api import AsyncClient

class CobraRouter:
    async_client: AsyncClient
    router: "Router"
    detector: "CobraDetector"
    swaps: "CobraSwaps"
    cleaner: "Cleaner"

    def __init__(self, rpc_url: str, session: aiohttp.ClientSession) -> None: ...
    async def ping(self) -> bool: ...
    async def list_mints(self, pubkey: str | Pubkey) -> list[str]: ...
    async def get_priority_fee(self, msg: Optional[VersionedMessage] = None) -> dict[str, float]: ...
    async def get_decimals(self, mint: str | Pubkey) -> Optional[int]: ...
    async def detect(self, mint: str, **kwargs) -> tuple[str, str]: ...
    async def get_price(self, mint: str, **kwargs) -> Optional[float]: ...
    async def swap(self, action: str, mint: str, pool: str, slippage: float, priority_level: str, dex: str, keypair: Keypair, sell_pct: int = 100, sol_amount_in: float = 0.0001) -> tuple[Optional[str], bool]: ...
    async def close(self) -> bool: ...
```

!!! note
    `detect()` races multiple probes and returns `(dex, pool)`. Kwargs: `use_cache`, `exclude_pools`.
    `priority_level` accepts `"low" | "medium" | "high" | "turbo"`. `slippage` is percentage (e.g., 10 = 10%).

### Router

Low-level orchestrator for market adapters and route probing.

```python
from typing import Optional
from solders.pubkey import Pubkey

class Router:
    async def get_mint_authority(self, mint: str) -> tuple[Optional[str], Optional[dict]]: ...
    async def get_decimals(self, mint: str | Pubkey) -> Optional[int]: ...
    async def find_best_market_for_mint(self, mint: str) -> tuple[Optional[str], Optional[str]]: ...
    async def find_best_market_for_mint_race(self, mint: str, *, prefer_authority: bool = True, timeout: float | None = None, exclude_pools: list[str] = [], use_cache: bool = False) -> tuple[Optional[str], Optional[str]]: ...
    async def close(self) -> bool: ...
```

Additional helpers
- `check_route_*` (PumpFun, Launchpad, Believe) and `check_ray_*`/`check_damm*`/`check_dlmm` utilities used internally by the race.

### CobraDetector

Slim detection wrapper.

```python
class CobraDetector:
    async def _detect(self, mint: str, exclude_pools: list[str] = [], use_cache: bool = False) -> tuple[str | None, str | None]: ...
```

### CobraSwaps

DEX-agnostic swap and transfer executor with dynamic priority fees.

```python
from typing import Optional
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.message import VersionedMessage

class CobraSwaps:
    async def priority_fee_levels(self, msg: Optional[VersionedMessage] = None, cu: int = 300_000) -> dict[str, float]: ...
    async def get_price(self, mint: str | Pubkey, pool: str | Pubkey, dex: str) -> float: ...  # routes to the correct adapter (DBC/DAMM/DLMM/Raydium/Launchpad/PumpFun/PumpSwap)
    async def get_balance(self, mint: str | Pubkey, pubkey: str | Pubkey) -> tuple[float, int, str]: ...
    async def get_multiple_balances(self, mints: list[str | Pubkey], pubkey: str | Pubkey) -> dict[str, tuple[float, int]]: ...
    async def buy(self, mint: str | Pubkey, pool: str | Pubkey, keypair: Keypair, sol_amount: float, slippage: float = 10, priority_fee_level: str = "medium", dex: str = "", **kwargs): ...
    async def sell(self, mint: str | Pubkey, pool: str | Pubkey, keypair: Keypair, sell_pct: float = 100.0, slippage: float = 10, priority_fee_level: str = "medium", dex: str = "", **kwargs): ...
    async def send_transfer(self, keypair: Keypair, mint: str | Pubkey, amount: float, to: str | Pubkey, priority_fee_level: str = "medium", return_instructions: bool = False): ...
    async def close(self) -> bool: ...
```

!!! note
    Rejects priority-fee budgets above 0.01 SOL. `return_instructions=True` returns built ixs without sending.
    Creates and closes temporary WSOL or ATAs as needed (per adapter).
    Some adapters simulate prior to sending; DLMM may return ("replay", False) if simulation detects price shift.

### Cleaner

Account maintenance utilities.

```python
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient

class Cleaner:
    @staticmethod
    async def close_wsol(client: AsyncClient, payer: Keypair, wsol_accounts: list[Pubkey] | None = None) -> None: ...

    @staticmethod
    async def close_token_account(client: AsyncClient, payer: Keypair, mint: Pubkey | str, to_burn: int = 1, decimals: int = 6) -> tuple[str, bool]: ...
```

### Examples

Detect, price, and buy with priority fee level

```python
dex, pool = await router.detect(mint, use_cache=True)
fees = await router.get_priority_fee()
sig, ok = await router.swap(
    action="buy",
    mint=mint,
    pool=str(pool),
    slippage=10,
    priority_level="high",
    dex=dex,
    keypair=keypair,
    sol_amount_in=0.002,
)
```

Close WSOL after trading

```python
from CobraRouter.CobraRouter.router import Cleaner
await Cleaner.close_wsol(router.async_client, keypair)
```

### Troubleshooting

- detect returns (None, None): mint not found or no supported pools. Ensure correct mint and network RPC availability.
- Priority fee zeros: RPC does not support `getRecentPrioritizationFees`; router falls back to defaults.
- PumpFun “migrated”: router will attempt PumpSwap or Raydium routes via migration checks.