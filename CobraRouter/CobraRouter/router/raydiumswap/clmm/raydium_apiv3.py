import httpx, json, asyncio
from httpx import Headers
import logging

#mute httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

class RaydiumURL:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def headers(self) -> Headers:
        headers = Headers({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        return headers

    def pools(self, pool_id: str):
        return f"{self.base_url}/pools/line/position?id={pool_id}"

class RaydiumAPI:
    def __init__(self):
        self.base_url = "https://api-v3.raydium.io"
        self.url = RaydiumURL(self.base_url)
        self.client = httpx.AsyncClient(base_url=self.base_url, headers=self.url.headers())

    async def get_pool_info(self, pool_id: str):
        try:
            url = self.url.pools(pool_id)
            response = await self.client.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error: {response.status_code} {response.text}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    async def get_list_of_ticks_for_pool(self, pool_id: str):
        ticks = []
        try:
            pool_info = await self.get_pool_info(pool_id)
            if pool_info is None:
                return None
            if pool_info.get('success'):
                data = pool_info.get('data')
                if data:
                    lines = data.get('line') # list of dicts
                    if lines:
                        for line in lines:
                            tick = line.get('tick')
                            if tick:
                                ticks.append(tick)
                        return ticks
        except Exception as e:
            print(f"Error: {e}")
            return None

async def main():
    raydium = RaydiumAPI()
    ticks = await raydium.get_list_of_ticks_for_pool("8bi27duMu38sFtwTJvDMHFURFNbhPLX91H1NKtReVhZr")
    print(ticks)

if __name__ == "__main__":
    asyncio.run(main())