from typing import Dict, Any, overload, Literal, Union
from .base_bioinsight_agent import BaseBioInsightAgent
from agents.processed_output import ProcessedOutput
from agents.processed_workflow_handler import ProcessedWorkflowHandler
from llama_index.core.workflow.handler import WorkflowHandler
from llama_index.core.agent.workflow.workflow_events import AgentOutput


class BioInsightAgent(BaseBioInsightAgent):
    """
    Extension of BioInsight Agent base class.

    Attributes:
        name (str): The name of the agent.
        description (str): A brief description of the agent.
        system_prompt (str): The system prompt for the agent.
    """

    def generate_schema(self) -> Dict[str, Any]:
        """
        Generate a schema for the agent.

        Returns:
            Dict[str, Any]: A dictionary containing the agent schema.
        """
        return {
            "name": self.name,
            "description": self.description,
            "tools": [
                {
                    "tool_name": getattr(tool.metadata, "name", None),
                    "tool_description": getattr(tool.metadata, "description", None),
                }
                for tool in (self.tools or [])
            ],
        }

    def post_run_agent_output(self, output: AgentOutput) -> ProcessedOutput:
        """
        Default implementation that converts an `AgentOutput` into a
        `ProcessedOutput` via a direct model dump.

        This simple conversion does not perform any domain-specific
        post-processing. Subclasses should override this method to implement
        agent-specific transformation logic when needed.
        """
        return ProcessedOutput(agent_output=output)

    @overload
    def run(self, *args, post_process: Literal[True], **kwargs) -> ProcessedWorkflowHandler: ...

    @overload
    def run(self, *args, post_process: Literal[False], **kwargs) -> WorkflowHandler: ...
    def run(self, *args, post_process: bool = True, **kwargs) -> Union[ProcessedWorkflowHandler, WorkflowHandler]:
        """Run the agent and return a framework handler.

        By default (`post_process=True`) the returned handler will be wrapped
        so that awaiting it will invoke `post_run_agent_output` on the final
        `AgentOutput` and yield a `ProcessedOutput`. The wrapper preserves
        streaming semantics so consumers can iterate `stream_events()` as
        before.

        Notes:
        - The `post_process` flag is removed from `kwargs` so it is not
          forwarded to the underlying framework run implementation.
        - A double-wrap guard prevents wrapping a handler that is already a
          `ProcessedWorkflowHandler`.
        """
        # Remove control flag from kwargs to avoid accidentally
        # forwarding it to the framework run implementation.
        kwargs.pop("post_process", None)

        # Call the parent run implementation to get the framework handler
        handler = super().run(*args, **kwargs)

        if not post_process:
            return handler

        # Guard against double-wrapping: if a subclass already returned a
        # ProcessedWorkflowHandler (or some wrapper), don't wrap again.
        if isinstance(handler, ProcessedWorkflowHandler):
            return handler

        try:
            return ProcessedWorkflowHandler(handler, self)
        except Exception:
            # If wrapping fails for any reason, fall back to returning the
            # original handler to preserve behavior.
            return handler
