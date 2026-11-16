from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING
from llama_index.core.agent.workflow.workflow_events import AgentOutput
from llama_index.core.agent.workflow.function_agent import FunctionAgent
from llama_index.core.bridge.pydantic import Field
from abc import ABC, abstractmethod

class BaseBioInsightAgent(FunctionAgent, ABC):
    """
    Base BioInsight Agent with required metadata and methods.

    Attributes:
        name (str): The name of the agent.
        description (str): A brief description of the agent.
        system_prompt (str): The system prompt for the agent.
    """

    # Common error response for all agents
    DEFAULT_ERROR_RESPONSE: str = "I'm sorry, I've encountered an internal error. Please try again."

    name: str = Field(..., description="The name of the agent.")
    description: str = Field(..., description="A brief description of the agent.")
    system_prompt: str = Field(..., description="The system prompt for the agent.")

    def __init__(self, name: str, description: str, system_prompt: str, **kwargs: Any) -> None:
        """
    Initialize the BaseBioInsightAgent.

        Args:
            name (str): The name of the agent.
            description (str): A brief description of the agent.
            system_prompt (str): The system prompt for the agent.
            **kwargs (Any): Additional keyword arguments.
        """
        super().__init__(name=name, description=description, system_prompt=system_prompt, **kwargs)

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
        Hook invoked after the agent's `run()` handler has completed.

        The framework's `run()` produces an `AgentOutput` which includes any
        streaming events and tool call results. Subclasses should implement
        this method to transform that raw `AgentOutput` into the project's
        `ProcessedOutput` (for example: normalize text, add hyperlinks,
        extract UI elements, attach citations, etc.).

        Implementations may assume tool outputs are present because the
        post-run hook runs after the underlying handler finishes.
        """
        raise NotImplementedError()

if TYPE_CHECKING:
    # Import only for static type checking to avoid runtime import cycles
    from agents.processed_output import ProcessedOutput
