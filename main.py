#! /usr/bin/env python3
import logging
import os
import sys
import asyncio
import traceback
from colors import *
import aiohttp
from CobraNET import CobraNET
from CobraWallets import CobraWallets
try: from CobraRouter.CobraRouter import CobraRouter; # type: ignore
except: from CobraRouter import CobraRouter; # type: ignore
from dotenv import load_dotenv
from pathlib import Path
from solders.keypair import Keypair # type: ignore
try: from CobraRouter.CobraRouter.router.libutils._common import ADDR_TO_DEX; # type: ignore
except: from CobraRouter.router.libutils._common import ADDR_TO_DEX; # type: ignore
try: from CobraRouter.CobraRouter.router.libutils.cleaner import Cleaner; # type: ignore
except: from CobraRouter.router.libutils.cleaner import Cleaner; # type: ignore

print(f"""
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}                                             {cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE} ▄████▄   ▒█████   ▄▄▄▄    ██▀███   ▄▄▄      {cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}▒██▀ ▀█  ▒██▒  ██▒▓█████▄ ▓██ ▒ ██▒▒████▄    {cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}▒▓█    ▄ ▒██░  ██▒▒██▒ ▄██▓██ ░▄█ ▒▒██  ▀█▄  {cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}▒▓▓▄ ▄██▒▒██   ██░▒██░█▀  ▒██▀▀█▄  ░██▄▄▄▄██ {cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}▒ ▓███▀ ░░ ████▓▒░░▓█  ▀█▓░██▓ ▒██▒ ▓█   ▓██▒{cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}░ ░▒ ▒  ░░ ▒░▒░▒░ ░▒▓███▀▒░ ▒▓ ░▒▓░ ▒▒   ▓▒█░{cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}  ░  ▒     ░ ▒ ▒░ ▒░▒   ░   ░▒ ░ ▒░  ▒   ▒▒ ░{cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}░        ░ ░ ░ ▒   ░    ░   ░░   ░   ░   ▒   {cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}░ ░          ░ ░   ░         ░           ░  ░{cc.RESET}
{cc.BRIGHT}{cc.LIGHT_BLACK}{cc.BG_WHITE}░                       ░                    {cc.RESET}      
""")

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
        self.cleaner = Cleaner()
        self.router = CobraRouter(HTTP_RPC, session)
        try: self.keypair = Keypair.from_base58_string(os.getenv("PRIVATE_KEY"));
        except: self.keypair = None
        if RUN_AS_CLI == "False":
            self.net = CobraNET(self.router)
        else:
            self.net = None

    async def CLI(self):
        try:
            self.wallets = CobraWallets(is_cli=True)

            logging.info("Welcome to Cobra! Made by FLOCK4H: https://t.me/flock4hcave | https://discord.gg/thREUECv2a")
            if not self.keypair:
                c = cinput(f"[-] Looks like there's no private key set in the `secrets.env` file, would you like to generate one now? (y/n)")
                if c == "y":
                    pubkey, privkey = await self.wallets.create_wallet()
                    self.keypair = Keypair.from_base58_string(privkey)
                    logging.info(f"[+] Wallet created: {pubkey}")
                    logging.info(f"[+] Private key: {privkey}")
                    with open(Path.cwd() / "secrets.env", "a") as f:
                        f.write(f"\nPRIVATE_KEY={privkey}")
                    logging.info(f"[+] Private key generated: {privkey}")
                else:
                    logging.error("[-] No private key found, exiting...")
                    sys.exit(1)

            while True:
                print("")
                cprint(f"1) Create a new wallet")
                cprint(f"2) Grind a new vanity wallet")
                cprint(f"3) Detect mint market")
                cprint(f"4) Buy a mint")
                cprint(f"5) Sell a mint")
                cprint(f"6) List your mints")
                cprint(f"7) Burn a mint")
                cprint(f"8) Exit")

                cmd = cinput("Enter your choice")
                if not cmd:
                    return
                cmd = cmd.replace(")", "").lstrip()

                if cmd == "1":
                    pubkey, privkey = await self.wallets.create_wallet()
                    logging.info(f"[+] Wallet created: {pubkey}")
                    logging.info(f"[+] Private key: {privkey}")
                    with open(Path.cwd() / "secrets.env", "a") as f:
                        f.write(f"\nPRIVATE_KEY={privkey}")
                    logging.info(f"[+] Private key saved to `secrets.env`")
                elif cmd == "2":
                    cprint(f"Warning! The more characters you grind, the longer it will take.")
                    includes = cinput("Enter the characters to grind (e.g. CB)")
                    pubkey, privkey = self.wallets.grind_custom_wallet(includes)
                    logging.info(f"[+] Wallet created: {pubkey}")
                    logging.info(f"[+] Private key: {privkey}")
                    with open(Path.cwd() / "secrets.env", "a") as f:
                        f.write(f"\nPRIVATE_KEY={privkey}")
                    logging.info(f"[+] Private key saved to `secrets.env`")
                elif cmd == "3":
                    mint = cinput("Enter the mint address")
                    info = await self.detect_mint_market(mint)
                    logging.info(f"[+] Mint market results: {info}")
                elif cmd == "4":
                    mint = cinput("Enter the mint address").lstrip()
                    amount = cinput("Enter the SOL amount to spend (e.g. 0.01)").lstrip()
                    await self.swap_mint("buy", mint, float(amount))
                elif cmd == "5":
                    mint = cinput("Enter the mint address").lstrip()
                    sell_pct = cinput("Enter the percentage to sell (e.g. 50)").lstrip()
                    await self.swap_mint("sell", mint, int(sell_pct))
                elif cmd == "6":
                    await self.list_mints()
                elif cmd == "7":
                    await self.burn_mint()
                elif cmd == "8":
                    await self.close()
                    sys.exit(0)
        except Exception as e:
            logging.error(f"[-] Error: {e}")
            traceback.print_exc()

    async def list_mints(self):
        try:
            logging.info(f"[+] Getting mint info...")
            mints = await self.router.list_mints(self.keypair.pubkey())
            if mints:
                mints_dict = {}
                to_sell = set()
                for mint in mints:
                    price = await self.router.get_price(str(mint), use_cache=True)
                    if not price:
                        to_sell.add(str(mint))
                        continue
                    mints_dict[str(mint)] = {"price": price}

                balances = await self.router.swaps.get_multiple_balances(list(mints_dict.keys()), self.keypair.pubkey())
                for mint, balances in balances.items():
                    if str(mint) in mints_dict:
                        mints_dict[str(mint)]["balance"] = balances[0]

                for mint, info in mints_dict.items():
                    logging.info(f"[+] Mint: {mint} | Price: {info['price']} | Balance: {info['balance']}")
            else:
                logging.error("[-] No mints found")
        except Exception as e:
            logging.error(f"[-] Error: {e}")
            traceback.print_exc()

    async def burn_mint(self):
        try:
            mint = cinput("Enter the mint address (or type `all` to burn all mints)")
            if mint == "all":
                mints = await self.router.list_mints(self.keypair.pubkey())
                if not mints: return;
                balances = await self.router.swaps.get_multiple_balances(list(mints), self.keypair.pubkey())
                for mint, info in balances.items():
                    logging.info(f"[+] Mint: {mint} | Balance: {info[0]}")
                c = cinput(f"Would you like to burn these mints and recover SOL? (y/n)")
                if c == "y":
                    for mint, info in balances.items():
                        balance_raw = info[1]
                        decimals = await self.router.get_decimals(str(mint))
                        sig, ok = await self.cleaner.close_token_account(self.router.async_client, self.keypair, mint, balance_raw, decimals)
                        if ok:
                            logging.info(f"[+] Burn transaction sent: https://solscan.io/tx/{sig}")
                        else:
                            logging.error("[-] Failed to send burn transaction")
                return

            logging.info(f"[!] Only burn mints that are not supported by Cobra.")
            logging.info(f"[+] Listing token balance...")
            balance, balance_raw, ok = await self.router.swaps.get_balance(str(mint), self.keypair.pubkey())
            decimals = await self.router.get_decimals(str(mint))
            logging.info(f"[+] Mint: {mint} | Balance: {balance} | Decimals: {decimals}")
            c = cinput(f"Would you like to burn this unsupported mint and recover SOL? (y/n)")
            if c == "y":
                sig, ok = await self.cleaner.close_token_account(self.router.async_client, self.keypair, mint, balance_raw, decimals)
                if ok:
                    logging.info(f"[+] Burn transaction sent: https://solscan.io/tx/{sig}")
                else:
                    logging.error("[-] Failed to send burn transaction")
        except Exception as e:
            logging.error(f"[-] Error: {e}")
            traceback.print_exc()

    async def detect_mint_market(self, mint: str):
        info = await self.router.detect(mint, use_cache=True)
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
        try:
            logging.info("Initializing Cobra, pass RUN_AS_CLI=True to the secrets.env to run as CLI...")
            await asyncio.gather(
                self.net.run() if self.net is not None else self.loop(),
                self.CLI() if RUN_AS_CLI == "True" else self.loop(),
            )
        except EOFError:
            logging.info("[-] EOFError detected, closing Cobra...")
            await self.close()
            sys.exit(0)
        finally:
            await self.close()

    async def close(self):
        await self.router.close()

async def main():
    session = aiohttp.ClientSession()
    cobra = Cobra(session)
    await cobra.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        logging.info("Keyboard interrupt detected, closing Cobra...")
        sys.exit(0)