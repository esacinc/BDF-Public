import re
from typing import Any, Dict, List, Union

from agents.bioinsight_agent_workflow import BioInsightAgentWorkflow
from agents.processed_output import ProcessedOutput
from agents.processed_workflow_handler import ProcessedWorkflowHandler
from data_sources.metabolomics_workbench.mwb.tools import MolView
from data_sources.metabolomics_workbench.prompts import DEFAULT_HANDOFF_OUTPUT_PROMPT
from llama_index.core.agent.workflow import ToolCallResult
from llama_index.core.agent.workflow.workflow_events import AgentOutput, ToolSelection
from llama_index.core.prompts import PromptTemplate, ChatMessage
from log_helper.logger import get_logger

logger = get_logger()

class MWBAgentWorkflow(BioInsightAgentWorkflow):
    """
    Extension of BioInsightAgentWorkflow for the Metabolomics Workbench workflow.
    """

    def run(self, user_query: Union[str, ChatMessage, None] = None, **kwargs: Any) -> ProcessedWorkflowHandler | ProcessedOutput:
        """
        Run the agent workflow with MWB-specific logic.

        Args:
            user_query (Union[str, ChatMessage, None]): The user query to process.
            **kwargs: Additional arguments for the workflow.

        Returns:
            ProcessedWorkflowHandler: The handler for event streaming or awaiting the final response.
        """
        # Pre-run logic: Update handoff_output_prompt
        prompts = self.get_prompts()
        prompts["handoff_output_prompt"] = PromptTemplate(DEFAULT_HANDOFF_OUTPUT_PROMPT.format(request=user_query))
        self.update_prompts(prompts)

        # Call the parent class's run method and return its handler. The base
        # implementation will apply the ProcessedWorkflowHandler wrapper by
        # default when post-processing is desired.
        handler = super().run(user_msg=user_query, **kwargs)
        return handler

    def post_run_agent_output(self, output: AgentOutput) -> ProcessedOutput:
        """
        Convert the raw AgentOutput into a ProcessedOutput by applying MWB-specific
        post-processing: hyperlinking study IDs, PNG URLs, and the Metabolomics
        Workbench name, and extracting element objects from tool calls.
        """
        # Extract the actual content from AgentOutput
        content = output.response.content if output.response else ""

        # Apply post-processing transformations
        content = self._hyperlink_study_ids(content)
        content = self._hyperlink_png_urls(content)
        content = self._hyperlink_metabolomics_workbench(content)

        # Fetch elements
        elements = self._fetch_elements(output.tool_calls)

        # Return a ProcessedOutput
        return ProcessedOutput(
            agent_output=output,
            processed_response=content,
            elements=elements,
        )

    def _hyperlink_study_ids(self, content: str) -> str:
        """
        Replace study IDs with Markdown links, but avoid study IDs that are already inside markdown links.

        Args:
            content (str): The content to process.

        Returns:
            str: The content with study IDs replaced by hyperlinks.
        """
        # Protect study IDs that already live inside markdown links or URLs so
        # they are not double-linked.  Strategy: temporarily swap protected
        # regions with null-byte placeholders, apply the bare-ID replacement,
        # then restore the originals.
        placeholders: List[str] = []

        def _protect(m: re.Match) -> str:
            placeholders.append(m.group(0))
            return f"\x00MWBLINK{len(placeholders) - 1}\x00"

        # 1. Protect existing markdown links:  [STxxxxxx](...)
        protected = re.sub(r"\[ST\d{6}\]\([^)]*\)", _protect, content)
        # 2. Protect study IDs inside any URL (http/https)
        protected = re.sub(r"https?://\S*ST\d{6}\S*", _protect, protected)
        # 3. Replace remaining bare study IDs
        protected = re.sub(r"\bST\d{6}\b", self._replace_study_ids, protected)
        # 4. Restore protected regions
        result = re.sub(r"\x00MWBLINK(\d+)\x00", lambda m: placeholders[int(m.group(1))], protected)
        return result

    @staticmethod
    def _replace_study_ids(match: re.Match) -> str:
        """
        Replace matched study IDs with Markdown-style links.

        Example: ST000123 -> [ST000123](https://www.metabolomicsworkbench.org/data/DRCCMetadata.php?StudyID=ST000123)

        Args:
            match (re.Match): The regex match object.

        Returns:
            str: The Markdown link for the study ID.
        """
        study_id = match.group(0)
        url = f"https://www.metabolomicsworkbench.org/data/DRCCMetadata.php?StudyID={study_id}"
        return f'[{study_id}]({url})'

    def _fetch_elements(self, tool_calls: List[ToolCallResult]) -> List[MolView]:
        """
        Extract elements from tool calls.

        Args:
            tool_calls (List[ToolCallResult]): The list of tool calls to process.

        Returns:
            List[MolView]: A list of extracted elements.
        """
        toolcallresults = {}
        toolselection = {}

        for tool_call in tool_calls:
            toolcallresults.update(self._toolcallresults_elements(tool_call))
            toolselection.update(self._toolselection_elements(tool_call))

        el_dict = toolcallresults | toolselection

        # Deduplicate MolView values using a set of canonical keys (cid preferred, then regno).
        return list(set(el_dict.values()))

    @staticmethod
    def _toolcallresults_elements(tool_call: ToolCallResult) -> Dict[str, MolView]:
        """
        Search ToolCallResults for elements.

        Args:
            tool_call (ToolCallResult): The tool call to process.

        Returns:
            Dict[str, MolView]: A dictionary of extracted elements.
        """
        if isinstance(tool_call, ToolCallResult) and isinstance(tool_call.tool_output.raw_output, MolView):
            return {tool_call.tool_id: tool_call.tool_output.raw_output}
        return {}

    @staticmethod
    def _toolselection_elements(tool_call: ToolSelection) -> Dict[str, MolView]:
        """
        Search ToolSelection for element-generating functions.

        Args:
            tool_call (ToolSelection): The tool call to process.

        Returns:
            Dict[str, MolView]: A dictionary of extracted elements.
        """
        if isinstance(tool_call, ToolSelection) and tool_call.tool_name == "generate_molecule_view":
            return {tool_call.tool_id: MolView(**tool_call.tool_kwargs)}
        return {}

    def _hyperlink_png_urls(self, content: str) -> str:
        """
        Format PNG URLs for proper rendering.

        Args:
            content (str): The content to process.

        Returns:
            str: The content with PNG URLs formatted.
        """
        pattern = r"!?(?:\[(.*?)\])?\s*\(?https?:\/\/\S*?(rest\/compound\S*?png\S*?)\)?"
        return re.sub(pattern, self._replace_png_urls, content, flags=re.IGNORECASE)

    @staticmethod
    def _replace_png_urls(match: re.Match) -> str:
        """
        Replace PNG URLs with markdown image syntax.

        Args:
            match (re.Match): The regex match object.

        Returns:
            str: The markdown image syntax for the PNG URL.
        """
        label = match.group(1) if match.group(1) else "Metabolomics Workbench Compound Structure"
        url = match.group(2)
        return f"![{label}](https://www.metabolomicsworkbench.org/{url})"

    def _hyperlink_metabolomics_workbench(self, content: str) -> str:
        """
        Hyperlink the first instance of "Metabolomics Workbench" (case insensitive) to its homepage
        using a Markdown-style link.

        Example: Metabolomics Workbench -> [Metabolomics Workbench](https://metabolomicsworkbench.org/)

        Args:
            content (str): The content to process.

        Returns:
            str: The content with the first instance of "Metabolomics Workbench" hyperlinked as Markdown.
        """
        pattern = r"(?i)(metabolomics workbench)"
        return re.sub(pattern, lambda m: f'[{m.group(1)}](https://metabolomicsworkbench.org/)', content, count=1)
