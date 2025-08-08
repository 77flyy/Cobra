import asyncio
from solders.pubkey import Pubkey # type: ignore
from spl.token.instructions import burn, BurnParams, close_account, CloseAccountParams, get_associated_token_address, burn_checked, BurnCheckedParams
from spl.token.constants import TOKEN_PROGRAM_ID
from solders.transaction import VersionedTransaction # type: ignore
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair # type: ignore
from solders.message import MessageV0 # type: ignore
from solana.rpc.types import TokenAccountOpts
from solana.rpc.commitment import Processed
import logging
RENT_EXEMPT     = 2039280
SOL_DECIMALS    = 1e9
WSOL_MINT       = Pubkey.from_string("So11111111111111111111111111111111111111112")

class Cleaner:
    __slots__ = ()

    @staticmethod
    async def _check_exists(client: AsyncClient, account: Pubkey) -> bool:
        resp = await client.get_account_info(account, commitment=Processed)
        return resp is not None and resp.value is not None and resp.value.data is not None

    @staticmethod
    async def close_wsol(client: AsyncClient, payer: Keypair, wsol_accounts: list[Pubkey] | None = None):
        tx = []

        bal_resp = await client.get_token_accounts_by_owner_json_parsed(
            payer.pubkey(), TokenAccountOpts(mint=WSOL_MINT), Processed
        )
        if not bal_resp.value:
            raise RuntimeError("no balance")

        if not wsol_accounts:
            wsol_accounts = []
            for acc in bal_resp.value:
                wsol_accounts.append(acc.pubkey)

        for acc in wsol_accounts:
            tx.append(
                close_account(
                    CloseAccountParams(
                        program_id=TOKEN_PROGRAM_ID,
                        account=acc,
                        dest=payer.pubkey(),
                        owner=payer.pubkey(),
                        signers=[],
                    )
                )
            )
        blockhash = (await client.get_latest_blockhash()).value.blockhash
        sig = await client.send_transaction(VersionedTransaction(MessageV0.try_compile(payer.pubkey(), tx, [], blockhash), [payer]))
        logging.info(f"✅ Unwrapped + Closed: {sig}")

    @staticmethod
    async def close_token_accounts(client: AsyncClient, payer: Keypair, mint: Pubkey | str, to_burn: int = 1, decimals: int = 6):
        tx = []
        mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
        token_account = get_associated_token_address(payer.pubkey(), mint)

        if not await Cleaner._check_exists(client, token_account):
            raise RuntimeError("token account does not exist")

        if to_burn > 0:
            tx.append(burn_checked(
                BurnCheckedParams(
                    mint=mint,
                    account=token_account,
                    owner=payer.pubkey(),
                    signers=[],
                    program_id=TOKEN_PROGRAM_ID,
                    amount=to_burn,
                    decimals=decimals,
                )
            ))
        tx.append(close_account(CloseAccountParams(program_id=TOKEN_PROGRAM_ID, account=token_account, dest=payer.pubkey(), owner=payer.pubkey(), signers=[])))

        blockhash = (await client.get_latest_blockhash()).value.blockhash
        sig = await client.send_transaction(VersionedTransaction(MessageV0.try_compile(payer.pubkey(), tx, [], blockhash), [payer]))
        return (sig.value, True)