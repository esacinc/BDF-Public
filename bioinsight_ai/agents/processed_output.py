from llama_index.core.agent.workflow.workflow_events import AgentOutput
from typing import Optional, List
from plotly.graph_objects import Figure
import plotly.io as pio
from workflows.context.serializers import JsonSerializer

class ProcessedOutput:
    """
    A wrapper around AgentOutput that adds post-processing functionality.

    This class uses composition to extend AgentOutput without subclassing it,
    allowing additional fields and methods to be added without interfering
    with Pydantic validation or the internal logic of AgentOutput.

    Attributes:
        agent_output (Optional[AgentOutput]): The original AgentOutput instance.
        processed_response (Optional[str]): A post-processed version of the LLM response.
        elements (Optional[List]): Additional elements extracted during processing.
        graphs (Optional[List[Figure]]): Visualizations generated from the output.
    """

    def __init__(
        self,
        agent_output: Optional[AgentOutput] = None,
        processed_response: Optional[str] = None,
        elements: Optional[List] = None,
        graphs: Optional[List[Figure]] = None
    ):
        # Allow agent_output to be optional for convenience in fallback flows
        object.__setattr__(self, "agent_output", agent_output)

        # Custom fields added by ProcessedOutput
        self.processed_response = processed_response
        self.elements = elements or []
        self.graphs = graphs or []
        
    def __str__(self):
        """
        Return a string representation of the processed output.

        If a processed response is available, return that string.
        Otherwise, delegate to the string representation of the wrapped AgentOutput
        instance if present; otherwise return an empty string.
        """
        if self.processed_response:
            return self.processed_response
        if getattr(self, "agent_output", None) is not None:
            return str(self.agent_output)
        return ""

    def __getattr__(self, name):
        # If an attribute is not found on ProcessedOutput, delegate access
        # to the wrapped AgentOutput instance when available.
        agent_out = getattr(self, "agent_output", None)
        if agent_out is not None:
            return getattr(agent_out, name)
        raise AttributeError(f"'ProcessedOutput' object has no attribute '{name}'")

    # JSON-serializer compatibility for Context serialization.
    # See data_sources/metabolomics_workbench/mwb/tools.py:MolView for the pattern:
    # JsonSerializer detects `class_name` and packages `to_dict()` in a component
    # envelope, calling `from_dict()` on the way back.
    @property
    def class_name(self) -> str:
        return f"{self.__class__.__module__}.{self.__class__.__name__}"

    def to_dict(self) -> dict:
        # Delegate nested serialization to JsonSerializer so AgentOutput (Pydantic)
        # and any component-typed elements (e.g. MolView) get the right envelopes.
        # Graphs may be Plotly Figure instances OR S3-URL reference dicts produced
        # by the plotting agent (e.g. {"type": "plotly_url", "url": ..., "objectKey": ...}).
        sub = JsonSerializer()
        return {
            "agent_output": sub.serialize_value(self.agent_output) if self.agent_output is not None else None,
            "processed_response": self.processed_response,
            "elements": [sub.serialize_value(e) for e in (self.elements or [])],
            "graphs": [_encode_graph(g) for g in (self.graphs or [])],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessedOutput":
        sub = JsonSerializer()
        ao_payload = data.get("agent_output")
        agent_output = sub.deserialize_value(ao_payload) if ao_payload is not None else None
        elements = [sub.deserialize_value(e) for e in (data.get("elements") or [])]
        graphs = [_decode_graph(g) for g in (data.get("graphs") or [])]
        return cls(
            agent_output=agent_output,
            processed_response=data.get("processed_response"),
            elements=elements,
            graphs=graphs,
        )


def _encode_graph(g):
    # Figures → JSON string (round-tripped via pio.from_json on the way back).
    # S3-URL reference dicts and any other already-JSON-safe value pass through unchanged.
    if isinstance(g, Figure):
        return g.to_json()
    return g


def _decode_graph(g):
    # Strings produced by Figure.to_json() rebuild into Figure; dicts stay as-is.
    if isinstance(g, str):
        return pio.from_json(g)
    return g