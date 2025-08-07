from llama_index.core.prompts import ChatPromptTemplate, ChatMessage
from llama_index.core.chat_engine import SimpleChatEngine
from log_helper.logger import get_logger
logger = get_logger()

import time

class StructuredIntentChatEngine(SimpleChatEngine):
    """
    Always uses StructuredLLM.apredict() with proper tool input format.
    """

    async def achat(self, message: str, **kwargs):
        logger.debug("StructuredIntentChatEngine.achat is being used.")

        total_start = time.time()
        # LlamaIndex expects a BasePromptTemplate or subclass
        user_msg = ChatMessage(role="user", content=message)
        await self.memory.aput(user_msg)

        chat_history = await self.memory.aget() # aget returns memory blocks, unlike aget_all()
        prompt = ChatPromptTemplate(
            message_templates=[*chat_history, user_msg]
        )

        #  time just the LLM prediction
        llm_start = time.time()
        response = await self._llm.apredict(prompt)
        llm_duration = time.time() - llm_start
        logger.info(f"[TIMER] StructuredLLM.apredict() call took {llm_duration:.2f}s")

        total_duration = time.time() - total_start
        logger.info(f"[TIMER] StructuredIntentChatEngine.achat() total time: {total_duration:.2f}s")

        logger.debug(f"[DEBUG] Response from StructuredLLM.apredict(): {type(response)}")
        return response

    @property
    def memory(self):
        return self._memory
