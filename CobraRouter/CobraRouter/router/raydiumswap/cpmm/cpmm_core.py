# cpmm_core.py
import asyncio
import logging, struct, traceback
from dataclasses import dataclass
from typing import Optional, Tuple
import solana.exceptions
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
from solders.pubkey import Pubkey # type: ignore
from solders.instruction import Instruction, AccountMeta # type: ignore
from solana.exceptions import SolanaRpcException
from solana.rpc.types import (
    DataSliceOpts,
    MemcmpOpts
)
from construct import Bytes, Int8ul, Int64ul, Struct as cStruct
import logging

CPMM_PROGRAM_ID = Pubkey.from_string("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C")
WSOL_MINT        = Pubkey.from_string("So11111111111111111111111111111111111111112")

AUTH_SEED        = b"vault_and_lp_mint_auth_seed"
POOL_VAULT_SEED  = b"pool_vault"
OBSERVATION_SEED = b"observation"
SWAP_BASE_IN_DISCRIM = bytes([0x8f, 0xbe, 0x5a, 0xda, 0xc4, 0x1e, 0x33, 0xde])

CPMM_POOL_LAYOUT = cStruct(
    "padding"            / Bytes(8), # u64
    "config_id"          / Bytes(32),
    "pool_creator"       / Bytes(32),
    "vault_a"            / Bytes(32),
    "vault_b"            / Bytes(32),
    "mint_lp"            / Bytes(32),
    "mint_a"             / Bytes(32),
    "mint_b"             / Bytes(32),
    "mint_program_a"     / Bytes(32),
    "mint_program_b"     / Bytes(32),
    "observation_id"     / Bytes(32),
    "bump"               / Int8ul,
    "status"             / Int8ul,
    "lp_decimals"        / Int8ul,
    "mint_decimal_a"     / Int8ul,
    "mint_decimal_b"     / Int8ul,
    "lp_amount"          / Int64ul,
    "protocol_fees_a"    / Int64ul,
    "protocol_fees_b"    / Int64ul,
    "fund_fees_a"        / Int64ul,
    "fund_fees_b"        / Int64ul,
    "open_time"          / Int64ul,
    "padding2"           / Bytes(32 * 8), # 256
)

@dataclass
class CpmmPoolKeys:
    program_id: Pubkey
    pool_id: Pubkey
    authority: Pubkey
    config_id: Pubkey

    mint_a: Pubkey
    mint_b: Pubkey
    decimals_a: int
    decimals_b: int
    vault_a: Pubkey
    vault_b: Pubkey

    observation_id: Pubkey
    mint_prog_a: Pubkey
    mint_prog_b: Pubkey

class RaydiumCpmmCore:
    def __init__(self, async_client):
        self.client = async_client

    async def async_fetch_pool_keys(self, pool_id: str | Pubkey) -> Optional[CpmmPoolKeys]:
        pool_pk = pool_id if isinstance(pool_id, Pubkey) else Pubkey.from_string(pool_id)
        try:
            acc = await self.client.get_account_info_json_parsed(pool_pk, commitment=Processed)
            decoded = CPMM_POOL_LAYOUT.parse(acc.value.data)

            authority, _ = Pubkey.find_program_address([AUTH_SEED], CPMM_PROGRAM_ID)
            obs_pda, _   = Pubkey.find_program_address([OBSERVATION_SEED, bytes(pool_pk)], CPMM_PROGRAM_ID)

            return CpmmPoolKeys(
                program_id     = CPMM_PROGRAM_ID,
                pool_id        = pool_pk,
                authority      = authority,
                config_id      = Pubkey.from_bytes(decoded.config_id),

                mint_a         = Pubkey.from_bytes(decoded.mint_a),
                mint_b         = Pubkey.from_bytes(decoded.mint_b),
                decimals_a     = decoded.mint_decimal_a,
                decimals_b     = decoded.mint_decimal_b,
                vault_a        = Pubkey.from_bytes(decoded.vault_a),
                vault_b        = Pubkey.from_bytes(decoded.vault_b),

                observation_id = obs_pda,
                mint_prog_a    = Pubkey.from_bytes(decoded.mint_program_a),
                mint_prog_b    = Pubkey.from_bytes(decoded.mint_program_b),
            )
        except Exception as exc:
            traceback.print_exc()
            logging.info(f"[CPMM] pool-decode failed: {exc}")
            return None

    async def get_price(self, pool_addr: str | Pubkey):
        pool_addr = pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)
        pool_keys = await self.async_fetch_pool_keys(pool_addr)
        if pool_keys is None:
            return None
        
        vault_a, vault_b = await self.async_get_pool_reserves(pool_keys)
        if vault_a is None or vault_b is None:
            return None
        if pool_keys.mint_a == WSOL_MINT:
            return vault_a / vault_b
        return vault_b / vault_a

    async def find_cpmm_pools_by_mint(self, mint: str | Pubkey, limit: int = 50, retry: bool = False) -> list[str]:
        """
           Takes in:
           - mint: str | Pubkey

           Returns:
           - list[str]
        """
        try:
            mint_pk = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)

            MINT_A_OFFSET = 168
            MINT_B_OFFSET = 200

            slice_opt = DataSliceOpts(offset=0, length=MINT_B_OFFSET + 32)  # just enough for the second mint

            pools = []
            for off in (MINT_B_OFFSET, MINT_A_OFFSET):
                resp = await self.client.get_program_accounts(
                    CPMM_PROGRAM_ID,
                    commitment="finalized",
                    encoding="base64",
                    data_slice=slice_opt,
                    filters=[MemcmpOpts(offset=off, bytes=str(mint_pk))]
                )
                if resp.value:
                    pools.extend(str(acc.pubkey) for acc in resp.value[:limit])
            return pools
        except solana.exceptions.SolanaRpcException as e:
            logging.info(f"Error in find_cpmm_pools_by_mint: We don't know the cause yet, but it's probably because the pool is not found, or the RPC is rate limited.")
            if retry:
                return []
            return await self.find_cpmm_pools_by_mint(mint, limit + 1000, retry=True)
        except Exception as e:
            logging.info(f"Error in find_cpmm_pools_by_mint: {e}")
            traceback.print_exc()
            return []

    async def find_suitable_pool(self, mint: str | Pubkey, pools: list[str], sol_amount: float = 0.000001) -> str:
        try:
            best_pool = None
            keys = None
            mint_pk = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)
            for pool in pools:
                keys = await self.async_fetch_pool_keys(pool)
                if keys:
                    reserve_a, reserve_b = await self.async_get_pool_reserves(keys)
                    token_a_mint = keys.mint_a
                    token_b_mint = keys.mint_b

                    logging.info(f"Pool: {pool}")
                    
                    if reserve_a <= 0 or reserve_b <= 0:
                        logging.info("Skipping pool with zero reserves")
                        continue
                    
                    if token_a_mint == mint_pk and token_b_mint == WSOL_MINT:
                        token_reserve = reserve_a
                        sol_reserve = reserve_b
                        price_per_sol = token_reserve / sol_reserve if sol_reserve > 0 else 0
                        required_tokens = sol_amount * price_per_sol
                        logging.info(f"Price per SOL: {price_per_sol:,.2f} tokens, Required tokens for {sol_amount} SOL: {required_tokens:,.6f}")
                        
                    elif token_b_mint == mint_pk and token_a_mint == WSOL_MINT:
                        sol_reserve = reserve_a
                        token_reserve = reserve_b
                        price_per_sol = token_reserve / sol_reserve if sol_reserve > 0 else 0
                        required_tokens = sol_amount * price_per_sol
                        logging.info(f"Price per SOL: {price_per_sol:,.2f} tokens, Required tokens for {sol_amount} SOL: {required_tokens:,.6f}")
                    else:
                        logging.info(f"Pool doesn't contain SOL, skipping")
                        continue
                    
                    if (
                        (required_tokens > 0 and price_per_sol > 0.0)
                        and token_reserve > required_tokens
                        and sol_reserve > sol_amount
                    ):
                        logging.info(f"✅ Pool has sufficient liquidity!")
                        best_pool = pool
                        break
                    else:
                        logging.info(f"❌ Insufficient liquidity (need {required_tokens:,.6f} tokens, {sol_amount} SOL)")
                await asyncio.sleep(0.1)
                
            return (best_pool, keys)
        except solana.exceptions.SolanaRpcException:
            logging.info(f"Error in find_suitable_pool: We don't know the cause yet, but it's probably because the pool is not found, or the RPC is rate limited.")
            return None
        except Exception as e:
            logging.info(f"Error in pool scanning: {e}")
            traceback.print_exc()
            return None

    async def async_get_pool_reserves(self, keys: CpmmPoolKeys) -> Tuple[float, float]:
        infos = await self.client.get_multiple_accounts_json_parsed(
            [keys.vault_a, keys.vault_b], commitment=Processed
        )
        ui_a = infos.value[0].data.parsed["info"]["tokenAmount"]["uiAmount"]
        ui_b = infos.value[1].data.parsed["info"]["tokenAmount"]["uiAmount"]
        return float(ui_a or 0), float(ui_b or 0)

    def create_swap_instruction_base_in(
            self,
            amount_in: int,
            min_amount_out: int,
            user_input_ata: Pubkey,
            user_output_ata: Pubkey,
            input_vault: Pubkey,
            output_vault: Pubkey,
            input_prog: Pubkey,
            output_prog: Pubkey,
            input_mint: Pubkey,
            output_mint: Pubkey,
            keys: CpmmPoolKeys,
            owner: Pubkey,
    ) -> Instruction:

        metas = [
            AccountMeta(owner,           True,  False),
            AccountMeta(keys.authority,  False, False),
            AccountMeta(keys.config_id,  False, False),
            AccountMeta(keys.pool_id,    False, True),

            AccountMeta(user_input_ata,  False, True),
            AccountMeta(user_output_ata, False, True),

            AccountMeta(input_vault,     False, True),
            AccountMeta(output_vault,    False, True),

            AccountMeta(input_prog,      False, False),
            AccountMeta(output_prog,     False, False),

            AccountMeta(input_mint,      False, False),
            AccountMeta(output_mint,     False, False),

            AccountMeta(keys.observation_id, False, True),
        ]

        data  = SWAP_BASE_IN_DISCRIM + struct.pack("<Q", amount_in) + struct.pack("<Q", min_amount_out)
        return Instruction(CPMM_PROGRAM_ID, data, metas)