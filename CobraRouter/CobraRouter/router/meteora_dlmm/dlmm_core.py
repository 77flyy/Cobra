import asyncio, struct, base64, traceback, json
from asyncpg.pool import logging
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from solders.instruction import Instruction, AccountMeta # type: ignore
from solana.rpc.commitment import Processed
from solana.rpc.async_api import AsyncClient
from construct import (
    Struct as cStruct, Array, Bytes, Int8ul, Int16ul,
    Int32sl, Int64sl, Int32ul, Int64ul
)
try: from dlmm_bin import DLMMBin, BitmapExtLike, derive_bitmap_ext_pda
except: from .dlmm_bin import DLMMBin, BitmapExtLike, derive_bitmap_ext_pda
from decimal import Decimal, getcontext
import logging
getcontext().prec = 80

BASIS_POINT_MAX = 10_000 # 1 bp = 0.01 %
_TWO64 = Decimal(1 << 64) # 2^64  – Q64.64 unit

WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
DLMM_PROGRAM_ID = Pubkey.from_string("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo")
HOST_FEE_IN = DLMM_PROGRAM_ID
PRESET_TAG      = b"preset_parameter"
PRESET2_TAG     = b"preset_parameter2"
ILM_BASE_KEY    = Pubkey.from_string("MFGQxwAmB91SwuYX36okv2Qmdc9aMuHTwWGUrp4AtB1")
BIN_ARRAY_BITMAP_EX = DLMM_PROGRAM_ID # 1:1 on every token checked
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
EVENT_AUTHORITY = Pubkey.from_string("D1ZN9Wj1fRSUQfCjhvnu1hqDMT7hzjzBBpi12nVniYD6")
SWAP2_DISCM = bytes([65, 75, 63, 76, 235, 91, 91, 136]) # 8-byte discriminator
MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")

# Construct Helpers
PUBKEY    = Bytes(32)
U128      = Bytes(16)# little-endian; cast with int.from_bytes()
I128      = Bytes(16)
Arr8U64   = Array(8,  Int64ul) # helper – 8× u64  (8 * 8  =  64  bytes)
Arr12U64  = Array(12, Int64ul) # helper – 12× u64 (12 * 8 =  96  bytes)

BinLayout = cStruct(
    "amount_x"         / Int64ul,   # u64
    "amount_y"         / Int64ul,   # u64
    "liquidity_supply" / U128,      # u128
    "price"            / U128,      # u128 – set on first read
)

BinArrayLayout = cStruct(
    "index"     / Int64sl,
    "version"   / Int8ul,
    "padding0"  / Bytes(7),
    "lb_pair"   / PUBKEY,
    "bins"      / Array(70, BinLayout),
)

BinArrayBitmapExtensionLayout = cStruct(
    "lb_pair"                     / PUBKEY,
    "positive_bin_array_bitmap"   / Array(12, Arr8U64),
    "negative_bin_array_bitmap"   / Array(12, Arr8U64),
)

StaticParametersLayout = cStruct(
    "base_factor"                / Int16ul,
    "filter_period"              / Int16ul,
    "decay_period"               / Int16ul,
    "reduction_factor"           / Int16ul,
    "variable_fee_control"       / Int32ul,
    "max_volatility_accumulator" / Int32ul,
    "min_bin_id"                 / Int32sl,
    "max_bin_id"                 / Int32sl,
    "protocol_share"             / Int16ul,
    "base_fee_power_factor"      / Int8ul,
    "padding"                    / Bytes(5),
)

VariableParametersLayout = cStruct(
    "volatility_accumulator" / Int32ul,
    "volatility_reference"   / Int32ul,
    "index_reference"        / Int32sl,
    "padding"                / Bytes(4),
    "last_update_timestamp"  / Int64sl,
    "padding1"               / Bytes(8),
)

ProtocolFeeLayout = cStruct(
    "amount_x" / Int64ul,
    "amount_y" / Int64ul,
)

RewardInfoLayout = cStruct(        # 120-byte struct × 2 = 240 bytes
    "mint"                         / PUBKEY,
    "vault"                        / PUBKEY,
    "funder"                       / PUBKEY,
    "reward_duration"              / Int64ul,
    "reward_duration_end"          / Int64ul,
    "reward_rate"                  / U128,
    "last_update_time"             / Int64ul,
    "cumulative_seconds_with_empty_liquidity_reward" / Int64ul,
)

LbPairLayout = cStruct(
    "parameters"                        / StaticParametersLayout,
    "v_parameters"                      / VariableParametersLayout,
    "bump_seed"                         / Bytes(1),
    "bin_step_seed"                     / Bytes(2),
    "pair_type"                         / Int8ul,
    "active_id"                         / Int32sl,
    "bin_step"                          / Int16ul,
    "status"                            / Int8ul,
    "require_base_factor_seed"          / Int8ul,
    "base_factor_seed"                  / Bytes(2),
    "activation_type"                   / Int8ul,
    "creator_pool_on_off_control"       / Int8ul,
    "token_x_mint"                      / PUBKEY,
    "token_y_mint"                      / PUBKEY,
    "reserve_x"                         / PUBKEY,
    "reserve_y"                         / PUBKEY,
    "protocol_fee"                      / ProtocolFeeLayout,
    "padding1"                          / Bytes(32),
    "reward_infos"                      / Array(2, RewardInfoLayout),
    "oracle"                            / PUBKEY,
    "bin_array_bitmap"                  / Array(16, Int64ul),  # 1024-bit map
    "last_updated_at"                   / Int64sl,
    "padding2"                          / Bytes(32),
    "pre_activation_swap_address"       / PUBKEY,
    "base_key"                          / PUBKEY,
    "activation_point"                  / Int64ul,   # u64
    "pre_activation_duration"           / Int64ul,   # u64
    "padding3"                          / Bytes(8),
    "padding4"                          / Int64ul,   # u64
    "creator"                           / PUBKEY,
    "token_mint_x_program_flag"         / Int8ul,
    "token_mint_y_program_flag"         / Int8ul,
    "reserved"                          / Bytes(22),
)

async def _gather_exists(client: AsyncClient, pks: list[Pubkey]) -> set[Pubkey]:
    """Batch existence checks."""
    CHUNK = 100
    out = set()
    for i in range(0, len(pks), CHUNK):
        chunk = pks[i : i + CHUNK]
        resp  = await client.get_multiple_accounts(chunk, commitment=Processed)
        for acc, pk in zip(resp.value, chunk):
            if acc is not None:
                out.add(pk)
    return out

class DLMMCore:
    def __init__(self, client: AsyncClient):
        self.client = client

    async def build_swap_instruction(              
        self,
        action: str,                            
        pool_hdr: dict,                            
        user_ata: Pubkey,                     
        temp_wsol: Pubkey,                    
        amount_in: int,
        extra_bin_arrays: list[Pubkey],
        payer: Pubkey,
        token_program_id: Pubkey = TOKEN_PROGRAM_ID,
    ) -> Instruction:
        """action: \"buy\" or \"sell\""""

        lb_pair   = Pubkey.from_string(pool_hdr["pool"])
        token_x = Pubkey.from_string(pool_hdr["token_x_mint"])
        token_y = Pubkey.from_string(pool_hdr["token_y_mint"])
        reserve_x = self.derive_reserve_pda(lb_pair, token_x)
        reserve_y = self.derive_reserve_pda(lb_pair, token_y)

        if action == "buy":
            user_in  = temp_wsol  
            user_out = user_ata  
        else:
            user_in  = user_ata   
            user_out = temp_wsol  

        keys = [
            AccountMeta(lb_pair,      False, True),
            AccountMeta(BIN_ARRAY_BITMAP_EX,   False, False),
            AccountMeta(reserve_x,    False, True),
            AccountMeta(reserve_y,    False, True),
            AccountMeta(user_in,      False, True),
            AccountMeta(user_out,     False, True),
            AccountMeta(token_x,      False, False),
            AccountMeta(token_y,      False, False),
            AccountMeta(Pubkey.from_string(pool_hdr["oracle"]), False, True),
            AccountMeta(HOST_FEE_IN,  False, False),
            AccountMeta(payer,  True,  False),
            AccountMeta(token_program_id, False, False),
            AccountMeta(TOKEN_PROGRAM_ID, False, False),
            AccountMeta(MEMO_PROGRAM_ID,  False, False),
            AccountMeta(EVENT_AUTHORITY,  False, False),
            AccountMeta(DLMM_PROGRAM_ID,  False, False),
        ]

        keys.extend(AccountMeta(p, False, True) for p in extra_bin_arrays)  # Bin arrays must be writable!
        min_amount_out = 0
        data  = (
            SWAP2_DISCM +
            amount_in.to_bytes(8, "little") +
            min_amount_out.to_bytes(8, "little") +
            bytes([0, 0, 0, 0])
        )

        return Instruction(program_id=DLMM_PROGRAM_ID,
                        accounts=keys,
                        data=data)

    def derive_reserve_pda(self, lb_pair: str | Pubkey, token_mint: str | Pubkey) -> Pubkey:
        lb_pair = lb_pair if isinstance(lb_pair, Pubkey) else Pubkey.from_string(lb_pair)
        token_mint = token_mint if isinstance(token_mint, Pubkey) else Pubkey.from_string(token_mint)
        seeds = [lb_pair.__bytes__(), token_mint.__bytes__()]
        return Pubkey.find_program_address(seeds, DLMM_PROGRAM_ID)[0]

    def convert_pool_keys(self, parsed) -> dict:
        return {
            "token_x_mint": str(Pubkey.from_bytes(parsed.token_x_mint)),
            "token_y_mint": str(Pubkey.from_bytes(parsed.token_y_mint)),
            "reserveX": str(Pubkey.from_bytes(parsed.reserve_x)),
            "reserveY": str(Pubkey.from_bytes(parsed.reserve_y)),
            "bin_step": parsed.bin_step,
            "creator": str(Pubkey.from_bytes(parsed.creator)),
            "active_id": parsed.active_id,
            "pair_type": parsed.pair_type,
            "status": parsed.status,
            "require_base_factor_seed": parsed.require_base_factor_seed,
            "base_factor_seed": parsed.base_factor_seed,
            "activation_type": parsed.activation_type,
            "creator_pool_on_off_control": parsed.creator_pool_on_off_control,
            "bin_array_bitmap": parsed.bin_array_bitmap,
            "last_updated_at": parsed.last_updated_at,
            "pre_activation_swap_address": str(Pubkey.from_bytes(parsed.pre_activation_swap_address)),
            "protocol_fee": parsed.protocol_fee,
            "oracle": str(Pubkey.from_bytes(parsed.oracle)),
            "base_key": str(Pubkey.from_bytes(parsed.base_key)),
        }

    async def fetch_pool_state(self, pool_addr: str | Pubkey) -> dict:
        """
        Fetch the state of a pool.
        """
        try:
            pool_addr = pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)
            resp = await self.client.get_account_info_json_parsed(pool_addr, commitment="confirmed")
            if not resp or not resp.value or not resp.value.data:
                raise Exception("Invalid account response")

            raw_data = resp.value.data
            parsed = LbPairLayout.parse(raw_data[8:])
            pdict = self.convert_pool_keys(parsed)
            pdict["pool"] = str(pool_addr)
            return pdict
        except Exception as e:
            logging.info(f"Error in fetch_pool_state: {e}")
            traceback.print_exc()
            return None

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
        *,
        pool_addr: str | Pubkey,
        strict_mint: str | Pubkey | None = None,
    ) -> dict | None:
        try:
            pool_pk: Pubkey = (
                pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)
            )
            hdr = await self.fetch_pool_state(pool_pk)
            if hdr is None:
                raise ValueError("pool header not found")

            x_mint = Pubkey.from_string(hdr["token_x_mint"])
            y_mint = Pubkey.from_string(hdr["token_y_mint"])

            if WSOL_MINT not in (x_mint, y_mint):
                raise ValueError("pair is not SOL‑denominated")

            sol_is_y   = (y_mint == WSOL_MINT)
            sol_mint   = WSOL_MINT
            token_mint = y_mint if not sol_is_y else x_mint

            if strict_mint and Pubkey.from_string(str(strict_mint)) != token_mint:
                raise ValueError("requested mint is not the non‑SOL side")

            active_id: int = hdr["active_id"]
            bin_step : int = hdr["bin_step"]

            base  = Decimal(1) + Decimal(bin_step) / BASIS_POINT_MAX
            ratio = base ** active_id

            token_dec = await self.get_decimals(token_mint)
            scale     = Decimal(10) ** (token_dec - 9) 

            if sol_is_y:
                sol_per_token = (ratio * scale)
            else:
                sol_per_token = (1 / ratio * scale)

            res_x_pda = self.derive_reserve_pda(pool_pk, x_mint)
            res_y_pda = self.derive_reserve_pda(pool_pk, y_mint)
            res_x, res_y = await self.async_get_pool_reserves(res_x_pda, res_y_pda)

            if sol_is_y: # unused
                token_reserve, sol_reserve = res_x, res_y
            else:
                token_reserve, sol_reserve = res_y, res_x

            return {
                "pool":          str(pool_pk),
                "token_mint":    str(token_mint),
                "price":         float(sol_per_token),
            }

        except Exception as exc:
            logging.info(f"get_price() error: {exc}")
            traceback.print_exc()
            return None

    async def fetch_bin_array_bitmap_ext(self, pool: str | Pubkey):
        pool = pool if isinstance(pool, Pubkey) else Pubkey.from_string(pool)
        resp = await self.client.get_account_info_json_parsed(pool, commitment="confirmed")
        if not resp or not resp.value or not resp.value.data:
            raise Exception("Invalid account response")
        raw_data = resp.value.data
        parsed = BinArrayBitmapExtensionLayout.parse(raw_data[8:])
        return parsed

    async def get_bin_arrays_for_swap(self, pool_header: dict, swap_for_y: bool, depth: int = 4) -> list[Pubkey]:
        bitmap_ext: BitmapExtLike | None = None
        if abs(pool_header["active_id"]) >= 512:
            ext_pda, _ = derive_bitmap_ext_pda(Pubkey.from_string(pool_header["pool"]))
            acc = await self.client.get_account_info(ext_pda, encoding="base64")
            if acc.value:
                bitmap_ext = BinArrayBitmapExtensionLayout.parse(base64.b64decode(acc.value.data[0])[8:])

        class _Hdr:
            pubkey           = Pubkey.from_string(pool_header["pool"])
            active_id        = pool_header["active_id"]
            bin_array_bitmap = pool_header["bin_array_bitmap"]

        raw_list = DLMMBin.bin_arrays_for_swap(_Hdr, swap_for_y, depth * 3, bitmap_ext)

        existing = []
        for chunk_start in range(0, len(raw_list), 100):
            chunk = raw_list[chunk_start : chunk_start + 100]
            infos = await self.client.get_multiple_accounts(chunk, commitment=Processed)
            existing.extend(pk for pk, acc in zip(chunk, infos.value) if acc)

            if len(existing) >= depth:
                break

        return existing[:depth]

    async def find_dlmm_pools_by_mint(
        self,
        mint_a: str | Pubkey,
        mint_b: str | Pubkey | None = None,
        max_preset_index: int = 256
    ) -> list[str]:
        """
        Return every live DLMM LbPair that trades (mint_a, mint_b).
        If mint_b is None the second side defaults to wSOL.
        """

        m0 = mint_a if isinstance(mint_a, Pubkey) else Pubkey.from_string(mint_a)
        m1 = mint_b if mint_b else WSOL_MINT
        m1 = m1 if isinstance(m1, Pubkey) else Pubkey.from_string(m1)
        t0, t1 = sorted([m0, m1], key=lambda pk: bytes(pk))

        candidates: list[Pubkey] = []

        preset_pks: list[Pubkey] = []
        for idx in range(max_preset_index):
            seed_idx = idx.to_bytes(2, "little")
            pk, _ = Pubkey.find_program_address(
                [PRESET2_TAG, seed_idx],
                DLMM_PROGRAM_ID,
            )
            preset_pks.append(pk)

        preset_pks = list(await _gather_exists(self.client, preset_pks))

        for preset in preset_pks:
            pool, _ = Pubkey.find_program_address(
                [preset.__bytes__(), t0.__bytes__(), t1.__bytes__()],
                DLMM_PROGRAM_ID,
            )
            candidates.append(pool)

        pool_ilm, _ = Pubkey.find_program_address(
            [ILM_BASE_KEY.__bytes__(), t0.__bytes__(), t1.__bytes__()],
            DLMM_PROGRAM_ID,
        )
        candidates.append(pool_ilm)

        BIN_STEPS = (1, 5, 10, 20, 25, 50, 100, 200, 400)
        for bs in BIN_STEPS:
            bs_bytes = bs.to_bytes(2, "little")
            preset, _ = Pubkey.find_program_address(
                [PRESET_TAG, bs_bytes],
                DLMM_PROGRAM_ID,
            )
            pool, _ = Pubkey.find_program_address(
                [preset.__bytes__(), t0.__bytes__(), t1.__bytes__()],
                DLMM_PROGRAM_ID,
            )
            candidates.append(pool)

            pool2, _ = Pubkey.find_program_address(
                [t0.__bytes__(), t1.__bytes__(), bs_bytes],
                DLMM_PROGRAM_ID,
            )
            candidates.append(pool2)

        existing = await _gather_exists(self.client, candidates)

        return [str(pk) for pk in sorted(existing, key=lambda pk: bytes(pk))]

    async def async_get_pool_reserves(self, vault_a: Pubkey, vault_b: Pubkey):
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

    async def find_suitable_pool(self, pools: list, mint: str | Pubkey, sol_amount: float = 0.001, exclude_pools: list[str] = []):
        """
            Returns:
                - pool: Pubkey
                - reserveX: Pubkey aka Token
                - reserveY: Pubkey aka WSOL
        """
        try:
            for pool in pools:
                logging.info(f"Excluding pools from DLMM: {exclude_pools}")
                if exclude_pools:
                    if pool in exclude_pools:
                        continue
                reserveX = self.derive_reserve_pda(pool, mint)
                reserveY = self.derive_reserve_pda(pool, WSOL_MINT)
                logging.info(f"ReserveX: {reserveX}, ReserveY: {reserveY}")
                reserveXamount, reserveYamount = await self.async_get_pool_reserves(reserveX, reserveY)
                if reserveXamount <= 0 or reserveYamount <= 0.25:
                    logging.info("Skipping pool with low/zero reserves (>=0.25 SOL)")
                    continue
                
                token_reserve = reserveXamount
                sol_reserve = reserveYamount
                price_per_sol = token_reserve / sol_reserve if sol_reserve > 0 else 0
                required_tokens = sol_amount * price_per_sol
                logging.info(f"Price per SOL: {price_per_sol:,.2f} tokens, Required tokens for {sol_amount} SOL: {required_tokens:,.6f}")
                
                if (
                    (required_tokens > 0 and price_per_sol > 0.0)
                    and token_reserve > required_tokens
                    and sol_reserve > sol_amount
                ):
                    logging.info(f"✅ Pool has sufficient liquidity!")
                    return pool, reserveX, reserveY
            return None, None, None
        except Exception as e:
            logging.info(f"Error: {e}")
            return None, None, None