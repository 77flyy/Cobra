import json

import asyncio, asyncpg
import logging

try:
    from colors import *
except ImportError:
    from .colors import *

class TGDBHook:
    def __init__(self):
        self.pool = None
        self.conn_lock = asyncio.Lock()

    async def connect(self):
        try:
            self.pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    database="cobra_db",
                    user="cobra_user",
                    password="admin123",
                    host="127.0.0.1",
                    min_size=4,
                    max_size=500,
                ),
                timeout=5
            )
            logging.info("Database connected successfully.")
            return True
        except asyncio.TimeoutError:
            logging.info(f"{cc.RED}Database connection timed out.{cc.RESET}")
        except Exception as e:
            logging.info(f"{cc.RED}Database connection error: {e}{cc.RESET}")
            return False

    async def cache_user(self, chat_id: int, username: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO telegram (chat_id, username)
                        VALUES ($1, $2)
                        ON CONFLICT (chat_id) DO UPDATE SET username = $2
                    """, chat_id, username)
                logging.info(f"User {username} ({chat_id}) cached successfully.")
        except Exception as e:
            logging.error(f"Error caching user: {e}")

    async def get_user(self, chat_id: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    return await conn.fetchrow("SELECT * FROM telegram WHERE chat_id = $1", str(chat_id))
        except Exception as e:
            logging.error(f"Error getting user: {e}")

    async def get_wallet(self, chat_id: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    wallet = await conn.fetchrow("SELECT * FROM wallets WHERE chat_id = $1", str(chat_id))
                    if wallet:
                        wallet = dict(wallet) if not isinstance(wallet, dict) else wallet
                        wallet["balance"] = float(wallet["balance"])
                        wallet["priority_level"] = wallet["priority_level"]
                        wallet["buy_slip"] = float(wallet["buy_slip"])
                        wallet["sell_slip"] = float(wallet["sell_slip"])
                        wallet["tokens"] = json.loads(wallet["tokens"])
                        wallet.pop("timestamp")
                        return wallet
                    else:
                        return None
        except Exception as e:
            logging.error(f"Error getting wallet: {e}")

    async def update_wallet(self, chat_id: str, **kwargs):
        """
        chat_id: str
        **kwargs:
            balance: float
            tokens: list[{"name":str,"balance":float}]
            buy_fee: float
            sell_fee: float
            buy_slip: float
            sell_slip: float
        """
        try:
            async with self.conn_lock:  
                async with self.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE wallets
                        SET balance = $1, tokens = $2, priority_level = $3, buy_slip = $4, sell_slip = $5
                        WHERE chat_id = $6
                    """, kwargs["balance"], kwargs["tokens"], kwargs["priority_level"], kwargs["buy_slip"], kwargs["sell_slip"], str(chat_id))
                logging.info(f"Wallet {chat_id} updated successfully.")
        except Exception as e:
            logging.error(f"Error updating wallet: {e}")

    async def update_priority_level(self, chat_id: str, priority_level: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE wallets SET priority_level = $1 WHERE chat_id = $2", str(priority_level), str(chat_id))
                logging.info(f"Wallet {chat_id} priority level updated successfully.")
        except Exception as e:
            logging.error(f"Error updating wallet priority level: {e}")

    async def update_withdrawal_address(self, chat_id: str, withdrawal_address: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE wallets SET withdraw_to = $1 WHERE chat_id = $2", str(withdrawal_address), str(chat_id))
                logging.info(f"Wallet {chat_id} withdrawal address updated successfully.")
        except Exception as e:
            logging.error(f"Error updating wallet withdrawal address: {e}")

    async def update_buy_slip(self, chat_id: str, buy_slip: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE wallets SET buy_slip = $1 WHERE chat_id = $2", str(buy_slip), str(chat_id))
                logging.info(f"Wallet {chat_id} buy slip updated successfully.")
        except Exception as e:
            logging.error(f"Error updating wallet buy slip: {e}")

    async def update_sell_slip(self, chat_id: str, sell_slip: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE wallets SET sell_slip = $1 WHERE chat_id = $2", str(sell_slip), str(chat_id))
                logging.info(f"Wallet {chat_id} sell slip updated successfully.")
        except Exception as e:
            logging.error(f"Error updating wallet sell slip: {e}")

    async def update_balance(self, chat_id: str, balance: float):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE wallets SET balance = $1 WHERE chat_id = $2", balance, str(chat_id))
                logging.info(f"Wallet {chat_id} balance updated successfully.")
        except Exception as e:
            logging.error(f"Error updating wallet balance: {e}")

    async def update_tokens(self, chat_id: str, new_tokens: list):
        """
        new_tokens: list[{"name": str, "balance": float}]
        This replaces or merges tokens in wallet.
        """
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    wallet = await conn.fetchrow("SELECT * FROM wallets WHERE chat_id = $1", str(chat_id))
                    if not wallet:
                        raise Exception(f"Wallet {chat_id} not found")

                    tokens = json.loads(wallet["tokens"])
                    token_map = {t["name"]: t for t in tokens}

                    for t in new_tokens:
                        if t["name"] in token_map:
                            token_map[t["name"]]["balance"] = t["balance"]
                        else:
                            token_map[t["name"]] = t

                    updated = list(token_map.values())

                    await conn.execute(
                        "UPDATE wallets SET tokens = $1 WHERE chat_id = $2",
                        json.dumps(updated), str(chat_id)
                    )

                    logging.info(f"Wallet {chat_id} tokens updated successfully.")
        except Exception as e:
            logging.error(f"Error updating wallet tokens: {e}")

    async def remove_token(self, chat_id: str, mint: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    wallet = await conn.fetchrow("SELECT * FROM wallets WHERE chat_id = $1", str(chat_id))
                    if wallet:
                        tokens = json.loads(wallet["tokens"])
                        tokens = [t for t in tokens if t["name"] != mint]
                    else:
                        raise Exception(f"Wallet {chat_id} not found")
                    await conn.execute("UPDATE wallets SET tokens = $1 WHERE chat_id = $2", json.dumps(tokens), str(chat_id))
                logging.info(f"Token {mint} removed successfully.")
        except Exception as e:
            logging.error(f"Error removing token: {e}")

    async def remove_user(self, chat_id: str):
        try:
            async with self.conn_lock:
                async with self.pool.acquire() as conn:
                    await conn.execute("DELETE FROM telegram WHERE chat_id = $1", str(chat_id))
                logging.info(f"User {chat_id} removed successfully.")
        except Exception as e:
            logging.error(f"Error removing user: {e}")

    async def close(self):
        try:
            if self.pool:
                await self.pool.close()
        except Exception as e:
            logging.error(f"Error closing database connection pool: {e}")