import solana.exceptions
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from solders.instruction import Instruction, AccountMeta # type: ignore
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address
from solana.rpc.types import MemcmpOpts, DataSliceOpts
from solana.rpc.commitment import Processed
import asyncio
import traceback
import base64
from construct import Struct, Int8ul, Int64ul, Bytes
from typing import Tuple
from decimal import Decimal
import logging
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
CP_AMM_PROGRAM_ID = Pubkey.from_string("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

PUBKEY = Bytes(32)

PrunedPoolLayout = Struct(
    "before_token_a" / Bytes(160),
    "token_a_mint" / PUBKEY,         # offset 160 (168 in account)
    "token_b_mint" / PUBKEY,         # offset 192 (200 in account)  
    "token_a_vault" / PUBKEY,        # offset 224
    "token_b_vault" / PUBKEY,        # offset 256
    "whitelisted_vault" / PUBKEY,    # offset 288
    "partner" / PUBKEY,              # offset 320
    "liquidity" / Bytes(16),         # u128 - offset 352
    "_padding" / Bytes(16),          # u128 padding - offset 368
    "protocol_a_fee" / Int64ul,      # offset 384
    "protocol_b_fee" / Int64ul,      # offset 392
    "partner_a_fee" / Int64ul,       # offset 400  
    "partner_b_fee" / Int64ul,       # offset 408
    "sqrt_min_price" / Bytes(16),    # u128 - offset 416
    "sqrt_max_price" / Bytes(16),    # u128 - offset 432
    "sqrt_price" / Bytes(16),        # u128 - offset 448
    "activation_point" / Int64ul,    # offset 464
    "activation_type" / Int8ul,      # offset 472
    "pool_status" / Int8ul,          # offset 473
    "token_a_flag" / Int8ul,
    "token_b_flag" / Int8ul,
    "collect_fee_mode" / Int8ul,
    "pool_type" / Int8ul,
)

def b58(x: bytes) -> str:
    return str(Pubkey.from_bytes(x))

def le_bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, "little")

class SwapParams:
    def __init__(
        self,
        payer: Pubkey,
        pool: Pubkey,
        base_mint: Pubkey,
        wsol_mint: Pubkey,
        amount_in: int,
        minimum_amount_out: int,
        token_a_vault: Pubkey,
        token_b_vault: Pubkey,
        token_a_mint: Pubkey,
        token_b_mint: Pubkey,
        token_a_program: Pubkey = TOKEN_PROGRAM_ID,
        token_b_program: Pubkey = TOKEN_PROGRAM_ID,
        referral_token_account: Pubkey = Pubkey.from_string("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG")
    ):
        self.payer = payer
        self.pool = pool
        self.base_mint = base_mint
        self.wsol_mint = wsol_mint
        self.amount_in = amount_in
        self.minimum_amount_out = minimum_amount_out
        self.token_a_vault = token_a_vault
        self.token_b_vault = token_b_vault
        self.token_a_mint = token_a_mint
        self.token_b_mint = token_b_mint
        self.token_a_program = token_a_program
        self.token_b_program = token_b_program
        self.referral_token_account = referral_token_account

class DAMM2SwapBuilder:
    def __init__(self, client: AsyncClient):
        self.client = client
    
    async def build_swap_instruction(self, action: str, params: SwapParams, temp_wsol: Pubkey) -> Instruction:
        pool_authority = DAMM2Core(self.client).derive_pool_authority()
        event_authority = DAMM2Core(self.client).derive_event_authority()
    
        if action == "buy":
            input_token_account = temp_wsol
            output_token_account = get_associated_token_address(params.payer, params.base_mint, params.token_a_program)
        else:
            input_token_account = get_associated_token_address(params.payer, params.base_mint, params.token_a_program)
            output_token_account = temp_wsol
        
        accounts = [
            AccountMeta(pubkey=pool_authority, is_signer=False, is_writable=False),
            AccountMeta(pubkey=params.pool, is_signer=False, is_writable=True),
            AccountMeta(pubkey=input_token_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=output_token_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=params.token_a_vault, is_signer=False, is_writable=True),
            AccountMeta(pubkey=params.token_b_vault, is_signer=False, is_writable=True),
            AccountMeta(pubkey=params.token_a_mint, is_signer=False, is_writable=False),
            AccountMeta(pubkey=params.token_b_mint, is_signer=False, is_writable=False),
            AccountMeta(pubkey=params.payer, is_signer=True, is_writable=False),
            AccountMeta(pubkey=params.token_a_program, is_signer=False, is_writable=False),
            AccountMeta(pubkey=params.token_b_program, is_signer=False, is_writable=False),
        ]
        
        accounts.append(AccountMeta(pubkey=params.referral_token_account, is_signer=False, is_writable=True))
        accounts.extend([
            AccountMeta(pubkey=event_authority, is_signer=False, is_writable=False),
            AccountMeta(pubkey=CP_AMM_PROGRAM_ID, is_signer=False, is_writable=True),
        ])
        
        discriminator = bytes([248, 198, 158, 145, 225, 117, 135, 200])
        
        amount_in_bytes = params.amount_in.to_bytes(8, 'little')
        minimum_amount_out_bytes = params.minimum_amount_out.to_bytes(8, 'little')
        
        instruction_data = discriminator + amount_in_bytes + minimum_amount_out_bytes
        
        return Instruction(
            program_id=CP_AMM_PROGRAM_ID,
            accounts=accounts,
            data=instruction_data
        )

class DAMM2Core:
    def __init__(self, client: AsyncClient):
        self.client = client

    def get_first_key(self, key1: Pubkey, key2: Pubkey) -> bytes:
        """get the lexicographically larger key buffer"""
        buf1 = key1.__bytes__()
        buf2 = key2.__bytes__()
        if buf1 > buf2:
            return buf1
        return buf2
    
    def get_second_key(self, key1: Pubkey, key2: Pubkey) -> bytes:
        buf1 = key1.__bytes__()
        buf2 = key2.__bytes__()
        if buf1 > buf2:
            return buf2
        return buf1
    
    def derive_pool_authority(self) -> Pubkey:
        seeds = [b"pool_authority"]
        pda, _ = Pubkey.find_program_address(seeds, CP_AMM_PROGRAM_ID)
        return pda
    
    def derive_config_address(self, index: int) -> Pubkey:
        seeds = [b"config", index.to_bytes(8, 'little')]
        pda, _ = Pubkey.find_program_address(seeds, CP_AMM_PROGRAM_ID)
        return pda
    
    def derive_pool_address(self, config: Pubkey, token_a_mint: Pubkey, token_b_mint: Pubkey) -> Pubkey:
        seeds = [
            b"pool",
            config.__bytes__(),
            self.get_first_key(token_a_mint, token_b_mint),
            self.get_second_key(token_a_mint, token_b_mint)
        ]
        pda, _ = Pubkey.find_program_address(seeds, CP_AMM_PROGRAM_ID)
        return pda
    
    def derive_customizable_pool_address(self, token_a_mint: Pubkey, token_b_mint: Pubkey) -> Pubkey:
        seeds = [
            b"cpool",
            self.get_first_key(token_a_mint, token_b_mint),
            self.get_second_key(token_a_mint, token_b_mint)
        ]
        pda, _ = Pubkey.find_program_address(seeds, CP_AMM_PROGRAM_ID)
        return pda
    
    def derive_token_vault_address(self, token_mint: Pubkey, pool: Pubkey) -> Pubkey:
        seeds = [b"token_vault", token_mint.__bytes__(), pool.__bytes__()]
        pda, _ = Pubkey.find_program_address(seeds, CP_AMM_PROGRAM_ID)
        return pda
    
    def derive_pool_vaults(self, token_a_mint: Pubkey, token_b_mint: Pubkey, pool: Pubkey) -> Tuple[Pubkey, Pubkey]:
        vault_a = self.derive_token_vault_address(token_a_mint, pool)
        vault_b = self.derive_token_vault_address(token_b_mint, pool)
        return vault_a, vault_b
    
    def derive_event_authority(self) -> Pubkey:
        seeds = [b"__event_authority"]
        pda, _ = Pubkey.find_program_address(seeds, CP_AMM_PROGRAM_ID)
        return pda

    async def fetch_pool_state(self, pool_address: str | Pubkey) -> dict:
        pool_pubkey = pool_address if isinstance(pool_address, Pubkey) else Pubkey.from_string(pool_address)
        
        try:
            account_info = await self.client.get_account_info(pool_pubkey, encoding="base64")
            if account_info.value is None:
                raise ValueError(f"Pool account not found: {pool_pubkey}")
            
            if isinstance(account_info.value.data, bytes):
                blob = account_info.value.data
            elif isinstance(account_info.value.data, tuple):
                blob = base64.b64decode(account_info.value.data[0])
            else:
                raise TypeError(f"Unexpected data field type: {type(account_info.value.data)}")
            
            blob = blob[8:]
            parsed = PrunedPoolLayout.parse(blob)
            out = {
                "pool_address": str(pool_pubkey),
                "token_a_mint": b58(parsed.token_a_mint),
                "token_b_mint": b58(parsed.token_b_mint),
                "token_a_vault": b58(parsed.token_a_vault),
                "token_b_vault": b58(parsed.token_b_vault),
                "whitelisted_vault": b58(parsed.whitelisted_vault),
                "partner": b58(parsed.partner),
                "liquidity": le_bytes_to_int(parsed.liquidity),
                "protocol_a_fee": parsed.protocol_a_fee,
                "protocol_b_fee": parsed.protocol_b_fee,
                "partner_a_fee": parsed.partner_a_fee,
                "partner_b_fee": parsed.partner_b_fee,
                "sqrt_min_price": le_bytes_to_int(parsed.sqrt_min_price),
                "sqrt_max_price": le_bytes_to_int(parsed.sqrt_max_price),
                "sqrt_price": le_bytes_to_int(parsed.sqrt_price),
                "activation_point": parsed.activation_point,
                "activation_type": parsed.activation_type,
                "pool_status": parsed.pool_status,
                "pool_type": parsed.pool_type,
            }
            
            return out
            
        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"Failed to fetch pool state: {e}")


    async def get_decimals(self, mint: str | Pubkey) -> int:
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            mint_info = await self.client.get_account_info_json_parsed(
                mint,
                commitment=Processed
            )
            if not mint_info:
                logging.info("Error: Failed to fetch mint info (tried to fetch token decimals).")
                return None
            dec_base = mint_info.value.data.parsed['info']['decimals']
            return int(dec_base)
        except Exception as e:
            logging.error(f"Error getting decimals for mint: {e}")
            traceback.print_exc()
            return None

    async def get_price(
        self,
        mint: str | Pubkey | None = None,
        *,
        pool_addr: str | Pubkey,
    ) -> dict | None:
        """
        Spot price of the *non‑SOL* token in the given pool.

        Returns
        -------
        {
            "pool":          ...,
            "token_mint":    ...,
            "token_reserve": ...,
            "sol_reserve":   ...,
            "price":         <SOL  per token>,
            "price_per_sol": <token per SOL>,
        }
        """
        try:
            pool_pk: Pubkey = (
                pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)
            )
            state = await self.fetch_pool_state(pool_pk)

            a_mint = Pubkey.from_string(state["token_a_mint"])
            b_mint = Pubkey.from_string(state["token_b_mint"])

            if WSOL_MINT in (a_mint, b_mint):
                sol_mint  = WSOL_MINT
                token_mint = b_mint if a_mint == WSOL_MINT else a_mint
            else:
                raise ValueError("Pool is not SOL‑denominated")

            if mint is not None and Pubkey.from_string(str(mint)) != token_mint:
                raise ValueError("Requested mint not in this pool")

            decs = await self.get_decimals(token_mint)
            diff = decs - 9

            sqrt_price_q64 = Decimal(state["sqrt_price"])
            sqrt_ratio = sqrt_price_q64 / Decimal(1 << 64)
            price_raw  = sqrt_ratio ** 2

            if b_mint == sol_mint:
                sol_per_token_raw = price_raw
            else:
                sol_per_token_raw = 1 / price_raw

            scale = Decimal(10) ** diff
            sol_per_token = (sol_per_token_raw * scale).normalize()

            return {
                "pool":          str(pool_pk),
                "token_mint":    str(token_mint),
                "price":         float(sol_per_token),
            }

        except Exception as exc:
            logging.info(f"get_price() error: {exc}")
            traceback.print_exc()
            return None

    async def async_get_pool_reserves(self, vault_a: Pubkey, vault_b: Pubkey) -> Tuple[float, float]:
        """
        Fetch vault reserves for DAMM v2 pool.
        Returns: (reserve_a, reserve_b) in decimal
        """
        try:
            infos = await self.client.get_multiple_accounts_json_parsed(
                [vault_a, vault_b], commitment=Processed
            )
            ui_a = infos.value[0].data.parsed["info"]["tokenAmount"]["uiAmount"]
            ui_b = infos.value[1].data.parsed["info"]["tokenAmount"]["uiAmount"]
            return float(ui_a or 0), float(ui_b or 0)
        except Exception as e:
            logging.info(f"Error fetching vault reserves: {e}")
            traceback.print_exc()
            return 0.0, 0.0

    async def find_pools_by_mint(self, mint: str | Pubkey, sol_amount: float = 0.01, limit: int = 10) -> str | None:
        """
        Find the best pool for a given mint with sufficient liquidity.
        Returns:
            Pool address string or None if no suitable pool found
        """
        mint_str = str(mint) if isinstance(mint, Pubkey) else mint
        mint = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)
        found_pools = []
        best_pool = None
        try:
            target_offsets = [168, 200] # 168 is offset of token_a_mint, 200 is offset of token_b_mint
            
            for target_offset in target_offsets:
                resp = await self.client.get_program_accounts(
                    CP_AMM_PROGRAM_ID,
                    commitment="confirmed",
                    encoding="base64",
                    data_slice=DataSliceOpts(offset=0, length=target_offset + 32),
                    filters=[
                        MemcmpOpts(offset=target_offset, bytes=mint_str)
                    ]
                )
                
                found_pools.extend(str(acc.pubkey) for acc in resp.value[:limit])
            
            found_pools = list(set(found_pools))
            
            for pool_addr in found_pools:
                try:
                    pool_state = await self.fetch_pool_state(pool_addr)
                    
                    liquidity = pool_state["liquidity"]
                    token_a_mint = Pubkey.from_string(pool_state["token_a_mint"])
                    token_b_mint = Pubkey.from_string(pool_state["token_b_mint"])
                    token_a_vault = Pubkey.from_string(pool_state["token_a_vault"])
                    token_b_vault = Pubkey.from_string(pool_state["token_b_vault"])
                    
                    reserve_a, reserve_b = await self.async_get_pool_reserves(token_a_vault, token_b_vault)
                    
                    logging.info(f"\nPool: {pool_addr}")
                    
                    if reserve_a <= 0 or reserve_b <= 0 or liquidity <= 0:
                        logging.info("Skipping pool with zero reserves")
                        continue
                    
                    if token_a_mint == mint and token_b_mint == WSOL_MINT:
                        token_reserve = reserve_a
                        sol_reserve = reserve_b
                        price_per_sol = token_reserve / sol_reserve if sol_reserve > 0 else 0
                        required_tokens = sol_amount * price_per_sol
                        logging.info(f"Price per SOL: {price_per_sol:,.2f} tokens, Required tokens for {sol_amount} SOL: {required_tokens:,.6f}")
                        
                    elif token_b_mint == mint and token_a_mint == WSOL_MINT:
                        sol_reserve = reserve_a
                        token_reserve = reserve_b
                        price_per_sol = token_reserve / sol_reserve if sol_reserve > 0 else 0
                        required_tokens = sol_amount * price_per_sol
                        logging.info(f"Price per SOL: {price_per_sol:,.10f} tokens, Required tokens for {sol_amount} SOL: {required_tokens:,.6f}")
                    else:
                        logging.info(f"Pool doesn't contain SOL, skipping")
                        continue
                    
                    if (
                        (required_tokens > 0 and price_per_sol > 0.0)
                        and token_reserve > required_tokens
                        and sol_reserve > sol_amount
                    ):
                        logging.info(f"✅ Pool has sufficient liquidity!")
                        best_pool = pool_addr
                        break
                    else:
                        logging.info(f"❌ Insufficient liquidity (need {required_tokens:,.6f} tokens, {sol_amount} SOL)")
                        
                except Exception as e:
                    logging.info(f"Error processing pool {pool_addr}: {e}")
                    continue

            return best_pool
        except solana.exceptions.SolanaRpcException:
            logging.info(f"Error in pool_scanning: We don't know the cause yet, but it's probably because the pool is not found, or the RPC is rate limited.")
            return None
        except Exception as e:
            logging.info(f"Error in damm2 pool scanning: {e}")
            traceback.print_exc()
            return None