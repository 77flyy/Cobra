# meteora_damm_v2/damm2_swap.py
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from solders.transaction import Transaction # type: ignore
from solders.instruction import Instruction, AccountMeta # type: ignore
from spl.token.instructions import get_associated_token_address
from solana.rpc.types import TxOpts, TokenAccountOpts
import traceback
import asyncio
import base64
import os
from solders.transaction import VersionedTransaction # type: ignore
from solders.message import MessageV0 # type: ignore
from spl.token.instructions import create_associated_token_account, initialize_account, InitializeAccountParams, close_account, CloseAccountParams, SyncNativeParams, sync_native
from solana.rpc.commitment import Processed
from solders.system_program import CreateAccountWithSeedParams, create_account_with_seed

try: from damm2_core import DAMM2Core, SwapParams, DAMM2SwapBuilder, TOKEN_PROGRAM_ID, WSOL_MINT;
except: from .damm2_core import DAMM2Core, SwapParams, DAMM2SwapBuilder, TOKEN_PROGRAM_ID, WSOL_MINT;

RENT_EXEMPT     = 2039280
ACCOUNT_SIZE    = 165
SOL_DECIMALS    = 1e9
COMPUTE_UNITS   = 150_000

class MeteoraDamm2:
    def __init__(self, async_client: AsyncClient):
        self.client = async_client
        self.core = DAMM2Core(self.client)
    
    async def _mint_owner(self, mint: Pubkey) -> Pubkey:
        try:
            info = await self.client.get_account_info(mint, commitment=Processed)
            if info.value is None:
                raise RuntimeError("mint account missing")
            return info.value.owner
        except Exception as e:
            traceback.print_exc()
            print(f"Failed to get token program id: {e}")
            return TOKEN_PROGRAM_ID
    
    async def normalize_mints(self, mint_a, mint_b):
        if str(mint_b) == str(WSOL_MINT):
            return (mint_a, mint_b)
        else:
            return (mint_b, mint_a)

    async def build_swap_params(self, state: dict, pool: str | Pubkey, base_mint: str | Pubkey, tokens_in: int, keypair: Keypair, minimum_amount_out: int = 0):
        token_a_program = await self._mint_owner(Pubkey.from_string(state["token_a_mint"]))
        token_b_program = await self._mint_owner(Pubkey.from_string(state["token_b_mint"]))
        print(f"Token A Program: {token_a_program}")
        print(f"Token B Program: {token_b_program}")
        swap_params = SwapParams(
            payer=keypair.pubkey(),
            pool=Pubkey.from_string(pool),
            base_mint=Pubkey.from_string(base_mint),
            wsol_mint=WSOL_MINT,
            amount_in=tokens_in,
            minimum_amount_out=minimum_amount_out,
            token_a_vault=Pubkey.from_string(state["token_a_vault"]),
            token_b_vault=Pubkey.from_string(state["token_b_vault"]),
            token_a_mint=Pubkey.from_string(state["token_a_mint"]),
            token_b_mint=Pubkey.from_string(state["token_b_mint"]),
            token_a_program=token_a_program,
            token_b_program=TOKEN_PROGRAM_ID,
        )
        return swap_params

    async def swap(self, action: str, pool: str | Pubkey, state: dict, keypair: Keypair, tokens_in: int = None, slippage: float = 0.5, percentage: float = None):
        """
        Execute a swap between two tokens using DAMM v2

        Args:
            action: "buy" or "sell"
            pool: Pool address
            state: Pool state
            tokens_in: Amount of input token to swap (in lamports)
            slippage: Slippage percentage for automatic minimum calculation
            percentage: Percentage of balance to sell
        
        Returns:
            Transaction signature or None if failed
        """
        try:
            minimum_amount_out = 0
            base_mint, wsol_mint = await self.normalize_mints(state["token_a_mint"], state["token_b_mint"])

            if action == "sell":
                if percentage is None or percentage <= 0:
                    raise ValueError("Percentage can't be 0 and is required for sell actions")

                if percentage > 100:
                    raise ValueError("Percentage can't be greater than 100")

                mint_info = await self.client.get_account_info_json_parsed(
                    Pubkey.from_string(base_mint) if isinstance(base_mint, str) else base_mint,
                    commitment=Processed
                )
                if not mint_info:
                    print("Error: Failed to fetch mint info (tried to fetch token decimals).")
                    return
                dec_base = mint_info.value.data.parsed['info']['decimals']

                await asyncio.sleep(0.1) # sleeper

                token_pk = Pubkey.from_string(base_mint) if isinstance(base_mint, str) else base_mint
                bal_resp = await self.client.get_token_accounts_by_owner_json_parsed(
                    keypair.pubkey(), TokenAccountOpts(mint=token_pk), Processed
                )
                if not bal_resp.value:
                    raise RuntimeError("no balance")

                token_balance = float(bal_resp.value[0].account.data.parsed["info"]["tokenAmount"]["uiAmount"] or 0)
                
                if token_balance <= 0:
                    raise RuntimeError("insufficient token balance")

                sell_amount = token_balance * (percentage / 100)
                if sell_amount <= 0:
                    raise RuntimeError("sell amount too small")
                
                tokens_in = int(sell_amount * 10**dec_base)
                print(f"Selling {tokens_in} tokens")

            elif action == "buy":
                if tokens_in is None or tokens_in <= 0:
                    raise ValueError("Tokens in can't be 0 and is required for buy actions")

            swap_params = await self.build_swap_params(state, pool, base_mint, wsol_mint, tokens_in, keypair, minimum_amount_out)

            if action == "buy":
                tx = await self.buy(swap_params, keypair=keypair)
            else:
                tx = await self.sell(swap_params, keypair=keypair)
            
            result = await self.client.send_transaction(tx, opts=TxOpts(skip_preflight=True, max_retries=0))
            print(f"Debug DAMM2 | Swap transaction sent: {result.value}")
            
            return result.value
            
        except Exception as e:
            traceback.print_exc()
            print(f"Error in DAMM2 swap: {e}")
            return None
    
    async def buy(
        self,
        params: SwapParams,
        keypair: Keypair,
        return_instructions: bool = False,
    ) -> Transaction | VersionedTransaction:
        """
        Returns:
            Signed transaction ready to be sent
        """
        ixs = []
        try:
            base_mint = params.base_mint if isinstance(params.base_mint, Pubkey) else Pubkey.from_string(params.base_mint)
            resp = await self.client.get_token_accounts_by_owner(keypair.pubkey(), TokenAccountOpts(mint=base_mint), Processed)
            if resp.value:
                create_ata_ix = None
            else:
                create_ata_ix = create_associated_token_account(
                    keypair.pubkey(), keypair.pubkey(), base_mint,
                    token_program_id=params.token_a_program
                )

            seed = base64.urlsafe_b64encode(os.urandom(12)).decode()
            temp_wsol = Pubkey.create_with_seed(keypair.pubkey(), seed, TOKEN_PROGRAM_ID)
            create_w_ix = create_account_with_seed(CreateAccountWithSeedParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=temp_wsol,
                base=keypair.pubkey(),
                seed=seed,
                lamports=RENT_EXEMPT + params.amount_in,
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

            ixs.append(sync_native(SyncNativeParams(program_id=TOKEN_PROGRAM_ID, account=temp_wsol)))

            builder = DAMM2SwapBuilder(self.client)
            swap_ix = await builder.build_swap_instruction("buy", params, temp_wsol)
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
            return tx
            
        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"Failed to create swap transaction: {e}")
    
    async def sell(
        self,
        params: SwapParams,
        keypair: Keypair,
        return_instructions: bool = False,
    ) -> Transaction | VersionedTransaction:
        """
        Returns:
            Signed transaction ready to be sent
        """
        ixs = []
        try:
            base_mint = params.base_mint if isinstance(params.base_mint, Pubkey) else Pubkey.from_string(params.base_mint)
            
            resp = await self.client.get_token_accounts_by_owner(keypair.pubkey(), TokenAccountOpts(mint=base_mint), Processed)
            if not resp.value:
                raise ValueError("No base token account found - cannot sell tokens you don't have")

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

            builder = DAMM2SwapBuilder(self.client)
            swap_ix = await builder.build_swap_instruction("sell", params, temp_wsol)
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
            msg = MessageV0.try_compile(keypair.pubkey(), ixs, [], blockhash)
            tx = VersionedTransaction(msg, [keypair])
            return tx
            
        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"Failed to create sell transaction: {e}")

    async def close(self):
        """Close the client connection"""
        await self.client.close()

__all__ = ["SwapParams", "DAMM2SwapBuilder", "create_swap_transaction"] 