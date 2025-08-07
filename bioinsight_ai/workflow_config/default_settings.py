from llama_index.core.settings import Settings
from config import DEFAULT_MODEL, AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, FAST_MODEL
from llama_index.llms.bedrock_converse.base import BedrockConverse

llm = BedrockConverse(
    model=DEFAULT_MODEL,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
    max_tokens=8192
)

fast_llm = BedrockConverse(
    model=FAST_MODEL,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
    max_tokens=8192
)

Settings.llm = llm
Settings.fast_llm = fast_llm