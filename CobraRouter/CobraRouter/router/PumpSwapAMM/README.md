# PumpSwapAMM

**Python SDK for Pump.fun AMM (PumpSwap) on Solana.**

- Trade tokens, create & manage pairs.

Latest update reflects newest (01.08.25) changes in Pump.fun AMM program, adds `reversed_buy` and `reversed_sell`; Use them when WSOL is the base token. You can also pass keypair to each function instead of having a single signer for the whole class, which is useful when you want to use different wallets for different operations.

The module implements ways to **fetch pool keys and price or account reserves, deriving addresses, finding pools and more...**

Tip wallet: `FL4CKfetEWBMXFs15ZAz4peyGbCuzVaoszRKcoVt3WfC`, **Thanks 💙**

## Contact & Support

**Discord: [FLOCK4H.CAVE](https://discord.gg/thREUECv2a)**, **Telegram: [FLOCK4H.CAVE](https://t.me/flock4hcave)**

**Telegram private handle: @dubskii420**

<img src="https://github.com/user-attachments/assets/d655c153-0056-47fc-8314-6f919f18ed6d" width="256" />

# Setup

**Most convenient:**

<h6>If module or a command can't be found, try installing in a shell with administrative rights</h6>

```
  $ pip install PumpSwapAMM
```

**When above fails for any reason:**

```
  $ git clone https://github.com/FLOCK4H/PumpSwapAMM
  $ cd PumpSwapAMM
  $ pip install .
```

# Usage

**Check out the `example.py` and `example_pool.py` scripts for a Plug & Play implementation**

```python
class PumpSwap(
    async_client: AsyncClient,
)

(method) def buy(
    pool_data: dict,
    sol_amount: float,
    keypair: Keypair | None = None,
    pool_type: str = NEW_POOL_TYPE,
    slippage_pct: float,
    fee_sol: float
    return_instructions: bool = False,
) -> Coroutine[Any, Any, bool]
Args:
    pool_data: dict
    sol_amount: float
    slippage_pct: float
    fee_sol: float
Returns:
    bool: True if successful, False otherwise

(method) def reversed_buy(
    pool_data: dict,
    sell_pct: float,
    keypair: Keypair,
    pool_type: str = NEW_POOL_TYPE,
    slippage_pct: float = 10, # slippage works differently here, we can't apply slippage because we spend all the tokens, so only way is to sell less, set slippage to as low as possible to sell as much WSOL
    fee_sol: float = 0.00001,         # total priority fee user wants to pay, e.g. 0.0005
    debug_prints: bool = False,
    return_instructions: bool = False,
):

(method) def sell(
    pool_data: dict,
    sell_pct: float,
    slippage_pct: float,
    fee_sol: float
) -> Coroutine[Any, Any, bool]
Args:
    pool_data: dict
    sell_pct: float
    slippage_pct: float
    fee_sol: float
Returns:
    bool: True if successful, False otherwise

(method) def reversed_sell(
    pool_data: dict,
    sol_amount: float,
    keypair: Keypair,
    pool_type: str = NEW_POOL_TYPE,
    slippage_pct: float = 10,
    fee_sol: float = 0.00001,
    debug_prints: bool = False,
    return_instructions: bool = False,
):

(function) def fetch_pool(
    pool: str,
    async_client: AsyncClient
) -> Coroutine[Any, Any, dict[str, Any]]

(function) def fetch_pool_base_price(
    pool_keys: Any,
    async_client: Any
) -> Coroutine[Any, Any, tuple[Decimal, Any, Any] | None]

(method) def derive_pool_address(
    creator: Pubkey,
    base_mint: Pubkey,
    quote_mint: Pubkey,
    index: int = 0
) -> Pubkey

(method) def create_pool(
    base_mint: Pubkey,
    base_amount_tokens: float,
    quote_amount_sol: float,
    decimals_base: int = 6,
    index: int = 0,
    fee_sol: float = 0.0005,
    mute: bool = False
) -> Coroutine[Any, Any, bool]

(method) def withdraw(
    pool_data: dict,
    withdraw_pct: float,
    fee_sol: float = 0.0003,
    mute: bool = False
) -> Coroutine[Any, Any, bool]

(method) def deposit(
    pool_data: dict,
    base_amount_tokens: float,
    slippage_pct: float = 1,
    fee_sol: float = 0.0003,
    sol_cap: float | None = None,
    mute: bool = False
) -> Coroutine[Any, Any, bool]
```

<h4>Examples</h4>

**Check `example.py` and `example_pool.py` for more examples.**

# Issues

- "get_account_info_json_parsed" may throw a 401 or 403 if you're using helius (& any other triton-based) **dedicated node** or staked APIs

# LICENSE

**Standard MIT License**

> THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
> LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
