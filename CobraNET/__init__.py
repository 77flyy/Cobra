"""
    CobraNET is an addon to the router; Telegram bot that allows you to manage your Cobra wallet and perform various actions such as buying, selling, and withdrawing tokens.
    It's basically a wrapper around CobraRouter module.
"""

from .main import CobraNET
from .db_hook import TGDBHook

__all__ = ["CobraNET", "TGDBHook"]