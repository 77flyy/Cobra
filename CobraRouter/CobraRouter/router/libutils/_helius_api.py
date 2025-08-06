import asyncio
import aiohttp
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv("secrets.env") # will walk down to find the API key, if doesn't work for some reason, please manually set the API key below

# HELIUS_API_KEY = "5exxxxx-your-api-key-here"
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

if not HELIUS_API_KEY:
    raise ValueError("HELIUS_API_KEY is not set in secrets.env | Or we couldn't find it, please manually set the API key in `CobraRouter/router/libutils/_helius_api.py`")

class Exceptions:
    class InvalidMint(Exception):
        pass

async def post_get_asset(mint_id, session):
    try:
        url = f'https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}'
        json={"jsonrpc":"2.0","id":"test","method":"getAsset","params":{"id": mint_id}}

        res = await session.post(url, json=json)
        data = await res.json()
        return data
    except Exception as e:
        print(e)
        return None
    
async def get_token_info(mint_id, session):
    try:
        asset = await post_get_asset(mint_id, session)
        if asset.get("error"):
            if "Pubkey Validation Err" in asset["error"]["message"]:
                raise Exceptions.InvalidMint("Invalid mint address")
        metadata = asset["result"]["content"]["metadata"]
        token_info = asset["result"]["token_info"]
        auth = asset["result"]["authorities"][0]["address"]

        return {
            "program": auth,
            "name": metadata["name"],
            "symbol": metadata["symbol"],
            "supply": str(token_info["supply"]),
            "decimals": token_info["decimals"],
        }

    except Exception as e:
        return {"error": str(e)}
    
async def get_mint_authority(session: aiohttp.ClientSession, mint: str):
    try:
        info = await get_token_info(mint, session)
        if info and "program" in info:
            return (info["program"], info)
        else:
            logging.error(f"Failed to get mint authority for {mint}, err: {info}")
            return ("INVALID", "INVALID")
    except Exceptions.InvalidMint:
        logging.info(f"This mint probably doesn't exist: {mint}, you can check on https://solscan.io/token/{mint}")
        return (None, None)
    except Exception as e:
        logging.error(f"Error fetching mint authority: {e}")

async def main():
    async with aiohttp.ClientSession() as session:
        # {'name': 'Cheetocoin', 'symbol': 'Cheetocoin', 'supply': '999002142162258', 'decimals': 6}
        data = await get_token_info("qQkRz3BeTQMpFNxmt8w7ZQnpXV9bgtF2JHGnSpppump", session)
        print(data)

if __name__ == "__main__":
    asyncio.run(main())
