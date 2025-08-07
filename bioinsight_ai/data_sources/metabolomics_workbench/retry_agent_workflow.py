from llama_index.core.agent.workflow import (
    AgentWorkflow,
    ToolCallResult
)
from log_helper.logger import get_logger
logger = get_logger()

class RetryAgentWorkflow(AgentWorkflow):
    async def run(self, 
                  user_query: str, 
                  max_retries: str = 3, 
                  fallback_message: str = "Sorry, I was unable to retrieve a valid response.",
                  **kwargs):
        """
        Run the agent workflow with retry logic and fallback behavior.
        Assumes reply.response.content always exists and can be overwritten.
        """
        reply = None

        for attempt in range(1, max_retries + 1):
            logger.info(f"[MWB RetryAgentWorkflow] Attempt {attempt} for query: {user_query}")
            try:        
                handler = super().run(user_query, **kwargs)
                current_agent = None
                async for event in handler.stream_events(): 
                    if (hasattr(event, "current_agent_name") and event.current_agent_name != current_agent):
                        current_agent = event.current_agent_name
                        logger.info(f"[MWB RetryAgentWorkflow] Current agent: {current_agent}")
                    if isinstance(event, ToolCallResult):
                        logger.info(
                            f"[MWB RetryAgentWorkflow] Tool Result ({event.tool_name}):\n"
                            f"Arguments: {event.tool_kwargs}\n"
                            f"Output: {event.tool_output}"
                            )
                        
                reply = await handler
                # 'current_agent_name' special key in context. If empty will use root agent
                # this forces each run to start with root agent
                if 'ctx' in kwargs:
                    await kwargs['ctx'].set('current_agent_name', None)
                logger.debug(f"[MWB RetryAgentWorkflow] response content produced: {reply.response.content}")

                if hasattr(reply, "response") and getattr(reply.response, "content", None):
                    logger.info("[MWB RetryAgentWorkflow] Successful response received.")
                    return reply
                else:
                    logger.warning("[MWB RetryAgentWorkflow] No content in response. Retrying...")
            except Exception as e:
                logger.exception(f"[MWB RetryAgentWorkflow] Exception during run: {e}")

        logger.error("[MWB RetryAgentWorkflow] Max retries reached. Returning fallback response.")

        # Assume reply exists and has .response.content
        if reply is not None and hasattr(reply, "response"):
            reply.response.content = fallback_message
            return reply

        # If reply or response is missing entirely, raise a clear error
        raise RuntimeError("AgentWorkflow failed and no valid reply object was returned.")
