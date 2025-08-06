import requests

def fetch_pool_info(mint: str):
    url = "https://api-v3.raydium.io/pools/info/mint"
    args = {
        "mint1": mint,
        "poolType": "all",
        "poolSortField": "default",
        "sortType": "desc",
        "pageSize": 100,
        "page": 1
    }

    try:
        response = requests.get(url, params=args)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception as e:
        print(e)
        return None
