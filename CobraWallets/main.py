try: from colors import *
except: from .colors import *;
try: from grind import *
except: from .grind import *;
import asyncio
import sys
import asyncpg, logging

logging.basicConfig(
    level=logging.INFO,
    format=f'{cc.LIGHT_BLUE}[CobraWallets] {cc.WHITE}%(message)s{cc.RESET}',
    handlers=[logging.StreamHandler(sys.stdout)],
)

class CobraWallets:
    def __init__(self, db_pool = None, is_cli = False):
        self.grinder = Grinder()
        self.pool = db_pool
        self.is_cli = is_cli
        self.grind_custom_wallet = self.grinder.grind_custom_wallet

    async def create_wallet(self, uid: str = None) -> tuple[str, str] | None:
        # Returns: (pubkey, privkey)
        if not self.is_cli:
            if not self.pool:
                logging.info("Connecting to database...")
                await self.connect()
            if not uid:
                logging.error("[-] UID is required when not running as CLI")
                raise ValueError("UID is required when not running as CLI")

        pubkey, privkey = self.grinder.grind_wallet()
        if pubkey is None:
            logging.info("[-] Grinder timed out after 60s")
            return None

        priority_level = "medium"
        buy_slip = 10
        sell_slip = 10
        balance = 0.0
        tokens = []
        withdraw_to = ""

        if not self.is_cli:
            await self.save_wallet(uid, pubkey, privkey, str(priority_level), str(buy_slip), str(sell_slip), str(balance), str(tokens), str(withdraw_to))

        return (pubkey, privkey)

    async def save_wallet(self, uid: str, pubkey: str, privkey: str, priority_level: str, buy_slip: float, sell_slip: float, balance: float, tokens: list, withdraw_to: str):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO wallets 
                    (chat_id, pubkey, privkey, priority_level, buy_slip, sell_slip, balance, tokens, withdraw_to) 
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (chat_id) DO UPDATE SET pubkey = $2, privkey = $3, priority_level = $4, buy_slip = $5, sell_slip = $6, balance = $7, tokens = $8, withdraw_to = $9
                    """,
                    uid, pubkey, privkey, priority_level, buy_slip, sell_slip, balance, tokens, withdraw_to
                )
                logging.info(f"[+] Wallet saved: {pubkey}")
        except Exception as e:
            logging.error(f"[-] Error saving wallet: {e}")

    async def connect(self):
        self.pool = await asyncpg.create_pool(
                database  = "cobra_db",
                user      = "cobra_user",
                password  = "admin123",
                host      = "127.0.0.1",
                min_size  = 4,
                max_size  = 500,
            )

    async def close(self):
        await self.pool.close()

if __name__ == "__main__":
    wallets = CobraWallets()
    asyncio.run(wallets.create_wallet())