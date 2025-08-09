## CobraWallets

Lightweight wallet management utilities with optional PostgreSQL persistence and a fast vanity wallet grinder.

### Overview

- Module: `CobraWallets`
- Purpose: Generate wallets, optionally persist settings and balances, and grind custom vanity addresses
- Storage: Optional PostgreSQL pool via `asyncpg`

### Quickstart

```python
import asyncio
from CobraWallets.main import CobraWallets

async def main():
    wallets = CobraWallets(is_cli=True)  # no DB
    pub, priv = await wallets.create_wallet()
    print("address:", pub)

asyncio.run(main())
```

With database persistence

```python
import asyncio
from CobraWallets.main import CobraWallets

async def main():
    cw = CobraWallets(is_cli=False)
    await cw.connect()  # creates asyncpg pool to PostgreSQL
    pub, priv = await cw.create_wallet(uid="12345")
    print("address:", pub)

asyncio.run(main())
```

### API

```python
from typing import Optional

class CobraWallets:
    def __init__(self, db_pool=None, is_cli: bool = False) -> None: ...

    # High-level
    async def create_wallet(self, uid: str | None = None) -> tuple[str, str] | None: ...
    async def save_wallet(self, uid: str, pubkey: str, privkey: str, priority_level: str, buy_slip: float, sell_slip: float, balance: float, tokens: list, withdraw_to: str): ...
    async def connect(self) -> None: ...  # asyncpg.create_pool(...)
    async def close(self) -> None: ...

    # Grinder shortcut
    # Exposes self.grinder and .grind_custom_wallet/.grind_wallet
```

Notes
- `create_wallet()` returns `(pubkey, privkey)` Base58. In non-CLI mode a `uid` is required and data is persisted.
- Defaults inserted on first save: `priority_level=medium`, `buy_slip=10`, `sell_slip=10`, `balance=0`, `tokens=[]`, `withdraw_to=""`.
- Database schema is created by project `database.py`; ensure PostgreSQL is running locally.

### Vanity grinder

```python
from CobraWallets.grind import Grinder

g = Grinder()
addr, secret = g.grind_custom_wallet("CB")  # startswith or endswith fragment
addr2, secret2 = g.grind_wallet()            # one-shot, no filter
```

API

```python
class Grinder:
    def grind_custom_wallet(self, includes: str = "CB") -> tuple[str, str] | tuple[None, None]: ...
    def grind_wallet(self) -> tuple[str, str] | tuple[None, None]: ...
```

Notes
- Fragment must be Base58 (`1-9A-HJ-NP-Za-km-z`); invalid chars raise `ValueError`.
- Spawns `cpu_count()-1` processes and times out after ~60s; returns first hit or `(None, None)`.
- Matches start or end of the Base58 address.

### Persistence model

`save_wallet()` upserts one row per `chat_id` (uid) with fields: `pubkey`, `privkey`, `priority_level`, `buy_slip`, `sell_slip`, `balance`, `tokens`, `withdraw_to`.

Example upsert call

```python
await wallets.save_wallet(
    uid="12345",
    pubkey=pub,
    privkey=priv,
    priority_level="high",
    buy_slip=10,
    sell_slip=10,
    balance=0.0,
    tokens=[],
    withdraw_to="",
)
```

### Security

- Store `privkey` securely; restrict DB access and backups. Consider client-side encryption if persisting secrets.
- Production deployments should set strict DB roles and use TLS to Postgres.


