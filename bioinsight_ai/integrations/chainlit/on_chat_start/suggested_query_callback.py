"""Register one callback per suggested query.

We map each distinct `payload['query']` from the cached opening message to the
same handler by using the raw query text as the Action `name`. Chainlit then
shows that query as the thread name in the sidebar on first click—workaround
to avoid a generic placeholder name.
"""
from typing import Callable, Awaitable, Any
from chainlit.config import config
from chainlit.utils import wrap_user_function

from integrations.chainlit.on_chat_start.salutation import Salutation

def _load_queries() -> list[str]:
    """Load distinct query strings via Salutation helper."""
    salutation = Salutation()
    data = salutation.greeting_dict
    if not data:
        return []
    actions = data.get("actions", [])
    queries: list[str] = []
    seen: set[str] = set()
    if isinstance(actions, list):
        for a in actions:
            if not isinstance(a, dict):
                continue
            payload = a.get("payload") or {}
            query = payload.get("query")
            if isinstance(query, str):
                q = query.strip()
                if not q or q in seen:
                    continue
                seen.add(q)
                queries.append(q)
    return queries


def suggested_query_callback() -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator factory registering a handler for each query.

    Returns a decorator that, when applied to a function expecting an Action,
    registers that function for every query in the cache using the raw query
    string as the action name.
    """
    queries = _load_queries()

    def decorator(func: Callable[..., Awaitable[Any]]):
        wrapped = wrap_user_function(func, with_task=False)
        for q in queries:
            # Avoid overwriting an existing callback of same name.
            if q not in config.code.action_callbacks:
                config.code.action_callbacks[q] = wrapped
        return func

    return decorator
