## Pump.fun

Bonding-curve token sales with migration to AMMs. Adapter provides price, buy/sell instruction builders.

### Overview

- Class: `PumpFun`
- Helpers: `check_has_migrated`, `get_associated_bonding_curve_address`

### Quickstart

```python
from CobraRouter.CobraRouter.router.pump_fun.pump_fun import PumpFun
from solders.keypair import Keypair

pf = PumpFun(session, async_client)
price = await pf.get_price(mint)
creator = await cobra_router.router.get_pump_fun_creator(async_client, pool)

# Buy 0.002 SOL of token (precompute lamports_to_tokens)
token_amount = await pf.lamports_to_tokens(int(0.002 * 1e9), price)
ixs = await pf.pump_buy(mint, pool, int(0.002 * 1e9), creator, keypair, token_amount, return_instructions=True)
```

### API

```python
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from decimal import Decimal

class PumpFun:
    async def fetch_pool_state(self, pool: str) -> tuple[dict | str, str | None]: ...
    async def get_price(self, mint: str | Pubkey): ...  # may return "NotOnPumpFun" or "migrated"
    async def lamports_to_tokens(self, lamports: int, price: Decimal) -> int: ...
    async def pump_buy(self, mint_address: str, bonding_curve_pda: str, sol_amount: int, creator: str, keypair: Keypair, token_amount: int, sim: bool = False, priority_micro_lamports: int = 0, slippage: float = 1.3, skip_ata_check: bool = False, return_instructions: bool = False): ...
    async def pump_sell(self, mint_address: str, bonding_curve_pda: str, token_amount: int, lamports_min_output: int, creator: str, keypair: Keypair, sim: bool = False, priority_micro_lamports: int = 0, return_instructions: bool = False): ...
```

!!! note
    `get_price` returns SOL per token or migration hints.
    `slippage` for `pump_buy` is applied by increasing `max_sol_cost`.
    `return_instructions=True` returns ixs for bundling; router wraps with fee ixs and sending.


