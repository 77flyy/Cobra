"""
    CobraNET is an addon to the router; Telegram bot that allows you to manage your Cobra wallet and perform various actions such as buying, selling, and withdrawing tokens.
    It's basically a wrapper around CobraRouter module.
"""

import time
from dotenv import load_dotenv
from pathlib import Path
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from telegram.error import NetworkError, TelegramError, BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, Defaults, filters, CallbackQueryHandler
from telegram.constants import ChatMemberStatus, ParseMode
import asyncio
import logging
import traceback
from io import BytesIO
from solders.keypair import Keypair # type: ignore
import html

FAILURE_MSG = "Possible reasons:\n1. Transaction doesn't exist on chain, set higher priority fee.\n2. 'Token Mint constraint violation' error, make sure the token you're trying to swap is paired with WSOL."
ELLIPSIS = "…"  # U+2026
RENT_EXEMPT = 2039280

try:
    from CobraNET.db_hook import TGDBHook
    from CobraWallets import CobraWallets
    from CobraRouter import CobraRouter 
    from colors import *
except ImportError:
    from .db_hook import TGDBHook
    from ..CobraWallets import CobraWallets
    from ..CobraRouter.CobraRouter import CobraRouter
    from .colors import *

logging.basicConfig(
    level=logging.INFO,
    format=f"{cc.LIGHT_BLUE}[CobraNET] {cc.WHITE}%(message)s{cc.RESET}",
    datefmt="%H:%M:%S"
)

logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv(dotenv_path=Path.cwd() / "secrets.env", override=False)

# Mainly used for avoiding spamming the bot in the group, totally optional
BLACKLIST_CHAT_IDS = [
    1087968824, # Flock4HCave
]

BOT_TOKEN = os.getenv("BOT_TOKEN")
WINDOW = 10
LIMIT  = 5

ALLOWED = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.OWNER,
}

def short_addr(addr: str, left: int = 4, right: int = 4) -> str:
    if len(addr) <= left + right + 1:
        return addr
    return f"{addr[:left]}{ELLIPSIS}{addr[-right:]}"

class CobraNET:
    def __init__(self, router: CobraRouter, bot_token: str = BOT_TOKEN, command_queue: asyncio.Queue = asyncio.Queue()):
        self.stop_event = asyncio.Event()
        self.application = (
            Application.builder()
            .token(BOT_TOKEN)
            .defaults(Defaults(parse_mode="HTML"))
            .build()
        )
        self.bot_token = bot_token
        self.command_queue = command_queue
        self.db_hook = TGDBHook()
        self.wallets = None
        self.rate = {}
        self.menu_msg = {}
        self.awaiting = {} # int, str
        self.router = router
        self.cleaner = router.cleaner
        self.exclude_pools = []

    async def guard(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        m = u.effective_message
        if not m or not m.from_user: return
        uid = m.from_user.id
        logging.info(f"Guard | uid: {uid}")
        if uid in BLACKLIST_CHAT_IDS:
            return (False, "group-chat")
        now = time.time()
        t, n = self.rate.get(uid, (now, 0))
        if now - t > WINDOW: t, n = now, 0
        self.rate[uid] = (t, n + 1)
        if n >= LIMIT:
            return (False, "rate-limit")
        ok  = await self.is_member(uid)
        if not ok:
            return (False, "not-member")
        
        return (True, "success")

    async def is_member(self, uid: int):
        try:
            #dummy function
            return True
        except TelegramError:
            traceback.print_exc()
            return False

    async def send_message(self, cid: int, txt: str, **kwargs):
        try:
            if cid not in BLACKLIST_CHAT_IDS:
                await self.application.bot.send_message(chat_id=cid, text=f"{txt}", **kwargs)
        except (BadRequest, TelegramError):
            pass

    async def load_img(self, image_path: str):
        try:
            root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            full_path = os.path.join(root_path, image_path)
            with open(full_path, "rb") as f:
                return BytesIO(f.read())
        except FileNotFoundError:
            logging.error(f"Image file not found: {image_path}")
            return None
        except Exception as e:
            logging.error(f"Error loading image: {e}")
            return None

    async def send_banner(self, cid: int, image_path: str):
        from telegram.constants import ParseMode
        if cid in BLACKLIST_CHAT_IDS: return
        img = await self.load_img(image_path)
        if img:
            await self.application.bot.send_photo(
                chat_id=cid,
                photo=img,
                caption="<b>Cobra 🐍</b>",
                show_caption_above_media=True, # caption on top (Bot API ≥ 9.0)
                parse_mode=ParseMode.HTML
            )

    async def start(self):
        """
            Use run() to start the bot instead of start().
        """
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
        except NetworkError as e:
            logging.error(f"Network error: {e}")
            await self.stop()

    async def stop(self):
        await self.application.stop()
        await self.application.shutdown()

    async def handle_command(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        command = u.effective_message.text
        if command.startswith("/"):
            full_command = command[1:]
            if full_command.startswith("start") or full_command.startswith("help") or full_command.startswith("menu"):
                await self.handle_start(u, c)
            else:
                logging.info(f"User sent unknown command: {command}")
        else:
            await self.handle_message(command)

    async def handle_start(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        uid = u.effective_chat.id
        logging.info(f"User {u.effective_chat.username} ({uid}) started the bot.")

        if await self.db_hook.get_user(str(uid)):
            await self.send_message(uid, "<b>✅ Access already granted</b>")
            await self.handle_wallet(uid)
            await self.show_menu(uid)
            return

        await self.send_message(uid, "<b>✅ Access granted</b>")
        await self.db_hook.cache_user(str(uid), str(u.effective_chat.username))
        await self.handle_wallet(uid)
        await self.show_menu(uid)

    async def handle_wallet(self, uid: int):
        if await self.db_hook.get_user(str(uid)):
            wallet = await self.db_hook.get_wallet(str(uid))
            if wallet:
                wallet = dict(wallet) if not isinstance(wallet, dict) else wallet
                await self.send_message(uid, f"<b>Wallet already exists.</b>\n\n<b>Address:</b> <code>{wallet['pubkey']}</code>")
                return
            else:
                data = await self.wallets.create_wallet(str(uid))
                if data is None:
                    await self.send_message(uid, f"<b>Wallet creation failed. Please try again.</b>")
                    return
                pubkey, privkey = data
                await self.send_message(uid, f"<b>✨ Cobra has created a new wallet.</b>\n\n<b>Fund the account 🌱, and increase your balance by sending SOL to this address:</b>\n\n<code>{pubkey}</code>")
                return
        else:
            logging.info(f"User ({uid}) is not a member of the group, or some error occurred.")

    async def get_stats(self, uid: int) -> dict:
        if not self.wallets:
            return {}

        wallet = await self.db_hook.get_wallet(str(uid))
        return {
            "pubkey": wallet["pubkey"],
            "balance": wallet["balance"],
            "tokens": wallet["tokens"],
            "priority_level": wallet["priority_level"],
            "buy_slip": wallet["buy_slip"],
            "sell_slip": wallet["sell_slip"],
        }

    # ───────────────────── menu builders
    async def build_menu_text(self, uid: int) -> str:
        s = await self.get_stats(uid) or {
            "pubkey": "",
            "balance": 0,
            "tokens": [],
            "priority_level": "high",
            "buy_slip": 0.0,
            "sell_slip": 0.0,
        }
        # tokens: list[{"name":mint, "balance":float}]
        rows = []
        toks = s.get("tokens") or []
        for i, tok in enumerate(toks, 1):
            mint  = str(tok["name"])
            bal   = float(tok["balance"])
            bal = f"{bal:.6f}"
            short = html.escape(short_addr(mint))
            rows.append(
                f"{i}. <a href='https://gmgn.ai/sol/token/{mint}'>{short}</a>: {bal}"
            )
        token_lines = "\n".join(rows) if rows else "  • <i>empty, better feed cobra 👀</i>"

        return (
            "<b>🍞 Wallet</b>\n"
            f"• Address: <code>{s['pubkey']}</code>\n"
            f"<b>• Balance: <code>{s['balance']:.4f}</code> SOL</b>\n\n"
            f"<b>🧺 Token Basket</b>\n{token_lines}\n"
            "\n"
            "<b>⚙️ Settings</b>\n"
            f"• Priority Fee Level: {s['priority_level']}\n"
            f"• Slippage:\n"
            f"  • Buy:  {s['buy_slip']:.2f}%\n"
            f"  • Sell: {s['sell_slip']:.2f}%\n\n"
            "<a href='https://t.me/flock4hcave'>Report issue</a>"
        )

    def build_menu_kb(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🟢 Buy",  callback_data="menu_buy"),
                 InlineKeyboardButton("🔴 Sell", callback_data="menu_sell"),
                 InlineKeyboardButton("📝 Tokens", callback_data="menu_list_tokens")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
                InlineKeyboardButton("💰 Withdraw", callback_data="menu_withdraw")],
                [InlineKeyboardButton("🔄 Refresh",  callback_data="menu_refresh")],
            ]
        )

    def build_settings_kb(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Priority Level", callback_data="set_priority_level"), 
                 InlineKeyboardButton("Withdrawal Address", callback_data="set_withdrawal_address")],
                [InlineKeyboardButton("Buy Slippage",  callback_data="set_buy_slip"),
                 InlineKeyboardButton("Sell Slippage", callback_data="set_sell_slip")],
                [InlineKeyboardButton("⬅ Back",        callback_data="menu_refresh")],
            ]
        )
    
    def build_priority_kb(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Low", callback_data="set_priority_level_low"),
                 InlineKeyboardButton("Medium", callback_data="set_priority_level_medium")],
                [InlineKeyboardButton("High", callback_data="set_priority_level_high"),
                 InlineKeyboardButton("Turbo", callback_data="set_priority_level_turbo")],
                [InlineKeyboardButton("⬅ Back", callback_data="menu_refresh")],
            ]
        )
    
    def build_withdraw_kb(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("SOL", callback_data="withdraw_sol")],
                [InlineKeyboardButton("Tokens", callback_data="withdraw_tokens")],
                [InlineKeyboardButton("⬅ Back", callback_data="menu_refresh")],
            ]
        )

    async def show_menu(self, uid: int):
        ok = await self.update_balance(uid)
        if ok == "no_wallet":
            await self.send_message(uid, "<b>No wallet found. Please create a wallet first.</b>")
            return
        
        await self.update_token_balances(uid)

        await self.send_banner(uid, "imgs/cobra_banner.png")
        text = await self.build_menu_text(uid)
        kb   = self.build_menu_kb()

        msg = await self.send_message(uid, text, reply_markup=kb, disable_web_page_preview=True)
        if msg:
            self.menu_msg[uid] = msg.message_id

    async def update_balance(self, uid: int):
        pub = (await self.db_hook.get_wallet(str(uid)))
        if not pub:
            return "no_wallet"
        pubkey = pub["pubkey"]
        balance, ok = await self.router.swaps.get_balance("So11111111111111111111111111111111111111112", pubkey)
        logging.info(f"Debug | balance for {pubkey}: {balance}")
        if balance > 0:
            balance = (balance / 1e9)
        if ok == "success":
            await self.db_hook.update_balance(str(uid), str(balance))
        else:
            logging.info(f"Error updating balance for {pubkey}: {ok}")

    async def update_token_balances(self, uid: int):
        wallet = await self.db_hook.get_wallet(str(uid))
        if not wallet:
            return
        pub = wallet["pubkey"]
        mints = [t["name"] for t in wallet["tokens"]]
        balances = await self.router.swaps.get_multiple_balances(mints, pub)
        if not balances:
            logging.info(f"Debug | no balances found for {pub}")
            return
        logging.info(f"Debug | balances for {pub}: {balances}")
        for mint, balance in balances.items():
            await self.db_hook.update_tokens(str(uid), [{"name": str(mint), "balance": str(balance)}])

    async def update_menu(self, uid: int):
        # fetch and update balance
        if uid not in self.menu_msg:
            await self.show_menu(uid)
            return

        await self.update_token_balances(uid)
        ok = await self.update_balance(uid)
        if ok == "no_wallet":
            await self.send_message(uid, "<b>No wallet found. Please create a wallet first.</b>")
            return

        text = await self.build_menu_text(uid)
        kb   = self.build_menu_kb()

        try:
            await self.application.bot.edit_message_text(
                chat_id=uid,
                message_id=self.menu_msg[uid],
                text=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except BadRequest:
            await self.show_menu(uid)

    async def cb_router(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        # Yes, could be done better, but it's not a big deal
        let = await self.guard(u, c)
        if not let:
            return

        if let[1] == "rate-limit":
            logging.info(f"User {u.effective_chat.username} ({u.effective_chat.id}) possible violation of rate limit.")
            return
        elif let[1] == "not-member":
            await self.send_retry_prompt(u.effective_chat.id)
            return

        q   = u.callback_query
        uid = q.from_user.id
        data = q.data or ""

        await q.answer()

        # MAIN MENU callbacks
        if data == "menu_refresh":
            await self.update_menu(uid)

        elif data == "menu_buy":
            await self.handle_buy(uid)

        elif data == "menu_sell":
            await self.handle_sell(uid)

        elif data == "menu_list_tokens":
            await self.handle_list_tokens(uid)

        elif data == "menu_settings":
            await self.open_settings(uid, q.message)

        elif data == "menu_withdraw":
            await self.handle_withdraw(uid, q.message)

        # SETTINGS callbacks
        elif data == "set_priority_level":
            await self.handle_set_priority_level(uid, q.message)

        elif data == "set_priority_level_low":
            await self.handle_set_priority_level(uid, q.message, "low")

        elif data == "set_priority_level_medium":
            await self.handle_set_priority_level(uid, q.message, "medium")

        elif data == "set_priority_level_high":
            await self.handle_set_priority_level(uid, q.message, "high")

        elif data == "set_priority_level_turbo":
            await self.handle_set_priority_level(uid, q.message, "turbo")

        elif data == "set_buy_slip":
            await self.handle_set_buy_slip(uid)

        elif data == "set_sell_slip":
            await self.handle_set_sell_slip(uid)

        # WITHDRAW callbacks
        elif data == "set_withdrawal_address":
            await self.handle_set_withdrawal_address(uid)

        elif data == "withdraw_sol":
            await self.handle_withdraw_sol(uid)

        elif data == "withdraw_tokens":
            await self.handle_withdraw_tokens(uid)

        # BURN callbacks
        elif data == "menu_burn_tokens":
            await self.handle_burn_tokens(uid)

        # RETRY (membership)
        elif data == "retry_access":
            await self.retry_callback(u, c)

    async def handle_burn_tokens(self, uid: int):
        self.awaiting[uid] = "burn_tokens"
        await self.send_message(
            uid,
            "<b>Enter token address and amount to burn.</b>",
            reply_markup=ForceReply(selective=True)
        )

    async def handle_buy(self, uid: int):
        self.awaiting[uid] = "buy"
        await self.send_message(
            uid,
            "<b>Enter mint address and SOL amount to spend.</b>\n"
            "<i>Example: Ey2zp...pump 0.01</i>",
            reply_markup=ForceReply(selective=True)
        )
        
    async def handle_sell(self, uid: int):
        self.awaiting[uid] = "sell"
        await self.send_message(
            uid,
            "<b>Enter mint address and percentage of token balance to sell.</b>\n"
            "<i>Example: Ey2zp...pump 100</i>",
            reply_markup=ForceReply(selective=True)
        )

    async def sf_get_token_info(self, mint: str):
        try:
            info = await self.router.router.get_token_info(mint, self.router.swaps.session)
            # {"program":str, "name":str, "symbol":str, "supply":str, "decimals":int}
            return info
        except Exception as e:
            logging.error(f"Error getting token info: {e}")
            return None

    async def handle_list_tokens(self, uid: int):
        try:
            s = await self.get_stats(uid) or {
                "pubkey": "",
                "balance": 0,
                "tokens": [],
                "priority_level": "high",
                "buy_slip": 0.0,
                "sell_slip": 0.0,
            }
            if not s:
                return
            # tokens: list[{"name":mint, "balance":float}]
            rows = []
            toks = s.get("tokens") or []
            for i, tok in enumerate(toks, 1):
                mint  = str(tok["name"])
                info = await self.sf_get_token_info(mint)
                if not info:
                    continue
                name = info.get("name", "Unknown")
                symbol = info.get("symbol", "Unknown")
                bal   = float(tok["balance"])
                bal = f"{bal}"
                price = await self.get_price(mint, tok["pool"], tok["dex"])
                if price:
                    price = f"Price: <code>{price:.10f} SOL</code>"
                else:
                    price = "Price: N/A"
                rows.append(
                    f"{i}) —————————————\nN: {name[:10] + '…' if len(name) > 10 else name}\nS: {symbol[:10] + '…' if len(symbol) > 10 else symbol}\n<code>{mint}</code>: {bal}\n{price}"
                )
            token_lines = "\n".join(rows) if rows else "<i>You don't have any tokens yet.</i>"

            await self.send_message(
                uid,
                f"<b>Tokens in your wallet:\n{token_lines}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Burn", callback_data="menu_burn_tokens")], [InlineKeyboardButton("⬅ Back", callback_data="menu_refresh")]]
                )
            )
        except Exception as e:
            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error listing tokens: {e}")
            traceback.print_exc()

    async def handle_withdraw(self, uid: int, msg):
        try:
            await msg.edit_text(
                "<b>Select below button to withdraw Solana $SOL or tokens, <i>make sure you have a valid withdrawal address or set one in settings</i></b>",
                reply_markup=self.build_withdraw_kb(),
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

    async def handle_withdraw_sol(self, uid: int):
        self.awaiting[uid] = "withdraw_sol"
        await self.send_message(
            uid, 
            "<b>Enter SOL amount to withdraw.</b>", 
            reply_markup=ForceReply(selective=True)
        )

    async def handle_withdraw_tokens(self, uid: int):
        self.awaiting[uid] = "withdraw_tokens"
        await self.send_message(
            uid, 
            "<b>Enter token address and amount to withdraw.</b>", 
            reply_markup=ForceReply(selective=True)
        )

    async def handle_set_priority_level(self, uid: int, msg, level: str = None):
        try:
            if level:
                await self.db_hook.update_priority_level(str(uid), level)
                await self.send_message(uid, f"<b>Priority Level set to {level}</b>")
                return

            await msg.edit_text(
                "<b>Select Priority Level</b>",
                reply_markup=self.build_priority_kb(),
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

    async def handle_set_withdrawal_address(self, uid: int, cmd = None):
        try:
            if cmd:
                address = cmd.strip()
                if not address or len(address) != 44:
                    await self.send_message(uid, "<b>Invalid input. Please enter a valid withdrawal address.</b>")
                    return
                
                await self.db_hook.update_withdrawal_address(str(uid), str(address))
                await self.send_message(uid, f"<b>Withdrawal address set to {address}</b>")
                return
            
            self.awaiting[uid] = "withdrawal_address"
            await self.send_message(
                uid,
                "<b>Enter your desired withdrawal address.</b>",
                reply_markup=ForceReply(selective=True)
            )
        except Exception as e:
            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error setting withdrawal address: {e}")
            traceback.print_exc()

    async def handle_set_buy_slip(self, uid: int, cmd: str = None):
        try:
            if cmd:
                await self.db_hook.update_buy_slip(str(uid), str(float(cmd)))
                await self.send_message(uid, f"<b>Buy Slippage set to {cmd}%</b>")
                return
            
            self.awaiting[uid] = "slip_buy"
            await self.send_message(
                uid,
                "<b>Enter your desired buy slippage percentage.</b>\n"
                "<i>Example: 10.5</i>",
                reply_markup=ForceReply(selective=True)
            )
        except Exception as e:
            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error setting buy slippage: {e}")
            traceback.print_exc()

    async def handle_set_sell_slip(self, uid: int, cmd: str = None):
        try:
            if cmd:
                await self.db_hook.update_sell_slip(str(uid), str(float(cmd)))
                await self.send_message(uid, f"<b>Sell Slippage set to {cmd}%</b>")
                return
            
            self.awaiting[uid] = "slip_sell"
            await self.send_message(
                uid,
                "<b>Enter your desired sell slippage percentage.</b>\n"
                "<i>Example: 10.5</i>",
                reply_markup=ForceReply(selective=True)
            )
        except Exception as e:
            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error setting sell slippage: {e}")
            traceback.print_exc()

    async def open_settings(self, uid: int, msg):
        try:
            await msg.edit_text(
                "<b>Select below button to change specific setting.\n\n<i>Priority Fee won't be higher than 0.01 SOL - even with Turbo, this is being paid directly to the validators to prioritize your transaction.</i></b>",
                reply_markup=self.build_settings_kb(),
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

    async def send_retry_prompt(self, cid: int):
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 Retry", callback_data="retry_access")]]
        )
        await self.send_message(
            cid,
            "<b>Welcome to Cobra 🐍</b>\n\n"
            "<b>⚠️ You must be a member of "
            f"{GROUP_CHAT_RETRY_MESSAGE} to gain access.</b>",
            reply_markup=keyboard,
        )

    async def retry_callback(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        q = u.callback_query
        await q.answer()
        uid = q.from_user.id

        if await self.is_member(uid):
            await self.db_hook.cache_user(str(uid), str(q.from_user.username))
            try:
                # Replace the old message so the user can’t press Retry again
                await q.edit_message_text("<b>✅ Access granted</b>")
                await self.handle_wallet(uid)
                await self.show_menu(uid)
            except BadRequest:
                pass # message was already edited / deleted
        else:
            # Still not a member – just refresh the button so they can try again
            try:
                await q.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🔄 Retry (again)", callback_data="retry_access")]]
                    )
                )
            except BadRequest:
                pass

    async def process_buy(self, uid: int, cmd: str):
        try:
            ok = await self.update_balance(uid)
            if ok == "no_wallet":
                await self.send_message(uid, "<b>No wallet found. Please create a wallet first.</b>")
                return
            mint, amount = cmd.split()
            mint, amount = str(mint), float(amount)
            if not mint or not amount:
                await self.send_message(uid, "<b>Invalid input. Please enter a valid mint address and amount.</b>")
                return
            
            dex, pool = await self.router.detect(mint, exclude_pools=self.exclude_pools)
            if not dex or not pool:
                await self.send_message(uid, "<b>No pool found. Please try again.</b>")
                return

            print(f"Dex: {dex}, Pool: {pool}")

            wallet = await self.db_hook.get_wallet(str(uid))
            if not wallet:
                await self.send_message(uid, "<b>Wallet not found. Please try again.</b>")
                return
            
            balance = float(wallet["balance"])
            if balance < amount + (RENT_EXEMPT*2 / 1e9):
                await self.send_message(uid, f"<b>Insufficient balance. There is <code>{balance:.4f}</code> SOL in your wallet, need: <code>{amount + (RENT_EXEMPT*2 / 1e9):.4f}</code> SOL.</b>")
                return
            
            slippage = wallet["buy_slip"]
            priority_level = wallet["priority_level"]
            keypair = Keypair.from_base58_string(wallet["privkey"])

            sig, ok = await self.router.swap(
                action="buy",
                mint=mint,
                pool=pool,
                sol_amount_in=amount,
                slippage=int(slippage),
                priority_level=priority_level,
                dex=dex,
                keypair=keypair,
            )
            if ok:
                await self.send_message(uid, f"<b>Transaction confirmed.</b>\n\n<b>Signature:</b> <a href='https://solscan.io/tx/{sig}'>{sig}</a>")
            elif sig == "replay":
                self.exclude_pools.append(pool)
                logging.info(f"Replaying buy with excluded pools: {self.exclude_pools}")
                await self.process_buy(uid, cmd)
            else:
                await self.send_message(uid, f"<b>Failure\n\n<i>{FAILURE_MSG}</i>\nSignature: <a href='https://solscan.io/tx/{sig}'>{sig}</a></b>")
            
            token_balance, ok = await self.router.swaps.get_balance(mint, keypair.pubkey())
            if ok == "success" and token_balance > 0:
                await self.db_hook.update_tokens(str(uid), [{"name": mint, "balance": token_balance, "dex": dex, "pool": pool}])
        except Exception as e:
            if "Priority fee is too high" in str(e):
                await self.send_message(uid, f"<b>Priority fee is too high (over 0.01 SOL). Please try again with a lower priority level.</b>")
                return

            elif "Simulation failed" in str(e):
                await self.send_message(uid, f"<b>Simulation failed. Please reach out to support. Err: <i>{e}</i></b>")
                return
            
            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error processing buy: {e}")
            traceback.print_exc()

    async def process_sell(self, uid: int, cmd: str):
        try:
            ok = await self.update_balance(uid)
            if ok == "no_wallet":
                await self.send_message(uid, "<b>No wallet found. Please create a wallet first.</b>")
                return
            mint, pct = cmd.split()
            mint, pct = str(mint.lstrip()), int(pct.lstrip().replace("%", ""))
            if not mint or not pct:
                await self.send_message(uid, "<b>Invalid input. Please enter a valid mint address and percentage.</b>")
                return
            if pct < 0 or pct > 100:
                await self.send_message(uid, "<b>Invalid input. Please enter a valid percentage (0-100).</b>")
                return
            
            dex, pool = await self.router.detect(mint, exclude_pools=self.exclude_pools)
            if not dex or not pool:
                await self.send_message(uid, "<b>No pool found. Please try again.</b>")
                return

            wallet = await self.db_hook.get_wallet(str(uid))
            if not wallet:
                await self.send_message(uid, "<b>Wallet not found. Please try again.</b>")
                return
            
            slippage = wallet["sell_slip"]
            priority_level = wallet["priority_level"]
            keypair = Keypair.from_base58_string(wallet["privkey"])

            sig, ok = await self.router.swap(
                action="sell",
                sell_pct=pct,
                mint=mint,
                pool=pool,
                slippage=int(slippage),
                priority_level=priority_level,
                dex=dex,
                keypair=keypair,
            )
            if ok:
                await self.send_message(uid, f"<b>Transaction confirmed.</b>\n\n<b>Signature:</b> <a href='https://solscan.io/tx/{sig}'>{sig}</a>")
            elif sig == "replay":
                self.exclude_pools.append(pool)
                logging.info(f"Replaying sell with excluded pools: {self.exclude_pools}")
                await self.process_sell(uid, cmd)
            else:
                await self.send_message(uid, f"<b>Failure\n\n<i>{FAILURE_MSG}</i>\nSignature: <a href='https://solscan.io/tx/{sig}'>{sig}</a></b>")

            token_balance, ok = await self.router.swaps.get_balance(mint, keypair.pubkey())
            if token_balance == 0:
                await self.db_hook.remove_token(str(uid), mint)
                return

            if ok != "success":
                await self.send_message(uid, f"<b>Error: {ok} | Contact support if this persists.</b>")
                return

            await self.db_hook.update_tokens(str(uid), [{"name": mint, "balance": token_balance, "dex": dex, "pool": pool}])

        except Exception as e:
            if "Priority fee is too high" in str(e):
                await self.send_message(uid, f"<b>Priority fee is too high (over 0.01 SOL). Please try again with a lower priority level.</b>")
                return

            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error processing sell: {e}")
            traceback.print_exc()

    async def process_withdraw_sol(self, uid: int, cmd: str):
        try:
            amount = float(cmd)
            if amount <= 0:
                await self.send_message(uid, "<b>Invalid input. Please enter a valid amount.</b>")
                return
            
            wallet = await self.db_hook.get_wallet(str(uid))
            if not wallet:
                await self.send_message(uid, "<b>Wallet not found. Please try again.</b>")
                return
            
            withdraw_to = wallet["withdraw_to"]
            if not withdraw_to:
                await self.send_message(uid, "<b>No withdrawal address set. Please set a withdrawal address in settings first.</b>")
                return

            balance = float(wallet["balance"])
            if balance < amount + (RENT_EXEMPT / 1e9):
                await self.send_message(uid, f"<b>Insufficient balance for RENT EXEMPT: {RENT_EXEMPT / 1e9} SOL. There is <code>{balance:.4f}</code> SOL in your wallet.</b>")
                return
            
            priority_level = wallet["priority_level"]

            sig, ok = await self.router.swaps.send_transfer(
                keypair=Keypair.from_base58_string(wallet["privkey"]),
                mint="So11111111111111111111111111111111111111112",
                amount=amount,
                to=withdraw_to,
                priority_fee_level=priority_level,
            )
            if ok:
                await self.send_message(uid, f"<b>Transaction confirmed.</b>\n\n<b>Signature:</b> <a href='https://solscan.io/tx/{sig}'>{sig}</a>")
            else:
                await self.send_message(uid, f"<b>Failure\n\n<i>{FAILURE_MSG}</i>\nSignature: <a href='https://solscan.io/tx/{sig}'>{sig}</a></b>")
        except Exception as e:
            logging.error(f"Error processing SOL withdraw: {e}")
            traceback.print_exc()

    async def get_price(self, mint: str, pool: str, dex: str):
        try:
            price = await self.router.swaps.get_price(mint, pool, dex)
            if not price:
                return None

            return price
        except Exception as e:
            logging.error(f"Error getting price: {e}")
            traceback.print_exc()
            return None

    async def process_withdraw_tokens(self, uid: int, cmd: str):
        try:
            mint, amount = cmd.split()
            mint, amount = str(mint.lstrip()), float(amount.lstrip())

            if not mint or not amount:
                await self.send_message(uid, "<b>Invalid input. Please enter a valid mint address and amount.</b>")
                return
            
            wallet = await self.db_hook.get_wallet(str(uid))
            if not wallet:
                await self.send_message(uid, "<b>Wallet not found. Please try again.</b>")
                return
            
            withdraw_to = wallet["withdraw_to"]
            if not withdraw_to:
                await self.send_message(uid, "<b>No withdrawal address set. Please set a withdrawal address in settings first.</b>")
                return

            balance = float(wallet["balance"])
            if balance <= RENT_EXEMPT / 1e9:
                await self.send_message(uid, f"<b>Insufficient balance to cover gas fees for RENT EXEMPT: {RENT_EXEMPT / 1e9} SOL. There is <code>{balance:.4f}</code> SOL in your wallet.</b>")
                return
            
            keypair = Keypair.from_base58_string(wallet["privkey"])
            token_balance, ok = await self.router.swaps.get_balance(mint, keypair.pubkey())
            if ok != "success":
                await self.send_message(uid, f"<b>Error: {ok} | Contact support if this persists.</b>")
                return
            
            if not token_balance or token_balance == 0:
                await self.send_message(uid, f"<b>Token not found in your wallet. Please try again.</b>")
                return
            
            if float(token_balance) < float(amount):
                await self.send_message(uid, f"<b>Insufficient balance. There is <code>{token_balance}</code> of {mint} in your wallet, need: <code>{amount}</code>.</b>")
                return
            
            priority_level = wallet["priority_level"]
            sig, ok = await self.router.swaps.send_transfer(
                keypair=keypair,
                mint=mint,
                amount=amount,
                to=withdraw_to,
                priority_fee_level=priority_level,
            )
            if ok:
                await self.send_message(uid, f"<b>Transaction confirmed.</b>\n\n<b>Signature:</b> <a href='https://solscan.io/tx/{sig}'>{sig}</a>")
                if token_balance == amount: # if all tokens are withdrawn, remove the token from the database
                    await self.db_hook.remove_token(str(uid), mint)
                else:
                    await self.db_hook.update_tokens(str(uid), [{"name": mint, "balance": float(token_balance) - float(amount)}])
            else:
                await self.send_message(uid, f"<b>Failure\n\n<i>{FAILURE_MSG}</i>\nSignature: <a href='https://solscan.io/tx/{sig}'>{sig}</a></b>")
        except Exception as e:
            if hasattr(e, "message") and "0x1" in e.message:
                await self.send_message(uid, f"<b>You don't have this much token. Please try again.</b>")
                return
            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error processing token withdraw: {e}")
            traceback.print_exc()
            
    async def process_burn_tokens(self, uid: int, cmd: str):
        try:
            if len(cmd) < 44:
                await self.send_message(uid, "<b>Invalid input. Please enter a valid mint address.</b>")
                return
            
            mint = cmd[:44]
            amount = float(cmd[44:].lstrip())

            if not mint:
                await self.send_message(uid, "<b>Invalid input. Please enter a valid mint address and amount to burn.</b>")
                return

            wallet = await self.db_hook.get_wallet(str(uid))
            if not wallet:
                await self.send_message(uid, "<b>Wallet not found. Please try again.</b>")
                return

            tokens = wallet["tokens"]
            if not tokens:
                await self.send_message(uid, "<b>No tokens found. Please try again.</b>")
                return

            if not any(t["name"] == mint for t in tokens):
                await self.send_message(uid, f"<b>Token not found in your wallet. Please try again.</b>")
                return

            if amount > 0:
                decimals = await self.router.router.get_decimals(mint)
                if not decimals:
                    await self.send_message(uid, f"<b>Failed to get decimals for {mint}. Please try again.</b>")
                    return

                amount = int(amount * 10 ** decimals)
            
            sig, ok = await self.cleaner.close_token_accounts(self.router.async_client, Keypair.from_base58_string(wallet["privkey"]), mint, amount, decimals)
            if ok:
                await self.send_message(uid, f"<b>Burn transaction sent: <a href='https://solscan.io/tx/{sig}'>{sig}</a></b>")
            else:
                await self.send_message(uid, f"<b>Failure: <a href='https://solscan.io/tx/{sig}'>{sig}</a></b>")

        except Exception as e:
            if hasattr(e, "message"):
                if "0x1" in e.message:
                    await self.send_message(uid, f"<b>You don't have this much token. Please try again.</b>")
                    return

            if "token account does not exist" in str(e):
                await self.send_message(uid, f"<b>Token account does not exist.</b>")
                await self.db_hook.remove_token(str(uid), mint)
                return

            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.error(f"Error processing token burn: {e}")
            traceback.print_exc()

    async def dispatcher(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        try:
            let = await self.guard(u, c)
            if not let:
                return

            uid  = u.effective_chat.id
            cmd = u.effective_message.text
            if not cmd:
                return

            if let[1] == "rate-limit":
                logging.info(f"User {u.effective_chat.username} ({u.effective_chat.id}) possible violation of rate limit.")
                return
            elif let[1] == "not-member":
                await self.send_retry_prompt(u.effective_chat.id)
                return
            elif not let[0]:
                return

            cmd = cmd.strip()

            if uid in self.awaiting:
                action = self.awaiting.pop(uid)

                if action == "buy":
                    await self.process_buy(uid, cmd)
                elif action == "sell":
                    await self.process_sell(uid, cmd)
                elif action == "slip_buy":
                    await self.handle_set_buy_slip(uid, cmd)
                elif action == "slip_sell":
                    await self.handle_set_sell_slip(uid, cmd)
                elif action == "withdrawal_address":
                    await self.handle_set_withdrawal_address(uid, cmd)
                elif action == "withdraw_sol":
                    await self.process_withdraw_sol(uid, cmd)
                elif action == "withdraw_tokens":
                    await self.process_withdraw_tokens(uid, cmd)
                elif action == "burn_tokens":
                    await self.process_burn_tokens(uid, cmd)
                await self.update_menu(uid)
                return 

            if cmd.startswith("/"):
                await self.handle_command(u, c)
            elif cmd == "retry_access":
                logging.info(f"User {u.effective_chat.username} ({u.effective_chat.id}) requested to retry access.")
                await self.retry_callback(u, c)
        except Exception as e:
            uid  = u.effective_chat.id
            await self.send_message(uid, f"<b>Unexpected error happened, please contact support or try again.</b>")
            logging.info(f"Error in dispatcher: {e}")
            traceback.print_exc()

    async def run(self):
        try:
            con = await self.db_hook.connect()
            if not con:
                logging.error("Failed to connect to database. Initialize the database first.")
                return
            self.wallets = CobraWallets(self.db_hook.pool)

            self.application.add_handler(MessageHandler(filters.ALL, self.dispatcher), group=-1)
            self.application.add_handler(CallbackQueryHandler(self.cb_router))

            await self.start()

        except Exception as e:
            logging.error(f"Error starting bot: {e}")

async def test():
    cobra_net = CobraNET(BOT_TOKEN)
    await cobra_net.run()

if __name__ == "__main__":
    asyncio.run(test())