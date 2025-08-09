## Meteora DLMM

Discrete Liquidity Market Maker pools. Requires bin selection; adapter resolves adjacent bin arrays and builds swap instructions.

### Overview

- Class: `MeteoraDLMM`
- Core: `DLMMCore`, helper `DLMMBin`

### Quickstart

```python
from CobraRouter.CobraRouter.router.meteora_dlmm.dlmm_swap import MeteoraDLMM
from solders.keypair import Keypair

dlmm = MeteoraDLMM(async_client)
state = await dlmm.core.fetch_pool_state(pool)
sig = await dlmm.buy(mint, state, int(0.005 * 1e9), keypair)
sig = await dlmm.sell(mint, state, 50, keypair)
```

### API

```python
from solders.keypair import Keypair
from solders.pubkey import Pubkey

class MeteoraDLMM:
    core: "DLMMCore"
    async def buy(self, mint: str | Pubkey, state: dict, amount_in: int, keypair: Keypair, fee_sol: float = 0.00001, return_instructions: bool = False) -> str | list: ...
    async def sell(self, mint: str | Pubkey, state: dict, percentage: float, keypair: Keypair, fee_sol: float = 0.00001, return_instructions: bool = False) -> str | list: ...

class DLMMCore:
    async def fetch_pool_state(self, pool_addr: str | Pubkey) -> dict: ...
    async def get_price(self, *, pool_addr: str | Pubkey, strict_mint: str | Pubkey | None = None) -> dict | None: ...
    async def find_dlmm_pools_by_mint(self, mint_a: str | Pubkey, mint_b: str | Pubkey | None = None, max_preset_index: int = 256) -> list[str]: ...
    async def find_suitable_pool(self, pools: list, mint: str | Pubkey, sol_amount: float = 0.001, exclude_pools: list[str] = []) -> tuple[str | None, str | None, str | None]: ...
```

!!! note
    Temporary WSOL is created and closed per swap.
    DLMM routes are simulated by `CobraSwaps` and may return ("replay", False) when price moved.
    `percentage` must be 0 < pct ≤ 100.

### Pricing

`DLMMCore.get_price(pool_addr=...)` returns `{"pool","token_mint","price"}` where `price` is SOL per 1 token.


