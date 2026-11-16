"""Generate and cache the BioInsight opening message.

This module prompts an LLM to produce a short opening message formatted as
JSON that can be deserialized into a Chainlit Message (with Action objects
created from README example queries). The produced JSON is written to a
cache file for faster subsequent startup.

Public helpers:
- read_cached_salutation() -> Optional[dict]: read the cached parsed JSON.
- write_cached_salutation(text: str) -> None: validate and write JSON text.
- generate_opening_message() -> Optional[str]: drive the LLM prompt and
    update the cache; retries automatically when the LLM output isn't valid JSON.
"""

import asyncio
import json
import uuid
from typing import Optional, Dict, Any

from llama_index.core.prompts import RichPromptTemplate
from llama_index.core.workflow import Context

from bioinsight_workflow import bioinsight_session

from integrations.chainlit.on_chat_start.cache import get_cache_path
from integrations.chainlit.on_chat_start.parse_examples import parse_example_queries
from integrations.chainlit.on_chat_start.salutation import Salutation

EXAMPLE_OUTPUT = """
<answer>
    {
    "message": "# Hello! I'm BioInsight 👋\n\nI'm your biomedical research assistant, designed to help you discover and analyze data from major public research repositories...\n\nHow can I assist you today?",
    "actions": [
        {
        "label": "Pan-Cancer data analysis challenges",
        "tooltip": "What are the analytical challenges in performing a pan-cancer analysis?",
        "payload": {
            "query": "What are the analytical challenges in performing a pan-cancer analysis?"
        },
        "icon": "dna"
        }
    ]
    }
</answer>
"""

OUTPUT_FORMAT = """
<answer>
    {
    "message": "<Welcome message text, including capabilities and limitations>",
    "actions": [
        {
        "label": "<abbreviated label for the action button without emojis>",
        "tooltip": "<Full example query>",
        "payload": {
            "query": "<Full example query>"
        },
        "icon": "<optional lucid icon name, exclude if none>"
        }
    ]
    }
</answer>
"""

PROMPT = RichPromptTemplate(
    """
    Generate a friendly opening message and introduce yourself as BioInsight.
    
    Start by reviewing each of the available agents, descriptions, and tools. Then construct an opening message with the following specifications:

    CAPABILITIES TO MENTION:
    - Biomedical research assistance
    - Discovery and analysis from public research repositories
    - For each research repository mention a bit of information about capabilities related to that data source by identifying which agents can access it and those agents' capabilities

    LIMITATIONS TO EXPLICITLY STATE:
    - Access to specified data sources only
    - No access to private or proprietary data
    - Uncertainty in responses
    - Potential for mistakes

    OUTPUT FORMAT:
    {{ output_format }}

    EXAMPLE OUTPUT:
    {{ example_output }}

    EXAMPLE QUERIES FOR ACTIONS:
    Select a six example queries from the following list that highlight BioInsight's diverse capabilities and highlight different data sources. You may ONLY select from these queries, and you MUST format them as specified above in the OUTPUT FORMAT section.
    {% for q in example_queries %}
    - {{ q }}
    {% endfor %}

    {% if cached_salutation %}
    CURRENT INTRODUCTION:
    {{ cached_salutation }}

    If this introduction is sufficient and includes all required capabilities and limitations, return it unchanged. Otherwise, amend it to add missing or updated information.
    {% endif %}
    
    You MUST answer this query directly.
    """
)

RETRY_PROMPT = RichPromptTemplate(
    """
    Your previous response failed to produce valid JSON.

    ORIGINAL FORMAT REQUIREMENT:
    {{ output_format }}

    EXAMPLE OF CORRECT OUTPUT:
    {{ example_output }}

    YOUR PREVIOUS ATTEMPT:
    {{ attempt }}

    ERROR ENCOUNTERED:
    {{ error_message }}

    INSTRUCTIONS FOR RETRY:
    1. Analyze the error message above to identify the JSON syntax issue
    2. Generate corrected JSON that matches the required format exactly
    3. Wrap your JSON response in <answer></answer> tags
    4. Inside the answer tags, include ONLY valid JSON (no markdown, no code fences, no explanatory text)
    5. Ensure all JSON syntax is valid (proper quotes, commas, brackets, escape characters)

    Format your response exactly like this:
    <answer>
    {
    "message": "...",
    "actions": [...]
    }
    </answer>

    Output your corrected response now:
    """
)


def read_cached_salutation() -> Optional[Dict[str, Any]]:
    """Compatibility wrapper that reads the cached salutation via Salutation.

    Delegates to Salutation.read_cached_salutation so callers can migrate.
    """

    return Salutation.read_cached_salutation()


def write_cached_salutation(text: str) -> None:
    """Validate and write the given JSON text to the cache file.

    Raises json.JSONDecodeError if text isn't valid JSON.
    """

    p = get_cache_path()
    obj = json.loads(text)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


async def generate_opening_message() -> Optional[str]:
    """Generate the opening message, inject cached salutation, and update cache.

    Retries up to 3 times when the LLM output isn't valid JSON.
    """

    cached_salutation = read_cached_salutation()
    try:
        example_queries = parse_example_queries()
    except Exception:
        # error but still write cache so downstream not impacted
        write_cached_salutation("{}")
        raise

    session = None
    try:
        session = await bioinsight_session(session_id=str(uuid.uuid4()))
        ctx = Context(session)

        prompt = PROMPT.format(
            cached_salutation=cached_salutation or None, 
            example_queries=example_queries or None,
            output_format=OUTPUT_FORMAT,
            example_output=EXAMPLE_OUTPUT)

        response = await session.run(query=prompt, ctx=ctx)

        tries = 1
        while True:
            salutation = response.get("response", "")
            try:
                write_cached_salutation(salutation)
                return salutation
            except Exception as exc:
                if tries >= 3:
                    write_cached_salutation("{}") # empty JSON
                    return None

                retry_prompt = RETRY_PROMPT.format(
                    output_format=OUTPUT_FORMAT,
                    example_output=EXAMPLE_OUTPUT,
                    attempt=salutation,
                    error_message=str(exc),
                )
                response = await session.run(query=retry_prompt, ctx=ctx)
                tries += 1
    finally:
        try:
            if session is not None:
                mcp_info = await session.unregister_mcp(client_name="Biomni")
        except Exception:
            pass


if __name__ == "__main__":
    async def _main():
        salutation = await generate_opening_message()
        print(f"Opening message generated:\n{salutation}")

    asyncio.run(_main())
