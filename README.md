<img src="https://github.com/FLOCK4H/Cobra/blob/main/imgs/cobra_banner.png" />

# Cobra

**Supported Solana Markets:**

1. Raydium CLMM
2. Meteora DLMM
3. PumpFun
4. PumpSwapAMM
5. MeteoraDAMM v1
6. MeteoraDAMM v2
7. Meteora Dynamic Bonding Curve
8. Raydium CPMM
9. Raydium AMM V4
10. Raydium Launchlab

Find their implementations here: [CobraRouter/router](https://github.com/FLOCK4H/Cobra/tree/main/CobraRouter/CobraRouter/router)

<h5>Every market implementation is a self-contained library, meaning you can copy a specific folder to your project and just import what you need.</h5>

Cobra composes of 3 parts:
- CobraRouter
- CobraNET
- CobraWallets

Generally, after setting up Cobra properly the features are:
- Generating Wallets, Grinding Custom Wallets
- Buying, selling on supported markets
- Detecting mint's market and pool address
- Fetching pool's states/ keys (for developers)
- Constructing transactions manually (for developers)

**So, even if you feel like a rookie when it comes to Solana - Don't worry, the setup is quick.**

# Setup

1. Download the repository and install the required modules

```
$ git clone https://github.com/FLOCK4H/Cobra
$ pip install -r req.txt
```

<h3>If you're a developer trying to any of the modules, skip this part</h3>

2. Configure the `.env` file (only if you will be using CLI):

> [!TIP]
> Required are: `HTTP_RPC`, `HELIUS_API_KEY` and `PRIVATE_KEY`.</br> 
> Helius can be free tier.</br>
> **Current fastest HTTP RPC Provider:** [Apewise](https://apewise.org)

```
RUN_AS_CLI=True
BOT_TOKEN=
GROUP_CHAT_ID=
GROUP_CHAT_RETRY_MESSAGE="<a href='https://t.me/flock4hcave'>FLOCK4H.CAVE</a>"
HTTP_RPC="https://api.apewise.org/rpc?api-key=" # apewise.org -> fastest right now

# For getting mint authority we use `getAsset` from Helius off-chain API, Free Tier works just fine:
HELIUS_API_KEY="your-helius-free-or-not-api-key" 

# CLI CONFIG SECTION
PRIVATE_KEY=2wY3abcde5Pj4xxxxxxxxxxxxxxxxxxxxxxxxxxxx
SLIPPAGE=30 # Set if using CLI
PRIORITY_FEE_LEVEL="high" # Set if using CLI | "low", "medium", "high", "turbo"
```

3. Run the CLI

`$ python main.py`

4. (Optional) Install CobraRouter as a module (for your projects):

```
  $ cd CobraRouter
  $ pip install .
```

**Example usage:**

```
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
    detect = await detector._detect("HCN3NazHfBKRDP8EqCmwjZKXtd71HXcXVmXur6VyXm5P")
    print(detect)

if __name__ == "__main__":
    asyncio.run(main())
```

## Contact & Support

**Discord: [FLOCK4H.CAVE](https://discord.gg/thREUECv2a)**, **Telegram: [FLOCK4H.CAVE](https://t.me/flock4hcave)**

**Telegram private handle: @dubskii420**

<img src="https://github.com/user-attachments/assets/d655c153-0056-47fc-8314-6f919f18ed6d" width="256" />

# LICENSE

Copyright 2025 FLOCK4H

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
