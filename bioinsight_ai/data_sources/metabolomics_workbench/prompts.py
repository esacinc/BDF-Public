from llama_index.core.prompts import PromptTemplate

# must have to_agent and reason for validation
DEFAULT_HANDOFF_OUTPUT_PROMPT = PromptTemplate(
    """Agent {to_agent} is now handling the request due to the following reason: {reason}."
    IMPORTANT: This is your primary task:
    "\"{request}\"
    Please continue with this request, using any prior context as needed."""
)
