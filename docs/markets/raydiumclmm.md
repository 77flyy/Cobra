## Raydium CLMM

Concentrated liquidity pools. Adapter estimates outputs conservatively and builds swap ixs across tick arrays.

### Overview

- Class: `RaydiumClmmSwap`
- Core: `ClmmCore`

### Quickstart

```python
from CobraRouter.CobraRouter.router.raydiumswap.clmm.clmm_swap import RaydiumClmmSwap
from solders.keypair import Keypair

clmm = RaydiumClmmSwap(async_client)
pool = await clmm.core.find_pool_by_mint_with_min_liquidity(mint, min_liquidity=10000)
ok, sig = await clmm.execute_clmm_buy_async(mint, 0.002, keypair, 1, 1_000_000, pool)
```

### API

```python
class RaydiumClmmSwap:
    async def execute_clmm_buy_async(self, token_mint: str, sol_amount: float, keypair: Keypair, min_out: int = 1, fee_micro_lamports: int = 1_000_000, pool_id: str | None = None, return_instructions: bool = False) -> tuple[bool, str] | list: ...
    async def execute_clmm_sell_async(self, token_mint: str, keypair: Keypair, sell_pct: int = 100, slippage_pct: int = 5, fee_micro_lamports: int = 1_000_000, pool_id: str | None = None, return_instructions: bool = False) -> tuple[bool, str] | list: ...

class ClmmCore:
    async def find_pool_by_mint_with_min_liquidity(self, mint: str | Pubkey, mint_b: str | Pubkey | None = None, min_liquidity: int = 0) -> Pubkey | None: ...
    async def get_price(self, pool_addr: str | Pubkey, *, strict_mint: str | Pubkey | None = None) -> dict | None: ...
```

!!! note
    WSOL wrapping/closing handled per swap; tick arrays fetched and appended as extra accounts.
    For sells, token must be `mint_b` (WSOL-token pool assumption).


