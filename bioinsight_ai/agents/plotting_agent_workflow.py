import asyncio
import json
import logging
import re
from typing import Any

from llama_index.core.llms import ChatMessage
import plotly.graph_objects as go
import urllib.request

from agents.bioinsight_agent import BioInsightAgent
from agents.processed_output import ProcessedOutput

from utils.plotting_agent_helpers import (
                                            is_base64_image_string,
                                            parse_response_content,
                                            exec_plot_code,
                                            draw_graph,
                                            sanitize_llm_code,
                                        )

logger = logging.getLogger(__name__)


class PlottingAgent(BioInsightAgent):
    """
    Dedicated plotting agent that consumes a data-bearing response (tool_calls)
    and a plotting query, delegates parsing/plot generation to helpers, uploads
    plot artifacts via the injected presigned_s3_client, and returns a
    ProcessedOutput compatible with the existing workflow.
    """
    # Declare runtime dependencies as pydantic-compatible model fields so that
    # constructing/serializing the agent does not raise on unknown attributes.
    llm: Any | None = None
    presigned_s3_client: Any | None = None
    logger: Any | None = None

    def __init__(
        self,
        name: str = "PlottingAgent",
        description: str | None = "Agent responsible for parsing tool outputs and producing plots (Plotly).",
        llm: Any | None = None,
        presigned_s3_client: Any | None = None,
        system_prompt: str | None = None,
        tools: list | None = None,
        runtime_logger: Any | None = None,
        **kwargs,
    ):
        # Keep constructor compatible with BioInsightAgent signature
        super().__init__(
            name=name,
            description=description,
            tools=tools or [],
            system_prompt=system_prompt,
            llm=llm,
            presigned_s3_client=presigned_s3_client,
            logger=runtime_logger,
            **kwargs,
        )
        # Agent-local dependencies
        self.llm = llm
        self.presigned_s3_client = presigned_s3_client
        # If caller didn't provide a runtime logger, fall back to module logger
        self.logger = runtime_logger or logger

    def _clean_message_text(self, text: Any) -> str:
        """
        Reduce message content to a safe, human-readable string suitable
        for sending to the LLM streaming path. Remove fenced code and
        large JSON/XML blobs.
        """
        if text is None:
            return ""
        if not isinstance(text, str):
            try:
                text = json.dumps(text) if not isinstance(text, bytes) else str(text)
            except Exception:
                text = str(text)
        # remove fenced code blocks
        cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)
        # drop inline 'json' followed by blob
        parts = re.split(r'\n\s*json\s*\n', cleaned, flags=re.IGNORECASE)
        if parts and parts[0].strip():
            cleaned = parts[0].strip()
        else:
            cleaned = cleaned.strip()
        # if a large JSON blob was appended without marker, trim at first '{' when the text is long
        brace_idx = cleaned.find('{')
        if brace_idx != -1 and brace_idx < 400 and len(cleaned) > 300:
            cleaned = cleaned[:brace_idx].strip()
        # remove XML-like top-level blocks
        cleaned = re.sub(r'<\?xml.*?\?>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<[a-zA-Z]+\b[^>]*>.*?</[a-zA-Z]+>', '', cleaned, flags=re.DOTALL)
        return cleaned or "[sanitized content]"

    def run(self, message: ChatMessage | None = None, chat_history: list | None = None, *args, **kwargs):
        """
        Sanitize message and chat_history before delegating to the framework run.

        This prevents passing structured/non-string payloads into the LLM streaming
        path (which can cause Bedrock ConverseStream cache errors).
        """
        try:
            # Sanitize chat_history: ensure list of ChatMessage with string content
            sanitized_history = []
            if chat_history:
                for m in chat_history:
                    try:
                        role = getattr(m, "role", "user")
                        content = getattr(m, "content", "")
                        content = self._clean_message_text(content)
                        sanitized_history.append(ChatMessage(role=role, content=content))
                    except Exception:
                        # On any failure, fall back to a minimal string representation
                        sanitized_history.append(ChatMessage(role="user", content=str(m)))
            else:
                sanitized_history = []

            # Sanitize the single message passed in (if any)
            sanitized_message = None
            if message is not None:
                try:
                    role = getattr(message, "role", "user")
                    content = getattr(message, "content", "")
                    content = self._clean_message_text(content)
                    sanitized_message = ChatMessage(role=role, content=content)
                except Exception:
                    sanitized_message = ChatMessage(role="user", content=str(message))
            # Delegate to parent run() with sanitized history/message
            self.logger.debug(f"PlottingAgent.run: delegating with sanitized message and chat history. {content[:200]}")
            return super().run(sanitized_message, chat_history=sanitized_history, *args, **kwargs)
        except Exception as e:
            # Defensive: if sanitization/delegation fails, return parent's run anyway (best-effort)
            self.logger.exception("PlottingAgent.run sanitization failed, delegating raw: %s", e)
            return super().run(message, chat_history=chat_history, *args, **kwargs)

    async def post_run_agent_output(self, output, query: str = "", attachments: list | None = None) -> ProcessedOutput:
        """
        Post-process the raw AgentOutput into a ProcessedOutput.

        - Converts plotting outputs to JSON-safe format to avoid workflow crashes.
        - Sends Plotly figures to UI without storing them directly in workflow state.
        """
        try:
            # Temporary debug logging to help diagnose invocation shape differences
            try:
                has_tool_calls = hasattr(output, "tool_calls")
                tool_calls_len = len(getattr(output, "tool_calls", [])) if has_tool_calls else 0
            except Exception:
                has_tool_calls = False
                tool_calls_len = 0
            self.logger.debug(
                "PlottingAgent.post_run_agent_output: called. output_type=%s, has_tool_calls=%s, tool_calls_len=%s, attachments_type=%s, llm_present=%s, presigned_s3_client_present=%s",
                type(output),
                has_tool_calls,
                tool_calls_len,
                type(attachments),
                self.llm is not None,
                self.presigned_s3_client is not None,
            )
            # Also log a short preview of attachments (defensive, truncated)
            try:
                attach_preview = repr(attachments)[:500]
            except Exception:
                attach_preview = "<unrepr-able>"
            self.logger.debug("PlottingAgent.post_run_agent_output: attachments_preview=%s", attach_preview)

            result = None
            self.logger.info("PlottingAgent.post_run_agent_output: starting post-processing of agent output.")

            # If structured attachments are provided, prefer them over inline parsing.
            if attachments:
                self.logger.debug("PlottingAgent.post_run_agent_output: attachments provided, attempting to use them for plotting.")
                from types import SimpleNamespace
                # Try code attachments first (they directly produce figures when executed)
                for att in attachments:
                    try:
                        if att.get("type") == "code":
                            code = sanitize_llm_code(att.get("content", ""))
                            self.logger.debug("Executing attached code for plotting (sanitized).")
                            try:
                                exec_result = await exec_plot_code(code, context={}, presigned_s3_client=self.presigned_s3_client, logger=self.logger)
                                if exec_result:
                                    result = exec_result
                                    break
                            except Exception as e:
                                self.logger.debug("Attached code execution failed: %s", e)
                                continue
                    except Exception:
                        continue

                # Next, try JSON/XML attachments by constructing a minimal response wrapper
                if result is None:
                    for att in attachments:
                        try:
                            if att.get("type") in ("json", "xml"):
                                content = att.get("content")
                                fake_resp = SimpleNamespace(tool_calls=[SimpleNamespace(tool_output=SimpleNamespace(content=content))])
                                try:
                                    self.logger.debug("Delegating attached json/xml content to central draw_graph helper.")
                                    result = await draw_graph(response=fake_resp, query=query, llm=self.llm, presigned_s3_client=self.presigned_s3_client, logger=self.logger)
                                    if result is not None:
                                        break
                                except Exception as e:
                                    self.logger.debug("draw_graph on attachment failed: %s", e)
                                    continue
                        except Exception:
                            continue

            # Fallback: try to generate a plot using central helper on the original output
            if result is None:
                try:
                    result = await draw_graph(
                        response=output,
                        query=query,
                        llm=self.llm,
                        presigned_s3_client=self.presigned_s3_client,
                        logger=self.logger,
                    )
                except Exception as e:
                    self.logger.exception("PlottingAgent.post_run_agent_output: draw_graph failed: %s", e)

            processed_response = (
                "Plot generated successfully."
                if result not in (None, -1)
                else "Plot generation failed or returned no result."
            )

            elements = []
            graphs = []

            if isinstance(result, dict):
                # # Heatmap or general figure
                # if "figure" in result:
                #     fig = result["figure"]
                #     self.logger.debug("PlottingAgent: sending figure to UI without storing raw Figure in state")

                #     # Add metadata to elements
                #     elements.append({
                #         "udi_spec_url": result.get("udi_spec_url"),
                #         "csv_url": result.get("csv_url")
                #     })

                #     # Serialize figure to JSON string for safe storage (optional)
                #     try:
                #         if isinstance(fig, go.Figure):
                #             # fig_json = fig.to_json()
                #             fig_json = fig.to_dict()
                #             graphs.append({"type": "plotly_json", "json": fig_json})
                #             self.logger.info("PlottingAgent: figure serialized to JSON for state storage")
                #     except Exception as e:
                #         self.logger.warning("Failed to serialize figure for state: %s", e)
                if "url" in result and "objectKey" in result:
                    # If a pre-uploaded plot was returned, prefer forwarding the presigned URL to the frontend.
                    graphs.append({
                        "type": "plotly_url",
                        "url": result["url"],
                        "objectKey": result["objectKey"]
                    })

                    # Optionally, attempt to fetch and rehydrate the Plotly JSON so we can also include
                    # a client-ready JSON payload in the `graphs` list. This helps consumers that
                    # expect an in-memory JSON representation instead of only a URL.
                    try:
                        if result.get("format") in ("plotly_json", "json"):
                            resp = urllib.request.urlopen(result["url"], timeout=10)
                            fig_bytes = resp.read()
                            fig_text = fig_bytes.decode("utf-8")
                            # parse to JSON object
                            fig_obj = json.loads(fig_text)
                            graphs.append({"type": "plotly_json", "json": fig_obj})
                            self.logger.info("PlottingAgent: successfully fetched and rehydrated plot JSON from S3 URL")
                    except Exception as e:
                        self.logger.debug("PlottingAgent: failed to fetch/rehydrate plot JSON from URL: %s", e)

                    # Include any uploaded artifact links in elements for debugging/inspection
                    art = {}
                    if result.get("udi_spec_url"):
                        art["udi_spec_url"] = result.get("udi_spec_url")
                    if result.get("csv_url"):
                        art["csv_url"] = result.get("csv_url")
                    if art:
                        elements.append(art)

                    self.logger.info("PlottingAgent: using S3 URL for plot rendering")

                # Pre-rendered static images
                elif isinstance(result, str) and is_base64_image_string(result):
                    graphs.append({"type": "static_image", "base64": result})
                    elements.append({"image_base64": result})
                    self.logger.info("PlottingAgent: received base64 image string, added to graphs and elements")

                # # Other URL-based plots
                # elif "url" in result and "objectKey" in result:
                #     graphs.append(result)
                #     elements.append(result)
                #     self.logger.info("PlottingAgent: received URL-based plot metadata, added to graphs and elements")

            else:
                # Handle if result is a raw Figure (rare case)
                try:
                    if isinstance(result, go.Figure):
                        self.logger.debug("PlottingAgent: raw Figure received, storing as JSON")
                        # graphs.append({"type": "plotly_json", "json": result.to_json()})
                        graphs.append({"type": "plotly_json", "json": result.to_dict()})
                except Exception:
                    self.logger.debug("PlottingAgent: result is not a Figure, skipping raw figure handling")
                    pass
            self.logger.info("PlottingAgent.post_run_agent_output: post-processing complete, returning ProcessedOutput.")
            self.logger.info("agent output type: %s, processed_response: %s, graphs: %s", type(output), type(processed_response), graphs[0]["type"] if graphs else None)
            return ProcessedOutput(
                agent_output=output,
                processed_response=processed_response,
                elements=elements,
                graphs=graphs,
            )

        except Exception as e:
            self.logger.exception("PlottingAgent.post_run_agent_output: unexpected error: %s", e)
            return ProcessedOutput(
                agent_output=output,
                processed_response="Plotting agent failed during post-processing.",
                elements=[],
                graphs=[]
            )