from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING
from llama_index.core.agent.workflow.workflow_events import AgentOutput
from llama_index.core.agent.workflow import AgentWorkflow
from llama_index.core.bridge.pydantic import Field
from abc import ABC, abstractmethod

class BaseBioInsightAgentWorkflow(AgentWorkflow, ABC):
    """
    Base BioInsight Agent Workflow with required metadata and methods.

    Attributes:
        name (str): The name of the agent.
        description (str): A brief description of the agent.
    """

    # Common error response for all workflows
    DEFAULT_ERROR_RESPONSE: str = "I'm sorry, I've encountered an internal error. Please try again."

    name: str = Field(..., description="The name of the agent.")
    description: str = Field(..., description="A brief description of the agent.")

    def __init__(self, name: str, description: str, **kwargs: Any) -> None:
        """
    Initialize the BaseBioInsightAgentWorkflow.

        Args:
            name (str): The name of the agent.
            description (str): A brief description of the agent.
            **kwargs (Any): Additional keyword arguments.
        """
        super().__init__(**kwargs)
        self.name = name
        self.description = description

    @abstractmethod
    def generate_schema(self) -> Dict[str, str]:
        """
        Abstract method to generate the agent's schema.

        Returns:
            Dict[str, str]: The schema of the agent.
        """
        raise NotImplementedError()

    @abstractmethod
    def post_run_agent_output(self, output: AgentOutput) -> ProcessedOutput:
        """
        Hook invoked after the workflow's `run()` handler has completed.

        The framework's `run()` produces an `AgentOutput` which includes any
        streaming events and tool call results. Implementations should convert
        that raw `AgentOutput` into a `ProcessedOutput` (for example: normalize
        text, add hyperlinks, extract UI elements, attach citations, etc.).

        This method runs after the underlying handler finishes so tool outputs
        are available to the post-processing logic.
        """
        raise NotImplementedError()

if TYPE_CHECKING:
    # Import only for static type checking to avoid runtime import cycles
    from agents.processed_output import ProcessedOutput
