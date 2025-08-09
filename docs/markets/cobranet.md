## CobraNET

Telegram bot wrapper around CobraRouter and CobraWallets. Provides a simple trading UI, wallet creation, and withdrawals over Telegram.

### Overview

- Class: `CobraNET` in `CobraNET/main.py`
- Integrations:
  - `CobraRouter` for detection, pricing, and swaps
  - `CobraWallets` for wallet creation and persistence
  - `TGDBHook` for PostgreSQL-backed user/wallet storage
  - `python-telegram-bot` for the UI

### Features

- Access control with basic rate-limiting and blacklist
- Create wallet and persist to DB (pubkey/privkey/settings)
- Show wallet balance and token basket with links
- Buy and sell flows with route detection and slippage/priority controls
- Withdraw SOL or tokens to a configured address
- Burn token accounts (close ATAs) and reclaim rent

### Setup

1) Environment

```env
RUN_AS_CLI=False
BOT_TOKEN=TELEGRAM_BOT_TOKEN_FROM_BOTFATHER
HTTP_RPC="https://api.apewise.org/rpc?api-key="
HELIUS_API_KEY="your-helius-api-key"
```

2) Database

Install PostgreSQL and initialize the schema using `database.py`:

```bash
python database.py
```

3) Run

```bash
python main.py
```

Open Telegram, start your bot, and send `/start`.

### High-level API

```python
class CobraNET:
    def __init__(self, router: CobraRouter, bot_token: str, command_queue: asyncio.Queue = asyncio.Queue()): ...
    async def run(self): ...                       # connects DB, registers handlers, starts bot
    async def start(self): ...                     # low-level: start polling
    async def stop(self): ...                      # stop polling

    # Command handling
    async def handle_start(self, u: Update, c: ContextTypes.DEFAULT_TYPE): ...
    async def handle_command(self, u: Update, c: ContextTypes.DEFAULT_TYPE): ...
    async def dispatcher(self, u: Update, c: ContextTypes.DEFAULT_TYPE): ...

    # Menu builders and UI
    async def show_menu(self, uid: int): ...
    async def build_menu_text(self, uid: int) -> str: ...
    def   build_menu_kb(self) -> InlineKeyboardMarkup: ...
```

### User flows

- Start/menu: `/start` shows wallet info (creates a wallet on first use), token list, and settings.
- Buy: prompts for `mint amount` then calls `router.detect()` and `router.swap(action="buy", ...)`.
- Sell: prompts for `mint pct` (0–100), runs detection, calls `router.swap(action="sell", ...)`.
- Withdraw SOL: sends system transfer; checks rent-exempt buffer.
- Withdraw tokens: builds SPL transfer with ATA creation if needed.
- Burn tokens: closes ATA; optionally burns an amount first.

### Settings

- Priority fee level: low | medium | high | turbo
- Buy/Sell slippage: percent
- Withdrawal address: SOL address

### Internals and safeguards

- Rate limiter (WINDOW=10s, LIMIT=5) per user
- Pool replay handling for DLMM: on "replay" result, pool gets added to `exclude_pools` and the action is retried
- Priority fee capped by CobraRouter at 0.01 SOL; error surfaced to user
- Balance and token holdings refreshed in menu updates

### Example: plugging into your app

```python
import asyncio, aiohttp
from CobraRouter.CobraRouter.main import CobraRouter
from CobraNET.main import CobraNET

async def main():
    async with aiohttp.ClientSession() as session:
        router = CobraRouter(os.environ["HTTP_RPC"], session)
        app = CobraNET(router)
        await app.run()

asyncio.run(main())
```

### Troubleshooting

- “No pool found”: token might not be paired with WSOL, or routing checks returned none; try again later.
- “Priority fee is too high”: reduce priority level; network congestion elevated.
- Insufficient balance: ensure rent-exempt lamports are available for temporary WSOL and ATA creation.


