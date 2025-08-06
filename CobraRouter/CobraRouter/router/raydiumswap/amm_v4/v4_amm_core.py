# raydium_core.py

import logging
import traceback
import asyncio

from solana.rpc.async_api import AsyncClient

logging.basicConfig(level=logging.INFO)

import struct
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from solana.rpc.commitment import Processed
from solders.instruction import AccountMeta, Instruction  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from construct import (
    Struct as cStruct,
    Bytes, Int8ul, Int16ul, Int32ul, Int64ul,
    Padding, Array
)

WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
RAYDIUM_AMM_V4 = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")

PUBKEY = Bytes(32)
U128   = Bytes(16)

AMM_SCHEME = cStruct(
    "status"                 / Int64ul,
    "nonce"                  / Int64ul,
    "order_count"            / Int64ul,
    "depth"                  / Int64ul,
    "coin_decimals"          / Int64ul,
    "pc_decimals"            / Int64ul,
    "state"                  / Int64ul,
    "reset_flag"             / Int64ul,
    "min_size"               / Int64ul,
    "vol_max_cut_ratio"      / Int64ul,
    "amount_wave_ratio"      / Int64ul,
    "coin_lot_size"          / Int64ul,
    "pc_lot_size"            / Int64ul,
    "min_price_multiplier"   / Int64ul,
    "max_price_multiplier"   / Int64ul,
    "system_decimals_value"  / Int64ul,
    "min_separate_numerator" / Int64ul,
    "min_separate_denominator" / Int64ul,
    "trade_fee_numerator"    / Int64ul,
    "trade_fee_denominator"  / Int64ul,
    "pnl_numerator"          / Int64ul,
    "pnl_denominator"        / Int64ul,
    "swap_fee_numerator"     / Int64ul,
    "swap_fee_denominator"   / Int64ul,
    "need_take_pnl_coin"     / Int64ul,
    "need_take_pnl_pc"       / Int64ul,
    "total_pnl_pc"           / Int64ul,
    "total_pnl_coin"         / Int64ul,
    "pool_open_time"         / Int64ul,
    "punish_pc_amount"       / Int64ul,
    "punish_coin_amount"     / Int64ul,
    "orderbook_to_init_time" / Int64ul,
    "swap_coin_in_amount"    / U128,
    "swap_pc_out_amount"     / U128,
    "swap_coin2pc_fee"       / Int64ul,
    "swap_pc_in_amount"      / U128,
    "swap_coin_out_amount"   / U128,
    "swap_pc2coin_fee"       / Int64ul,
    "pool_coin_token_account"    / PUBKEY,
    "pool_pc_token_account"      / PUBKEY,
    "coin_mint_address"          / PUBKEY,
    "pc_mint_address"            / PUBKEY,
    "lp_mint_address"            / PUBKEY,
    "amm_open_orders"            / PUBKEY,
    "serum_market"               / PUBKEY,
    "serum_program_id"           / PUBKEY,
    "amm_target_orders"          / PUBKEY,
    "pool_withdraw_queue"        / PUBKEY,
    "pool_temp_lp_token_account" / PUBKEY,
    "amm_owner"                  / PUBKEY,
    "pnl_owner"                  / PUBKEY,
)

ACCOUNT_SCHEME = cStruct("bits" / Int64ul)

# Serum v3 market header
MARKET_SCHEME = cStruct(
    Padding(5),
    "account_flags"        / Int64ul,
    "own_address"          / PUBKEY,
    "vault_signer_nonce"   / Int64ul,
    "base_mint"            / PUBKEY,
    "quote_mint"           / PUBKEY,
    "base_vault"           / PUBKEY,
    "base_deposits_total"  / Int64ul,
    "base_fees_accrued"    / Int64ul,
    "quote_vault"          / PUBKEY,
    "quote_deposits_total" / Int64ul,
    "quote_fees_accrued"   / Int64ul,
    "quote_dust_threshold" / Int64ul,
    "request_queue"        / PUBKEY,
    "event_queue"          / PUBKEY,
    "bids"                 / PUBKEY,
    "asks"                 / PUBKEY,
    "base_lot_size"        / Int64ul,
    "quote_lot_size"       / Int64ul,
    "fee_rate_bps"         / Int64ul,
    "referrer_rebate_accrued" / Int64ul,
    Padding(7),
)


@dataclass
class RaydiumPoolKeys:
    pool_id: Pubkey
    token_base: Pubkey
    token_quote: Pubkey
    decimals_base: int
    decimals_quote: int
    orders_open: Pubkey
    orders_target: Pubkey
    vault_base: Pubkey
    vault_quote: Pubkey
    market_id: Pubkey
    market_auth: Pubkey
    market_vault_base: Pubkey
    market_vault_quote: Pubkey
    bids: Pubkey
    asks: Pubkey
    event_queue: Pubkey
    ray_auth_v4: Pubkey
    open_book_prog: Pubkey
    token_prog_id: Pubkey

class SwapDirection(Enum):
    BUY = 0
    SELL = 1

class RaydiumCore:
    def __init__(self, async_client):
        self.async_client = async_client

    async def async_fetch_pool_keys(self, pool_address: str | Pubkey) -> Optional[RaydiumPoolKeys]:
        pool_address = pool_address if isinstance(pool_address, Pubkey) else Pubkey.from_string(pool_address)
        def _pack_u64(value: int) -> bytes:
            if not (0 <= value < 2**64):
                raise ValueError("Value must be within u64 range.")
            return struct.pack('<Q', value)
    
        try:
            pool_id = pool_address
            account_info = await self.async_client.get_account_info_json_parsed(pool_id, commitment=Processed)
            pool_data = account_info.value.data
            decoded_pool = AMM_SCHEME.parse(pool_data)
            market_id = Pubkey.from_bytes(decoded_pool.serum_market)
            market_info = await self.async_client.get_account_info_json_parsed(market_id, commitment=Processed)
            decoded_market = MARKET_SCHEME.parse(market_info.value.data)
            vault_nonce = decoded_market.vault_signer_nonce
            
            ray_auth = Pubkey.from_string("5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1")
            open_book_prog = Pubkey.from_string("srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX")
            token_prog = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

            pool_keys = RaydiumPoolKeys(
                pool_id=pool_id,
                token_base=Pubkey.from_bytes(decoded_market.base_mint),
                token_quote=Pubkey.from_bytes(decoded_market.quote_mint),
                decimals_base=decoded_pool.coin_decimals,
                decimals_quote=decoded_pool.pc_decimals,
                orders_open=Pubkey.from_bytes(decoded_pool.amm_open_orders),
                orders_target=Pubkey.from_bytes(decoded_pool.amm_target_orders),
                vault_base=Pubkey.from_bytes(decoded_pool.pool_coin_token_account),
                vault_quote=Pubkey.from_bytes(decoded_pool.pool_pc_token_account),
                market_id=market_id,
                market_auth=Pubkey.create_program_address(
                    seeds=[bytes(market_id), _pack_u64(vault_nonce)], 
                    program_id=open_book_prog
                ),
                market_vault_base=Pubkey.from_bytes(decoded_market.base_vault),
                market_vault_quote=Pubkey.from_bytes(decoded_market.quote_vault),
                bids=Pubkey.from_bytes(decoded_market.bids),
                asks=Pubkey.from_bytes(decoded_market.asks),
                event_queue=Pubkey.from_bytes(decoded_market.event_queue),
                ray_auth_v4=ray_auth,
                open_book_prog=open_book_prog,
                token_prog_id=token_prog
            )

            return pool_keys
        except Exception as exc:
            logging.info(f"Error fetching pool keys: {exc}")
            return None

    async def get_price(self, pool_addr: str | Pubkey):
        pool_addr = pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)
        pool_keys = await self.async_fetch_pool_keys(pool_addr)
        if pool_keys is None:
            return None
        vault_a, vault_b, decs = await self.async_get_pool_reserves(pool_keys)
        if vault_a is None or vault_b is None:
            return None
        return vault_b / vault_a

    def create_pool_swap_instruction(
        self,
        input_amount: int, 
        min_output_amount: int, 
        input_token_account: Pubkey, 
        output_token_account: Pubkey, 
        pool_keys: RaydiumPoolKeys,
        owner_pubkey: Pubkey
    ) -> Instruction:
        """Create swap instruction for the pool."""
        try:
            account_metas = [
                AccountMeta(pubkey=pool_keys.token_prog_id, is_signer=False, is_writable=False),
                AccountMeta(pubkey=pool_keys.pool_id, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.ray_auth_v4, is_signer=False, is_writable=False),
                AccountMeta(pubkey=pool_keys.orders_open, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.orders_target, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.vault_base, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.vault_quote, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.open_book_prog, is_signer=False, is_writable=False), 
                AccountMeta(pubkey=pool_keys.market_id, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.bids, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.asks, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.event_queue, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.market_vault_base, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.market_vault_quote, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_keys.market_auth, is_signer=False, is_writable=False),
                AccountMeta(pubkey=input_token_account, is_signer=False, is_writable=True),  
                AccountMeta(pubkey=output_token_account, is_signer=False, is_writable=True), 
                AccountMeta(pubkey=owner_pubkey, is_signer=True, is_writable=False) 
            ]
            
            instruction_data = bytearray()
            discriminator = 9
            instruction_data.extend(struct.pack('<B', discriminator))
            instruction_data.extend(struct.pack('<Q', input_amount))
            instruction_data.extend(struct.pack('<Q', min_output_amount))
            swap_ix = Instruction(RAYDIUM_AMM_V4, bytes(instruction_data), account_metas)
            
            return swap_ix
        except Exception as exc:
            traceback.print_exc()
            logging.info(f"Error creating swap instruction: {exc}")
            return None

    async def async_get_pool_reserves(self, pool_keys: RaydiumPoolKeys) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """Asynchronously get pool reserves."""
        try:
            vault_quote = pool_keys.vault_quote
            decimals_quote = pool_keys.decimals_quote
            
            vault_base = pool_keys.vault_base
            decimals_base = pool_keys.decimals_base
            token_base = pool_keys.token_base
            
            accounts_resp = await self.async_client.get_multiple_accounts_json_parsed(
                [vault_quote, vault_base], 
                commitment=Processed
            )
            accounts_data = accounts_resp.value

            account_quote = accounts_data[0]
            account_base = accounts_data[1]
            
            quote_balance = account_quote.data.parsed['info']['tokenAmount']['uiAmount']
            base_balance = account_base.data.parsed['info']['tokenAmount']['uiAmount']
            
            if quote_balance is None or base_balance is None:
                logging.info("Couldn't get pool reserves.")
                return None, None, None
            
            if token_base == WSOL_MINT:
                reserve_base = quote_balance  
                reserve_quote = base_balance  
                token_decimals = decimals_quote 
            else:
                reserve_base = base_balance  
                reserve_quote = quote_balance
                token_decimals = decimals_base

            return reserve_base, reserve_quote, token_decimals

        except Exception as exc:
            logging.info(f"Error fetching pool reserves: {exc}")
            return None, None, None