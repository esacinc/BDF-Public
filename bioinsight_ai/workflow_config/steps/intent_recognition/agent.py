import asyncio
from config import (
    AWS_ACCESS_KEY,
    AWS_REGION,
    AWS_SECRET_KEY,
    CONTEXT_KB_ID
)
from workflow_config.default_settings import Settings
from workflow_config.steps.intent_recognition.context_augmented_intent_recognition import (
    ContextAugmentedIntentRecognitionAgent
)
from workflow_config.steps.intent_recognition.context_prompts import query_dict
from workflow_config.steps.intent_recognition.intent import Intent
from workflow_config.steps.intent_recognition.prompts.system_prompt import system_prompt
from workflow_config.steps.intent_recognition.prompts.user_query_template import  USER_QUERY_TEMPLATE
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.retrievers.bedrock import AmazonKnowledgeBasesRetriever
from llama_index.llms.bedrock_converse import BedrockConverse
from types import MethodType
from log_helper.logger import get_logger
logger = get_logger()

# Data source metadata knowledge base
contextKB = AmazonKnowledgeBasesRetriever(
    knowledge_base_id=CONTEXT_KB_ID,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
    retrieval_config={
        "vectorSearchConfiguration": {
            "overrideSearchType": "HYBRID"
        }
    },
)

response_synthesizer = get_response_synthesizer(
    response_mode="compact"
)

# Structured output that produces an Intent class output. See Intent module for more details about
# output and configuration 
#sllm = Settings.fast_llm.as_structured_llm(Intent)
sllm = Settings.fast_llm.as_structured_llm(Intent)

# `Intent` tool is defined automatically by LlamaIndex StructuredLLM, only need to define output_cls
def extend_prepare_chat_with_tools(llm_instance: BedrockConverse):
    """
    Monkey-patches the `_prepare_chat_with_tools` method of the underlying BedrockConverse LLM
    to always invoke the 'Intent' tool by setting `tool_choice` and `tool_choice_required`. See
    https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolChoice.html for more detail.
    
    Intended for use in custom agents to enforce tool usage, where the 'Intent' tool is defined. 
    """
    
    original_method = llm_instance._prepare_chat_with_tools
    
    def wrapped_prepare_chat_with_tools(self, **kwargs):
        # Inject or override the tool parameters
        kwargs["tool_required"] = True
        kwargs["tool_choice"] = {"tool": {"name": "Intent"}}
        payload = original_method(**kwargs)
        return payload
    
    llm_instance._prepare_chat_with_tools = MethodType(wrapped_prepare_chat_with_tools, llm_instance)
    
async def create_intent_agent(session_id: str):
    logger.info('Augmenting intent agent memory')
    agent = await ContextAugmentedIntentRecognitionAgent.from_defaults(
        contextKB=contextKB,
        response_synthesizer=response_synthesizer,
        context_retrieval_prompts=query_dict,
        force_refresh=False,
        context_cache="./workflow_config/steps/intent_recognition/context_cache.json",      
        system_prompt=system_prompt,  
        llm=sllm,
        session_id=session_id
    )
    # Patch the BedrockConverse inside StructuredLLM inside StructuredIntentChatEngine
    extend_prepare_chat_with_tools(agent._chat_engine._llm.llm)
    return agent