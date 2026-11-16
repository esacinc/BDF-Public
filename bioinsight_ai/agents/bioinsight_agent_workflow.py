from typing import Dict, Any, overload, Literal, Union
from .base_bioinsight_agent_workflow import BaseBioInsightAgentWorkflow
from agents.processed_output import ProcessedOutput
from agents.processed_workflow_handler import ProcessedWorkflowHandler
from llama_index.core.workflow.handler import WorkflowHandler
from llama_index.core.agent.workflow.workflow_events import AgentOutput

class BioInsightAgentWorkflow(BaseBioInsightAgentWorkflow):
    """
    Extension of BioInsight Agent Workflow base class.

    Attributes:
        name (str): The name of the workflow.
        description (str): A brief description of the workflow.
    """

    def generate_schema(self) -> Dict[str, Any]:
        """
        Generate a schema for the workflow.

        Returns:
            Dict[str, Any]: A dictionary containing the workflow schema.
        """
        return {
            "name": self.name,
            "description": self.description,
            "agents": [
                agent.generate_schema()
                for agent in self.agents.values()
            ],
        }

    def post_run_agent_output(self, output: AgentOutput) -> ProcessedOutput:
        """
        Default implementation that converts an `AgentOutput` into a
        `ProcessedOutput` via a direct model dump.

        This simple conversion does not perform domain-specific post-processing.
        Workflow subclasses should override this method to implement workflow-
        level transformations when required.
        """
        return ProcessedOutput(agent_output=output)

    @overload
    def run(self, *args, post_process: Literal[True], **kwargs) -> ProcessedWorkflowHandler: ...

    @overload
    def run(self, *args, post_process: Literal[False], **kwargs) -> WorkflowHandler: ...
    def run(self, *args, post_process: bool = True, **kwargs) -> Union[ProcessedWorkflowHandler, WorkflowHandler]:
        """Run the workflow and return a handler tied to the framework.

        By default (`post_process=True`) the returned handler will be wrapped
        so that when it is awaited the workflow's `post_run_agent_output`
        is invoked on the final `AgentOutput` and a `ProcessedOutput` is
        returned. The wrapper preserves streaming semantics so consumers can
        iterate `stream_events()` as before.

        Behavior notes:
        - The `post_process` control flag is removed from `kwargs` so it is
          not forwarded to the underlying framework.
        - If `post_process` is False the raw framework handler is returned.
        - A double-wrap guard prevents wrapping a handler that is already a
          `ProcessedWorkflowHandler`.
        """
        # Remove our control flag so it's not forwarded to the framework
        kwargs.pop("post_process", None)
        handler = super().run(*args, **kwargs)

        if not post_process:
            return handler

        # Guard against double-wrapping
        if isinstance(handler, ProcessedWorkflowHandler):
            return handler

        try:
            return ProcessedWorkflowHandler(handler, self)
        except Exception:
            return handler
