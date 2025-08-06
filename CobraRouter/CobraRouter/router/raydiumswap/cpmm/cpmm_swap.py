# cpmm_swap.py
import os, base64, asyncio, traceback
from typing import  Tuple

from solana.rpc.types import (
    TokenAccountOpts,
    TxOpts,
)
from solana.rpc.commitment import Processed, Confirmed
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair # type: ignore
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price # type: ignore
from solders.system_program import CreateAccountWithSeedParams, create_account_with_seed
from solders.transaction import VersionedTransaction # type: ignore
from solders.message import MessageV0 # type: ignore
from spl.token.instructions import (
    create_associated_token_account,
    get_associated_token_address,
    initialize_account,
    CloseAccountParams, close_account, InitializeAccountParams
)

try: from cpmm_core import RaydiumCpmmCore, WSOL_MINT
except: from .cpmm_core import RaydiumCpmmCore, WSOL_MINT

RENT_EXEMPT     = 2039280
ACCOUNT_SIZE    = 165
SOL_DECIMALS    = 1e9
COMPUTE_UNITS   = 150_000
TOKEN_PROGRAM   = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

class RaydiumCpmmSwap:
    def __init__(self, client: AsyncClient):
        self.client  = client
        self.core    = RaydiumCpmmCore(client)

    async def _mint_owner(self, mint: Pubkey) -> Pubkey:
        try:
            info = await self.client.get_account_info(mint, commitment=Processed)
            if info.value is None:
                raise RuntimeError("mint account missing")
            return info.value.owner
        except Exception as e:
            traceback.print_exc()
            print(f"Failed to get token program id: {e}")
            return TOKEN_PROGRAM

    @staticmethod
    def convert_sol_to_tokens(sol: float, r_base: float, r_quote: float, fee_pct=0.25) -> float:
        eff = sol * (1 - fee_pct / 100)
        k   = r_base * r_quote
        new_base = k / (r_quote + eff)
        return round(r_base - new_base, 9)

    @staticmethod
    def convert_tokens_to_sol(tokens: float, r_base: float, r_quote: float, fee_pct=0.25) -> float:
        eff   = tokens * (1 - fee_pct / 100)
        k     = r_base * r_quote
        new_q = k / (r_base + eff)
        return round(r_quote - new_q, 9)

    async def execute_cpmm_buy_async(
        self,
        token_mint: str,
        sol_amount: float,
        keypair: Keypair,
        slippage_pct: float = 5,
        fee_micro_lamports: int = 1_000_000,
        pool_id: str | Pubkey | None = None,
        return_instructions: bool = False,
    ) -> Tuple[bool, str]:
        
        sol_lamports = int(sol_amount * SOL_DECIMALS)
        if pool_id is None:
            pool = await self.core.find_cpmm_pools_by_mint(token_mint)
            if not pool:
                raise RuntimeError("no CPMM pool found for mint")
            pool_id = pool

        pool_id = pool_id if isinstance(pool_id, Pubkey) else Pubkey.from_string(pool_id)

        keys = await self.core.async_fetch_pool_keys(pool_id)
        if keys is None:
            raise RuntimeError("cannot decode pool")
        reserves = await self.core.async_get_pool_reserves(keys)

        if keys.mint_a == WSOL_MINT:                 
            input_vault  = keys.vault_a              
            output_vault = keys.vault_b              
            input_prog   = keys.mint_prog_a
            output_prog  = keys.mint_prog_b
            input_mint   = keys.mint_a              
            output_mint  = keys.mint_b
            out_dec      = keys.decimals_b
            token_reserve, sol_reserve = reserves[1], reserves[0]
        elif keys.mint_b == WSOL_MINT:
            input_vault  = keys.vault_b
            output_vault = keys.vault_a
            input_prog   = keys.mint_prog_b
            output_prog  = keys.mint_prog_a
            input_mint   = keys.mint_b
            output_mint  = keys.mint_a
            out_dec      = keys.decimals_a
            token_reserve, sol_reserve = reserves[0], reserves[1]
        else:                                        
            raise RuntimeError("buy path only supports pools where WSOL is mintA")

        expected = self.convert_sol_to_tokens(sol_lamports / SOL_DECIMALS, token_reserve, sol_reserve)
        min_out  = int(expected * (1 - slippage_pct/100) * 10**out_dec)

        user_token_mint = Pubkey.from_string(token_mint)
        resp = await self.client.get_token_accounts_by_owner(
            keypair.pubkey(),
            TokenAccountOpts(mint=user_token_mint),
            Processed,
        )
        if resp.value:
            user_out_ata = resp.value[0].pubkey
            create_out_ata_ix = None
        else:
            token_program_id = await self._mint_owner(user_token_mint)
            user_out_ata = get_associated_token_address(keypair.pubkey(), user_token_mint, token_program_id=token_program_id)
            create_out_ata_ix = create_associated_token_account(
                keypair.pubkey(), keypair.pubkey(), user_token_mint, token_program_id=token_program_id
            )

        seed = base64.urlsafe_b64encode(os.urandom(12)).decode("utf-8")
        temp_wsol = Pubkey.create_with_seed(keypair.pubkey(), seed, TOKEN_PROGRAM)

        create_wsol_ix = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey = keypair.pubkey(),
                to_pubkey   = temp_wsol,
                base        = keypair.pubkey(),
                seed        = seed,
                lamports    = RENT_EXEMPT + sol_lamports,
                space       = ACCOUNT_SIZE,
                owner       = TOKEN_PROGRAM,
            )
        )
        init_wsol_ix = initialize_account(
            InitializeAccountParams(
                program_id = TOKEN_PROGRAM,
                account    = temp_wsol,
                mint       = WSOL_MINT,
                owner      = keypair.pubkey(),
            )
        )

        swap_ix = self.core.create_swap_instruction_base_in(
                    amount_in         = sol_lamports,
                    min_amount_out    = min_out,
                    user_input_ata    = temp_wsol,
                    user_output_ata   = user_out_ata,
                    input_vault       = input_vault,
                    output_vault      = output_vault,
                    input_prog        = input_prog,
                    output_prog       = output_prog,
                    input_mint        = input_mint,
                    output_mint       = output_mint,
                    keys              = keys,
                    owner             = keypair.pubkey(),
        )

        close_wsol_ix = close_account(
            CloseAccountParams(
                program_id = TOKEN_PROGRAM,
                account    = temp_wsol,
                dest       = keypair.pubkey(),
                owner      = keypair.pubkey(),
            )
        )

        if not return_instructions:
            ixs = [
                set_compute_unit_limit(COMPUTE_UNITS),
                set_compute_unit_price(fee_micro_lamports),
            ]
        else:
            ixs = []

        ixs.append(create_wsol_ix)
        ixs.append(init_wsol_ix)


        if create_out_ata_ix:
            ixs.append(create_out_ata_ix)
        ixs.extend([swap_ix, close_wsol_ix])

        if return_instructions:
            return ixs

        bh = (await self.client.get_latest_blockhash()).value.blockhash
        msg = MessageV0.try_compile(keypair.pubkey(), ixs, [], bh)
        sig = await self.client.send_transaction(
            VersionedTransaction(msg, [keypair]),
            opts = TxOpts(skip_preflight=True, max_retries=0),
        )
        print(sig)
        ok = await self._await_confirm(sig.value)
        return ok, sig.value

    async def execute_cpmm_sell_async(
        self,
        token_mint: str,
        keypair: Keypair,
        sell_pct: float = 100,
        slippage_pct: float = 5,
        fee_micro_lamports: int = 1_000_000,
        pool_hint: str | None = None,
        return_instructions: bool = False,
    ) -> Tuple[bool, str]:

        pool_id = pool_hint or await self.core.find_cpmm_pools_by_mint(token_mint)
        if pool_id is None:
            raise RuntimeError("no CPMM pool found")

        keys = await self.core.async_fetch_pool_keys(pool_id)
        if keys is None:
            raise RuntimeError("decode failed")

        reserves = await self.core.async_get_pool_reserves(keys)

        if str(keys.mint_b) == token_mint:          # normal case (WSOL is mintA)
            input_vault  = keys.vault_b
            output_vault = keys.vault_a
            input_prog   = keys.mint_prog_b
            output_prog  = keys.mint_prog_a
            input_mint   = keys.mint_b
            output_mint  = keys.mint_a
            dec_in       = keys.decimals_b
            token_reserve, sol_reserve = reserves[1], reserves[0]
        elif str(keys.mint_a) == token_mint:        # rare: pool where WSOL is mintB
            input_vault  = keys.vault_a
            output_vault = keys.vault_b
            input_prog   = keys.mint_prog_a
            output_prog  = keys.mint_prog_b
            input_mint   = keys.mint_a
            output_mint  = keys.mint_b
            dec_in       = keys.decimals_a
            token_reserve, sol_reserve = reserves[0], reserves[1]
        else:
            raise RuntimeError("token not in pool")

        # ---------- user balance ----------------------------------------------
        bal_resp = await self.client.get_token_accounts_by_owner_json_parsed(
            keypair.pubkey(), TokenAccountOpts(mint=input_mint), Processed
        )
        if not bal_resp.value:
            raise RuntimeError("no balance")

        ui_bal = float(bal_resp.value[0].account.data.parsed["info"]["tokenAmount"]["uiAmount"] or 0)
        amount_tokens = ui_bal * sell_pct / 100
        lamports_in   = int(amount_tokens * 10 ** dec_in)

        expected_sol  = self.convert_tokens_to_sol(amount_tokens, token_reserve, sol_reserve)
        min_lam_out   = int(expected_sol * (1 - slippage_pct / 100) * SOL_DECIMALS)

        user_in_ata = bal_resp.value[0].pubkey

        # ---------- temp WSOL account to receive ------------------------------
        seed = base64.urlsafe_b64encode(os.urandom(12)).decode()
        temp_wsol = Pubkey.create_with_seed(keypair.pubkey(), seed, TOKEN_PROGRAM)

        create_wsol_ix = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=temp_wsol,
                base=keypair.pubkey(),
                seed=seed,
                lamports=RENT_EXEMPT,
                space=ACCOUNT_SIZE,
                owner=TOKEN_PROGRAM,
            )
        )
        init_wsol_ix = initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM,
                account=temp_wsol,
                mint=WSOL_MINT,
                owner=keypair.pubkey(),
            )
        )

        swap_ix = self.core.create_swap_instruction_base_in(
            amount_in       = lamports_in,
            min_amount_out  = min_lam_out,
            user_input_ata  = user_in_ata,
            user_output_ata = temp_wsol,
            input_vault     = input_vault,
            output_vault    = output_vault,
            input_prog      = input_prog,
            output_prog     = output_prog,
            input_mint      = input_mint,
            output_mint     = output_mint,
            keys            = keys,
            owner           = keypair.pubkey(),
        )

        close_wsol_ix = close_account(
            CloseAccountParams(
                program_id=TOKEN_PROGRAM,
                account=temp_wsol,
                dest=keypair.pubkey(),
                owner=keypair.pubkey(),
            )
        )

        if not return_instructions:
            ixs = [
                set_compute_unit_limit(COMPUTE_UNITS),
                set_compute_unit_price(fee_micro_lamports),
            ]
        else:
            ixs = []
        
        ixs.append(create_wsol_ix)
        ixs.append(init_wsol_ix)
        ixs.append(swap_ix)
        ixs.append(close_wsol_ix)

        if return_instructions:
            return ixs

        bh  = (await self.client.get_latest_blockhash()).value.blockhash
        msg = MessageV0.try_compile(keypair.pubkey(), ixs, [], bh)
        sig = await self.client.send_transaction(
            VersionedTransaction(msg, [keypair]),
            opts=TxOpts(skip_preflight=True, max_retries=0),
        )
        print(sig)
        ok = await self._await_confirm(sig.value)
        return ok, sig.value

    async def _await_confirm(self, sig: str, tries=3, delay=3):
        for _ in range(tries):
            res = await self.client.get_transaction(sig, commitment=Confirmed, max_supported_transaction_version=0)
            if res.value and res.value.transaction.meta.err is None:
                return True
            await asyncio.sleep(delay)
        return False

    async def close(self):
        await self.client.close()