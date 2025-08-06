from __future__ import annotations
import asyncio
import itertools
from typing import List, Sequence

from solders.pubkey import Pubkey # type: ignore
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed

DLMM_PROGRAM_ID = Pubkey.from_string("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo")

MAX_BIN_PER_ARRAY: int = 70
BIN_ARRAY_BITMAP_SIZE: int = 512# 1 Ki bits 1024-bit bitmap
EXTENSION_BINARRAY_BITMAP_SIZE: int = 12 # 12x 512-bit
BASIS_POINT_MAX: int = 10_000

class LbPairLike:
    pubkey: Pubkey
    active_id: int
    bin_array_bitmap: Sequence[int]

class BitmapExtLike:
    positive_bin_array_bitmap: Sequence[Sequence[int]]  # [12][8] u64
    negative_bin_array_bitmap: Sequence[Sequence[int]]  # [12][8] u64

async def _check_exists(client: AsyncClient, account: Pubkey) -> bool:
    resp = await client.get_account_info(account, commitment=Processed)
    return resp is not None and resp.value is not None and resp.value.data is not None

def _u64_le_bytes(value: int) -> bytes:
    """8-byte little-endian, two's complement if negative."""
    return (value & ((1 << 64) - 1)).to_bytes(8, "little")

def bin_id_to_array_index(bin_id: int) -> int:
    """
    Positive side is simple integer division.
    For the negative side we need ceiling-style division
    """
    if bin_id >= 0:
        return bin_id // MAX_BIN_PER_ARRAY
    return -((abs(bin_id) + MAX_BIN_PER_ARRAY - 1) // MAX_BIN_PER_ARRAY)

def derive_bin_array_pda(lb_pair: Pubkey, index: int) -> Pubkey:
    seed_idx = _u64_le_bytes(index)
    return Pubkey.find_program_address(
        [b"bin_array", bytes(lb_pair), seed_idx],
        DLMM_PROGRAM_ID,
    )[0]

def derive_bitmap_ext_pda(lb_pair: Pubkey) -> Pubkey:
    return Pubkey.find_program_address([b"bitmap", bytes(lb_pair)], DLMM_PROGRAM_ID)[0]

class DLMMBin:
    __slots__ = ()

    @staticmethod
    def _int_from_u64_array(u64s: Sequence[int]) -> int:
        v = 0
        for limb in reversed(u64s):
            v = (v << 64) | (limb & ((1 << 64) - 1))
        return v

    @staticmethod
    def _get_bitmap_offset(bin_array_index: int) -> int:
        return bin_array_index + BIN_ARRAY_BITMAP_SIZE

    @staticmethod
    def _next_bin_array_index_with_liquidity_internal(
        bitmap: int, 
        start_array_index: int, 
        swap_for_y: bool
    ) -> tuple[int, bool]:
        """Find next bin array index with liquidity in internal bitmap"""
        array_offset = DLMMBin._get_bitmap_offset(start_array_index)
        min_bitmap_id = -BIN_ARRAY_BITMAP_SIZE
        max_bitmap_id = BIN_ARRAY_BITMAP_SIZE - 1
        
        if swap_for_y:
            bitmap_range = max_bitmap_id - min_bitmap_id
            offset_bitmap = bitmap << (bitmap_range - array_offset)
            
            if offset_bitmap == 0:
                return (min_bitmap_id - 1, False)
            else:
                leading_zeros = 0
                temp = offset_bitmap
                for i in range(1024):
                    if temp & (1 << (1023 - i)):
                        leading_zeros = i
                        break
                return (start_array_index - leading_zeros, True)
        else:
            offset_bitmap = bitmap >> array_offset
            
            if offset_bitmap == 0:
                return (max_bitmap_id + 1, False)
            else:
                trailing_zeros = 0
                temp = offset_bitmap
                while temp and not (temp & 1):
                    trailing_zeros += 1
                    temp >>= 1
                return (start_array_index + trailing_zeros, True)

    @staticmethod
    def _next_bin_array_index_with_liquidity_extension(
        bitmap_extension: BitmapExtLike,
        start_index: int,
        swap_for_y: bool
    ) -> tuple[int, bool]:
        """Find next bin array index with liquidity in extension bitmap"""
        if start_index > 0:
            bitmap_array = bitmap_extension.positive_bin_array_bitmap
        else:
            bitmap_array = bitmap_extension.negative_bin_array_bitmap
            
        abs_index = abs(start_index)
        bitmap_offset = (abs_index // BIN_ARRAY_BITMAP_SIZE) - 1
        
        if bitmap_offset >= len(bitmap_array):
            return (0, False)
            
        for i in range(len(bitmap_array)):
            if swap_for_y and start_index > 0:
                search_offset = bitmap_offset - i
                if search_offset < 0:
                    break
            elif not swap_for_y and start_index < 0:
                search_offset = bitmap_offset + i
                if search_offset >= len(bitmap_array):
                    break
            else:
                search_offset = bitmap_offset + (i if not swap_for_y else -i)
                if search_offset < 0 or search_offset >= len(bitmap_array):
                    break
                    
            bitmap_limbs = bitmap_array[search_offset]
            bitmap = DLMMBin._int_from_u64_array(bitmap_limbs)
            
            if bitmap != 0:
                if swap_for_y:
                    bit_pos = 0
                    temp = bitmap
                    while temp and not (temp & 1):
                        bit_pos += 1
                        temp >>= 1
                else:
                    bit_pos = 511
                    temp = bitmap
                    while temp and not (temp & (1 << bit_pos)):
                        bit_pos -= 1
                        
                base_index = (search_offset + 1) * BIN_ARRAY_BITMAP_SIZE
                if start_index < 0:
                    return (-(base_index + bit_pos) - 1, True)
                else:
                    return (base_index + bit_pos, True)
                    
        return (0, False)

    @staticmethod
    def bin_arrays_for_swap(
        lb_pair_state: LbPairLike,
        swap_for_y: bool,
        count: int = 4,
        bitmap_extension_acc: BitmapExtLike | None = None,
    ) -> List[Pubkey]:
        """get bin array PDAs needed for swap"""
        
        active_bin_array_index = bin_id_to_array_index(lb_pair_state.active_id)
        bitmap = DLMMBin._int_from_u64_array(lb_pair_state.bin_array_bitmap)
        
        result = []
        current_index = active_bin_array_index
        
        while len(result) < count:
            found_liquidity = False
            
            if -BIN_ARRAY_BITMAP_SIZE <= current_index < BIN_ARRAY_BITMAP_SIZE:
                next_index, has_liquidity = DLMMBin._next_bin_array_index_with_liquidity_internal(
                    bitmap, current_index, swap_for_y
                )
                
                if has_liquidity:
                    result.append(derive_bin_array_pda(lb_pair_state.pubkey, next_index))
                    current_index = next_index + (1 if not swap_for_y else -1)
                    found_liquidity = True
                else:
                    current_index = -BIN_ARRAY_BITMAP_SIZE - 1 if swap_for_y else BIN_ARRAY_BITMAP_SIZE
            else:
                if bitmap_extension_acc is not None:
                    next_index, has_liquidity = DLMMBin._next_bin_array_index_with_liquidity_extension(
                        bitmap_extension_acc, current_index, swap_for_y
                    )
                    
                    if has_liquidity:
                        result.append(derive_bin_array_pda(lb_pair_state.pubkey, next_index))
                        current_index = next_index + (1 if not swap_for_y else -1)
                        found_liquidity = True
                        
            if not found_liquidity:
                break
                
        return result

    @staticmethod
    def _find_bin_arrays(active_id: int, lb_pair: Pubkey) -> list[Pubkey, Pubkey, Pubkey]:
        bin_index = bin_id_to_array_index(active_id)
        if bin_index >= 0:
            bin_index_left = bin_index - 1
            bin_index_right = bin_index + 1
            current_bin_pda = derive_bin_array_pda(lb_pair, bin_index)
            next_bin_pda_left = derive_bin_array_pda(lb_pair, bin_index_left)
            next_bin_pda_right = derive_bin_array_pda(lb_pair, bin_index_right)
            return [next_bin_pda_left, current_bin_pda, next_bin_pda_right]
        else:
            bin_index_left = bin_index + 1
            bin_index_right = bin_index_left + 1
            current_bin_pda = derive_bin_array_pda(lb_pair, bin_index)
            next_bin_pda_left = derive_bin_array_pda(lb_pair, bin_index_left)
            next_bin_pda_right = derive_bin_array_pda(lb_pair, bin_index_right)
            return [next_bin_pda_left, current_bin_pda, next_bin_pda_right]

    @staticmethod
    async def find_adjacent_bin_arrays(client: AsyncClient, active_id: int, lb_pair: Pubkey) -> list[Pubkey]:
        """
        Return the three PDAs in the exact order expected by `swap2`:
        [ previous , current , next ]   (a.k.a. left, centre, right)
        Works for both positive and negative indices.
        """
        cur  = bin_id_to_array_index(active_id)
        left = derive_bin_array_pda(lb_pair, cur - 1)
        middle = derive_bin_array_pda(lb_pair, cur)
        right = derive_bin_array_pda(lb_pair, cur + 1)
        coll = [left, middle, right]
        for ar_bin in coll:
            exists = await _check_exists(client, ar_bin)
            if not exists:
                coll.remove(ar_bin)
        return coll

# -3: F9zCW8rWEpE9rsNgS3A6dpAJzXYQAg35TLSG6nPKDdGk
# -2: HW6enBekqB9nFhBTswCmGhvncJ8FF5YoUjhK9hD1uX5N
# -1: 8EWhSv4sjo8DrkMXtDaiWZc2YaupV2t7kFhN8ZueMeYv
# 0: G21uDwDDoGCyqnwYJFj5BvEPDZrZsGiQMcYAotstXhzm
# 1: 6DPkAXuprsDdPpaK8NpQjwr6gfaQLroT1R4m77x9ivKy
# 2: 7ds1eRTZDV16t7u3ofntN3M6NgD1CZdqpcvEEoEGGHBZ
async def main():
    bin = DLMMBin()
    bin_index = bin_id_to_array_index(-2627)
    print(bin_index)
    bin_pda = derive_bin_array_pda(Pubkey.from_string("AahrUPni3rscneV2A4HeXnfb7s1XM81dNa3NEwGGCC6"), -6)
    print(bin_pda)

if __name__ == "__main__":
    asyncio.run(main())
    