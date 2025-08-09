## Raydium AMM v4

Raydium v4 AMM using OpenBook market routing. Adapter can estimate outputs and swap using temporary WSOL.

### Overview

- Class: `RaydiumSwap`
- Core: `RaydiumCore`

### Quickstart

```python
from CobraRouter.CobraRouter.router.raydiumswap.amm_v4.v4_amm_swap import RaydiumSwap
from solders.keypair import Keypair

ray = RaydiumSwap(async_client)
pool = await ray.find_pool_by_mint(mint)
ok, sig = await ray.execute_buy_async(mint, 0.002, 10, 0, pool, keypair)
```

### API

```python
class RaydiumSwap:
    async def find_pool_by_mint(self, mint: str | Pubkey) -> str | None: ...
    async def execute_buy_async(self, mint_address: str = "", sol_amount: float = 0.0001, slippage_percentage: int = 5, fee: int = 1000000, pool = None, keypair: Keypair = None, return_instructions: bool = False): ...
    async def execute_sell_async(self, mint_address: str, keypair: Keypair, sell_pct: int = 100, slippage_percentage: int = 5, fee: int = 1000000, return_instructions: bool = False): ...

class RaydiumCore:
    async def async_fetch_pool_keys(self, pool_address: str | Pubkey) -> RaydiumPoolKeys | None: ...
    async def get_price(self, pool_addr: str | Pubkey) -> float | None: ...
```

!!! note 
    Wraps WSOL accounts for buy/sell and closes them.
    `slippage_percentage` applies to output min calculation.


