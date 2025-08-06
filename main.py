import logging
import os
import sys
import asyncio
import traceback
from colors import *
import aiohttp
from CobraNET import CobraNET
from CobraWallets import CobraWallets
from CobraRouter.CobraRouter import CobraRouter
from dotenv import load_dotenv
from pathlib import Path
from solders.keypair import Keypair # type: ignore
from CobraRouter.CobraRouter.router.libutils._common import ADDR_TO_DEX

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format=f'{cc.LIGHT_BLUE}[{cc.LIGHT_GREEN}Cobra{cc.LIGHT_BLUE}] {cc.LIGHT_WHITE}%(message)s{cc.RESET}',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)

HTTP_RPC = os.getenv("HTTP_RPC")

load_dotenv(dotenv_path=Path.cwd() / "secrets.env", override=False)

RUN_AS_CLI = os.getenv("RUN_AS_CLI")

class CLISettings:
    SLIPPAGE = int(os.getenv("SLIPPAGE"))
    PRIORITY_LEVEL = str(os.getenv("PRIORITY_FEE_LEVEL"))

class Cobra:
    def __init__(self, session: aiohttp.ClientSession):
        self.router = CobraRouter(HTTP_RPC, session)
        self.keypair = Keypair.from_base58_string(os.getenv("PRIVATE_KEY"))
        # self.net = CobraNET(self.router) # Uncomment this to initialize the Telegram bot

    async def CLI(self):
        try:
            logging.info("Welcome to Cobra! Made by FLOCK4H: https://t.me/flock4hcave | https://discord.gg/thREUECv2a")

            self.wallets = CobraWallets(is_cli=True)
            while True:
                cprint(f"1) Create a new wallet")
                cprint(f"2) Detect mint market")
                cprint(f"3) Buy a mint")
                cprint(f"4) Sell a mint")

                cmd = cinput("Enter your choice")
                cmd = cmd.replace(")", "").lstrip()

                if cmd == "1":
                    pubkey, privkey = await self.wallets.create_wallet()
                    logging.info(f"[+] Wallet created: {pubkey}")
                    logging.info(f"[+] Private key: {privkey}")
                elif cmd == "2":
                    mint = cinput("Enter the mint address")
                    info = await self.detect_mint_market(mint)
                    logging.info(f"[+] Mint market results: {info}")
                elif cmd == "3":
                    mint = cinput("Enter the mint address").lstrip()
                    amount = cinput("Enter the SOL amount to spend (e.g. 0.01)").lstrip()
                    await self.swap_mint("buy", mint, float(amount))
                elif cmd == "4":
                    mint = cinput("Enter the mint address").lstrip()
                    sell_pct = cinput("Enter the percentage to sell (e.g. 50)").lstrip()
                    await self.swap_mint("sell", mint, int(sell_pct))
        except Exception as e:
            logging.error(f"[-] Error: {e}")
            traceback.print_exc()

    async def detect_mint_market(self, mint: str):
        info = await self.router.detect(mint)
        if info:
            dex, pool = info
            if dex and pool:
                return f"\n[+] DEX: {ADDR_TO_DEX[dex]}\n[+] POOL: {pool}\n"
            else:
                return "\n[-] No pool found. Please try again.\n"
        else:
            return "\n[-] No pool found. Please try again.\n"
    
    async def swap_mint(self, action: str, mint: str, amount: float | str):
        """
        action: "buy" or "sell"
        """
        dex, pool = await self.router.detect(mint)
        if not dex or not pool:
            logging.error("[-] No pool found. Please try again.")
            return

        info = await self.router.swap(
                action=action,
                mint=mint,
                pool=pool,
                slippage=CLISettings.SLIPPAGE,
                priority_level=CLISettings.PRIORITY_LEVEL,
                dex=dex,
                keypair=self.keypair, 
                sol_amount_in=amount,
                sell_pct=amount
            )
        return info

    async def test(self):
        info = await self.router.detect("2M8Jy2e35n1VeWYNmS6A9eHZb2u4axuYhJBiBqispump")
        print(info)

    async def loop(self):
        while True:
            await asyncio.sleep(1)

    async def run(self):
        logging.info("Initializing Cobra, remember to pass RUN_AS_CLI=True to run as CLI...")
        await asyncio.gather(
            # self.net.run(),
            self.CLI() if RUN_AS_CLI else self.loop(),
        )
        await self.close()

    async def close(self):
        await self.router.close()

async def main():
    try:
        session = aiohttp.ClientSession()
        cobra = Cobra(session)

        await cobra.run()
    except (KeyboardInterrupt, EOFError):
        cprint(f"Keyboard interrupt detected, closing Cobra...")
        try:
            await cobra.close()
        except:
            traceback.print_exc() 
            pass
        sys.exit(0)
    except Exception as e:
        logging.error(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())