## Meteora DBC (Bonding Curve)

Virtual pools with migration support. Provides pool fetch, pricing, and swap instructions with referral support.

### Overview

- Class: `MeteoraDBC`
- Swap: `MeteoraDBCSwap`
- Helpers: `fetch_virtual_pool`, `price_from_sqrt`, `find_pool`

### Quickstart

```python
from CobraRouter.CobraRouter.router.meteoraDBC.meteora import MeteoraDBC
from solders.keypair import Keypair

dbc = MeteoraDBC(async_client)
pool, state = await dbc.fetch_state(mint)
price = await dbc.get_price(pool, async_client)

# Buy SOL->token
sig = await dbc.swap.buy(state, int(0.005 * 1e9), 1, keypair)

# Sell 50%
sig = await dbc.swap.sell(state, 50, keypair, slippage_pct=5)
```

### API

```python
from solders.keypair import Keypair
from solders.pubkey import Pubkey

class MeteoraDBC:
    async def fetch_state(self, mint: str | Pubkey) -> tuple[str | None, dict | str]: ...
    async def buy(self, mint: str, sol_amount: float, fee_sol: float = 0.00001) -> str | None: ...
    async def sell(self, mint: str, percentage: float, fee_sol: float = 0.00001) -> str | None: ...
    async def close(self) -> None: ...

class MeteoraDBCSwap:
    async def buy(self, state: dict, amount_in: int, min_amount_out: int, keypair: Keypair, quote_mint: Pubkey | str = "So111...12", fee_sol: float = 0.00001, referral_ata: Pubkey | None = None, return_instructions: bool = False): ...
    async def sell(self, state: dict, pct: float, keypair: Keypair, slippage_pct: float = 5.0, fee_sol: float = 0.00001, quote_mint: str = "So111...12", referral_ata: Pubkey | None = None, return_instructions: bool = False): ...
```

!!! note
    `fetch_state` returns `(pool_addr, state)`; `state["is_migrated"] == 1` signals migration.
    `buy` wraps SOL to WSOL ATA; `sell` closes WSOL to SOL.
    `return_instructions=True` returns instruction list.

### Pricing

`get_price(pool, ctx)` returns a float price computed from sqrt price and decimals.


