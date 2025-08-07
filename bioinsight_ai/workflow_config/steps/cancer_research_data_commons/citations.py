from log_helper.logger import get_logger
logger = get_logger()
import re
from typing import Set, List
from llama_index.core.chat_engine.types import AgentChatResponse

def hyperlink_urls(text: str) -> str:
    """Converts URLs in the input text into Markdown-style hyperlinks."""
    url_pattern = re.compile(r"(https?://[^\s]+)")
    return url_pattern.sub(r"\1", text)

def extract_unique_metadata_values(response: AgentChatResponse, key: str) -> List[str]:
    """Extracts unique values for a given key from source metadata."""
    seen: Set[str] = set()
    ordered_values = []

    sources = getattr(response, "sources", [])
    for source in sources:
        raw_output = getattr(source, "raw_output", None)
        if not raw_output:
            continue
        metadata = getattr(raw_output, "metadata", {})
        if not isinstance(metadata, dict):
            continue
        for value in metadata.values():
            if not isinstance(value, dict):
                continue
            item = value.get("sourceMetadata", {}).get(key)
            if item and isinstance(item, str) and item not in seen:
                seen.add(item)
                ordered_values.append(item)

    return ordered_values

def format_list_section(title: str, items: List[str]) -> str:
    """Formats a list of items into a numbered section with a title."""
    if not items:
        return ""
    linked_items = [hyperlink_urls(item) for item in items]
    return f"{title}:\n" + "\n".join(f"{i + 1}. {item}" for i, item in enumerate(linked_items))

def add_citations_and_journal_urls(response: AgentChatResponse) -> AgentChatResponse:
    """Appends formatted citations and journal URLs to the response text."""
    try:
        citations = extract_unique_metadata_values(response, "citation")
        journal_urls = extract_unique_metadata_values(response, "journal_url")

        sections = [
            format_list_section("Citations", citations),
            format_list_section("Journal URLs", journal_urls)
        ]

        combined_sections = "\n\n".join(filter(None, sections))
        if combined_sections:
            original_response = getattr(response, 'response', '')
            if not isinstance(original_response, str):
                original_response = str(original_response)
            response.response = f"{original_response}\n\n{combined_sections}"
    except Exception as e:
        logger.warning(f"[CRDC Step] Citations requested but none were added due to: {str(e)}")
        pass

    return response
