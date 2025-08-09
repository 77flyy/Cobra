from ast import Pass
import asyncio, aiohttp, logging, json, os, sys, time, collections, httpx, traceback, base64
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
try:
    from .meteoraDBC import MeteoraDBC
    from .pump_fun import PumpFun, check_has_migrated, get_associated_bonding_curve_address, find_migration_source, get_creator, find_pumpswap_pools
    from .raydiumswap.amm_v4 import RaydiumSwap
    from .PumpSwapAMM import PumpSwap, fetch_pool_state
    from .raydiumswap.cpmm.cpmm_swap import RaydiumCpmmSwap
    from .raydiumswap.launchlab.launchlab_swap import RaydiumLaunchpadSwap
    from .raydiumswap.clmm.clmm_swap import RaydiumClmmSwap
    from .raydiumswap.amm_v4.v4_amm_swap import RaydiumSwap as RaydiumSwapV4
    from .meteora_damm_v1.damm_swap import MeteoraDamm1
    from .meteora_damm_v2.damm2_swap import MeteoraDamm2
    from .meteora_dlmm.dlmm_swap import MeteoraDLMM
except:
    from meteoraDBC import MeteoraDBC
    from pump_fun import PumpFun, check_has_migrated, get_associated_bonding_curve_address, find_migration_source, get_creator, find_pumpswap_pools
    from raydiumswap.amm_v4 import RaydiumSwap
    from PumpSwapAMM import PumpSwap, fetch_pool_state
    from raydiumswap.cpmm.cpmm_swap import RaydiumCpmmSwap
    from raydiumswap.launchlab.launchlab_swap import RaydiumLaunchpadSwap
    from raydiumswap.clmm.clmm_swap import RaydiumClmmSwap
    from raydiumswap.amm_v4.v4_amm_swap import RaydiumSwap as RaydiumSwapV4
    from meteora_damm_v1.damm_swap import MeteoraDamm1
    from meteora_damm_v2.damm2_swap import MeteoraDamm2
    from meteora_dlmm.dlmm_swap import MeteoraDLMM    
    
from solana.rpc.commitment import Processed

try:
    from libutils import SUPPORTED_DEXES, ADDR_TO_DEX, WSOL_MINT
    from libutils.colors import *
except:
    from .libutils import SUPPORTED_DEXES, ADDR_TO_DEX, WSOL_MINT
    from .libutils.colors import *

async def _check_exists(client: AsyncClient, account: Pubkey) -> bool:
    resp = await client.get_account_info(account, commitment=Processed)
    return resp is not None and resp.value is not None and resp.value.data is not None

class Router:
    def __init__(self, ctx: AsyncClient, session: aiohttp.ClientSession):
        self.session = session
        self.async_client = ctx

        self.pump_fun = PumpFun(session=self.session, async_client=self.async_client)
        self.get_pump_fun_creator = get_creator
        self.raydiumswap = RaydiumSwap(async_client=self.async_client)
        self.cpmm_swap = RaydiumCpmmSwap(client=self.async_client)
        self.clmm_swap = RaydiumClmmSwap(client=self.async_client)
        self.launchlab_swap = RaydiumLaunchpadSwap(client=self.async_client)
        self.pump_swap = PumpSwap(async_client=self.async_client)
        self.pump_swap_fetch_state = fetch_pool_state
        self.meteora_dbc = MeteoraDBC(async_client=self.async_client)
        self.raydiumswap_v4 = RaydiumSwapV4(async_client=self.async_client)
        self.damm_v1 = MeteoraDamm1(async_client=self.async_client)
        self.damm_v2 = MeteoraDamm2(async_client=self.async_client)
        self.dlmm = MeteoraDLMM(async_client=self.async_client)
        self.local_cache = {}

    async def get_mint_authority(self, mint: str):
        """
        Get mint authority and mint info
        Returns:
            tuple: (update_authority, out_info)
                update_authority: str | None
                out_info: dict | None
        """
        try:
            mint_pk = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            mint_resp = await self.async_client.get_account_info_json_parsed(mint_pk, commitment=Processed)
            if not mint_resp or not mint_resp.value or not mint_resp.value.data:
                return (None, None)

            parsed = mint_resp.value.data.parsed
            info = parsed.get('info', {}) if parsed else {}
            freeze_authority = info.get('freezeAuthority')
            mint_authority = info.get('mintAuthority')
            decimals = info.get('decimals')
            supply = info.get('supply')

            try:
                METADATA_PROGRAM_ID = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
                seeds = [b"metadata", bytes(METADATA_PROGRAM_ID), bytes(mint_pk)]
                metadata_pda, _bump = Pubkey.find_program_address(seeds, METADATA_PROGRAM_ID)

                meta_resp = await self.async_client.get_account_info(metadata_pda, commitment=Processed)
                update_authority = None
                if meta_resp and meta_resp.value and meta_resp.value.data:
                    try:
                        data_b64 = meta_resp.value.data[0]
                        data_bytes = base64.b64decode(data_b64)
                        if len(data_bytes) >= 1 + 32:
                            ua_bytes = data_bytes[1:33]
                            try:
                                ua_pk = Pubkey(ua_bytes)
                            except Exception:
                                import base58
                                ua_b58 = base58.b58encode(ua_bytes).decode()
                                update_authority = ua_b58
                            else:
                                update_authority = str(ua_pk)
                    except Exception as pe:
                        logging.debug("Failed to parse metadata account: %s", pe, exc_info=True)
                        update_authority = None
                else:
                    update_authority = None
            except Exception as me:
                logging.debug("Metadata PDA/read error: %s", me, exc_info=True)
                update_authority = None

            out_info = {
                "info": {
                    "decimals": decimals,
                    "freezeAuthority": freeze_authority,
                    "isInitialized": info.get("isInitialized"),
                    "mintAuthority": mint_authority,
                    "supply": supply,
                },
                "updateAuthority": update_authority,
                "mint": str(mint_pk),
            }

            return (update_authority, out_info)
        except Exception as e:
            logging.error(f"Error getting mint authority: {e}")
            traceback.print_exc()
            return (None, None)

    async def get_decimals(self, mint: str | Pubkey) -> int:
        """
        Get the decimals of a mint.
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            mint_info = await self.async_client.get_account_info_json_parsed(
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

    async def check_route_pump(self, mint: str):
        """
        Check if a mint is a PumpFun mint.
        Args:
            mint: str
        Returns:
            tuple: (dex, pool)
        """
        try:
            bc = get_associated_bonding_curve_address(Pubkey.from_string(mint))[0]
            if not await _check_exists(self.async_client, bc):
                return (None, None)
            
            has_migrated = await check_has_migrated(self.async_client, bc)
            if has_migrated:
                best_pool = await find_migration_source(self.async_client, mint)
                if best_pool["source"] == "pumpswap":
                    return (SUPPORTED_DEXES["PumpSwap"], best_pool["result"][0]["pubkey"])
                elif best_pool["source"] == "raydium":
                    return (SUPPORTED_DEXES["RaydiumAMM"], best_pool["result"])
                else:
                    raise Exception("route_pump: No pool found")
            else:
                return (SUPPORTED_DEXES["PumpFun"], bc)
        except Exception as e:
            logging.error(f"Error routing pump: {e}")
            traceback.print_exc()
            return (None, None)
        
    async def check_route_pumpswap(self, mint: str):
        """
        Check if a mint is a PumpSwap mint.
        Args:
            mint: str
        Returns:
            tuple: (dex, pool)
        """
        try:
            pool1, pool2 = None, None
            pool1 = await find_pumpswap_pools(
                self.async_client,
                mint,
                WSOL_MINT
            )
            pool2 = await find_pumpswap_pools(
                self.async_client,
                WSOL_MINT,
                mint
            )
            if pool1:
                return (True, pool1[0]["pubkey"])
            elif pool2:
                return (True, pool2[0]["pubkey"])
            else:
                return (False, None)

        except Exception as e:
            logging.error(f"Error routing pumpswap: {e}")
            traceback.print_exc()
            return (None, None)

    async def check_route_launchpad(self, mint: str):
        """
        Check if a mint is a Launchpad mint.
        Args:
            mint: str
        Returns:
            tuple: (dex, pool)
        """
        try:
            pool = await self.launchlab_swap.core.find_launchpad_pool_by_mint(mint)
            if pool:
                has_migrated = await self.launchlab_swap.core.launchpad_check_has_migrated(pool)
                if has_migrated:
                    ok, pool = await self.check_ray_cpmm_for_mint(mint)
                    if ok:
                        return (SUPPORTED_DEXES["RayCPMM"], pool)
                    else:
                        return (SUPPORTED_DEXES["Launchpad"], None)
                else:
                    return (SUPPORTED_DEXES["Launchpad"], pool)
            else:
                return (SUPPORTED_DEXES["Launchpad"], None)
        except Exception as e:
            logging.error(f"Error routing launchpad: {e}")
            traceback.print_exc()
            return (None, None)
        
    async def check_route_believe(self, mint: str):
        """
        Check if a mint is a Believe mint.
        Args:
            mint: str
        Returns:
            tuple: (dex, pool)
        """
        try:
            pool, state = await self.meteora_dbc.fetch_state(mint)
            if pool:
                if state["is_migrated"] == 1:
                    ok, pool = await self.check_damm_v2_for_mint(mint)
                    if ok:
                        return (SUPPORTED_DEXES["MeteoraDamm2"], pool)
                    else:
                        return (SUPPORTED_DEXES["Believe"], None)
                else:
                    return (SUPPORTED_DEXES["Believe"], pool)
            else:
                return (SUPPORTED_DEXES["Believe"], None)
        except Exception as e:
            logging.error(f"Error routing believe: {e}")
            traceback.print_exc()
            return (None, None)
        
    async def check_ray_cpmm_for_mint(self, mint: str | Pubkey):
        """
        Check if a mint is a RaydiumCPMM mint.
        Args:
            mint: str | Pubkey
        Returns:
            tuple: (bool, pool)
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pools = await self.cpmm_swap.core.find_cpmm_pools_by_mint(mint, limit=500)
            if not pools:
                return (False, None)

            pool, _ = await self.cpmm_swap.core.find_suitable_pool(mint, pools)
            if pool:
                return (True, pool)
            else:
                return (False, None)
        except Exception as e:
            logging.error(f"Error checking ray cpmm for mint: {e}")
            traceback.print_exc()
            return (False, None)
        
    async def check_ray_clmm_for_mint(self, mint: str | Pubkey):
        """
        Check if a mint is a RaydiumCLMM mint.
        Args:
            mint: str | Pubkey
        Returns:
            tuple: (bool, pool)
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pool = await self.clmm_swap.core.find_pool_by_mint_with_min_liquidity(mint, min_liquidity=10000)
            if pool:
                return (True, pool)
            else:
                return (False, None)
        except Exception as e:
            logging.error(f"Error checking ray clmm for mint: {e}")
            traceback.print_exc()
            return (False, None)
        
    async def check_ray_v4_for_mint(self, mint: str | Pubkey):
        """
        Check if a mint is a RaydiumV4 mint.
        Args:
            mint: str | Pubkey
        Returns:
            tuple: (bool, pool)
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pool = await self.raydiumswap_v4.find_pool_by_mint(mint)
            if pool:
                return (True, pool)
            else:
                return (False, None)
        except Exception as e:
            logging.error(f"Error checking ray v4 for mint: {e}")
            traceback.print_exc()
            return (False, None)
        
    async def check_dbc_for_mint(self, mint: str | Pubkey):
        """
        Check if a mint is a MeteoraDBC mint.
        Args:
            mint: str | Pubkey
        Returns:
            tuple: (bool, pool)
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pool, state = await self.meteora_dbc.fetch_state(mint)
            if not pool or not state:
                return (False, None)
            is_migrated = state["is_migrated"]
            if is_migrated == 1:
                return (False, "migrated")
            else:
                return (True, pool)
        except ValueError as e:
            return (False, None)
        except Exception as e:
            logging.error(f"Error checking dbc for mint: {e}")
            traceback.print_exc()
            return (False, None)

    async def check_damm_v1_for_mint(self, mint: str | Pubkey):
        """
        Check if a mint is a MeteoraDAMM1 mint.
        Args:
            mint: str | Pubkey
        Returns:
            tuple: (bool, pool)
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pool = await self.damm_v1.core.find_pool_by_mint(mint)
            if pool:
                return (True, pool)
            else:
                return (False, None)
        except Exception as e:
            logging.error(f"Error checking damm v1 for mint: {e}")
            traceback.print_exc()
            return (False, None)
        
    async def check_damm_v2_for_mint(self, mint: str | Pubkey):
        """
        Check if a mint is a MeteoraDAMM2 mint.
        Args:
            mint: str | Pubkey
        Returns:
            tuple: (bool, pool)
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pool = await self.damm_v2.core.find_pools_by_mint(mint, limit=50)
            if pool:
                return (True, pool)
            else:
                return (False, None)
        except Exception as e:
            logging.error(f"Error checking damm v2 for mint: {e}")
            traceback.print_exc()
            return (False, None)
        
    async def check_dlmm_for_mint(self, mint: str | Pubkey, exclude_pools: list[str] = []):
        """
        Check if a mint is a MeteoraDLMM mint.
        Args:
            mint: str | Pubkey
            exclude_pools: list[str]
        Returns:
            tuple: (bool, pool)
        """
        try:
            mint = Pubkey.from_string(mint) if isinstance(mint, str) else mint
            pools = await self.dlmm.core.find_dlmm_pools_by_mint(mint)
            pool, _, _ = await self.dlmm.core.find_suitable_pool(pools, mint, 0.001, exclude_pools=exclude_pools)
            if pool:
                return (True, pool)
            else:
                return (False, None)
        except Exception as e:
            logging.error(f"Error checking dlmm for mint: {e}")
            traceback.print_exc()
            return (False, None)

    async def find_best_market_for_mint(self, mint: str):
        """
        Find the best market for a mint.
        Args:
            mint: str
        Returns:
            tuple: (dex, pool)
        """
        try:
            dex_addr = None
            authority, info = await self.get_mint_authority(mint)
            if authority is None and info is None:
                raise Exception("find_best_market_for_mint: Mint not found")
            
            cprint(f"Mint: {mint} | Authority: {authority}")
            if authority in SUPPORTED_DEXES.values():
                if ADDR_TO_DEX[authority] == "PumpFun":
                    dex_addr, pool = await self.check_route_pump(mint)
                elif ADDR_TO_DEX[authority] == "Launchpad":
                    dex_addr, pool = await self.check_route_launchpad(mint)
            elif "BLV" in mint:
                dex_addr, pool = await self.check_route_believe(mint)
                
            if dex_addr is None:
                is_pumpswap, pool = await self.check_route_pumpswap(mint)
                if is_pumpswap:
                    return (SUPPORTED_DEXES["PumpSwap"], pool)
                
                is_ray_cpmm, pool = await self.check_ray_cpmm_for_mint(mint)
                if is_ray_cpmm:
                    return (SUPPORTED_DEXES["RayCPMM"], pool)
                is_ray_v4, pool = await self.check_ray_v4_for_mint(mint)
                if is_ray_v4:
                    return (SUPPORTED_DEXES["RaydiumAMM"], pool)
                is_ray_clmm, pool = await self.check_ray_clmm_for_mint(mint)
                if is_ray_clmm:
                    return (SUPPORTED_DEXES["RayCLMM"], pool)
                
                # DBC MIGRATION CHECK
                is_dbc, pool = await self.check_dbc_for_mint(mint)
                if is_dbc:
                    return (SUPPORTED_DEXES["MeteoraDBC"], pool)
                elif pool == "migrated":
                    is_damm2, pool = await self.check_damm_v2_for_mint(mint)
                    if is_damm2:
                        return (SUPPORTED_DEXES["MeteoraDamm2"], pool)
                    is_damm1, pool = await self.check_damm_v1_for_mint(mint)
                    if is_damm1:
                        return (SUPPORTED_DEXES["MeteoraDamm1"], pool)
                # END DBC MIGRATION CHECK
                    
                is_dlmm, pool = await self.check_dlmm_for_mint(mint)
                if is_dlmm:
                    return (SUPPORTED_DEXES["MeteoraDLMM"], pool)
                is_damm1, pool = await self.check_damm_v1_for_mint(mint)
                if is_damm1:
                    return (SUPPORTED_DEXES["MeteoraDamm1"], pool)
                is_damm2, pool = await self.check_damm_v2_for_mint(mint)
                if is_damm2:
                    return (SUPPORTED_DEXES["MeteoraDamm2"], pool)
                
            if dex_addr is None:
                raise Exception("find_best_market_for_mint: Cannot find dex for a mint, is this a valid mint?")
            elif pool is None:
                raise Exception("find_best_market_for_mint: Cannot find pool for a mint, is this a valid mint?")

            return (dex_addr, pool)
        except Exception as e:
            logging.error(f"Error finding best route: {e}")
            traceback.print_exc()
            return (None, None)

    async def find_best_market_for_mint_race(
        self,
        mint: str,
        *,
        prefer_authority: bool = True,
        timeout: float | None = None,
        exclude_pools: list[str] = [],
        use_cache: bool = False
    ):
        """
            Args:
                mint: str
                prefer_authority: bool
                timeout: float | None
                exclude_pools: list[str]
                use_cache: bool <- if True, will use local cache to avoid duplicate RPC calls

        Race all known DEX route probes concurrently and return the first that yields
        a usable (dex_addr, pool). Optional `prefer_authority` short-circuits when
        mint authority already maps to a known DEX (PumpFun / Launchpad / Believe).
        `timeout` caps total wait (seconds). None = wait until all done.
        """
        try:
            if use_cache and str(mint) in self.local_cache:
                return self.local_cache[str(mint)]
            
            # 0. authority hint (fast, low RPC cost)
            authority, info = await self.get_mint_authority(mint)
            if authority == "INVALID":
                pass
            elif authority is None and info is None:
                logging.error("find_best_market_for_mint_race: mint not found on-chain.")
                return (None, None)

            if prefer_authority:
                if authority in SUPPORTED_DEXES.values():
                    dex_name = ADDR_TO_DEX[authority]
                    if dex_name == "PumpFun":
                        return await self.check_route_pump(mint)
                    elif dex_name == "Launchpad":
                        return await self.check_route_launchpad(mint)
                elif "BLV" in mint:
                    return await self.check_route_believe(mint)

            # 1. task runners
            async def run_pump():
                return await self.check_route_pump(mint)

            async def run_launchpad():
                return await self.check_route_launchpad(mint)

            async def run_believe():
                return await self.check_route_believe(mint)

            async def run_pumpswap():
                ok, pool = await self.check_route_pumpswap(mint)
                return (SUPPORTED_DEXES["PumpSwap"], pool) if ok and pool else (None, None)

            async def run_ray_cpmm():
                ok, pool = await self.check_ray_cpmm_for_mint(mint)
                return (SUPPORTED_DEXES["RayCPMM"], pool) if ok and pool else (None, None)

            async def run_ray_v4():
                ok, pool = await self.check_ray_v4_for_mint(mint)
                return (SUPPORTED_DEXES["RaydiumAMM"], pool) if ok and pool else (None, None)

            async def run_ray_clmm():
                ok, pool = await self.check_ray_clmm_for_mint(mint)
                return (SUPPORTED_DEXES["RayCLMM"], pool) if ok and pool else (None, None)

            async def run_dbc():
                ok, pool = await self.check_dbc_for_mint(mint)
                if ok and pool not in (None, "migrated"):
                    return (SUPPORTED_DEXES["MeteoraDBC"], pool)
                return (None, None)

            async def run_damm_v2():
                ok, pool = await self.check_damm_v2_for_mint(mint)
                return (SUPPORTED_DEXES["MeteoraDamm2"], pool) if ok and pool else (None, None)

            async def run_damm_v1():
                ok, pool = await self.check_damm_v1_for_mint(mint)
                return (SUPPORTED_DEXES["MeteoraDamm1"], pool) if ok and pool else (None, None)

            async def run_dlmm():
                ok, pool = await self.check_dlmm_for_mint(mint, exclude_pools=exclude_pools)
                return (SUPPORTED_DEXES["MeteoraDLMM"], pool) if ok and pool else (None, None)

            runners = {
                "pump": run_pump,
                "launchpad": run_launchpad,
                "believe": run_believe,
                "pumpswap": run_pumpswap,
                "ray_cpmm": run_ray_cpmm,
                "ray_v4": run_ray_v4,
                "ray_clmm": run_ray_clmm,
                "dbc": run_dbc,
                "damm_v2": run_damm_v2,
                "damm_v1": run_damm_v1,
                "dlmm": run_dlmm,
            }

            tasks = {name: asyncio.create_task(fn(), name=name) for name, fn in runners.items()}

            try:
                if timeout is not None:
                    iter_ = asyncio.as_completed(tasks.values(), timeout=timeout)
                else:
                    iter_ = asyncio.as_completed(tasks.values())

                for fut in iter_:
                    try:
                        dex_addr, pool = await fut
                    except asyncio.CancelledError:
                        continue
                    except Exception as e:
                        logging.debug("route task error: %s", e, exc_info=True)
                        continue

                    if dex_addr is not None and pool is not None:
                        logging.info(f"Route found: {ADDR_TO_DEX[dex_addr]} -> {pool}")
                        for t in tasks.values():
                            if t is not fut and not t.done():
                                t.cancel()
                        await asyncio.gather(*tasks.values(), return_exceptions=True)
                        if use_cache and mint not in self.local_cache:
                            logging.info("Caching %s -> %s", mint, (dex_addr, pool))
                            self.local_cache[str(mint)] = (dex_addr, pool)
                        return (dex_addr, pool)

            except asyncio.TimeoutError:
                logging.warning("find_best_market_for_mint_race: timeout (%.2fs) for %s", timeout, mint)
            finally:
                for t in tasks.values():
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*tasks.values(), return_exceptions=True)

            logging.error("find_best_market_for_mint_race: no routes resolved for %s", mint)
            return (None, None)

        except Exception as e:
            logging.error("find_best_market_for_mint_race: %s", e)
            traceback.print_exc()
            return (None, None)

    async def close(self):
        """
        Close the router.
        """
        try:
            await self.pump_fun.close()
            await self.raydiumswap.close()
            await self.pump_swap.close()
            await self.meteora_dbc.close()
            await self.session.close()
            return True
        except Exception as e:
            logging.error(f"Error closing router: {e}")
            return False









