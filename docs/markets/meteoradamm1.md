## Meteora DAMM v1

Constant-product pools on Meteora (v1). This adapter wraps pool discovery, pricing, and swap instruction building.

### Overview

- Class: `MeteoraDamm1`
- Core: `DAMM1Core`
- Pool authority program: `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB`

### Quickstart

```python
from CobraRouter.CobraRouter.router.meteora_damm_v1.damm_swap import MeteoraDamm1
from solders.keypair import Keypair

md1 = MeteoraDamm1(async_client)
pool = await md1.core.find_pool_by_mint(mint, sol_amount=0.005)
state = await md1.core.fetch_pool_state(pool)

# Buy ~0.005 SOL worth
tx_sig = await md1.buy(mint, state, int(0.005 * 1e9), keypair)

# Sell 25% of current token balance
tx_sig = await md1.sell(mint, state, 25, keypair)
```

### API

```python
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from typing import Optional

class MeteoraDamm1:
    core: "DAMM1Core"

    async def buy(self, mint: str | Pubkey, state: dict, amount_in: int, keypair: Keypair, fee_sol: float = 0.00001, return_instructions: bool = False) -> str | list: ...
    async def sell(self, mint: str | Pubkey, state: dict, percentage: float, keypair: Keypair, fee_sol: float = 0.00001, return_instructions: bool = False) -> str | list: ...
    async def close(self) -> None: ...

class DAMM1Core:
    async def get_price(self, mint: str | Pubkey, *, pool_addr: str | Pubkey | None = None) -> dict | None: ...
    async def fetch_pool_state(self, pool_addr: str | Pubkey) -> dict | None: ...
    async def find_pool_by_mint(self, mint: str | Pubkey, sol_amount: float = 0.001, limit: int = 50) -> str | None: ...
    async def async_get_pool_reserves(self, vault_a: Pubkey, vault_b: Pubkey) -> tuple[float, float]: ...
```

!!! note
    `amount_in` is lamports of SOL (wraps and closes temporary WSOL account).
    `percentage` must be 0 < pct ≤ 100; decimals are derived on-chain.
    `return_instructions=True` returns raw instruction list instead of sending.

### Pricing

`DAMM1Core.get_price` returns a dict:

```python
{"pool": str, "token_reserve": float, "sol_reserve": float, "price": float}
```

`price` is SOL per 1 token.

### Using via CobraRouter

```python
sig, ok = await cobra_router.swap(
    action="buy",
    mint=mint,
    pool=pool_addr,
    slippage=10,
    priority_level="medium",
    dex=cobra_router.router.damm_v1.core.WSOL_MINT and "MeteoraDamm1",  # pass the detected dex from cobra_router.detect
    keypair=keypair,
    sol_amount_in=0.005,
)
```


