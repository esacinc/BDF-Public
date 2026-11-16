import json
import re
from log_helper.logger import get_logger
logger = get_logger()
from typing import List, Union
from plotly.graph_objs import Figure

from llama_index.core.llms import ChatMessage
from llama_index.core.memory import Memory, FactExtractionMemoryBlock
from llama_index.core.workflow import (
    step,
    Context,
    StartEvent,
    StopEvent,
    Workflow,
)
from llama_index.core.agent.workflow import ToolCall
from llama_index.core.base.llms.types import ThinkingBlock # from llama_index.core.llms import ThinkingBlock newer llama_index versions
from llama_index.llms.bedrock_converse import BedrockConverse
from workflow_config.default_settings import Settings
from workflow_config.events import (
    ConcludeEvent, 
    ResponseEvent
)

from workflow_config.steps.synthesize import SYNTHESIZE_SYSTEM_PROMPT, SYNTHESIZE_TEMPLATE
from workflow_config.steps.execute_plan.prompts import AGENT_PROMPT
from workflow_config.memory.prompts import FACT_EXTRACTION_PROMPT, FACT_CONDENSE_PROMPT
from agents.bioinsight_agent import BioInsightAgent
from agents.bioinsight_agent_workflow import BioInsightAgentWorkflow
from agents.agent_registry import AgentRegistry
from agents.processed_output import ProcessedOutput
from agents.plotting_agent import agent as plotting_agent
from workflow_config.steps.orchestration.plan import Plan
from workflow_config.steps.orchestration.prompts import ORCHESTRATION_SYSTEM_PROMPT, ORCHESTRATION_TEMPLATE
from data_sources.metabolomics_workbench import agent as mwb_agent
from data_sources.cancer_research_data_commons.agent import agent as crdc_agent
from data_sources.proteome_exchange.agent import agent as px_agent
from data_sources.clinical_trials.agent import agent as ct_agent
from utils.transform import transform_wide_to_long  
from utils.udi_helpers import build_heatmap_udi_spec, infer_heatmap_fields
from utils.tracing import Tracer
from utils.plotting_agent_helpers import draw_graph as helper_draw_graph

class BioInsightWorkflow(Workflow):
    def __init__(
        self,
        session_id: str,
        agent_registry: List[Union[BioInsightAgent, BioInsightAgentWorkflow]],
        llm: BedrockConverse | None = None,
        thinking_llm: BedrockConverse | None = None,
        presigned_s3_client=None,
        memory_token_limit: int = 500000,
        agent_history_turns: int = 2,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.llm = llm
        self.thinking_llm = thinking_llm or Settings.thinking_llm # thinking_llm is an optional separate LLM used for internal "thinking"/planning tasks.
        self.logger = logger
        self.presigned_s3_client = presigned_s3_client
        self.session_id = session_id
        self.agents = AgentRegistry(agents=agent_registry)
        self.default_error_msg = ChatMessage(role="assistant", content="Apologies, I encountered an error while processing your request. Please try again later or rephrase your query.")
        self.memory = Memory.from_defaults(
            session_id=session_id,
            token_limit=memory_token_limit,
            token_flush_size=50000,
            memory_blocks=[
                FactExtractionMemoryBlock(
                    name="condensed_conversation_history",
                    llm=self.llm,
                    max_facts=50,
                    priority=0,
                    fact_extraction_prompt_template=FACT_EXTRACTION_PROMPT,
                    fact_condense_prompt_template=FACT_CONDENSE_PROMPT,
                ),
            ],
        )
        self.agent_history_turns = agent_history_turns
            
    @classmethod
    async def new_session(cls, session_id, agents, llm, presigned_s3_client, memory_token_limit: int = 500000, agent_history_turns: int = 2, **kwargs):
        instance = cls(
            session_id=session_id,
            agent_registry=agents,
            llm=llm,
            thinking_llm=kwargs.get('thinking_llm', None),
            presigned_s3_client=presigned_s3_client,
            memory_token_limit=memory_token_limit,
            agent_history_turns=agent_history_turns,
            **kwargs
        )
        
        # Register the PlottingAgent so plotting is available as a first-class agent
        try:
            instance.agents["PlottingAgent"].llm = llm
            instance.agents["PlottingAgent"].presigned_s3_client = presigned_s3_client 
            instance.logger.info(f"Registered plotting agent '{instance.agents['PlottingAgent'].name}'")
        except Exception as e:
            instance.logger.warning(f"Failed to register PlottingAgent during new_session: {e}")

        return instance

    async def append_to_history(self, ctx: Context, user_message, assistant_message=None):
        """Append a user/assistant exchange to the Memory object.

        Parameters:
        - ctx: workflow Context (kept for signature compatibility)
        - user_message: the user's message text
        - assistant_message: assistant response text; defaults to self.default_error_msg.content
        """
        if assistant_message is None:
            assistant_message = self.default_error_msg.content
        if user_message:
            await self.memory.aput(ChatMessage(role="user", content=str(user_message)))
        if assistant_message:
            await self.memory.aput(ChatMessage(role="assistant", content=str(assistant_message)))

        # Log memory state and extracted facts
        try:
            active_msgs = await self.memory.aget_all()
            active_count = len(active_msgs) if active_msgs else 0
            fact_block = next((b for b in self.memory.memory_blocks if isinstance(b, FactExtractionMemoryBlock)), None)
            facts = fact_block.facts if fact_block else []
            self.logger.info(
                f"[MEMORY] Active messages: {active_count} | "
                f"Facts extracted: {len(facts)} | "
                f"Facts: {facts}"
            )
        except Exception as e:
            self.logger.debug(f"[MEMORY] Failed to log memory state: {e}")

    async def get_chat_history(self) -> list:
        """Retrieve the full (token-managed) conversation history from Memory."""
        return await self.memory.aget()

    async def get_agent_history(self) -> list:
        """Retrieve a limited slice of conversation history for agent invocations.
        
        Returns the last N turns (user+assistant pairs) based on self.agent_history_turns.
        """
        history = await self.memory.aget()
        if not history:
            return []
        # Each turn is a user+assistant pair, so take last N*2 messages
        max_messages = self.agent_history_turns * 2
        return history[-max_messages:] if len(history) > max_messages else history

    async def flush_memory_to_context(self, ctx: Context) -> None:
        """Flush the Memory contents into ctx.store for serialization.
        
        Call this before ctx.to_dict() so that conversation history survives
        serialization/deserialization (e.g. on_chat_end → on_chat_resume).
        """
        messages = await self.memory.aget_all()
        await ctx.store.set("memory_snapshot", messages)
        # Persist fact block state
        for block in self.memory.memory_blocks:
            if isinstance(block, FactExtractionMemoryBlock):
                await ctx.store.set("fact_block_facts", block.facts)

    async def load_memory_from_context(self, ctx: Context) -> None:
        """Load Memory contents from a previously serialized ctx.store snapshot.
        
        Call this after Context.from_dict() to rehydrate the Memory object
        from the snapshot saved by flush_memory_to_context().
        """
        snapshot = await ctx.store.get("memory_snapshot", [])
        if snapshot:
            await self.memory.aset(snapshot)
            self.logger.info(f"Restored {len(snapshot)} messages into Memory from context snapshot")
        # Restore fact block state
        facts = await ctx.store.get("fact_block_facts", [])
        if facts:
            for block in self.memory.memory_blocks:
                if isinstance(block, FactExtractionMemoryBlock):
                    block.facts = facts
                    self.logger.info(f"Restored {len(facts)} facts from context snapshot")


    async def _handle_error(self, error: Exception, logger_prefix: str, ctx: Context, assistant: Union[str, ChatMessage] | None = None, user: str | None = None) -> StopEvent:
        """Private helper to log an error, update chat history via append_to_history, and return a StopEvent.

        Parameters:
        - error: exception object to log
        - logger_prefix: short string prefix for log messages
        - ctx: workflow Context
        - assistant: assistant message text or ChatMessage; if None defaults to self.default_error_msg
        - user: optional user message text to include

        Returns a StopEvent with a dict payload {"response": <assistant_text>}.
        """
        # Log the error with the provided prefix
        try:
            self.logger.error(f"{logger_prefix}: {error}")
        except Exception:
            # Fallback logging
            try:
                self.logger.error(f"{logger_prefix}: <unprintable error>")
            except Exception:
                pass

        # Normalize assistant text
        if assistant is None:
            assistant_text = getattr(self, 'default_error_msg').content if getattr(self, 'default_error_msg', None) is not None else "An internal error occurred."
        elif isinstance(assistant, ChatMessage):
            assistant_text = assistant.content
        else:
            assistant_text = str(assistant)

        # Delegate history update to shared method
        try:
            await self.append_to_history(ctx, user, assistant_text)
        except Exception as e:
            self.logger.debug(f"[ERROR HANDLER] Failed to update memory: {e}")

        return StopEvent(result={"response": assistant_text})

    
    def is_input_too_long_error(self, e) -> bool:
        """
        Check for ConverseStream error: 
        'An error occurred (ValidationException) when calling the ConverseStream operation: The model returned the following errors: Input is too long for requested model.'
        OR
        'An error occurred (ValidationException) when calling the ConverseStream operation: The model returned the following errors: prompt is too long: X tokens > Y maximum'
        """
        from botocore.exceptions import ClientError

        # Check if it's a botocore ClientError with the right structure
        if isinstance(e, ClientError):
            error_dict = e.response.get('Error', {})
            error_msg = error_dict.get('Message', '').lower()
            error_code = error_dict.get('Code', '')

            if error_code == 'ValidationException' and ('input is too long' in error_msg or 'prompt is too long' in error_msg):
                return True
        
        # Fallback: check the string representation of the error
        error_str = str(e).lower()
        if 'validationexception' in error_str and ('input is too long' in error_str or 'prompt is too long' in error_str):
            return True
        
        return False

    async def draw_graph(self, ctx: Context, response, query):
        """
        Thin wrapper delegating plotting responsibilities to the centralized
        helper in `utils.plotting_agent_helpers`. Keeps existing callsites
        unchanged and provides a single source of plotting logic.
        """
        try:
            result = await helper_draw_graph(
                response=response,
                query=query or "",
                llm=self.llm,
                presigned_s3_client=self.presigned_s3_client,
                logger=self.logger,
            )
            return result
        except Exception as e:
            self.logger.exception("draw_graph wrapper: delegated helper failed: %s", e)
            return -1

    def _sanitize_assistant_content(self, text: str) -> str:
        """
        Strip embedded JSON, XML, or code blocks from assistant text so the UI
        only receives human-readable summaries. Keep the short summary before
        any embedded structured payload (e.g., 'json\\n{...}').
        """
        if not text:
            return ""

        # Ensure we're working with a string (ChatMessage or other objects may be passed in)
        try:
            cleaned = str(text)
        except Exception:
            cleaned = ""

        # 1) Remove properly-closed fenced code blocks: ```...```
        cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

        # 2) If an opening fence was emitted but no closing fence exists, remove from the first ``` to the end
        if '```' in cleaned:
            first = cleaned.find('```')
            # remove the opening fence and anything after it
            cleaned = cleaned[:first].strip()

        # 3) Remove common indented code blocks (lines starting with 4+ spaces)
        cleaned = re.sub(r"(?m)^ {4,}.*$", "", cleaned)

        # 4) If assistant included a literal 'json' marker followed by structured data, keep only the human summary before it.
        parts = re.split(r'\n\s*json\s*\n', cleaned, flags=re.IGNORECASE)
        if parts and parts[0].strip():
            cleaned = parts[0].strip()
        else:
            cleaned = cleaned.strip()

        # 5) If a large JSON blob was appended without the 'json' marker, drop everything starting at a top-level '{' if it follows a human summary.
        brace_idx = cleaned.find('{')
        if brace_idx != -1 and brace_idx < 400 and len(cleaned) > 300:
            cleaned = cleaned[:brace_idx].strip()

        # 6) Final safety: remove leftover angle-bracket XML-like blocks
        cleaned = re.sub(r'<\?xml.*?\?>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<[a-zA-Z]+\b[^>]*>.*?</[a-zA-Z]+>', '', cleaned, flags=re.DOTALL)

        # Fallback message when stripping results in nothing meaningful
        return cleaned.strip() or "Generated plot (details available in the attached visualization)."

    def _sanitize_and_extract(self, text: str) -> tuple[str, list]:
        """
        Sanitize assistant content like `_sanitize_assistant_content` but also
        extract structured payloads (code blocks, large JSON/XML blobs) instead
        of discarding them. Returns a tuple `(clean_summary, attachments)` where
        `attachments` is a list of dicts with keys `type` and `content`.
        """
        if not text:
            return "", []

        try:
            src = str(text)
        except Exception:
            src = ""

        attachments: list = []

        # Extract fenced code blocks (```...```) including language marker
        code_blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]*\n)?([\s\S]*?)```", src, flags=re.IGNORECASE)
        for cb in code_blocks:
            cb_str = cb.strip()
            if cb_str:
                attachments.append({"type": "code", "content": cb_str})

        # Remove fenced blocks from source
        cleaned = re.sub(r"```(?:[a-zA-Z0-9_+-]*\n)?[\s\S]*?```", "", src, flags=re.IGNORECASE)

        # Extract XML prolog or large XML blocks
        xml_blocks = re.findall(r"<\?xml[\s\S]*?\?>", cleaned, flags=re.IGNORECASE)
        for xb in xml_blocks:
            attachments.append({"type": "xml", "content": xb})
        cleaned = re.sub(r"<\?xml[\s\S]*?\?>", "", cleaned, flags=re.IGNORECASE)

        # Extract large JSON-like blobs (heuristic: balanced braces and length)
        json_candidates = re.findall(r"\{[\s\S]{200,}\}", cleaned)
        for jc in json_candidates:
            attachments.append({"type": "json", "content": jc})
            cleaned = cleaned.replace(jc, "")

        # Fallback: extract any other XML-like element blocks
        other_xml = re.findall(r"<[a-zA-Z]+\b[^>]*>[\s\S]*?<\/[a-zA-Z]+>", cleaned)
        for ox in other_xml:
            # Avoid adding tiny HTML fragments
            if len(ox) > 100:
                attachments.append({"type": "xml", "content": ox})
                cleaned = cleaned.replace(ox, "")

        # Reuse existing sanitizer logic to produce a short human summary
        summary = self._sanitize_assistant_content(cleaned)

        return summary, attachments

    @step
    async def plan(self, ctx: Context, ev: StartEvent) -> Plan | None:
        message_history = await self.get_chat_history()
        # Sanitize any existing assistant messages to avoid inline code/image placeholders
        sanitized_history = []
        for i, msg in enumerate(message_history):
            try:
                content = getattr(msg, 'content', '')
                role = getattr(msg, 'role', None)
                if role == 'assistant' and content:
                    content = self._sanitize_assistant_content(content)
                sanitized_history.append(ChatMessage(role=role or 'assistant', content=content))
                logger.info(f"Message history [{i}]: role={role}, content={content[:100] + content[-100:] if len(content) > 200 else content}")
            except Exception:
                sanitized_history.append(msg)
        message_history = sanitized_history
        
        # CLEANUP: Clear old execution state to prevent pollution
        await ctx.store.set("responses", [])
        await ctx.store.set("plan", None)
        await ctx.store.set("last_agent_output", None) # Critical: Clear old data

        query = ev.query
        await ctx.store.set("query", query)

        orchestration_msg = ORCHESTRATION_TEMPLATE.format_messages(
                USER_REQUEST=query,
                # AVAILABLE_AGENTS=available_agents,
                # AGENT_NAMES=agent_names_text
                AVAILABLE_AGENTS=self.agents.agent_schema_str,
                AGENT_NAMES=self.agents.names()
            ) # [ChatMessage(role="user", content=...)]
        try:
            response = await self.thinking_llm.achat(
                messages=[ORCHESTRATION_SYSTEM_PROMPT] + message_history + orchestration_msg
            )
        except Exception as e:
            return await self._handle_error(
                error=e,
                logger_prefix="[PLAN] Orchestration LLM call failed",
                ctx=ctx,
                assistant=self.default_error_msg,
                user=query,
            )

        content = getattr(response.message, "content", "")
        logger.info(f"[PLAN] Orchestration response: \n{content}")
        
        thinking_blocks = [block for block in response.message.blocks if isinstance(block, ThinkingBlock)]
        thinking_content = [block.content for block in thinking_blocks]
        extended_thinking = "\n".join(thinking_content)
        self.logger.info(f"[PLAN] Orchestration extended thinking: \n{extended_thinking}")

        # Check for a direct answer response from the orchestrator
        answer_match = re.search(r"<answer>\s*(.*?)\s*</answer>", content, re.DOTALL | re.IGNORECASE)
        if answer_match:
            answer_text = answer_match.group(1).strip()
            try:                
                await self.append_to_history(ctx, query, answer_text)
            except Exception as e:
                return await self._handle_error(
                    error=e,
                    logger_prefix="[PLAN] Failed to persist memory for orchestration answer",
                    ctx=ctx,
                    assistant=self.default_error_msg,
                    user=query,
                )
            return StopEvent(result={"response": answer_text})
        
        # Check for clarification from the orchestrator
        clarify_match = re.search(r"<clarify>\s*(.*?)\s*</clarify>", content, re.DOTALL | re.IGNORECASE)
        if clarify_match:
            clarify_text = clarify_match.group(1).strip()
            try:                
                await self.append_to_history(ctx, query, clarify_text)
            except Exception as e:
                return await self._handle_error(
                    error=e,
                    logger_prefix="[PLAN] Failed to persist memory for orchestration clarification",
                    ctx=ctx,
                    assistant=self.default_error_msg,
                    user=query
                )
            return StopEvent(result={"response": clarify_text})

        # Otherwise, attempt to build a Plan object from the orchestration output
        try:
            plan = Plan(xml_string=content, agent_names=self.agents.names())
            self.logger.info(f"[PLAN] Created Plan:\n{str(plan)}")
        except Exception as e:
            return await self._handle_error(
                error=e,
                logger_prefix="[PLAN] Failed to parse Plan from orchestration output",
                ctx=ctx,
                assistant=self.default_error_msg,
                user=query,
            )

        # Write the Plan object directly to the event stream
        ctx.write_event_to_stream(plan)

        actions = getattr(plan, "actions", [])
        await ctx.store.set("plan", plan)

        return plan
        
    @step
    async def execute_plan(self, ctx: Context, plan: Plan) -> ResponseEvent | StopEvent:
        """
        Unified step to handle agent execution.
        """
        query = await ctx.store.get("query")
        agent_history = await self.get_agent_history()
        responses = [] # reset responses for each plan execution
        input_too_long = False
        num_actions = len(plan.actions)

        for action in plan.actions:
            action.status = "running"
            ctx.write_event_to_stream(action)
            ctx.write_event_to_stream(plan)
            
            agent_name = action.agent_name
            agent = self.agents.get(agent_name)
            if not agent:
                action.status = "failed"
                ctx.write_event_to_stream(plan)
                self.logger.error(f"Agent {agent_name} not found.")
                continue 
 
            messages = AGENT_PROMPT.format_messages(USER_QUERY=query, TASK_DESCRIPTION=action.description) # format_message outputs list of ChatMessage
            message = messages[0]  if messages[0].role == "user" else None # None assumes user message in chat history
            tracer = Tracer(label=f"run_{agent_name}")
            async with tracer.async_step("run_agent_workflow"):
                try:
                    # Special-case: avoid invoking the streaming LLM path for PlottingAgent.
                    # PlottingAgent performs post-run processing on an upstream agent's ProcessedOutput.
                    # Running it via agent.run(...) can trigger Bedrock ConverseStream caching/validation errors.
                    if agent_name == "PlottingAgent":
                        # Use the most recent agent_output (if any) as input.
                        # This allows PlottingAgent to process the output from a prior agent action.
                        last_agent_output = None
                        if responses:
                            # responses list contains dicts we appended for prior agents; try to recover the original ProcessedOutput
                            # If we preserved the ProcessedOutput object earlier, it will be in a special key.
                            # The safest available payload is to look in ctx.store for the last handler result.
                            try:
                                last_agent_output = await ctx.store.get("last_agent_output")
                            except Exception:
                                last_agent_output = None

                        # If we don't have a stored raw AgentOutput/ProcessedOutput, fall back to streaming as before.
                        if last_agent_output is not None:
                            self.logger.info(f"Delegating plotting to PlottingAgent.post_run_agent_output (avoid streaming) for agent: {agent_name}")
                            plot_out = await agent.post_run_agent_output(last_agent_output, query=query)
                            agent_output = plot_out
                        else:
                            # Fallback to the streaming run if we couldn't locate prior output
                            self.logger.info(f"No prior agent output found in ctx.store; falling back to agent.run() for {agent_name}")
                            self.logger.info(f"Running agent: {agent_name} with prompt: \n{getattr(message,'content',None)}")
                            handler = agent.run(message, chat_history=agent_history)
                            async for event in handler.stream_events():
                                if isinstance(event, ToolCall):
                                    self.logger.info(f"🔨 {agent.name} calling tool '{event.tool_name}':\n"
                                                     f"Arguments: {event.tool_kwargs}")
                                    ctx.write_event_to_stream(event)
                                elif not isinstance(event, StopEvent): # stop event closes stream
                                    ctx.write_event_to_stream(event)
                            agent_output = await handler
                    else:
                        self.logger.info(f"Running agent: {agent_name} with prompt: \n{getattr(message,'content',None)}")
                        handler = agent.run(message, chat_history=agent_history)
                        async for event in handler.stream_events():
                            if isinstance(event, ToolCall):
                                self.logger.info(f"🔨 {agent.name} calling tool '{event.tool_name}':\n"
                                                 f"Arguments: {event.tool_kwargs}")
                                ctx.write_event_to_stream(event)
                            elif not isinstance(event, StopEvent): # stop event closes stream
                                ctx.write_event_to_stream(event)
                        agent_output = await handler
                    
                    if not isinstance(agent_output, ProcessedOutput):
                         self.logger.error(f"Agent {agent_name} did not return a `ProcessedOutput` object.")
                     
                    # Persist the raw AgentOutput (or ProcessedOutput) for downstream agents (e.g., PlottingAgent)
                    try:
                        await ctx.store.set("last_agent_output", agent_output)
                    except Exception:
                        self.logger.debug("Could not persist last_agent_output to ctx.store")

                    resp_dict = {"response": getattr(agent_output, "processed_response") or getattr(agent_output.response, "content")}
                    # Sanitize assistant-produced response to avoid embedding raw code/markdown/images in chat history
                    try:
                        if isinstance(resp_dict.get("response"), str):
                            resp_dict["response"] = self._sanitize_assistant_content(resp_dict["response"])
                    except Exception:
                        pass
                     
                    if agent_output.elements:
                         resp_dict['elements'] = agent_output.elements
                         
                    if agent_output.graphs:
                        # resp_dict['graphs'] = agent_output.graphs
                        # Always expose a single renderable graph
                        graph = agent_output.graphs[0]
                        # If it's a Plotly Figure, pass it directly
                        resp_dict['graph'] = graph

                    response = resp_dict.get("response", None)
                    if not response or response == agent.DEFAULT_ERROR_RESPONSE:
                        action.status = "failed"
                        ctx.write_event_to_stream(plan)
                        self.logger.error(f"Agent {agent_name} did not return a valid response.")
                
                    self.logger.info(f"Agent {agent_name} response:\n{response}")
                    responses.append(resp_dict)
                
                    tracer.report({"query": query, "status": "success"})
                    self.logger.info(f"Agent {agent_name} executed successfully.")
                    action.status = "done"
                    ctx.write_event_to_stream(plan)
                except Exception as e:
                    action.status = "failed"
                    ctx.write_event_to_stream(plan)
                    
                    # Debug logging to see error type and message
                    self.logger.debug(f"[EXECUTE_PLAN] Exception type: {type(e)}")
                    self.logger.debug(f"[EXECUTE_PLAN] Exception message: {str(e)}")
                    
                    if self.is_input_too_long_error(e):
                        self.logger.error(f"Requested input is too long for {agent_name}.")
                        responses.append({"response": f"Error processing task '{action.description}': {str(e)}\n\nUser may need to rephrase their query."})
                        input_too_long = True
                    else:
                        return await self._handle_error(
                        error=e,
                        logger_prefix=f"[EXECUTE_PLAN] Agent {agent_name} execution failed",
                        ctx=ctx,
                        assistant=self.default_error_msg,
                        user=query,
                )
        
        await ctx.store.set("responses", responses)
        await ctx.store.set("plan", plan)    
        if num_actions == 1 and not input_too_long: 
            await ctx.store.set("response", responses[0])
            return ConcludeEvent()
        else:
            return ResponseEvent()

    @step
    async def synthesize(self, ev: ResponseEvent, ctx: Context) -> ConcludeEvent | StopEvent:
        tracer = Tracer(label="synthesize")
        ctx.write_event_to_stream(ev)
        plan = await ctx.store.get("plan")

        responses = await ctx.store.get("responses", [])
        message_history = await self.get_chat_history()
        query = await ctx.store.get("query", "")

        chat_info = {name: [] for name in ['assistant', 'elements', 'graphs']}
        for response in responses:
            reply = response.get("response", "")
            elements = response.get('elements', [])
            # graphs = response.get('graphs', [])
            graphs = response.get('graphs') or response.get('graph') or []

            chat_info['assistant'].append(reply)
            if elements and not isinstance(elements, list):
                elements = [elements]
            chat_info['elements'].extend(elements)
            if graphs and not isinstance(graphs, list):
                graphs = [graphs]
            chat_info['graphs'].extend(graphs)

        assistant_responses = "\n\n".join(
            f"<response>\n{response}\n</response>" for response in chat_info['assistant']
        )

        context_query = SYNTHESIZE_TEMPLATE.format_messages(AGENT_RESPONSES=assistant_responses, USER_QUERY=query)
        self.logger.info(f"Synthesis template:\n{context_query[0]}")
        async with tracer.async_step("llm_synthesis"):
            resp = await self.llm.achat(messages=[SYNTHESIZE_SYSTEM_PROMPT] + message_history + context_query)

        self.logger.info(f"Synthesis response: {resp.message.content}")
        
        # Inline extraction of first <answer>...</answer> block (case-insensitive, multiline)
        resp_text = getattr(resp.message, 'content', '')
        answer_match = re.search(r"<answer>\s*(.*?)\s*</answer>", resp_text, re.DOTALL | re.IGNORECASE)
        answer_text = answer_match.group(1).strip() if answer_match else None
        
        resp_dict = {'response': answer_text}
        if not resp_dict['response']:
            self.logger.error("Synthesis failed to produce a valid response.")
        if chat_info['elements']:
            resp_dict['elements'] = chat_info['elements']
        if chat_info['graphs']:
            # first_graph = chat_info['graphs'][0]
            # # resp_dict['graph'] = chat_info['graphs']
            # resp_dict['graph'] = first_graph
            resp_dict['graphs'] = chat_info['graphs']
            
        await ctx.store.set("response", resp_dict)

        self.logger.info(f"Synthesized response: {str(resp_dict)}")
        tracer.report({"query": query, "status": "synthesized"})

        return ConcludeEvent()
        
    @step
    async def conclude(self, ctx: Context, ev: ConcludeEvent) -> StopEvent:
        """Final step that persists conversation history and returns the response."""
        tracer = Tracer(label="conclude")

        ctx.write_event_to_stream(ev)
        
        response = await ctx.store.get("response", {})
        query = await ctx.store.get("query", "")
        
        # Store clean answer text in memory, not the full response dict
        answer_text = response.get("response", "") if isinstance(response, dict) else str(response)
        
        self.logger.info(f"Persisting to memory - user: {query[:100]}... assistant: {answer_text[:100]}...")
        await self.append_to_history(ctx, query, answer_text)
        
        tracer.report({"query": query, "status": "completed"})
        return StopEvent(result=response)
        
async def bioinsight_session(session_id: str, presigned_s3_client=None):
    return await BioInsightWorkflow.new_session(
        agents=[
            plotting_agent
            , crdc_agent
            , px_agent
            , ct_agent
            , mwb_agent
        ],
        llm=Settings.llm,
        presigned_s3_client=presigned_s3_client,
        timeout=600,
        verbose=True,
        session_id=session_id,
    )