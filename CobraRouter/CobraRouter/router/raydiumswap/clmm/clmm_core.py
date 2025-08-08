import asyncio
import struct
from dataclasses import dataclass
import traceback
from typing import Optional, Tuple

from asyncpg.pool import logging
from solders.pubkey import Pubkey # type: ignore
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta # type: ignore
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import MemcmpOpts, DataSliceOpts
from solana.rpc.commitment import Processed
from solders.keypair import Keypair # type: ignore

CLMM_PROGRAM_ID       = Pubkey.from_string("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK")
WSOL_MINT             = Pubkey.from_string("So11111111111111111111111111111111111111112")
TOKEN_PROGRAM_ID      = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM_ID = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
_ANCHOR_DISCRIM_SWAP  = bytes([43, 4, 237, 11, 26, 201, 30, 98])
MEMO_PROGRAM_ID = Pubkey.from_string(
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
)
_MINT_A_OFF = 73
_MINT_B_OFF = 105

POOL_ACCOUNT_SIZE = 448

@dataclass
class ClmmPoolKeys:
    id: Pubkey
    program_id: Pubkey
    mint_a: Pubkey
    mint_b: Pubkey
    vault_a: Pubkey
    vault_b: Pubkey
    amm_cfg: Pubkey
    observation_id: Pubkey
    ex_bitmap: Pubkey

_AMM_CONFIGS = [
    Pubkey.from_string("9iFER3bpjf1PTTCQCfTRu17EJgvsxo9pVyA9QWwEuX4x"),
    Pubkey.from_string("EdPxg8QaeFSrTYqdWJn6Kezwy9McWncTYueD9eMGCuzR"),
    Pubkey.from_string("9EeWRCL8CJnikDFCDzG8rtmBs5KQR1jEYKCR5rRZ2NEi"),
    Pubkey.from_string("3h2e43PunVA5K34vwKCLHWhZF4aZpyaC9RmxvshGAQpL"),
    Pubkey.from_string("3XCQJQryqpDvvZBfGxR7CLAw5dpGJ9aa7kt1jRLdyxuZ"),
    Pubkey.from_string("DrdecJVzkaRsf1TQu1g7iFncaokikVTHqpzPjenjRySY"),
    Pubkey.from_string("J8u7HvA1g1p2CdhBFdsnTxDzGkekRpdw4GrL9MKU2D3U"),
    Pubkey.from_string("RPxHtdN5V7ajwkoG6NnwSBAeaX5k9giY37dpp98xTjD"),
    Pubkey.from_string("9WjDVMHWCirG9jkchbetHTnSzdXbAPnD9bsoGRcz1xUw"),
    Pubkey.from_string("FMrUDGjEe1izXPbn8SZPNjMfB5JvvhVq5ymmpZDebB5R"),
    Pubkey.from_string("E64NGkDLLCdQ2yFNPcavaKptrEgmiQaNykUuLC1Qgwyp"),
    Pubkey.from_string("Y6YhgJbt9FRk3JVjwdZtsioVCJwCKhy1hum8HMDYyB1"),
    Pubkey.from_string("47Nq74YtwjVeTQF6KFKRKU4cY1Vd5AXBHpYRkubkDLZi"),
    Pubkey.from_string("DQeN7dZyQvXKT7YwmgqyuC7AYFkwMoP7RwtucsDEdfYZ"),
    Pubkey.from_string("A1BBtTYJd4i3xU8D6Tc2FzU6ZN4oXZWXKZnCxwbHXr8x"),
    Pubkey.from_string("Gex2NJRS3jVLPfbzSFM5d5DRsNoL5ynnwT1TXoDEhanz"),
    Pubkey.from_string("CDpiwv9eLsRvvuzZEJ8CBtK14wdvkSnkub4vmGtzzdK8"),
    Pubkey.from_string("6tBc3ABLaYTTWu94DiRD5PWi92HML34UpAQ8pPTYgudw"),
]
_POOL_SEED = b"pool"

class ClmmCore:
    def __init__(self, client: AsyncClient):
        self.client = client

    async def _pool_exists(self, addr: Pubkey) -> bool:
        info = await self.client.get_account_info(addr, commitment="processed")
        return info.value is not None

    async def find_pool_by_mint(
        self,
        mint_a: Pubkey | str,
        mint_b: Pubkey | str | None = None,
    ) -> Pubkey | None:
        """
        Resolve the CLMM pool PDA for (mint_a, mint_b).
        """
        mint_a = mint_a if isinstance(mint_a, Pubkey) else Pubkey.from_string(mint_a)
        mint_b = mint_b if isinstance(mint_b, Pubkey) else (
            Pubkey.from_string(mint_b) if mint_b else
            Pubkey.from_string("So11111111111111111111111111111111111111112")  # WSOL
        )

        mints_ordered = sorted([mint_a, mint_b], key=lambda pk: bytes(pk))

        for cfg in _AMM_CONFIGS:
            seeds = [_POOL_SEED, bytes(cfg), bytes(mints_ordered[0]), bytes(mints_ordered[1])]
            pool, _bump = Pubkey.find_program_address(seeds, CLMM_PROGRAM_ID)
            if await self._pool_exists(pool):
                return pool
        return None

    async def async_fetch_pool_liquidity(self, pool_id: Pubkey) -> int:
        """
        Fetch the raw 'liquidity' (u128) field from the on-chain pool account.
        """
        acc = await self.client.get_account_info(pool_id, commitment="confirmed")
        if acc.value is None:
            raise RuntimeError(f"Pool {pool_id} not found")

        data = acc.value.data
        if isinstance(data, str):
            import base64
            data = base64.b64decode(data)

        liq = int.from_bytes(data[237:253], "little", signed=False)
        return liq

    async def find_pool_by_mint_with_min_liquidity(
        self,
        mint_a: Pubkey | str,
        mint_b: Pubkey | str | None = None,
        min_liquidity: int = 0,
    ) -> Pubkey | None:
        """
        Like find_pool_by_mint, but only returns the first pool whose 
        on-chain liquidity >= min_liquidity.
        """
        mint_a = mint_a if isinstance(mint_a, Pubkey) else Pubkey.from_string(mint_a)
        mint_b = (
            mint_b if isinstance(mint_b, Pubkey)
            else Pubkey.from_string(mint_b) if mint_b
            else WSOL_MINT
        )
        # order lexically, as Raydium seeds them
        m0, m1 = sorted([mint_a, mint_b], key=lambda pk: bytes(pk))

        for cfg in _AMM_CONFIGS:
            seeds = [b"pool", bytes(cfg), bytes(m0), bytes(m1)]
            pool, _bump = Pubkey.find_program_address(seeds, CLMM_PROGRAM_ID)
            if not await self._pool_exists(pool):
                continue

            liq = await self.async_fetch_pool_liquidity(pool)
            if liq >= min_liquidity:
                return pool

        return None

    async def async_fetch_pool_keys(self, pool_id: Pubkey) -> Optional[ClmmPoolKeys]:
        """Very light decode"""
        acc = await self.client.get_account_info(pool_id, commitment="confirmed")
        if acc.value is None:
            return None
        data = acc.value.data
        if isinstance(data, str):
            import base64
            data = base64.b64decode(data)

        def _pk(off: int) -> Pubkey:
            return Pubkey.from_bytes(data[off: off + 32])

        # offsets from PoolInfoLayout (see layout.ts)
        keys = ClmmPoolKeys(
            id           = pool_id,
            program_id   = CLMM_PROGRAM_ID,
            amm_cfg      = _pk(  9),        
            mint_a       = _pk(_MINT_A_OFF),
            mint_b       = _pk(_MINT_B_OFF),
            vault_a      = _pk(137),        
            vault_b      = _pk(169),       
            observation_id = _pk(201),
            ex_bitmap    = self._derive_ex_bitmap(pool_id)
        )
        return keys

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
        pool_addr: str | Pubkey,
        *,
        strict_mint: str | Pubkey | None = None,
    ) -> dict | None:
        """
        Returns
        -------
        {
            "pool":          "...",
            "token_mint":    "...",          # the non-SOL side
            "token_reserve": <float>,        # ui-amount in vault
            "sol_reserve":   <float>,        # ui-amount in vault
            "price":         <float>,        # SOL  per 1 token
            "price_per_sol": <float>,        # token per 1 SOL
        }
        """
        try:
            pool_pk = pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)

            keys = await self.async_fetch_pool_keys(pool_pk)
            if keys is None:
                raise ValueError("pool decode failed")

            if WSOL_MINT not in (keys.mint_a, keys.mint_b):
                raise ValueError("pool is not SOL-denominated")

            sol_is_a   = (keys.mint_a == WSOL_MINT)
            token_mint = keys.mint_b if sol_is_a else keys.mint_a

            if strict_mint and Pubkey.from_string(str(strict_mint)) != token_mint:
                raise ValueError("requested mint is not the pool’s non-SOL token")

            res_a, res_b = await self.async_get_pool_reserves(keys)

            sol_reserve, token_reserve = (res_a, res_b) if sol_is_a else (res_b, res_a)

            if sol_reserve == 0 or token_reserve == 0:
                raise ValueError("zero vault balance – cannot price")

            token_dec = await self.get_decimals(token_mint)
            scale = 10 ** (token_dec - 9)
            sol_per_token  = sol_reserve / token_reserve

            return {
                "pool":          str(pool_pk),
                "token_mint":    str(token_mint),
                "token_reserve": token_reserve,
                "price":         sol_per_token,
            }

        except Exception as exc:
            logging.info(f"get_price() error: {exc}")
            traceback.print_exc()
            return None

    async def async_fetch_pool_tickinfo(self, pool_id: Pubkey) -> tuple[int, int]:
        acc = await self.client.get_account_info(pool_id, commitment="confirmed")
        if acc.value is None:
            raise RuntimeError("Pool account not found")

        data = acc.value.data
        if isinstance(data, str):
            import base64
            data = base64.b64decode(data)

        tick_spacing = int.from_bytes(data[235:237], "little", signed=False)
        tick_current = int.from_bytes(data[269:273], "little", signed=True)

        return tick_spacing, tick_current

    @staticmethod
    def _derive_ex_bitmap(pool_id: Pubkey) -> Pubkey:
        """
        Raydium SDK's getPdaExBitmapAccount:
            findProgramAddress(
                ["pool_tick_array_bitmap_extension", pool_id],
                CLMM_PROGRAM_ID
            )
        """
        seed_tag = b"pool_tick_array_bitmap_extension"
        pda, _ = Pubkey.find_program_address(
            [seed_tag, bytes(pool_id)],
            CLMM_PROGRAM_ID,
        )
        return pda

    async def async_get_pool_reserves(self, keys: ClmmPoolKeys) -> Tuple[float, float]:
        infos = await self.client.get_multiple_accounts_json_parsed(
            [keys.vault_a, keys.vault_b], commitment=Processed
        )
        ui_a = infos.value[0].data.parsed["info"]["tokenAmount"]["uiAmount"]
        ui_b = infos.value[1].data.parsed["info"]["tokenAmount"]["uiAmount"]
        return float(ui_a or 0), float(ui_b or 0)

    def create_swap_instruction_base_in(
        self,
        keys: ClmmPoolKeys,
        owner: Pubkey,
        user_in_ata: Pubkey,
        user_out_ata: Pubkey,
        input_mint: Pubkey,
        amount_in: int,
        min_amount_out: int,
        sqrt_price_limit_x64: int = 0,
        extra_accounts: list[Pubkey] = [],
    ) -> Instruction:
        data = (
            struct.pack("<Q", amount_in) +
            struct.pack("<Q", min_amount_out) +
            struct.pack("<16s", sqrt_price_limit_x64.to_bytes(16, "little")) +
            b"\x01"                               # isBaseInput = true
        )
        ix_data = _ANCHOR_DISCRIM_SWAP + data

        is_in_a = input_mint == keys.mint_a
        accs = [
            AccountMeta(owner,             True,  False),
            AccountMeta(keys.amm_cfg,      False, False),
            AccountMeta(keys.id,           False, True),
            AccountMeta(user_in_ata,       False, True),
            AccountMeta(user_out_ata,      False, True),
            AccountMeta(keys.vault_a if is_in_a else keys.vault_b, False, True),
            AccountMeta(keys.vault_b if is_in_a else keys.vault_a, False, True),
            AccountMeta(keys.observation_id, False, True),
            AccountMeta(TOKEN_PROGRAM_ID,  False, False),
            AccountMeta(TOKEN_2022_PROGRAM_ID, False, False),
            AccountMeta(MEMO_PROGRAM_ID,   False, False),
            AccountMeta(keys.mint_a if is_in_a else keys.mint_b, False, False),
            AccountMeta(keys.mint_b if is_in_a else keys.mint_a, False, False),
        ]
        if extra_accounts:
            accs.extend(AccountMeta(a, False, True) for a in extra_accounts)
        return Instruction(keys.program_id, ix_data, accs)