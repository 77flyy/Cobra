## Meteora DAMM v2

Meteora constant-product pools (v2). Includes pool discovery, pricing, and swap builders with typed `SwapParams`.

### Overview

- Class: `MeteoraDamm2`
- Core: `DAMM2Core`, `DAMM2SwapBuilder`, `SwapParams`

### Quickstart

```python
from CobraRouter.CobraRouter.router.meteora_damm_v2.damm2_swap import MeteoraDamm2
from solders.keypair import Keypair

md2 = MeteoraDamm2(async_client)
pool = await md2.core.find_pools_by_mint(mint)
state = await md2.core.fetch_pool_state(pool)

swap_params = await md2.build_swap_params(state, pool, mint, tokens_in=1000000, keypair=keypair)
tx = await md2.buy(swap_params, keypair)
```

### API

```python
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from typing import Optional

class MeteoraDamm2:
    core: "DAMM2Core"
    async def build_swap_params(self, state: dict, pool: str | Pubkey, base_mint: str | Pubkey, tokens_in: int, keypair: Keypair, minimum_amount_out: int = 0) -> "SwapParams": ...
    async def swap(self, action: str, pool: str | Pubkey, state: dict, keypair: Keypair, tokens_in: int | None = None, slippage: float = 0.5, percentage: float | None = None) -> str | None: ...
    async def buy(self, params: "SwapParams", keypair: Keypair, return_instructions: bool = False): ...
    async def sell(self, params: "SwapParams", keypair: Keypair, return_instructions: bool = False): ...
    async def close(self) -> None: ...

class DAMM2Core:
    async def fetch_pool_state(self, pool_address: str | Pubkey) -> dict: ...
    async def find_pools_by_mint(self, mint: str | Pubkey, sol_amount: float = 0.01, limit: int = 10) -> str | None: ...
    async def get_price(self, mint: str | Pubkey | None = None, *, pool_addr: str | Pubkey) -> dict | None: ...
```

!!! note
    `tokens_in` are base token units for `buy`/`sell` in builder methods; UI conversions required.
    Temporary WSOL accounts are created and closed automatically.
    `swap(action=...)` convenience path builds and sends a transaction directly.

### Pricing

`DAMM2Core.get_price(pool_addr=...)` returns a dict with `pool`, `token_mint`, and `price` (SOL per 1 token).

### Using via CobraRouter

```python
sig, ok = await cobra_router.swap(
    action="sell",
    mint=mint,
    pool=pool_addr,
    slippage=10,
    priority_level="medium",
    dex="MeteoraDamm2",
    keypair=keypair,
    sell_pct=50,
)
```


