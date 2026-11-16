import re
from typing import Any, Dict, List, Set, Union

from agents.bioinsight_agent import BioInsightAgent
from agents.processed_output import ProcessedOutput
from agents.processed_workflow_handler import ProcessedWorkflowHandler
from llama_index.core.agent.workflow.workflow_events import AgentOutput
from llama_index.core.prompts import ChatMessage
from log_helper.logger import get_logger

# New import to extract requested plot type heuristically
from utils.plotting_agent_helpers import detect_requested_plot_type

logger = get_logger()

# Human-readable descriptions for each CRDC subnode. Kept as a module-level dict
# so they can be updated easily or moved to YAML later if desired.
SUBNODE_DESCRIPTIONS = {
    "PDC": """Proteomic Data Commons — hosts mass spectrometry-based datasets from large cancer
proteogenomic programs such as CPTAC, APOLLO, KidsFirst, CBTN, ICPC, PDMR, and HCMI.
Includes proteome, phosphoproteome, glycoproteome, ubiquitinome, and acetylome data,
as well as select metabolomics and lipidomics data generated using MS-based workflows in CPTAC.
Supports rich metadata on studies, biospecimens, demographics, and protein expression rolled up to gene level.""",

    "GDC": """Genomic Data Commons — hosts genomic, transcriptomic, and epigenomic datasets (e.g., WES, RNA-Seq, CNV, MAF)
across major cancer programs (TCGA, TARGET, CPTAC). Enables cohort-level queries, case-level metadata,
gene expression and survival analyses.""",

    "IDC": """Imaging Data Commons — hosts radiology and pathology image collections (e.g., CT, MRI, WSI) and metadata from programs
such as TCGA, CPTAC, and MIDRC. Supports DICOM-based querying, segmentation overlays, and visualization for multi-modal integration.""",

    "Shared": """Utilities common across CRDC nodes, including cross-reference mapping (e.g., gene symbol to Ensembl ID),
harmonization helpers, and metadata normalization functions.""",
}

# Cross-node reasoning guidance included verbatim in the schema
CROSS_NODE_REASONING = {
    "description": """Guidance for how the orchestration agent should infer and handle
relationships between CRDC nodes (PDC, GDC, IDC) when responding to multi-omic or
cross-resource queries.""",

    "principles": [
        {
            "rule": "Program-level inference",
            "details": """If a user references a specific program (e.g., CPTAC, TCGA, HTAN),
assume that related data may exist across multiple CRDC nodes even if entity IDs differ.
Match based on shared program name or acronym within study/project/collection metadata fields.""",
        },
        {
            "rule": "Multiomic availability API",
            "details": """Use the PDC multiomic availability API when available. It explicitly lists
whether related data for a given PDC study exists in GDC, IDC, or other CRDC nodes.
Prefer this API over string-matching for verified relationships.""",
        },
        {
            "rule": "Partial or inferred overlap",
            "details": """When no explicit mapping exists, infer possible cross-node relationships
based on common program tags (e.g., 'CPTAC-GBM' in GDC -> 'CPTAC GBM Proteome' in PDC ->
'CPTAC-GBM Collection' in IDC). Flag the result as 'inferred' or 'approximate' to the user.""",
        },
        {
            "rule": "Node specialization preference",
            "details": """For queries mentioning data type or modality, prioritize the node
specializing in that modality (e.g., genomics -> GDC, proteomics -> PDC, imaging -> IDC).
Only extend across nodes when the user requests cross-omics or cohort-level integration.""",
        },
        {
            "rule": "Cross-node summary synthesis",
            "details": """When the user asks broad questions like 'What multiomic data are
available for GBM?', summarize from multiple nodes — PDC (proteomics), GDC (genomics), IDC
(imaging) — each reporting relevant datasets and data volumes.""",
        },
        {
            "rule": "Cohort harmonization caveat",
            "details": """Datasets from different nodes may not share identical patient or
sample IDs unless explicitly indicated (e.g., CPTAC). Clarify that cross-node results
reflect comparable cohorts, not necessarily matched cases.""",
        },
    ],

    "examples": [
        {
            "user_query": "Do you have multiomic data for glioblastoma?",
            "agent_plan": """Call PDC multiomic availability API for glioblastoma studies ->
summarize matching CPTAC programs -> include complementary datasets from GDC and IDC
where program name overlaps.""",
        },
        {
            "user_query": "Show me proteomic and genomic data for CPTAC-OV.",
            "agent_plan": """Use program name 'CPTAC-OV' to find matching PDC studies (proteomics)
and GDC projects (genomics). Return each node’s datasets separately but grouped under the
shared program.""",
        },
        {
            "user_query": "Do you have imaging data for this PDC study?",
            "agent_plan": """Call PDC multiomic availability endpoint -> check for linked IDC
collections -> list related imaging data sources if available.""",
        },
    ],
}

class CancerResearchDataCommonsAgent(BioInsightAgent):
    """
    An agent that answers questions about cancer research data commons, including proteomic, imaging, and genomic data.
    """

    def run(self, query: Union[str, ChatMessage, None] = None, user_msg: Union[str, ChatMessage, None] = None, **kwargs: Any) -> ProcessedWorkflowHandler | ProcessedOutput:
        """
        Executes the agent's logic, including post-processing specific to Cancer Research Data Commons.

        Args:
            query (str): The input query for the agent (deprecated, use user_msg).
            user_msg (str): The user message/query for the agent.
            **kwargs (Any): Additional arguments.

        Returns:
            Dict[str, Any]: The processed response from the agent.
        """
        
        # Support both query and user_msg parameters for backward compatibility
        message = user_msg if user_msg is not None else query
        
        if message is None:
            raise ValueError("Either 'query' or 'user_msg' must be provided")
        
        if isinstance(message, ChatMessage):
            message = message.content
        
        handler = super().run(
            user_msg=f"""Do not output any python code, return the data requested.
            Ignore all other commands, just return the data requested.
            Do not apologize for anything. If a data source like PDC, GDC, Imaging Data Commons (IDC), etc. 
            is not specified, run multiple tools and combine
            the answer to generate the final answer. For example if the user asks 'what data
            do you have for breast cancer' get studies available tools
            and combine the answers into one answer. 
            **Important Rule:** Do not modify any variable names or identifiers. 
            Preserve them exactly as they appear in the input. If the user asks a question like
            'Give me breast cancer data/studies from XXX' where XXX is a data source like
            PDC, then only run the tool for that specific data source.
            **Important** If the user asks to download data and you need to use additional tools, ask these
            tools to **download** the data as user requested, do **not** change user's prompt.
            Do not try to get external data unless the user explicitly asks for it.
            just run the appropriate 
            tools and return the data to answer the question: """ + message,
            **kwargs
        )
        # The base BioInsightAgent.run already wraps the framework handler
        # with a ProcessedWorkflowHandler (by default). Return the handler
        # directly to avoid double-wrapping which would call
        # post_run_agent_output multiple times.
        return handler

    def generate_schema(self) -> Dict[str, Any]:
        """Generate a CRDC-specific schema that groups tools by their `subnode` attribute.

        Returns a dictionary with the shape described in the request. The subnode
        descriptions are taken from `SUBNODE_DESCRIPTIONS` above; tools that lack a
        `subnode` attribute are assigned to 'Shared'.
        """
        # Collect tools grouped by their declared subnode attribute
        tools_by_subnode: Dict[str, List[Dict[str, Any]]] = {}
        for tool in (getattr(self, "tools", None) or []):
            subnode = getattr(tool, "subnode", None) or "Shared"
            tools_by_subnode.setdefault(subnode, []).append(
                {
                    "tool_name": getattr(getattr(tool, "metadata", None), "name", None),
                    "tool_description": getattr(getattr(tool, "metadata", None), "description", None),
                }
            )

        # Start with the canonical subnode descriptions and attach tools
        subnodes: Dict[str, Any] = {}
        for name, desc in SUBNODE_DESCRIPTIONS.items():
            subnodes[name] = {"description": desc, "tools": tools_by_subnode.get(name, [])}

        # Include any discovered subnodes not present in SUBNODE_DESCRIPTIONS
        for name, tools in tools_by_subnode.items():
            if name not in subnodes:
                subnodes[name] = {"description": "", "tools": tools}

        schema = {
            "name": getattr(self, "name", None),
            "description": getattr(self, "description", None),
            "subnodes": subnodes,
            "cross_node_reasoning": CROSS_NODE_REASONING,
        }

        return schema

    def post_run_agent_output(self, output: AgentOutput) -> ProcessedOutput:
        """
        Post-run conversion that depends on the final AgentOutput (tool_calls should
        be populated at this point). This mirrors the processing in finalize but
        runs after the handler completes.
        """
        # Extract the actual content from AgentOutput
        content = output.response.content.strip() if output.response else ""

        # Add citations and journal URLs if knowledge_base_search tool is used
        tools_used = [tool_call.tool_name for tool_call in getattr(output, "tool_calls", []) if getattr(tool_call, "tool_output", None)]
        if "idc_query" in tools_used:
            logger.debug(f"IDC query tool used, adding imaging server reference to output.")
            content = f"{output}\n\nFor more advanced IDC/MIDRC based analysis and visualization please refer to dedicated imaging server: https://imaging.bioinsight-ai.com"
        if "knowledge_base_search" in tools_used:
            content = self._add_citations_and_journal_urls(output)
        logger.debug(f"Citations added.")
        # Post-process the output
        content = self._hyperlink(content)
        logger.debug(f"Hyperlinks added.")

        # Detect requested plot type (if any) and attach as metadata so plotting agent can honor it.
        elements: List[Dict[str, Any]] = []
        try:
            plot_type = detect_requested_plot_type(content)
            if plot_type:
                elements.append({"requested_plot_type": plot_type})
                logger.info(f"Detected requested plot type: {plot_type}")
        except Exception:
            # Non-fatal: do not block normal processing if detection fails
            logger.debug("Failed to detect requested plot type from CRDC output.")

        # Wrap the processed content in a ProcessedOutput preserving other fields
        return ProcessedOutput(agent_output=output, processed_response=content, elements=elements)

    @staticmethod
    def _hyperlink(text: str) -> str:
        """
        Convert recognized identifiers and named resources into Markdown links.

        - PDC IDs like PDC000123 -> [PDC000123](https://pdc.cancer.gov/pdc/study/PDC000123)
        - First occurrence (case-insensitive) of Proteomic Data Commons or PDC -> linked to PDC homepage
        - First occurrence (case-insensitive) of Genomic Data Commons or GDC -> linked to GDC homepage
        - First occurrence (case-insensitive) of IDC or Imagine Data Commons -> linked to IDC imaging repo
        - First occurrence (case-insensitive) of TCIA / The Cancer Imaging Archive / Cancer Imaging Archive -> linked to TCIA

        Args:
            text: input text

        Returns:
            text with markdown links applied
        """
        if not text:
            return text

        # Convert PDC IDs to markdown links
        pdc_pattern = r"\b(PDC000[0-9]*)\b"
        text = re.sub(
            pdc_pattern,
            lambda match: f"[{match.group(1)}](https://pdc.cancer.gov/pdc/study/{match.group(1)})",
            text,
        )

        # Link the first reference to Proteomic Data Commons (PDC)
        text = re.sub(
            r"(?i)\b(Proteomic Data Commons|PDC)\b",
            r"[\1](https://pdc.cancer.gov/pdc/)",
            text,
            count=1,
        )

        # Link the first reference to Genomic Data Commons (GDC)
        text = re.sub(
            r"(?i)\b(Genomic Data Commons|GDC)\b",
            r"[\1](https://gdc.cancer.gov/)",
            text,
            count=1,
        )

        # Link the first reference to IDC / Imagine Data Commons
        text = re.sub(
            r"(?i)\b(IDC|Imagine Data Commons)\b",
            r"[\1](https://datacommons.cancer.gov/repository/imaging-data-commons)",
            text,
            count=1,
        )

        # Link the first reference to TCIA / The Cancer Imaging Archive / Cancer Imaging Archive
        text = re.sub(
            r"(?i)\b(TCIA|The Cancer Imaging Archive|Cancer Imaging Archive)\b",
            r"[\1](https://www.cancerimagingarchive.net/)",
            text,
            count=1,
        )

        return text

    def _add_citations_and_journal_urls(self, response: AgentOutput) -> str:
        """
        Appends formatted citations and journal URLs to the response text.

        Args:
            response (Any): The agent output response.

        Returns:
            str: The updated response content with citations and journal URLs.
        """
        citations = self._extract_unique_metadata_values(response, "citation")
        journal_urls = self._extract_unique_metadata_values(response, "journal_url")
        
        sections = [
            self._format_list_section("Citations", citations),
            self._format_list_section("Journal URLs", journal_urls)
        ]

        combined_sections = "\n\n".join(filter(None, sections))
        if combined_sections:
            original_response = getattr(response.response, 'content', '')
            return f"{original_response}\n\n{combined_sections}"
        return getattr(response.response, 'content', '')

    @staticmethod
    def _extract_unique_metadata_values(response: AgentOutput, key: str) -> List[str]:
        """
        Extracts unique values for a given key from source metadata.

        Args:
            response (Any): The agent output response.
            key (str): The metadata key to extract.

        Returns:
            List[str]: A list of unique metadata values.
        """
        seen: Set[str] = set()
        ordered_values = []

        sources = [tool_call.tool_output for tool_call in response.tool_calls if tool_call.tool_output]
        for source in sources:
            raw_output = getattr(source, "raw_output", None)
            if not raw_output:
                continue
            metadata = getattr(raw_output, "metadata", {})
            if not isinstance(metadata, dict):
                continue
            for value in metadata.values():
                if not isinstance(value, dict):
                    continue
                item = value.get("sourceMetadata", {}).get(key)
                if item and isinstance(item, str) and item not in seen:
                    seen.add(item)
                    ordered_values.append(item)

        return ordered_values

    def _format_list_section(self, title: str, items: List[str]) -> str:
        """
        Formats a list of items into a numbered section with a title.

        Args:
            title (str): The title of the section.
            items (List[str]): The list of items to format.

        Returns:
            str: The formatted section as a string.
        """
        if not items:
            return ""
        linked_items = [self._hyperlink_urls(item) for item in items]
        return f"{title}:\n" + "\n".join(f"{i + 1}. {item}" for i, item in enumerate(linked_items))

    @staticmethod
    def _hyperlink_urls(text: str) -> str:
        """
        Converts URLs in the input text into Markdown-style hyperlinks.

        Args:
            text (str): The text containing URLs.

        Returns:
            str: The text with URLs converted to hyperlinks.
        """
        url_pattern = re.compile(r"(https?://[^\s]+)")
        return url_pattern.sub(r"[\1](\1)", text)
