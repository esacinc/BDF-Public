"""
Parse example queries from a markdown file (default: chainlit.md).
"""

import os
import re
from typing import List

_ITALIC_RE = re.compile(r"(?<=-\s_)(.*?)(?=_\s*$)", re.S | re.M)


def parse_example_queries(path: str | None = None, mdfile: str = "chainlit.md") -> List[str]:
    """Read a markdown file and return example queries formatted as '- _..._'.

    Args:
        path: Optional explicit directory that contains the markdown file. If
            omitted, the function will dynamically walk parent directories from
            this file until it finds the `bioinsight_ai` package root and use
            that as the base directory.
        mdfile: Filename to read (default: "chainlit.md"). Absolute paths are
            used as-is.
    """

    def _detect_bioinsight_root() -> str:
        """Ascend parent directories until `bioinsight_ai` is found.

        Returns:
            Absolute path to the `bioinsight_ai` directory.

        Raises:
            RuntimeError: If the directory cannot be located (e.g. code moved
                outside expected package layout).
        """

        cur = os.path.abspath(__file__)
        cur = os.path.dirname(cur)
        while True:
            if os.path.basename(cur) == "bioinsight_ai":
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:  # Reached filesystem root
                raise RuntimeError(
                    "Could not locate 'bioinsight_ai' directory above parse_examples.py"
                )
            cur = parent

    base_dir = path or _detect_bioinsight_root()
    md_path = mdfile if os.path.isabs(mdfile) else os.path.join(base_dir, mdfile)

    if not os.path.exists(md_path):
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    with open(md_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)

    matches = _ITALIC_RE.findall(text)

    seen = set()
    results: List[str] = []
    for m in matches:
        s = m.strip()
        if s and s not in seen:
            seen.add(s)
            results.append(s)

    return results

if __name__ == "__main__":
    example_queries = parse_example_queries()
    for i, q in enumerate(example_queries):
        print(f"{i + 1}) {q}")