## PumpSwap AMM

On-chain AMM used by pump.fun migration. Supports buy/sell, reversed pools (WSOL-token), plus LP ops: create_pool, deposit, withdraw.

### Overview

- Class: `PumpSwap`
- Helpers: `fetch_pool_state`, `fetch_pool_base_price`, `convert_sol_to_base_tokens` etc.

### Quickstart

```python
from CobraRouter.CobraRouter.router.PumpSwapAMM.PumpSwapAMM import PumpSwap
from solders.keypair import Keypair

ps = PumpSwap(async_client)
base_price, base_bal, quote_sol = await ps.fetch_pool_base_price(pool)

# Buy 0.003 SOL of base token
confirmed, sig, pool_type, amount_out = await ps.buy(pool_data, 0.003, keypair, pool_type)

# Sell 50%
confirmed, sig, pool_type, min_sol = await ps.sell(pool_data, 50, keypair, pool_type)
```

### API

```python
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from typing import Optional

class PumpSwap:
    async def fetch_pool_base_price(self, pool: str | Pubkey) -> tuple[float, float, float]: ...
    async def buy(self, pool_data: dict, sol_amount: float, keypair: Keypair, pool_type: str = "NEW", slippage_pct: float = 10, fee_sol: float = 0.00001, debug_prints: bool = False, return_instructions: bool = False): ...
    async def sell(self, pool_data: dict, sell_pct: float, keypair: Keypair, pool_type: str = "NEW", slippage_pct: float = 10, fee_sol: float = 0.00001, debug_prints: bool = False, return_instructions: bool = False): ...
    async def reversed_buy(self, pool_data: dict, sol_amount: float, keypair: Keypair, pool_type: str = "NEW", slippage_pct: float = 10, fee_sol: float = 0.00001, debug_prints: bool = False, return_instructions: bool = False): ...
    async def reversed_sell(self, pool_data: dict, sell_pct: float, keypair: Keypair, pool_type: str = "NEW", slippage_pct: float = 10, fee_sol: float = 0.00001, debug_prints: bool = False, return_instructions: bool = False): ...
    async def create_pool(self, base_mint: Pubkey, base_amount_tokens: float, quote_amount_sol: float, keypair: Keypair, decimals_base: int = 6, index: int = 0, fee_sol: float = 0.0005, debug_prints: bool = False) -> str | None: ...
    async def deposit(self, pool_data: dict, base_amount_tokens: float, keypair: Keypair, slippage_pct: float = 1.0, fee_sol: float = 0.0003, sol_cap: float | None = None, debug_prints: bool = False) -> bool: ...
    async def withdraw(self, pool_data: dict, withdraw_pct: float, fee_sol: float = 0.0003, debug_prints: bool = False, keypair: Keypair | None = None) -> bool: ...
```

!!! note
    `pool_data` requires: `pool_pubkey`, `token_base`, `token_quote`, pool vault ATAs, balances, decimals, and for NEW pools `coin_creator`.
    Reversed pools (WSOL-token) use `reversed_buy`/`reversed_sell` to swap WSOL<->TOKEN.
    All flows wrap/unwrap WSOL as needed; unsafe priority-fee caps are enforced at the router layer.


