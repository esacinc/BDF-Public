"""
Chainlit on_chat_start helpers for BioInsight.

This package contains the opening-message generator, cache handling, and
helpers to deserialize the cached JSON into Chainlit Message/Action objects.
"""

from .opening_message import generate_opening_message, read_cached_salutation, write_cached_salutation
from .greeting import greeting
from .salutation import Salutation
from .suggested_query_callback import suggested_query_callback

__all__ = [
    "generate_opening_message",
    "read_cached_salutation",
    "write_cached_salutation",
    "greeting",
    "Salutation",
    "suggested_query_callback"
]
