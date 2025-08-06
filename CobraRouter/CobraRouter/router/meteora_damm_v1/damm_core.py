from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair # type: ignore
import asyncio
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import DataSliceOpts, MemcmpOpts
import traceback
from construct import Struct as cStruct, Int8ul, Int64ul, Bytes
from solana.rpc.commitment import Processed, Confirmed
from spl.token.instructions import get_associated_token_address
from solders.instruction import Instruction, AccountMeta # type: ignore
import solana.exceptions
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
DAMM_V1_PROGRAM_ID = Pubkey.from_string("Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB")
VAULT_PROGRAM_ID = Pubkey.from_string("24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi")
VAULT_BASE_ID = Pubkey.from_string("HWzXGcGHy4tcpYfaRDCyLNzXqBTv3E6BttpCH2vJxArv")
WSOL_LP_MINT = Pubkey.from_string("FZN7QZ8ZUUAxMPfxYEYkH3cXUASzH8EqA6B4tyCL8f1j")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
PUBKEY = Bytes(32)

DammV1PoolState = cStruct(
    "lp_mint" / PUBKEY,
    "token_a_mint" / PUBKEY,
    "token_b_mint" / PUBKEY,
    "a_vault" / PUBKEY,
    "b_vault" / PUBKEY,
    "a_vault_lp" / PUBKEY,
    "b_vault_lp" / PUBKEY,
    "a_vault_lp_bump" / Int8ul,
    "enabled" / Int8ul,
    "protocol_token_a_fee" / PUBKEY,
    "protocol_token_b_fee" / PUBKEY,
    "fee_last_updated_at" / Int64ul,
)

class DAMM1Core:
    def __init__(self, client: AsyncClient):
        self.client = client

    async def build_swap_instruction(
        self, 
        action: str, 
        mint: str | Pubkey, 
        state: dict, 
        amount_in: int, 
        temp_wsol: Pubkey,
        keypair: Keypair,
        token_program_id: Pubkey = TOKEN_PROGRAM_ID,
    ) -> Instruction:
        """
           #1 Pool
           #2 User Source Token
           #3 User Destination Token
           #4 A Vault
           #5 B Vault
           #6 A Token Vault
           #7 B Token Vault
           #8 A Vault LP Mint
           #9 B Vault LP Mint
           #10 A Vault LP
           #11 B Vault LP
           #12 Protocol Token Fee
           #13 User
           #14 Vault Program
           #15 Token Program
        """

        mint = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)

        a_token_vault = await self.derive_token_vault_address(Pubkey.from_string(state["a_vault"]))
        b_token_vault = await self.derive_token_vault_address(Pubkey.from_string(state["b_vault"]))
        a_vault_lp_mint = await self.derive_lp_mint_address(Pubkey.from_string(state["a_vault"]))

        if action == "buy":
            input_token_account = temp_wsol
            output_token_account = get_associated_token_address(keypair.pubkey(), mint)
            protocol_token_fee = Pubkey.from_string(state["protocol_token_b_fee"])
        else:
            input_token_account = get_associated_token_address(keypair.pubkey(), mint)
            output_token_account = temp_wsol
            protocol_token_fee = Pubkey.from_string(state["protocol_token_a_fee"])
        
        accounts = [
            AccountMeta(pubkey=state["pool"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=input_token_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=output_token_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=Pubkey.from_string(state["a_vault"]), is_signer=False, is_writable=True),
            AccountMeta(pubkey=Pubkey.from_string(state["b_vault"]), is_signer=False, is_writable=True),
            AccountMeta(pubkey=a_token_vault, is_signer=False, is_writable=True),
            AccountMeta(pubkey=b_token_vault, is_signer=False, is_writable=True),
            AccountMeta(pubkey=a_vault_lp_mint, is_signer=False, is_writable=True),
            AccountMeta(pubkey=WSOL_LP_MINT, is_signer=False, is_writable=True),
            AccountMeta(pubkey=Pubkey.from_string(state["a_vault_lp"]), is_signer=False, is_writable=True),
            AccountMeta(pubkey=Pubkey.from_string(state["b_vault_lp"]), is_signer=False, is_writable=True),
            AccountMeta(pubkey=protocol_token_fee, is_signer=False, is_writable=True),
            AccountMeta(pubkey=keypair.pubkey(), is_signer=True, is_writable=True),
            AccountMeta(pubkey=VAULT_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=token_program_id, is_signer=False, is_writable=False),
        ]
        
        discriminator = bytes([248, 198, 158, 145, 225, 117, 135, 200])

        minimum_amount_out = 0
        amount_in_bytes = amount_in.to_bytes(8, 'little')
        minimum_amount_out_bytes = minimum_amount_out.to_bytes(8, 'little')
        
        instruction_data = discriminator + amount_in_bytes + minimum_amount_out_bytes
        
        return Instruction(
            program_id=DAMM_V1_PROGRAM_ID,
            accounts=accounts,
            data=instruction_data
        )

    def convert_pool_keys(self, container):
        return {
            "lp_mint": str(Pubkey.from_bytes(container.lp_mint)),
            "token_a_mint": str(Pubkey.from_bytes(container.token_a_mint)),
            "token_b_mint": str(Pubkey.from_bytes(container.token_b_mint)),
            "a_vault": str(Pubkey.from_bytes(container.a_vault)),
            "b_vault": str(Pubkey.from_bytes(container.b_vault)),
            "a_vault_lp": str(Pubkey.from_bytes(container.a_vault_lp)),
            "b_vault_lp": str(Pubkey.from_bytes(container.b_vault_lp)),
            "a_vault_lp_bump": container.a_vault_lp_bump,
            "enabled": container.enabled,
            "protocol_token_a_fee": str(Pubkey.from_bytes(container.protocol_token_a_fee)),
            "protocol_token_b_fee": str(Pubkey.from_bytes(container.protocol_token_b_fee)),
            "fee_last_updated_at": container.fee_last_updated_at,
        }

    async def get_price(
        self,
        mint: str | Pubkey,
        *,
        pool_addr: str | Pubkey | None = None,
    ) -> dict | None:
        """
        Fetch the current marginal price for a token in a DAMM v1 constant
        product pool expressed both ways:

            * price           ––  SOL per 1 token
            * price_per_sol   ––  tokens per 1 SOL

        Parameters
        ----------
        mint : str | Pubkey
            The token mint whose price you want.
        pool_addr : str | Pubkey | None, default None
            Optionally pass the pool address you already know; if omitted the
            helper `find_pool_by_mint` is called.

        Returns
        -------
        dict | None
            {
                "pool": <Pubkey>,
                "token_reserve": <float>,
                "sol_reserve":   <float>,
                "price":         <float>,   # SOL ➜ 1 token
                "price_per_sol": <float>,   # token ➜ 1 SOL
            }
            or **None** when the pool cannot be found / has zero liquidity.
        """
        try:
            # ------------------------------------------------------------
            # 0. Resolve arguments
            # ------------------------------------------------------------
            mint_pk: Pubkey = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)

            if pool_addr is None:
                pool_addr = await self.find_pool_by_mint(mint_pk)
                if pool_addr is None:
                    print("get_price(): no suitable pool found")
                    return None

            pool_pk: Pubkey = pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)

            # ------------------------------------------------------------
            # 1. Load on‑chain pool state
            # ------------------------------------------------------------
            state = await self.fetch_pool_state(pool_pk)
            if state is None:
                print("get_price(): failed to load pool state")
                return None

            a_mint = Pubkey.from_string(state["token_a_mint"])
            b_mint = Pubkey.from_string(state["token_b_mint"])

            # ------------------------------------------------------------
            # 2. Identify which side is SOL and fetch reserves
            #    We read reserves from the *LP token* accounts exactly like
            #    `find_pool_by_mint` already does.
            # ------------------------------------------------------------
            a_lp_vault = Pubkey.from_string(state["a_vault_lp"])
            b_lp_vault = Pubkey.from_string(state["b_vault_lp"])

            reserve_a, reserve_b = await self.async_get_pool_reserves(a_lp_vault, b_lp_vault)
            if reserve_a == 0 or reserve_b == 0:
                print("get_price(): pool has no liquidity")
                return None

            # ------------------------------------------------------------
            # 3. Compute marginal price (constant‑product invariant)
            # ------------------------------------------------------------
            if a_mint == WSOL_MINT:
                sol_reserve   = reserve_a
                token_reserve = reserve_b
            elif b_mint == WSOL_MINT:
                sol_reserve   = reserve_b
                token_reserve = reserve_a
            else:
                # The helper is intended for SOL/token pools only
                print("get_price(): neither side is wSOL – unsupported")
                return None

            price         = sol_reserve / token_reserve          # SOL ÷ token (inverse)

            return {
                "pool":          str(pool_pk),
                "token_reserve": token_reserve,
                "sol_reserve":   sol_reserve,
                "price":         price,
            }

        except Exception as exc:
            print(f"get_price() error: {exc}")
            traceback.print_exc()
            return None

    async def derive_vault_address(self, mint: str | Pubkey) -> Pubkey:
        mint = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)
        seeds = [b"vault", mint.__bytes__(), VAULT_BASE_ID.__bytes__()]
        pool_pda, _ = Pubkey.find_program_address(seeds, VAULT_PROGRAM_ID)
        return pool_pda

    async def derive_token_vault_address(self, vault: str | Pubkey) -> Pubkey:
        vault = vault if isinstance(vault, Pubkey) else Pubkey.from_string(vault)
        seeds = [b"token_vault", vault.__bytes__()]
        pool_pda, _ = Pubkey.find_program_address(seeds, VAULT_PROGRAM_ID)
        return pool_pda

    async def derive_lp_mint_address(self, vault: str | Pubkey) -> Pubkey:
        vault = vault if isinstance(vault, Pubkey) else Pubkey.from_string(vault)
        seeds = [b"lp_mint", vault.__bytes__()]
        pool_pda, _ = Pubkey.find_program_address(seeds, VAULT_PROGRAM_ID)
        return pool_pda

    async def async_get_pool_reserves(self, vault_a: Pubkey, vault_b: Pubkey):
        """
        Fetch vault reserves for DAMM v2 pool.
        Returns: (reserve_a, reserve_b) in decimal
        """
        try:
            infos = await self.client.get_multiple_accounts_json_parsed(
                [vault_a, vault_b], commitment=Processed
            )
            ui_a = infos.value[0].data.parsed["info"]["tokenAmount"]["uiAmount"] # type: ignore
            ui_b = infos.value[1].data.parsed["info"]["tokenAmount"]["uiAmount"] # type: ignore
            return float(ui_a or 0), float(ui_b or 0) # type: ignore
        except Exception as e:
            print(f"Error fetching vault reserves: {e}")
            traceback.print_exc()
            return 0.0, 0.0

    async def fetch_pool_state(self, pool_addr: str | Pubkey) -> dict | None:
        """
        Fetch the state of a pool.
        """
        try:
            pool_addr = pool_addr if isinstance(pool_addr, Pubkey) else Pubkey.from_string(pool_addr)
            resp = await self.client.get_account_info_json_parsed(pool_addr, commitment=Confirmed)
            if not resp or not resp.value or not resp.value.data:
                raise Exception("Invalid account response")

            raw_data = resp.value.data
            parsed = DammV1PoolState.parse(raw_data[8:]) # type: ignore

            pdict = self.convert_pool_keys(parsed)
            pdict["pool"] = pool_addr
            return pdict
        except Exception as e:
            print(f"Error in fetch_pool_state: {e}")
            traceback.print_exc()
            return None

    async def find_pool_by_mint(self, mint: str | Pubkey, sol_amount: float = 0.001, limit: int = 50) -> str | None:
        """
        Find the best pool for a given mint with sufficient liquidity.
        Returns:
            Pool address string or None if no suitable pool found
        """
        mint_str = str(mint) if isinstance(mint, Pubkey) else mint
        mint = mint if isinstance(mint, Pubkey) else Pubkey.from_string(mint)
        target_offset = 40
        found_pools = []
        best_pool = None
        try:
            resp = await self.client.get_program_accounts(
                DAMM_V1_PROGRAM_ID,
                commitment=Confirmed,
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
                    token_a_mint = Pubkey.from_string(pool_state["token_a_mint"])
                    token_b_mint = Pubkey.from_string(pool_state["token_b_mint"])

                    if token_b_mint != WSOL_MINT:
                        continue
                    token_a_vault = Pubkey.from_string(pool_state["a_vault_lp"])
                    token_b_vault = Pubkey.from_string(pool_state["b_vault_lp"])
                    print(f"pool_addr: {pool_addr}")
                    
                    reserve_a, reserve_b = await self.async_get_pool_reserves(token_a_vault, token_b_vault)
                    
                    if reserve_a <= 0 or reserve_b <= 0:
                        continue
                    
                    if token_a_mint == mint and token_b_mint == WSOL_MINT:
                        token_reserve = reserve_a
                        sol_reserve = reserve_b
                        price_per_sol = token_reserve / sol_reserve if sol_reserve > 0 else 0
                        required_tokens = sol_amount * price_per_sol
                        
                    elif token_b_mint == mint and token_a_mint == WSOL_MINT:
                        sol_reserve = reserve_a
                        token_reserve = reserve_b
                        price_per_sol = token_reserve / sol_reserve if sol_reserve > 0 else 0
                        required_tokens = sol_amount * price_per_sol
                    else:
                        continue
                    
                    if (
                        (required_tokens > 0 and price_per_sol > 0.0)
                        and token_reserve > required_tokens
                        and sol_reserve > sol_amount
                    ):
                        best_pool = pool_addr
                        break
                    else:
                        print(f"❌ Insufficient liquidity (need {required_tokens:,.6f} tokens, {sol_amount} SOL)")
                        
                except Exception as e:
                    print(f"Error processing pool {pool_addr}: {e}")
                    continue

            return best_pool
        except solana.exceptions.SolanaRpcException as e:
            return None
        except Exception as e:
            print(f"Error in pool scanning: {e}")
            traceback.print_exc()
            return None