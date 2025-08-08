import asyncio
import aiohttp
import json
import logging
import os
from dotenv import load_dotenv

# !!! Helius API is only used in CobraNET

load_dotenv("secrets.env")

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

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
        logging.info(e)
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
    
async def main():
    async with aiohttp.ClientSession() as session:
        # {'name': 'Cheetocoin', 'symbol': 'Cheetocoin', 'supply': '999002142162258', 'decimals': 6}
        data = await get_token_info("qQkRz3BeTQMpFNxmt8w7ZQnpXV9bgtF2JHGnSpppump", session)
        logging.info(data)

if __name__ == "__main__":
    asyncio.run(main())
