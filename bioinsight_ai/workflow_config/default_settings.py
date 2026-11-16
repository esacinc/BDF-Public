from llama_index.core.settings import Settings
from config import DEFAULT_MODEL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
from llama_index.llms.bedrock_converse.base import BedrockConverse

llm = BedrockConverse(
    model=DEFAULT_MODEL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
    max_tokens=15000,
    timeout=600.0,
    system_prompt_caching=True,
    tool_caching=True,
    additional_kwargs={"additionalModelRequestFields": 
        {"anthropic_beta": ["context-1m-2025-08-07"]}
    }
)

thinking_llm = BedrockConverse(
    model=DEFAULT_MODEL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
    max_tokens=20000,
    timeout=600.0,
    temperature=1.0, # required for extended thinking,
    thinking={'type': 'enabled', 'budget_tokens': 2000},
    system_prompt_caching=True
)

Settings.llm = llm
Settings.thinking_llm = thinking_llm