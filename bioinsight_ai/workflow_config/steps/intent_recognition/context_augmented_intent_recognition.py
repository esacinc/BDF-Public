import asyncio
import json
import time
import os
from workflow_config.steps.intent_recognition.structured_intent_chat_engine import StructuredIntentChatEngine
from llama_index.core.memory import Memory
from llama_index.core.memory.memory_blocks import StaticMemoryBlock
from llama_index.core.prompts import ChatMessage
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import BaseSynthesizer
from llama_index.retrievers.bedrock import AmazonKnowledgeBasesRetriever
from log_helper.logger import get_logger
logger = get_logger()

DEFAULT_SYSTEM_PROMPT = ChatMessage(role="system", content = 
    """
    You are a context-aware agent designed to chat with a user about their context.
    """
)

DEFAULT_CONTEXT_RETRIEVAL_PROMPT= {
    'general_info': ChatMessage(
    """
    Provide a comprehensive summary of the data sources available focusing on what they specialize and compare and contrast them.
    """
    )
}

DEFAULT_TOKEN_LIMIT = 300000

class ContextAugmentedIntentRecognitionAgent:
    """
        A chat engine that augments intent recognition with contextual knowledge retrieved
        from an external knowledge base. This class extends `SimpleChatEngine` by injecting
        static context into the memory using a retriever and synthesizer.
        Uses StructuredIntentChatEngine internally to guarantee safe structured output.
    """
        
    @classmethod
    async def from_defaults(
        cls,
        contextKB: AmazonKnowledgeBasesRetriever,
        response_synthesizer: BaseSynthesizer,
        context_retrieval_prompts: dict[str, list[ChatMessage]],
        system_prompt: ChatMessage | str = DEFAULT_SYSTEM_PROMPT,
        token_limit: int = DEFAULT_TOKEN_LIMIT,
        context_cache: str = "context_cache.json",
        force_refresh: bool = False,
        session_id: str = None,
        **kwargs
    ) -> "ContextAugmentedIntentRecognitionAgent":

        """
        Asynchronously creates an instance of the agent with default settings and
        initializes it with static memory derived from retrieved context.

        This method sets up the internal retriever query engine, fetches or builds
        static memory blocks from a knowledge base, and initializes a structured
        chat engine for intent recognition.

        Args:
            contextKB (AmazonKnowledgeBasesRetriever): Knowledge base retriever.
            response_synthesizer (BaseSynthesizer): Synthesizer for generating responses.
            context_retrieval_prompts (dict[str, list[ChatMessage]]): Prompts used to retrieve
                contextual information for memory preloading.
            system_prompt (ChatMessage, optional): Initial system prompt to seed memory.
            token_limit (int, optional): Token limit for memory context. Defaults to DEFAULT_TOKEN_LIMIT.
            context_cache (str, optional): Path to cache file for storing/retrieving context. Defaults to "context_cache.json".
            force_refresh (bool, optional): If True, bypasses cache and re-fetches context. Defaults to False.
            session_id (str): Unique session identifier used to isolate memory per user session.
            **kwargs: Additional arguments passed to StructuredIntentChatEngine.

        Returns:
            ContextAugmentedIntentRecognitionAgent: An initialized agent instance with context-augmented memory.
        """

        # Create instance without calling __init__
        self = cls.__new__(cls)

        # Assign custom attributes
        self.contextKB = contextKB
        self.response_synthesizer = response_synthesizer
        self.system_prompt = system_prompt if isinstance(system_prompt, ChatMessage) else ChatMessage(content=system_prompt, role="system")
        self.context_retrieval_prompts = context_retrieval_prompts
        self.token_limit = token_limit
        self.session_id = session_id

        # Initialize engine and memory
        self._create_engine()
        memory = await self._astatic_memory(force_refresh=force_refresh, 
                                            context_cache=context_cache,
                                            session_id=session_id
                                            )

        logger.debug("Building StructuredIntentChatEngine as internal _chat_engine")
        self._chat_engine = StructuredIntentChatEngine.from_defaults(
            memory=memory,
            **kwargs
        )
        logger.debug(f"StructuredIntentChatEngine type: {type(self._chat_engine)}")
        # Merge base class attributes into this instance
        return self
    # ----------------------
    # Properties
    # ----------------------
    @property
    def engine(self) -> RetrieverQueryEngine:
        """
        Returns the current retriever query engine.

        Returns:
            RetrieverQueryEngine: The engine used for querying the knowledge base.
        """
        return self._engine

    @engine.setter
    def engine(self, retriever_engine: RetrieverQueryEngine) -> None:
        """
        Sets the retriever query engine.

        Args:
            retriever_engine (RetrieverQueryEngine): The engine to be used for querying.
        """
        self._engine = retriever_engine

    @property
    def memory(self) -> Memory:
        return self._chat_engine.memory
    
    # ----------------------
    # Internal Methods
    # ----------------------
    def _create_engine(self) -> None:
        """
        Internal method to create and assign the retriever query engine
        using the provided context retriever and response synthesizer.
        """
        self._engine = RetrieverQueryEngine(
            retriever=self.contextKB,
            response_synthesizer=self.response_synthesizer
        )

    async def _query_kb_for_memory_preload(self, block: str, message: ChatMessage) -> tuple[str, str]:
        """
        Sends a query to the knowledge base to retrieve a response for memory preloading.

        Args:
            block (str): The name of the memory block associated with the query.
            message (ChatMessage): The chat message containing the query content.

        Returns:
            tuple[str, str]: A tuple containing the block name and the response string.
        """
        try:
            logger.debug(f"Retrieving context: {message.content}")

            start = time.time()
            response = await self._engine.aquery(message.content)
            duration = time.time() - start
            logger.info(f"[TIMER] KB query for block '{block}' took {duration:.2f}s")

            return block, response.response
        except Exception as e:
            logger.error(f"Error querying for `{block}` query: {message.content}")
            raise e

    async def _astatic_response(self, force_refresh: bool, context_cache: str) -> dict[str, list[str]]:
        """
        Asynchronously queries the knowledge base using the provided context retrieval prompts
        and stores the responses in a cache file for reuse.

        If a cached version exists and `force_refresh` is False, it loads the responses from
        the cache instead of querying again. Otherwise, it concurrently queries the knowledge
        base for each prompt and saves the results.

        Args:
            force_refresh (bool): Whether to bypass the cache and re-fetch context.
            context_cache (str): Path to the JSON file used for caching context responses.

        Returns:
            dict[str, list[str]]: A dictionary mapping each memory block name to a list of
            retrieved response strings.
        """

        if not force_refresh and os.path.exists(context_cache):
            with open(context_cache, "r") as f:
                self._context_response = json.load(f)
                logger.debug("Loaded context from cache.")
                return self._context_response
        else:
            # Run the queries and cache the result
            tasks = []
            for block in self.context_retrieval_prompts:
                for message in self.context_retrieval_prompts[block]:
                    tasks.append(self._query_kb_for_memory_preload(block, message))

            results = await asyncio.gather(*tasks)

            all_responses = {}
            for block, response in results:
                all_responses.setdefault(block, []).append(response)

            with open(context_cache, "w") as f:
                json.dump(all_responses, f)

            self._context_response = all_responses
            return all_responses


    async def _astatic_memory(self, force_refresh: bool, context_cache: str, session_id: str) -> Memory:
        """
        Asynchronously constructs static memory blocks from retrieved context and initializes
        a Memory object with those blocks and the system prompt.

        This method uses the context responses (either from cache or fresh retrieval)
        to build `StaticMemoryBlock` instances, which are then used to create a `Memory`
        object that supports structured intent recognition.

        Args:
            force_refresh (bool): Whether to bypass the cache and re-fetch context.
            context_cache (str): Path to the JSON file used for caching context responses.
            session_id (str): Unique session identifier used to create session-specific memory.

        Returns:
            Memory: A memory instance initialized with static context blocks and the system prompt.
        """

        start = time.time()
        context_dict = await self._astatic_response(force_refresh=force_refresh,
                                                    context_cache=context_cache)
        logger.debug(f"Creating memory blocks: {', '.join(context_dict.keys())}")
        duration = time.time() - start
        logger.info(f"[TIMER] _astatic_memory took {duration:.2f}s (memory construction from KB)")
        memory_blocks = []
        for block, responses in context_dict.items():
            combined_response = f"### {block}\n" + "\n\n".join(responses)
            # consider cleaning up blocks here (proposed prompt):
            # Please clean up the following text by removing any sentences or paragraphs where the model says it cannot answer, lacks context, or refuses to provide information. Keep only the informative, helpful, or content-rich parts of the text. 
            memory_blocks.append(
                StaticMemoryBlock(
                    name=block,
                    static_content=combined_response,
                    priority=1,
                    accept_short_term_memory=False
                )
            )

        memory = Memory.from_defaults(
            memory_blocks=memory_blocks,
            chat_history=[self.system_prompt],
            token_limit=self.token_limit,
            session_id=session_id
        )
        logger.debug(f"Memory successfully augmented for session: {session_id}")
        return memory

    async def achat(self, *args, **kwargs):
        """
        Forward `achat` to StructuredIntentChatEngine to ensure StructuredLLM.call() is always used.
        """
        logger.debug("ContextAugmentedIntentRecognitionAgent.achat forwarding to _chat_engine")
        start = time.time()
        result = await self._chat_engine.achat(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"[TIMER] ContextAugmentedIntentRecognitionAgent.achat() took {duration:.2f}s")
        
        return result