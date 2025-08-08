## Quick start

This page shows two ways to get going fast: programmatic usage and the CLI.

### Programmatic: detect a market and initialize the router

```python
from CobraRouter.detect import CobraDetector
from CobraRouter.router import Router
import asyncio
from solana.rpc.async_api import AsyncClient
import aiohttp

async def main():
    client = AsyncClient("https://api.apewise.org/rpc?api-key=")
    session = aiohttp.ClientSession()
    router = Router(client, session)
    detector = CobraDetector(router, "https://api.apewise.org/rpc?api-key=")
    detect = await detector._detect("9R1pCPM7GRr9F4gk978LqBQiPKfYStbZKc5iKV4imoon")
    print(detect)
    await client.close()
    await session.close()
    await router.close()

if __name__ == "__main__":
    asyncio.run(main())
```

Example output:

```bash
BMBcZ9GWMCi9HaCE7BagrLxakzffy6fAGdEpihLRfVPw
[CobraRouter] Route winner (?): 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 -> BMBcZ9GWMCi9HaCE7BagrLxakzffy6fAGdEpihLRfVPw
("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "BMBcZ9GWMCi9HaCE7BagrLxakzffy6fAGdEpihLRfVPw")
```

### CLI: trade from your terminal

1) Create `secrets.env` with the required variables:

```bash
RUN_AS_CLI=True
BOT_TOKEN=
HTTP_RPC="https://api.apewise.org/rpc?api-key="
HELIUS_API_KEY="your-helius-free-or-not-api-key"

# CLI CONFIG SECTION
PRIVATE_KEY=2wY3abcde5Pj4xxxxxxxxxxxxxxxxxxxxxxxxxxxx
SLIPPAGE=30
PRIORITY_FEE_LEVEL="high"  # low | medium | high | turbo
```

2) Run the CLI from the repository root:

```bash
python main.py
```

That’s it — you’re ready to explore pools, route swaps, and build on top of Cobra.
