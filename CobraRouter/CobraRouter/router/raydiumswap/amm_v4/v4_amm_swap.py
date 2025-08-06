# swap.py
import logging
import base64
import os
import json
import asyncio
from typing import Optional
import traceback
from solana.rpc.commitment import Processed, Confirmed
from solana.rpc.types import TokenAccountOpts, TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price  # type: ignore   
from solders.message import MessageV0  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.system_program import CreateAccountWithSeedParams, create_account_with_seed  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore
from solders.keypair import Keypair  # type: ignore
from spl.token.instructions import (
    CloseAccountParams,
    InitializeAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address,
    initialize_account,
)
try: from v4_amm_core import (
    RaydiumPoolKeys,
    RaydiumCore,
)
except: from .v4_amm_core import (
    RaydiumPoolKeys,
    RaydiumCore,
)
try: from v4_amm_api import fetch_pool_info
except: from .v4_amm_api import fetch_pool_info

from solana.rpc.async_api import AsyncClient

logging.basicConfig(level=logging.INFO)

suppress_logs = [
    "socks",
    "requests",
    "httpx",
    "trio.async_generator_errors",
    "trio",
    "trio.abc.Instrument",
    "trio.abc",
    "trio.serve_listeners",
    "httpcore.http11",
    "httpcore",
    "httpcore.connection",
    "httpcore.proxy",
]

for log_name in suppress_logs:
    logging.getLogger(log_name).setLevel(logging.CRITICAL)
    logging.getLogger(log_name).handlers.clear()
    logging.getLogger(log_name).propagate = False

RENT_EXEMPT_AMOUNT = 2039280
COMPUTE_UNITS = 150_000
TOKEN_PROGRAM_KEY = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ACCOUNT_SIZE = 165
WSOL_ADDRESS = Pubkey.from_string("So11111111111111111111111111111111111111112")
SOL_DECIMALS = 1e9

class RaydiumSwap:
    def __init__(self, async_client: AsyncClient):
        self.async_client = async_client
        self.raydium_core = RaydiumCore(self.async_client)
        self.COMPUTE_UNITS = COMPUTE_UNITS

    def convert_sol_to_tokens(self, sol_amt: float, base_vault: float, quote_vault: float, fee_pct: float = 0.25) -> float:
        raw = base_vault * quote_vault
        return round(base_vault - raw / (quote_vault + sol_amt - (sol_amt * (fee_pct / 100))), 9)

    def convert_tokens_to_sol(self, token_amt: float, base_vault: float, quote_vault: float, fee_pct: float = 0.25) -> float:
        raw = base_vault * quote_vault
        return round(quote_vault - raw / (base_vault + token_amt - (token_amt * (fee_pct / 100))), 9)

    async def fetch_token_balance_async(self, keypair: Keypair, mint_pubkey_str: str) -> Optional[float]:
        token_mint = Pubkey.from_string(mint_pubkey_str)
        response = await self.async_client.get_token_accounts_by_owner_json_parsed(
            keypair.pubkey(),
            TokenAccountOpts(mint=token_mint),
            commitment=Processed
        )
        if response.value:
            accounts = response.value
            if accounts:
                balance = accounts[0].account.data.parsed['info']['tokenAmount']['uiAmount']
                if balance is not None:
                    return float(balance)
        return None

    async def await_confirm_transaction(self, tx_signature: str, max_attempts: int = 20, retry_delay: int = 3) -> Optional[bool]:
        attempt = 1
        while attempt < max_attempts:
            try:
                txn_resp = await self.async_client.get_transaction(
                    tx_signature,
                    encoding="json",
                    commitment=Confirmed,
                    max_supported_transaction_version=0
                )
                txn_meta = txn_resp.value.transaction.meta
                if txn_meta.err is None:
                    return True
                if txn_meta.err:
                    return False
            except Exception:
                attempt += 1
                await asyncio.sleep(retry_delay)
        logging.info("Max attempts reached. Transaction confirmation failed.")
        return None

    async def find_pool_by_mint(self, mint: str | Pubkey) -> Optional[RaydiumPoolKeys]:
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pool_info = fetch_pool_info(mint)
            pool_data = pool_info.get("data", {}).get("data", [])
            if not pool_data:
                return None
            
            program_id = pool_data[0]["programId"]
            if program_id != "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8":
                return None
            pool_key = pool_data[0]["id"]
            return pool_key
        except Exception as e:
            logging.error(f"Error finding pool by mint: {e}")
            traceback.print_exc()
            return None

    async def execute_buy_async(self, mint_address: str = "", sol_amount: float = 0.0001, slippage_percentage: int = 5, fee: int = 1000000, pool = None, keypair: Keypair = None, return_instructions: bool = False) -> bool:
        try:
            try:
                if not pool:
                    pool_info = fetch_pool_info(mint_address) # TODO: fix this shi, change to what we use in cpmm
                    pool_key = pool_info["data"]["data"][0]["id"]
                else:
                    pool_key = pool
            except IndexError:
                logging.info(f"Pool key could not be found for {mint_address}. Trying again...")
                await asyncio.sleep(3)
                return await self.execute_buy_async(mint_address, sol_amount, slippage_percentage, fee)

            sol_lamports = int(sol_amount * SOL_DECIMALS)
            keys = await self.raydium_core.async_fetch_pool_keys(pool_key)
            if keys is None:
                return False

            token_mint = keys.token_base if keys.token_base != WSOL_ADDRESS else keys.token_quote
            sol_amount = sol_lamports / SOL_DECIMALS

            base_reserve, quote_reserve, token_decimals = await self.raydium_core.async_get_pool_reserves(keys)
            tokens_expected = self.convert_sol_to_tokens(sol_amount, base_reserve, quote_reserve)

            slippage_factor = 1 - (slippage_percentage / 100)
            adjusted_tokens = tokens_expected * slippage_factor
            min_tokens_out = int(adjusted_tokens * 10**token_decimals)

            token_acct_response = await self.async_client.get_token_accounts_by_owner(
                keypair.pubkey(), TokenAccountOpts(token_mint), Processed
            )
            if token_acct_response.value:
                user_token_account = token_acct_response.value[0].pubkey
                create_token_account_ix = None
            else:
                user_token_account = get_associated_token_address(keypair.pubkey(), token_mint)
                create_token_account_ix = create_associated_token_account(
                    keypair.pubkey(), keypair.pubkey(), token_mint
                )

            seed_value = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
            temp_wsol_account = Pubkey.create_with_seed(
                keypair.pubkey(), seed_value, TOKEN_PROGRAM_KEY
            )

            create_wsol_ix = create_account_with_seed(
                CreateAccountWithSeedParams(
                    from_pubkey=keypair.pubkey(),
                    to_pubkey=temp_wsol_account,
                    base=keypair.pubkey(),
                    seed=seed_value,
                    lamports=int(RENT_EXEMPT_AMOUNT + sol_lamports),
                    space=ACCOUNT_SIZE,
                    owner=TOKEN_PROGRAM_KEY,
                )
            )

            init_wsol_ix = initialize_account(
                InitializeAccountParams(
                    program_id=TOKEN_PROGRAM_KEY,
                    account=temp_wsol_account,
                    mint=WSOL_ADDRESS,
                    owner=keypair.pubkey(),
                )
            )

            swap_ix = self.raydium_core.create_pool_swap_instruction(
                input_amount=sol_lamports,
                min_output_amount=min_tokens_out,
                input_token_account=temp_wsol_account,
                output_token_account=user_token_account,
                pool_keys=keys,
                owner_pubkey=keypair.pubkey(),
            )

            close_wsol_ix = close_account(
                CloseAccountParams(
                    program_id=TOKEN_PROGRAM_KEY,
                    account=temp_wsol_account,
                    dest=keypair.pubkey(),
                    owner=keypair.pubkey(),
                )
            )

            if not return_instructions:
                instructions = [
                    set_compute_unit_limit(self.COMPUTE_UNITS),
                    set_compute_unit_price(fee),
                ]
            else:
                instructions = []

            instructions.append(create_wsol_ix)
            instructions.append(init_wsol_ix)

            if create_token_account_ix is not None:
                instructions.append(create_token_account_ix)

            instructions.append(swap_ix)
            instructions.append(close_wsol_ix)

            if return_instructions:
                return instructions

            latest_blockhash_resp = await self.async_client.get_latest_blockhash()
            compiled_message = MessageV0.try_compile(
                keypair.pubkey(),
                instructions,
                [],
                latest_blockhash_resp.value.blockhash,
            )

            txn_signature = await self.async_client.send_transaction(
                txn=VersionedTransaction(compiled_message, [keypair]),
                opts=TxOpts(skip_preflight=True, max_retries=0)
            )

            logging.info(f"Transaction signature: {txn_signature.value}")
            confirmed = await self.await_confirm_transaction(txn_signature.value)
            logging.info("Transaction successful!" if confirmed else "Transaction failed.")
            return (confirmed, txn_signature.value)

        except Exception as err:
            logging.info("Error occurred during transaction:", err)
            traceback.print_exc()
            return False

    async def execute_sell_async(self, mint_address: str, keypair: Keypair, sell_pct: int = 100, slippage_percentage: int = 5, fee: int = 1000000, return_instructions: bool = False) -> bool:
        try:
            if not (1 <= sell_pct <= 100):
                return False

            try:
                pool_info = fetch_pool_info(mint_address)
                pool_key = pool_info["data"]["data"][0]["id"]
            except IndexError:
                logging.info(f"Pool key could not be found for {mint_address}. Trying again...")
                await asyncio.sleep(3)
                return await self.execute_sell_async(mint_address, sell_pct, slippage_percentage, fee)

            keys = await self.raydium_core.async_fetch_pool_keys(pool_key)
            if keys is None:
                return False

            token_mint = keys.token_base if keys.token_base != WSOL_ADDRESS else keys.token_quote

            token_balance = await self.fetch_token_balance_async(str(token_mint))
            if token_balance is None or token_balance == 0:
                logging.info("Token has no balance.")
                return False

            sell_balance = token_balance * (sell_pct / 100)

            base_reserve, quote_reserve, token_decimals = await self.raydium_core.async_get_pool_reserves(keys)
            lamports_expected = self.convert_tokens_to_sol(sell_balance, base_reserve, quote_reserve)

            slippage_factor = 1 - (slippage_percentage / 100)
            adjusted_lamports = lamports_expected * slippage_factor
            min_lamports_out = int(adjusted_lamports * SOL_DECIMALS)

            lamports_in = int(sell_balance * 10**token_decimals)
            user_token_account = get_associated_token_address(keypair.pubkey(), token_mint)

            seed_value = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
            temp_wsol_account = Pubkey.create_with_seed(
                keypair.pubkey(), seed_value, TOKEN_PROGRAM_KEY
            )

            create_wsol_ix = create_account_with_seed(
                CreateAccountWithSeedParams(
                    from_pubkey=keypair.pubkey(),
                    to_pubkey=temp_wsol_account,
                    base=keypair.pubkey(),
                    seed=seed_value,
                    lamports=int(RENT_EXEMPT_AMOUNT),
                    space=ACCOUNT_SIZE,
                    owner=TOKEN_PROGRAM_KEY,
                )
            )

            init_wsol_ix = initialize_account(
                InitializeAccountParams(
                    program_id=TOKEN_PROGRAM_KEY,
                    account=temp_wsol_account,
                    mint=WSOL_ADDRESS,
                    owner=keypair.pubkey(),
                )
            )

            swap_ix = self.raydium_core.create_pool_swap_instruction(
                input_amount=lamports_in,
                min_output_amount=min_lamports_out,
                input_token_account=user_token_account,
                output_token_account=temp_wsol_account,
                pool_keys=keys,
                owner_pubkey=keypair.pubkey(),
            )

            close_wsol_ix = close_account(
                CloseAccountParams(
                    program_id=TOKEN_PROGRAM_KEY,
                    account=temp_wsol_account,
                    dest=keypair.pubkey(),
                    owner=keypair.pubkey(),
                )
            )

            if not return_instructions:
                instructions = [
                    set_compute_unit_limit(self.COMPUTE_UNITS),
                    set_compute_unit_price(fee),
                ]
            else:
                instructions = []

            instructions.append(create_wsol_ix)
            instructions.append(init_wsol_ix)
            instructions.append(swap_ix)
            instructions.append(close_wsol_ix)

            if return_instructions:
                return instructions

            latest_blockhash_resp = await self.async_client.get_latest_blockhash()
            compiled_message = MessageV0.try_compile(
                keypair.pubkey(),
                instructions,
                [],
                latest_blockhash_resp.value.blockhash,
            )

            txn_signature = await self.async_client.send_transaction(
                txn=VersionedTransaction(compiled_message, [keypair]),
                opts=TxOpts(skip_preflight=True, max_retries=0)
            )

            logging.info(f"Transaction signature: {txn_signature.value}")
            confirmed = await self.await_confirm_transaction(txn_signature.value)
            logging.info("Transaction successful!" if confirmed else "Transaction failed.")
            return (confirmed, txn_signature.value)

        except Exception as err:
            logging.info(f"Error occurred during transaction: {err}")
            return False

    async def close(self):
        await self.async_client.close()