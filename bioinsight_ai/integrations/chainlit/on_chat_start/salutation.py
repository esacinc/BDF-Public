"""Salutation helper: read cached JSON and deserialize to Chainlit Message.

Provides a Salutation class which reads the cache on init and exposes a
deserialize_chainlit_message() method to build a chainlit.Message with
optional Action objects.
"""

import json
from typing import Optional, Dict, Any
from chainlit import Message, Action
from integrations.chainlit.on_chat_start.cache import get_cache_path

class Salutation:
    def __init__(self) -> None:
        self.greeting_dict: Optional[Dict[str, Any]] = self.read_cached_salutation()

    @staticmethod
    def read_cached_salutation() -> Optional[Dict[str, Any]]:
        """Return the cached greeting dictionary, if available.

        Attempts to open and parse the cache JSON file. Any exception (file not
        found, JSON decode error, unexpected structure) results in a None
        return so callers can treat absence uniformly.

        Returns:
            A non-empty dict if a valid cached greeting exists, otherwise None.
        """
        p = get_cache_path()
        try:
            with p.open("r", encoding="utf-8") as fh:
                obj = json.load(fh)
            if isinstance(obj, dict) and obj:
                return obj
            return None
        except Exception:
            return None

    def deserialize_chainlit_message(self) -> Optional[Message]:
        """Deserialize cached greeting into a `Message` with per-query action names."""
        if self.greeting_dict is None:
            return None

        obj = self.greeting_dict
        message_text = obj.get("message", "")
        actions_raw = obj.get("actions", [])
        actions = []
        if isinstance(actions_raw, list):
            for a in actions_raw:
                try:
                    payload = a.get("payload", {}) or {}
                    query = payload.get("query")
                    if query:
                        a["name"] = query  # Raw query becomes action name.
                    else:
                        # Fallback: use label if present.
                        label = a.get("label")
                        if label:
                            a["name"] = label
                        else:
                            # Skip if we can't derive a stable name.
                            continue
                    actions.append(Action.from_dict(a))
                except Exception:
                    continue

        return Message(content=message_text or "", actions=actions or None)
