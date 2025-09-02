from log_helper.logger import get_logger
logger = get_logger()
from typing import Optional
from llama_index.llms.bedrock_converse.base import BedrockConverse
import tiktoken

def check_token_limit(
    llm: BedrockConverse,
    text: str,
    threshold: float = 0.8
) -> Optional[str]:
    """
    Checks if the token count of the input text exceeds a threshold of the LLM's context window.

    Args:
        llm (BedrockConverse): The LLM instance with metadata.
        text (str): The text to evaluate.
        threshold (float): Proportion of the context window to allow (default is 0.8).

    Returns:
        Optional[str]: A warning message if the token count exceeds the threshold, otherwise None.
    """
    model_name = llm.metadata.model_name
    context_window = llm.metadata.context_window

    try:
        tokenizer = tiktoken.encoding_for_model(model_name)
    except KeyError:
        tokenizer = tiktoken.get_encoding("cl100k_base")  # Fallback tokenizer

    token_count = len(tokenizer.encode(text))

    if token_count > threshold * context_window:
        msg = f"""⚠️ The retrieved data contains approximately {token_count} tokens, which exceeds
            {int(threshold * 100)}% of the context window for model '{model_name}'
            (max {context_window} tokens). This may result in incomplete processing or errors.\n\n
            Please try to reduce the amount of information requested, or consider summarizing the data before passing it to the model."""
        logger.warning(f"[Token Limit] {msg}")
        return msg

    return None
