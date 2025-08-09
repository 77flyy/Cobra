## Raydium DLMM

Price derived from active bin id and bin step; reserves read from vaults.

### Overview

- Core: `DLMMCore` (Raydium variant under `raydiumswap/dlmm`)

### API (pricing)

```python
class DLMMCore:
    async def get_price(self, *, pool_addr: str | Pubkey, strict_mint: str | Pubkey | None = None) -> dict | None: ...
```

!!! note
    `price` is SOL per 1 token; validates SOL-denominated pools.


