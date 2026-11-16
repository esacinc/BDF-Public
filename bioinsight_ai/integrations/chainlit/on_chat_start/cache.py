from pathlib import Path

# Directory and filename used to store a serialized Chainlit Message produced by the LLM.
# We place the cache in a `.cache` directory next to this module to avoid littering the source tree.
CACHE_DIRNAME = ".cache"
CACHE_FILENAME = "serialized_chainlit_message.json"


def get_cache_path() -> Path:
    """Return a Path to the cache file inside a `.cache` directory next to this module.

    Ensures the `.cache` directory exists when called.
    """
    module_dir = Path(__file__).resolve().parent
    cache_dir = module_dir / CACHE_DIRNAME
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If directory creation fails for any reason, return the intended path anyway.
        # Callers should handle IO errors when writing to the file.
        pass

    return cache_dir / CACHE_FILENAME
