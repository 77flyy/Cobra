# libs/raydiumswap/clmm/clmm_swap.py

import asyncio, base64, os, traceback
from typing import Tuple, Optional

from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair # type: ignore
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price # type: ignore
from solders.transaction import VersionedTransaction # type: ignore
from solders.message import MessageV0 # type: ignore
from spl.token.instructions import (
    create_associated_token_account,
    get_associated_token_address,
    initialize_account,
    close_account,
    sync_native, SyncNativeParams,
    CloseAccountParams, InitializeAccountParams
)

from solana.rpc.types import TokenAccountOpts, TxOpts
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed, Confirmed
from solders.system_program import create_account_with_seed, CreateAccountWithSeedParams
try: from .clmm_core import ClmmCore, CLMM_PROGRAM_ID, WSOL_MINT, TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID;
except: from clmm_core import ClmmCore, CLMM_PROGRAM_ID, WSOL_MINT, TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID;
try: from .ticks import RaydiumFuckingTicks;
except: from ticks import RaydiumFuckingTicks;

RENT_EXEMPT   = 5039280
ACCOUNT_SIZE  = 165
SOL_DECIMALS  = 1e9
COMPUTE_UNITS = 200_000

TOKEN_PROGRAMS = {
    "legacy": TOKEN_PROGRAM_ID,
    "2022":   TOKEN_2022_PROGRAM_ID,
}

class RaydiumClmmSwap:
    def __init__(self, client: AsyncClient):
        self.client  = client
        self.ticks   = RaydiumFuckingTicks()
        self.core    = ClmmCore(client)

    async def estimate_clmm_output(self, pool_keys, input_mint: Pubkey, amount_in: int) -> int:
        """
        Estimate output for CLMM swap using pool reserves and current price.
        This is more conservative than the incorrect constant product formula.
        """
        try:
            token_reserve, sol_reserve = await self.core.async_get_pool_reserves(pool_keys)
            
            if token_reserve <= 0 or sol_reserve <= 0:
                print("Warning: Invalid reserves, using fallback")
                return amount_in // 10000
            
            if input_mint == pool_keys.mint_b:
                token_price_in_sol = sol_reserve / token_reserve
                amount_in_ui = amount_in / 1e6
                estimated_sol_out = amount_in_ui * token_price_in_sol
                impact_factor = max(0.7, 1 - (amount_in_ui / token_reserve * 10))
                final_sol_out = estimated_sol_out * impact_factor * 0.9975
                return int(final_sol_out * 1e9)
            else:  # Selling SOL for token
                sol_price_in_tokens = token_reserve / sol_reserve
                amount_in_sol = amount_in / 1e9
                estimated_tokens_out = amount_in_sol * sol_price_in_tokens
                impact_factor = max(0.7, 1 - (amount_in_sol / sol_reserve * 10))
                final_tokens_out = estimated_tokens_out * impact_factor * 0.9975
                return int(final_tokens_out * 1e6)
                
        except Exception as e:
            print(f"Error in CLMM estimation: {e}")
            traceback.print_exc()
            return None

    async def estimate_clmm_output_with_decimals(self, pool_keys, input_mint: Pubkey, amount_in: int, token_decimals: int) -> int:
        """
        Conservative CLMM output estimation. 
        CLMM reserves don't represent active liquidity - only a fraction is available at current tick.
        """
        try:
            token_reserve, sol_reserve = await self.core.async_get_pool_reserves(pool_keys)
            
            if token_reserve <= 0 or sol_reserve <= 0:
                print("Warning: Invalid reserves, using minimal fallback")
                return max(amount_in // 10000, 1)
            
            if input_mint == pool_keys.mint_b: # Selling token for SOL
                amount_in_ui = amount_in / (10 ** token_decimals)
                active_token_liquidity = token_reserve * 0.001
                active_sol_liquidity = sol_reserve * 0.001
                
                if amount_in_ui > active_token_liquidity * 0.01:
                    print("Warning: Trade too large for active liquidity, using minimal output")
                    return max(amount_in // 50000, 1)
                
                conservative_rate = min(amount_in_ui * 0.0001, 0.001)
                print(f"Debug: Ultra-conservative estimated SOL out: {conservative_rate}")
                
                return max(int(conservative_rate * 1e9), 1000)
                
            else:
                amount_in_sol = amount_in / 1e9
                print(f"Debug: Selling {amount_in_sol} SOL")
                
                active_token_liquidity = token_reserve * 0.001
                active_sol_liquidity = sol_reserve * 0.001
                
                if amount_in_sol > active_sol_liquidity * 0.01:
                    return max(amount_in // 50000, 1)
                
                conservative_tokens = min(amount_in_sol * 1000, 1.0)
                print(f"Debug: Ultra-conservative estimated tokens out: {conservative_tokens}")
                
                return max(int(conservative_tokens * (10 ** token_decimals)), 1)
                
        except Exception as e:
            print(f"Error in CLMM estimation with decimals: {e}")
            return max(amount_in // 100000, 1)

    @staticmethod
    def convert_tokens_to_sol_simple(tokens: float, r_base: float, r_quote: float, fee_pct=0.25) -> float:
        """
        Simple constant product estimation - NOT accurate for CLMM, kept for reference.
        Use estimate_clmm_output instead for better accuracy.
        """
        if r_base <= 0 or r_quote <= 0:
            return 0.0
        
        price = r_quote / r_base
        eff_tokens = tokens * (1 - fee_pct / 100)
        estimated_sol = eff_tokens * price
        impact_factor = min(0.99, 1 - (eff_tokens / r_base))
        return round(estimated_sol * impact_factor, 9)

    async def _mint_owner(self, mint: Pubkey) -> Pubkey:
        info = await self.client.get_account_info(mint, commitment=Processed)
        if info.value is None:
            raise RuntimeError("mint account missing")
        return info.value.owner

    async def _get_or_create_ata(self, owner: Pubkey, mint: Pubkey):
        token_prog = await self._mint_owner(mint)
        resp = await self.client.get_token_accounts_by_owner(
            owner, TokenAccountOpts(mint=mint), Processed)

        if resp.value:
            return resp.value[0].pubkey, None, token_prog

        ata = get_associated_token_address(owner, mint, token_prog)
        ix  = create_associated_token_account(
                payer        = owner,
                owner  = owner,
                mint    = mint,
                token_program_id = token_prog)
        return ata, ix, token_prog

    async def _await_confirm(self, sig: str, tries=5, delay=3):
        for _ in range(tries):
            res = await self.client.get_transaction(sig, commitment=Confirmed,
                                                    max_supported_transaction_version=0)
            if res.value and res.value.transaction.meta.err is None:
                return True
            await asyncio.sleep(delay)
        return False

    async def _wrap_sol_temp(
        self,
        lamports: int,
        payer: Pubkey
    ) -> tuple[Pubkey, list]:
        """
        Returns (temp_wsol_pubkey, [ix0, ix1, ix2])
        """
        seed = base64.urlsafe_b64encode(os.urandom(9)).decode()
        temp = Pubkey.create_with_seed(payer, seed, TOKEN_PROGRAM_ID)

        rent     = RENT_EXEMPT
        funding  = lamports + rent

        create_ix = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey      = payer,
                to_pubkey        = temp,
                base      = payer,
                seed             = seed,
                lamports         = funding,
                space            = ACCOUNT_SIZE,
                owner       = TOKEN_PROGRAM_ID,
            )
        )

        init_ix = initialize_account(
            InitializeAccountParams(
                program_id = TOKEN_PROGRAM_ID,
                account    = temp,
                mint       = WSOL_MINT,
                owner      = payer,
            )
        )

        sync_ix = sync_native(SyncNativeParams(program_id=TOKEN_PROGRAM_ID, account=temp))
        return temp, [create_ix, init_ix, sync_ix]

    async def execute_clmm_buy_async(
        self,
        token_mint: str,
        sol_amount: float,
        keypair: Keypair,
        min_out: int = 1, # TODO: make this a slippage
        fee_micro_lamports: int = 1_000_000,
        pool_id: Optional[str] = None,
        return_instructions: bool = False,
    ) -> Tuple[bool, str]:

        sol_lamports = int(sol_amount * SOL_DECIMALS)
        pool_id = pool_id or await self.core.find_pool_by_mint(token_mint)
        if pool_id is None:
            raise RuntimeError("no CLMM pool found for mint")

        keys = await self.core.async_fetch_pool_keys(pool_id)
        if keys is None:
            raise RuntimeError("decode failed")

        extra_accounts = []

        pda_ex_bitmap = self.core._derive_ex_bitmap(keys.id)
        extra_accounts.append(pda_ex_bitmap)

        tick_spacing, tick_current = await self.core.async_fetch_pool_tickinfo(pool_id)
        print(f"Tick spacing: {tick_spacing}, Tick current: {tick_current}")

        tick_arrays = await self.ticks.get_tick_arrays(pool_id, tick_current, tick_spacing)
        for tick_array in tick_arrays:
            extra_accounts.append(tick_array)
        
        if keys.mint_a != WSOL_MINT:
            raise RuntimeError("buy helper assumes WSOL is mintA (most pools follow this)")

        user_out_ata, create_out_ix, out_token_prog = \
        await self._get_or_create_ata(keypair.pubkey(), Pubkey.from_string(token_mint))

        temp_wsol, wrap_ixs = await self._wrap_sol_temp(sol_lamports, keypair.pubkey())

        ixs: list = [
            *wrap_ixs,
        ]

        if not return_instructions:
            ixs.append(set_compute_unit_limit(COMPUTE_UNITS))
            ixs.append(set_compute_unit_price(fee_micro_lamports))

        if create_out_ix:
            ixs.append(create_out_ix)

        close_wsol_ix = close_account(
            CloseAccountParams(TOKEN_PROGRAM_ID, temp_wsol,
                               keypair.pubkey(), keypair.pubkey())
        )

        ixs.append(
            self.core.create_swap_instruction_base_in(
                keys           = keys,
                owner          = keypair.pubkey(),
                user_in_ata    = temp_wsol,
                user_out_ata   = user_out_ata,
                input_mint     = WSOL_MINT,
                amount_in      = sol_lamports,
                min_amount_out = min_out,
                extra_accounts = extra_accounts
            )
        )

        ixs.append(close_wsol_ix)

        if return_instructions:
            return ixs

        bh = (await self.client.get_latest_blockhash()).value.blockhash
        msg = MessageV0.try_compile(keypair.pubkey(), ixs, [], bh)
        sig = await self.client.send_transaction(
            VersionedTransaction(msg, [keypair]),
            opts=TxOpts(skip_preflight=True, max_retries=0),
        )
        print(sig)
        ok = await self._await_confirm(sig.value)
        return ok, sig.value

    async def execute_clmm_sell_async(
        self,
        token_mint: str,
        keypair: Keypair,
        sell_pct: int = 100,
        slippage_pct: int = 5,
        fee_micro_lamports: int = 1_000_000,
        pool_id: Optional[str] = None,
        return_instructions: bool = False,
    ) -> Tuple[bool, str]:

        pool_id = pool_id or await self.core.find_pool_by_mint(token_mint)
        if pool_id is None:
            raise RuntimeError("no CLMM pool found for mint")

        keys = await self.core.async_fetch_pool_keys(pool_id)
        if keys is None:
            raise RuntimeError("decode failed")

        if Pubkey.from_string(token_mint) != keys.mint_b:
            raise RuntimeError("sell helper assumes token is mintB (WSOL-token pools)")

        bal_resp = await self.client.get_token_accounts_by_owner_json_parsed(
            keypair.pubkey(), TokenAccountOpts(mint=Pubkey.from_string(token_mint)), Processed
        )
        if not bal_resp.value:
            raise RuntimeError("no balance")

        mint_info = await self.client.get_account_info_json_parsed(
            Pubkey.from_string(token_mint),
            commitment=Processed
        )
        if not mint_info:
            print("Error: Failed to fetch mint info (tried to fetch token decimals).")
            return
        dec_base = mint_info.value.data.parsed['info']['decimals']

        ui_bal = float(bal_resp.value[0].account.data.parsed["info"]["tokenAmount"]["uiAmount"] or 0)
        if ui_bal <= 0:
            raise RuntimeError("no balance")

        amount_tokens = ui_bal * sell_pct / 100
        lamports_in   = int(amount_tokens * 10 ** dec_base)

        estimated_out_lamports = await self.estimate_clmm_output_with_decimals(
            keys, keys.mint_b, lamports_in, dec_base
        )
        print(f"CLMM estimated output (lamports): {estimated_out_lamports}")
        expected_sol = estimated_out_lamports / SOL_DECIMALS
        min_lam_out = int(expected_sol * (1 - slippage_pct/100) * SOL_DECIMALS)

        print(f"Expected SOL: {expected_sol}, Min LAM: {min_lam_out}")
        extra_accounts: list[Pubkey] = [self.core._derive_ex_bitmap(keys.id)]

        tick_spacing, tick_current = await self.core.async_fetch_pool_tickinfo(pool_id)
        tick_arrays = await self.ticks.get_tick_arrays(
            pool_id, tick_current, tick_spacing,
        )
        extra_accounts.extend(tick_arrays)

        resp = await self.client.get_token_accounts_by_owner(
            keypair.pubkey(), TokenAccountOpts(mint=keys.mint_b), Processed
        )
        if not resp.value:
            raise RuntimeError("no token balance for sell")
        user_in_ata = resp.value[0].pubkey

        temp_wsol, wrap_ixs = await self._wrap_sol_temp(0, keypair.pubkey())

        ixs: list = [
            *wrap_ixs,
        ]

        if not return_instructions:
            ixs.append(set_compute_unit_limit(COMPUTE_UNITS))
            ixs.append(set_compute_unit_price(fee_micro_lamports))

        swap_ix = self.core.create_swap_instruction_base_in(
            keys             = keys,
            owner            = keypair.pubkey(),
            user_in_ata      = user_in_ata,
            user_out_ata     = temp_wsol,
            input_mint       = keys.mint_b,
            amount_in        = lamports_in,
            min_amount_out   = min_lam_out,
            extra_accounts   = extra_accounts,
        )
        close_wsol_ix = close_account(
            CloseAccountParams(TOKEN_PROGRAM_ID, temp_wsol,
                               keypair.pubkey(), keypair.pubkey())
        )

        ixs.extend([swap_ix, close_wsol_ix])

        if return_instructions:
            return ixs

        bh = (await self.client.get_latest_blockhash()).value.blockhash
        msg = MessageV0.try_compile(keypair.pubkey(), ixs, [], bh)
        sig = await self.client.send_transaction(
            VersionedTransaction(msg, [keypair]),
            opts=TxOpts(skip_preflight=True, max_retries=0),
        )
        ok = await self._await_confirm(sig.value)
        return ok, sig.value

    async def close(self):
        await self.client.close()