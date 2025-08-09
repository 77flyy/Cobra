## Raydium Launchpad

IDO-style pools with virtual/real reserves. Adapter supports buy/sell with constant-product approximations and migration checks.

### Overview

- Class: `RaydiumLaunchpadSwap`
- Core: `RaydiumLaunchpadCore`

### Quickstart

```python
from CobraRouter.CobraRouter.router.raydiumswap.launchlab.launchlab_swap import RaydiumLaunchpadSwap
from solders.keypair import Keypair

lp = RaydiumLaunchpadSwap(async_client)
pool = await lp.core.find_launchpad_pool_by_mint(mint)
ok, sig = await lp.execute_lp_buy_async(mint, 0.01, 5, keypair, pool)
```

### API

```python
class RaydiumLaunchpadSwap:
    async def execute_lp_buy_async(self, token_mint: str, sol_amount: float, slippage_pct: float, keypair: Keypair, pool_id: str | Pubkey | None = None, fee_micro_lamports: int = 1_000_000, return_instructions: bool = False): ...
    async def execute_lp_sell_async(self, token_mint: str, keypair: Keypair, sell_pct: float = 100, slippage_pct: float = 5, pool_id: str | Pubkey | None = None, fee_micro_lamports: int = 1_000_000, return_instructions: bool = False): ...

class RaydiumLaunchpadCore:
    async def find_launchpad_pool_by_mint(self, mint: str) -> str | None: ...
    async def launchpad_check_has_migrated(self, pool_id: str | Pubkey) -> bool: ...
    async def async_fetch_pool_keys(self, pool_id: str | Pubkey) -> LaunchpadPoolKeys | None: ...
    async def get_price(self, pool_addr: str | Pubkey) -> float | None: ...
```

!!! note
    Uses temporary WSOL accounts; closes after swap.
    Price computed from virtual/real reserves and decimals.


