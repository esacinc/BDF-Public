from llama_index.core.prompts import RichPromptTemplate

MATCH_PROMPT_TEMPLATE = RichPromptTemplate(
    """
    {% chat role="user" %}
    We are mapping a user's dataset (source) to an established {{match_type}} (target).
    The user requested to see more matches for the following source columns:
    {{source_columns}}

    We provided the following ranked {{match_type}} matches:
    <Start Matches>
    {{ranked_matches}}
    <End Matches>

    The user responded with:
    \"\"\"{{user_feedback}}\"\"\"

    The current {match_type} matches are:
    {{current_matches}}

    Based on this information, determine whether the user wants to:
    - Keep the current mappings (do nothing), or
    - Modify one or more mappings.

    If modifications are needed, return an updated {{match_type}} match in the following format:

    ```json
    {{current_matches}}
    ```
    If no changes are needed, return an empty list: []
    Only return the JSON list. Do not include any explanation.
    {% endchat %}
    """
    )