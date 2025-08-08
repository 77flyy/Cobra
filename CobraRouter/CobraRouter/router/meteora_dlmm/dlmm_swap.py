import asyncio, base64, os, traceback, sys
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from solana.rpc.commitment import Processed, Confirmed
from solders.system_program import CreateAccountWithSeedParams, create_account_with_seed
from spl.token.instructions import create_associated_token_account, initialize_account, InitializeAccountParams, close_account, CloseAccountParams, get_associated_token_address
from solders.transaction import Transaction, VersionedTransaction # type: ignore
from solders.message import MessageV0 # type: ignore
from solana.rpc.types import TxOpts, TokenAccountOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price # type: ignore
import logging
try: from dlmm_bin import DLMMBin
except: from .dlmm_bin import DLMMBin

try: from dlmm_core import DLMMCore, TOKEN_PROGRAM_ID, _gather_exists
except: from .dlmm_core import DLMMCore, TOKEN_PROGRAM_ID, _gather_exists

RENT_EXEMPT     = 2039280
ACCOUNT_SIZE    = 165
SOL_DECIMALS    = 1e9
COMPUTE_UNITS   = 250_000

def compute_unit_price_from_total_fee(
    total_lams: int,
    compute_units: int = 120_000
) -> int:
    lamports_per_cu = total_lams / float(compute_units)
    micro_lamports_per_cu = lamports_per_cu * 1_000_000
    return int(micro_lamports_per_cu)

class MeteoraDLMM:
    def __init__(self, async_client: AsyncClient):
        self.client = async_client
        self.core = DLMMCore(self.client)
        self.dlmm_bin = DLMMBin()

    async def _mint_owner(self, mint: Pubkey) -> Pubkey:
        try:
            info = await self.client.get_account_info(mint, commitment=Processed)
            if info.value is None:
                raise RuntimeError("mint account missing")
            return info.value.owner
        except Exception as e:
            traceback.print_exc()
            logging.info(f"Failed to get token program id: {e}")
            return TOKEN_PROGRAM_ID
        
    async def buy(
        self,
        mint: str | Pubkey,
        state: dict,
        amount_in: int,
        keypair: Keypair,
        fee_sol: float = 0.00001,
        return_instructions: bool = False,
    ) -> Transaction:
        """
        Returns:
            True if successful, False otherwise
        """
        ixs = []
        try:
            if not return_instructions:
                lamports_fee = int(fee_sol * 1e9)
                micro_lamports = compute_unit_price_from_total_fee(
                    lamports_fee,
                    compute_units=COMPUTE_UNITS
                )

                ixs.append(set_compute_unit_limit(COMPUTE_UNITS))
                ixs.append(set_compute_unit_price(micro_lamports))

            base_mint = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)
            resp = await self.client.get_token_accounts_by_owner(keypair.pubkey(), TokenAccountOpts(mint=base_mint), Processed)
            if resp.value:
                user_ata = resp.value[0].pubkey
                create_ata_ix = None
            else:
                user_ata = get_associated_token_address(keypair.pubkey(), base_mint)
                create_ata_ix = create_associated_token_account(
                    keypair.pubkey(), keypair.pubkey(), base_mint,
                    token_program_id=await self._mint_owner(base_mint)
                )
                
            seed = base64.urlsafe_b64encode(os.urandom(12)).decode()
            temp_wsol = Pubkey.create_with_seed(keypair.pubkey(), seed, TOKEN_PROGRAM_ID)
            create_w_ix = create_account_with_seed(CreateAccountWithSeedParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=temp_wsol,
                base=keypair.pubkey(),
                seed=seed,
                lamports=RENT_EXEMPT + amount_in,
                space=ACCOUNT_SIZE,
                owner=TOKEN_PROGRAM_ID,
            ))
            ixs.append(create_w_ix)

            init_w_ix = initialize_account(
                InitializeAccountParams(
                    program_id=TOKEN_PROGRAM_ID,
                    account=temp_wsol,
                    mint=Pubkey.from_string("So11111111111111111111111111111111111111112"),
                    owner=keypair.pubkey(),
                )
            )
            ixs.append(init_w_ix)

            if create_ata_ix:
                ixs.append(create_ata_ix)

            bins = await DLMMBin.find_adjacent_bin_arrays(self.client, state["active_id"],
                                Pubkey.from_string(state["pool"]))

            token_program_id = await self._mint_owner(base_mint)
            swap_ix = await self.core.build_swap_instruction("buy", state, user_ata, temp_wsol, amount_in, bins, keypair.pubkey(), token_program_id=token_program_id)
            ixs.append(swap_ix)

            ixs.append(close_account(CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=temp_wsol,
                dest=keypair.pubkey(),
                owner=keypair.pubkey(),
            )))

            if return_instructions:
                return ixs

            blockhash = (await self.client.get_latest_blockhash()).value.blockhash
            msg      = MessageV0.try_compile(keypair.pubkey(), ixs, [], blockhash)
            tx       = VersionedTransaction(msg, [keypair])
            result = await self.client.send_transaction(tx, opts=TxOpts(skip_preflight=True, max_retries=0))
            logging.info(f"Debug DLMM | Swap transaction sent: {result.value}")
            ok = await self._await_confirm(result.value)
            logging.info(f"Debug DLMM | Swap transaction confirmed: {ok}")
            return (result.value, ok)
        except Exception as e:
            logging.info(f"Error: {e}")
            traceback.print_exc()
            return None

    async def sell(
        self,
        mint: str | Pubkey,
        state: dict,
        percentage: float,
        keypair: Keypair,
        fee_sol: float = 0.00001,
        return_instructions: bool = False,
    ) -> Transaction:
        """
        Returns:
            True if successful, False otherwise
        """
        ixs = []
        try:
            if not return_instructions:
                lamports_fee = int(fee_sol * 1e9)
                micro_lamports = compute_unit_price_from_total_fee(
                    lamports_fee,
                    compute_units=COMPUTE_UNITS
                )

                ixs.append(set_compute_unit_limit(COMPUTE_UNITS))
                ixs.append(set_compute_unit_price(micro_lamports))

            base_mint = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)
            if percentage is None or percentage <= 0:
                raise ValueError("Percentage can't be 0 and is required for sell actions")

            if percentage > 100:
                raise ValueError("Percentage can't be greater than 100")

            mint_info = await self.client.get_account_info_json_parsed(
                Pubkey.from_string(base_mint) if isinstance(base_mint, str) else base_mint,
                commitment=Processed
            )
            if not mint_info:
                logging.info("Error: Failed to fetch mint info (tried to fetch token decimals).")
                return
            dec_base = mint_info.value.data.parsed['info']['decimals']

            await asyncio.sleep(0.1) # sleeper

            token_pk = Pubkey.from_string(base_mint) if isinstance(base_mint, str) else base_mint
            bal_resp = await self.client.get_token_accounts_by_owner_json_parsed(
                keypair.pubkey(), TokenAccountOpts(mint=token_pk), Processed
            )
            if not bal_resp.value:
                raise RuntimeError("no balance")

            user_ata = bal_resp.value[0].pubkey
            token_balance = float(bal_resp.value[0].account.data.parsed["info"]["tokenAmount"]["uiAmount"] or 0)
            
            if token_balance <= 0:
                raise RuntimeError("insufficient token balance")

            sell_amount = token_balance * (percentage / 100)
            if sell_amount <= 0:
                raise RuntimeError("sell amount too small")
            
            tokens_in = int(sell_amount * 10**dec_base)
            logging.info(f"Selling {tokens_in} tokens")

            seed = base64.urlsafe_b64encode(os.urandom(12)).decode()
            temp_wsol = Pubkey.create_with_seed(keypair.pubkey(), seed, TOKEN_PROGRAM_ID)
            create_w_ix = create_account_with_seed(CreateAccountWithSeedParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=temp_wsol,
                base=keypair.pubkey(),
                seed=seed,
                lamports=RENT_EXEMPT,
                space=ACCOUNT_SIZE,
                owner=TOKEN_PROGRAM_ID,
            ))
            ixs.append(create_w_ix)

            init_w_ix = initialize_account(
                InitializeAccountParams(
                    program_id=TOKEN_PROGRAM_ID,
                    account=temp_wsol,
                    mint=Pubkey.from_string("So11111111111111111111111111111111111111112"),
                    owner=keypair.pubkey(),
                )
            )
            ixs.append(init_w_ix)

            bins = await DLMMBin.find_adjacent_bin_arrays(self.client, state["active_id"],
                                Pubkey.from_string(state["pool"]))

            token_program_id = await self._mint_owner(base_mint)
            swap_ix = await self.core.build_swap_instruction("sell", state, user_ata, temp_wsol, tokens_in, bins, keypair.pubkey(), token_program_id=token_program_id)
            ixs.append(swap_ix)

            ixs.append(close_account(CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=temp_wsol,
                dest=keypair.pubkey(),
                owner=keypair.pubkey(),
            )))

            if return_instructions:
                return ixs

            blockhash = (await self.client.get_latest_blockhash()).value.blockhash
            msg      = MessageV0.try_compile(keypair.pubkey(), ixs, [], blockhash)
            tx       = VersionedTransaction(msg, [keypair])
            result = await self.client.send_transaction(tx, opts=TxOpts(skip_preflight=True, max_retries=0))
            logging.info(f"Debug DLMM | Swap transaction sent: {result.value}")
            
            ok = await self._await_confirm(result.value)
            logging.info(f"Debug DLMM | Swap transaction confirmed: {ok}")
            return (result.value, ok)
        except Exception as e:
            logging.info(f"Error: {e}")
            traceback.print_exc()
            return None

    async def _await_confirm(self, sig: str, tries=3, delay=2):
        for _ in range(tries):
            res = await self.client.get_transaction(sig, commitment=Confirmed, max_supported_transaction_version=0)
            if res.value and res.value.transaction.meta.err is None:
                return True
            await asyncio.sleep(delay)
        return False

    async def close(self):
        try:
            await self.client.close()
        except Exception as e:
            logging.info(f"Error: {e}")