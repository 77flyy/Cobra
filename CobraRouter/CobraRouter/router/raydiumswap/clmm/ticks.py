#!/usr/bin/env python3
import struct, asyncio
from solders.pubkey import Pubkey # type: ignore
try: from raydium_apiv3 import RaydiumAPI
except: from .raydium_apiv3 import RaydiumAPI

CLMM_PROGRAM_ID = Pubkey.from_string("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK")
TICK_ARRAY_SEED = b"tick_array"
TICK_ARRAY_SIZE = 60
TICK_SPACING    = 60

# NOTE:
# This is my first fucking time using offensive language in a python file.
# I'm sorry.
class RaydiumFuckingTicks:
    def __init__(self):
        pass

    def get_array_start_index(self, tick_index: int, tick_spacing: int = TICK_SPACING) -> int:
        """
        Return the first tick index in the tick-array that contains `tick_index`.
        """

        tpm = TICK_ARRAY_SIZE * tick_spacing
        return (tick_index // tpm) * tpm

    def derive_tick_array_pda(self, pool_id: Pubkey, start_tick: int) -> Pubkey:
        be = struct.pack(">i", start_tick)
        pda, _ = Pubkey.find_program_address(
            [TICK_ARRAY_SEED, bytes(pool_id), be],
            CLMM_PROGRAM_ID
        )
        return pda

    async def get_tick_arrays(
            self,
            pool_id: Pubkey,
            tick_current: int,
            tick_spacing: int = TICK_SPACING,
        ) -> list[str] | None:
        """
        Return PDAs for three *distinct* tick-arrays centred on `tick_current`:
        - one immediately below
        - the first one above
        - the next one whose startTickIndex differs from the previous
        """
        try:
            raydium = RaydiumAPI()
            ticks: list[int] = await raydium.get_list_of_ticks_for_pool(str(pool_id))

            # index of the first tick strictly greater than tick_current
            first_above_idx = next((i for i, t in enumerate(ticks) if t > tick_current), None)
            if first_above_idx is None:
                raise ValueError("tick_current is above the highest on-chain tick")

            starts: list[int] = []
            pda_list: list[str] = []

            print(f"\nTickArray PDAs for current_tick = {tick_current}:\n")

            # Begin one tick below current, then keep moving up until we have 3 unique arrays
            idx = first_above_idx - 1
            while len(starts) < 5 and 0 <= idx < len(ticks):
                tick = ticks[idx]
                start = self.get_array_start_index(tick, tick_spacing)

                if start not in starts:
                    starts.append(start)
                    pda = self.derive_tick_array_pda(pool_id, start)
                    pda_list.append(pda)
                    print(f"tick = {tick:>6} -> startTickIndex = {start:>7} -> PDA = {pda}")

                idx += 1

            if len(starts) < 1:
                raise ValueError("Unable to find 1 unique tick-array start")

            return pda_list

        except Exception as e:
            print(f"Error: {e}")
            return None
        

async def main():
    pool_id = Pubkey.from_string("5jXDXGzfWZRAqHiXrtcPGFTMvRZUwXf1Vn99gWM4bLJJ")
    tick_current = 27740
    tick_spacing = 1
    ticks = RaydiumFuckingTicks()
    tick_arrays = await ticks.get_tick_arrays(pool_id, tick_current, tick_spacing)
    print(tick_arrays)

if __name__ == "__main__":
    asyncio.run(main())
