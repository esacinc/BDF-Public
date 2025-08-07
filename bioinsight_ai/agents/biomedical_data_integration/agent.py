import logging
logger = logging.getLogger()


# import sys
# import os

# # Add the parent directory of bioinsight_ai to the Python path
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from workflow_config.default_settings import Settings
llm = Settings.llm

import chainlit as cl
from llama_index.core.workflow import (
    Context, 
    InputRequiredEvent, 
    HumanResponseEvent,
    Workflow,
    StartEvent, 
    StopEvent,
    step,
    Event
    )

from llama_index.core.agent.workflow import (
    AgentInput,
    AgentOutput,
    ToolCall,
    ToolCallResult,
    AgentStream
)

import asyncio
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.memory import Memory
from agents.biomedical_data_integration.interaction.chainlit_interaction_event import ChainlitInteractionEvent
from agents.biomedical_data_integration.interaction.tools import tools
from agents.biomedical_data_integration.harmonization.bdikit_tools import bdi_tools
from agents.biomedical_data_integration.prompts.system_prompt import system_prompt

def create_bdi_agent(session_id: str) -> dict:
    memory = Memory.from_defaults(session_id=session_id, token_limit=80000)

    bdi_agent = FunctionAgent(
        system_prompt=system_prompt,
        allow_parallel_tool_calls=False,
        tools=tools + bdi_tools
    )

    context = Context(bdi_agent)

    return {
        "agent": bdi_agent,
        "context": context,
        "memory": memory
    }


# memory = Memory.from_defaults(token_limit=80000)

# agent = FunctionAgent(
#     system_prompt=system_prompt,
#     allow_parallel_tool_calls=False,
#     tools=tools + bdi_tools
# )

# context = Context(agent)

# class MyWorkflow(Workflow):
#     @step(pass_context=True)
#     async def step_one(self, ctx: Context, ev: StartEvent) -> StopEvent:
#         handler = agent.run(ev.user_msg, ctx=context)
#         async for event in handler.stream_events():
#             if isinstance(event, Event):
#                 if isinstance(event, ChainlitInteractionEvent):
#                     response = await ctx.wait_for_event(
#                         HumanResponseEvent,
#                         waiter_event=event) 
#                     handler.ctx.send_event(response)
#                 else:    
#                     ctx.write_event_to_stream(event)
#         result = await handler
#         return StopEvent(result=result)
    
    
# workflow = MyWorkflow(timeout=None)

# @cl.on_message
# async def on_message(message: cl.Message):
#     handler = workflow.run(user_msg=message.content)
#     # resp = cl.Message(content="")
 
#     async for event in handler.stream_events():
#         if isinstance(event, ChainlitInteractionEvent):
#             # await resp.remove()
#             try:
#                 messages = event.build_chainlit_message()
#             except Exception as e:
#                 logger.exception("Failed to build Chainlit message.")
#                 continue

#             user_input = None

#             for msg in messages:
#                 if isinstance(msg, cl.Message):
#                     logger.info(f"Sending Message: {msg.content}")
#                     await msg.send()
#                     logger.info(f"Message sent.")
#                 else:
#                     try:
#                         logger.info(f"Sending Ask* message: {msg.content}")
#                         user_input = await msg.send()
#                         logger.info(f"Ask* message of type {type(msg)} sent.")
#                     except Exception as e:
#                         logger.exception("Failed to send Ask* message.")
#                         continue
#             if user_input is not None:
#                 handler.ctx.send_event(HumanResponseEvent(response=user_input))
#             else:
#                 logger.warning("No user input received from Ask* message.")
                
#         elif isinstance(event, ToolCall):
#             logger.info(
#                 f"[BDI] Using Tool: ({event.tool_name}):\n"
#                 f"Arguments: {event.tool_kwargs}\n"
#                 )
#         if isinstance(event, ToolCallResult) and not isinstance(event, ToolCall):
#             logger.info(
#                 f"[BDI] Tool Result ({event.tool_name}):\n"
#                 f"Output: {event.tool_output}"
#                 )
#         if isinstance(event, StopEvent):
#             logger.info(f"[BDI] StopEvent: {repr(StopEvent)}")
#             await cl.Message(content=event.result.response.content).send()