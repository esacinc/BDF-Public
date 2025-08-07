import json
from enum import Enum
from typing import Optional, Dict, List, Type
from llama_index.core.bridge.pydantic import (
    Field,
    PrivateAttr,
    BaseModel,
    model_validator,
)
from llama_index.core.workflow import Event
from workflow_config.events import CRDCEvent, MWBEvent, PXEvent


class AvailableSources(str, Enum):
    """
    Enum representing standardized biomedical data sources used in structured LLM workflows.

    Each enum member includes:
    - A human-readable string value (used in LLM outputs and user-facing interfaces)
    - An associated event class that defines how to handle queries for that source

    This design allows for seamless integration between natural language inputs and
    structured backend logic, enabling both LLM-friendly communication and type-safe
    event dispatching.
    """

    PDC = ("Proteomic Data Commons", CRDCEvent)
    """Proteomic Data Commons: A repository for proteomics datasets. Uses CRDCEvent."""

    GDC = ("Genomic Data Commons", CRDCEvent)
    """Genomic Data Commons: A repository for genomic datasets. Uses CRDCEvent."""

    IDC = ("Imaging Data Commons", CRDCEvent)
    """Imaging Data Commons: A repository for medical imaging data. Uses CRDCEvent."""

    MWB = ("Metabolomics Workbench", MWBEvent)
    """Metabolomics Workbench: A repository for metabolomics data. Uses MWBEvent."""

    PX = ("Proteome Exchange", PXEvent)
    """Proteome Exchange: A global consortium for proteomics data sharing. Uses PXEvent."""

    def __new__(cls, value: str, event_class):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.event_class = event_class
        return obj


class Intent(BaseModel):
    """
    Represents the structured interpretation of a user's query in a conversational system.

    This model captures metadata about the query, including whether it's a follow-up,
    off-topic, or related to harmonization of user data. It also identifies whether a plot
    is requested, which data sources are relevant, and provides context-specific queries
    for each source.

    Fields:
    - off_topic: Flags whether the query is unrelated to supported biomedical topics.
    - off_topic_reply: Optional friendly response to redirect off-topic queries.
    - harmonization: Indicates if the user wants to align their own dataset to a known schema
    (e.g., GDC, PDC). This includes standardizing column names or values. If True, the
    agent assumes the user is working with their own data and does not populate source-related fields.
    - plot: Specifies whether the response should include a visualization.
    - sources: List of relevant biomedical data sources (may be empty).
    - reply: Optional response when no sources are relevant but the query is still on-topic.
    - source_contexts: A mapping of each relevant source to a context-enriched version of the user's query.
    """

    off_topic: bool = Field(
        description="Indicates if the user's query is unrelated to the subject matter."
    )
    off_topic_reply: Optional[str] = Field(
        description="""Used only when off_topic is True. If the user's query is determined to be off-topic, optionally generate a polite and friendly 
        response that acknowledges the query and gently redirects the user toward supported topics or offers 
        suggestions for how they might reframe their question."""
    )
    context_enriched_query: Optional[str] = Field(
        description="""
        A rewritten version of the user's query that is fully self-contained and understandable
        without requiring access to prior conversation history. This field is especially important
        in multi-turn conversations where the user refers to earlier responses using vague or
        context-dependent language (e.g., "the first study", "that dataset", "as mentioned earlier").

        The enriched query should resolve such references explicitly and clearly, while preserving
        the user's original intent, tone, and level of specificity. This helps downstream agents
        interpret the query accurately without relying on memory or chat history.

        Examples:
        - Original: "Can you tell me more about the first study?"
        Enriched: "Can you tell me more about study ST000001?"
        - Original: "What were the results from that dataset?"
        Enriched: "What were the results from the dataset on breast cancer metabolomics (ST000045)?"

        This field should be populated only when the original query contains ambiguous references
        that require clarification for standalone interpretation.
        """
    )
    harmonization: bool = Field(
        description="""
        Indicates that the user's intent is to harmonize or standardize their own dataset to a known biomedical schema 
        (e.g., GDC). This includes aligning column names and/or values to match a target schema or vocabulary.

        Set this to True when the user expresses a desire to:
        - Harmonize, align, or map their dataset to a schema like GDC, PDC, etc.
        - Standardize column names or values in their own data
        - Upload a dataset for transformation or schema matching

        Do NOT set this to True if the user is asking to retrieve data from a public source (e.g., "Get me data from GDC").

        If harmonization is True, you should assume the user is working with their own data and intends to transform it.
        In this case, do NOT populate the `sources`, or `source_contexts` fields, even if the user 
        mentions a known data source like GDC — unless they are explicitly requesting to retrieve data from that source.
    """
    )
    plot: bool = Field(
        description="""
        Set to True if the user is requesting a data visualization such as a chart, graph, or statistical plot 
        (e.g., bar chart, scatter plot, line graph, heatmap, etc.). 

        Do NOT set this to True for requests involving structural images, 3D renderings, or compound/molecular visualizations 
        (e.g., 'Show me the structure of 1-monopalmitin').
        """
        )
    sources: List[AvailableSources] = Field(
    description="""
    Provide a list of relevant data sources associated with the user's query. This list must be context-aware and adapt to the user's intent and expertise.

    - If the user is asking a new question not tied to previous responses, include all relevant sources.
    - If the user has previously received information from multiple sources and is now asking a follow-up question that clearly refers to one of them, only include that specific source.
    - Do not include sources that are not explicitly or implicitly relevant to the current query, especially if the user is narrowing their focus.

    Inclusion principles:
    - Be inclusive when the user does not specify a source: if multiple sources could plausibly contain relevant data, include them all.
    - Be precise when the user specifies a source: restrict your output to only those sources.
    - Adapt to user expertise:
    - If the user appears to be an expert (e.g., uses precise terminology, references specific datasets or identifiers), prioritize their guidance and avoid over-inclusion.
    - If the user appears to be exploring or unfamiliar with the data landscape, be more proactive and inclusive in suggesting relevant sources.

    This list is required, but it may be empty if no sources are applicable."""
    )
    reply: Optional[str] = Field(
        description="""If no relevant sources are found but the user's query is still on-topic, generate an optional, 
                     friendly response that acknowledges the query and offers helpful guidance, clarification, or 
                     next steps. The tone should be supportive and conversational. This is only used when off_topic is False and sources is empty."""
    )
    source_contexts: Optional[Dict[AvailableSources, str]] = Field(
        description="""Mapping of each relevant source to a context-enriched version of the user's query.
            For each relevant source, generate a version of the user's query that is enriched with contextual information. 
            The enriched query should be self-contained and understandable without requiring access to prior conversation history. 
            Required if sources are provided. Can be an empty dict if no sources are specified."""
        )

    _data_source_events: List[Type[Event]] = PrivateAttr(default_factory=list)
    
    @model_validator(mode="before")
    @classmethod
    def convert_strings_to_enums(cls, values):
        """
        Converts string representations of sources and source_contexts keys
        into AvailableSources enum members.

        This allows the model to accept LLM-friendly JSON input where sources
        are provided as strings (e.g., "Proteomic Data Commons") and ensures
        they are converted to enum instances internally.
        """
        if "sources" in values:
            values["sources"] = [
                AvailableSources(s) if isinstance(s, str) else s
                for s in values["sources"]
            ]
            
        if "source_contexts" not in values or values["source_contexts"] is None:
            values["source_contexts"] = {}

        values["source_contexts"] = {
            AvailableSources(k) if isinstance(k, str) else k: v
            for k, v in values["source_contexts"].items()
        }

        return values

    @model_validator(mode="after")
    def validate_source_context_required(self):
        """
        Ensures that if `sources` is provided, `source_contexts` must also be populated.
        """
        missing_contexts = set(self.sources) - set(self.source_contexts.keys())
        if missing_contexts:
            raise ValueError(f"Missing source_contexts for sources: {missing_contexts}")
        return self

    @classmethod
    def from_str(cls, content: str):
        """
        Creates an `Intent` instance from a JSON string.
        
        Args:
            content (str): JSON string representing the Intent object.
        
        Returns:
            Intent: Parsed Intent instance.
        """
        return cls(**json.loads(content))

    def source_events(self, unique: bool = False) -> List[Event]:
        """
        Instantiates and stores event objects corresponding to each source in `self.sources`.

        Each source in the `sources` list is associated with an event class via the
        `AvailableSources` enum. This method creates an instance of each event class,
        assigns the source name to the `src_name` attribute, and stores the resulting
        list in the private `_data_source_events` attribute.

        Args:
            unique (bool): If True, ensures that the returned list of events contains
                        only unique instances (based on class identity).

        Returns:
            List[Event]: A list of instantiated event objects corresponding to the sources.
        """
        event_list = []
        for source in self.sources:
            event = source.event_class
            event.src_name = source.value
            event_list.append(event)
            
        self._validate_events(event_list)
        self._data_source_events = list(set(event_list)) if unique else event_list
        return self._data_source_events


    def _validate_events(self, event_list: List[Event]) -> None:
        """
        Validates that the event list contains valid event instances.

        Raises:
            ValueError: If the list is empty or contains only None values.
        """
        if not event_list or all(event is None for event in event_list):
            raise ValueError(
                f"Could not generate valid events for sources: {[s.value for s in self.sources]}"
            )

    @property
    def data_source_events(self) -> list:
        """
        Public accessor for the list of data source event objects.

        Returns:
            list: List of event objects associated with the sources.
        """
        return self._data_source_events