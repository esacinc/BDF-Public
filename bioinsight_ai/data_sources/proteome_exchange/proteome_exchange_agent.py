import re
from typing import Any

from agents.bioinsight_agent import BioInsightAgent
from agents.processed_output import ProcessedOutput
from llama_index.core.agent.workflow.workflow_events import AgentOutput

class ProteomeExchangeAgent(BioInsightAgent):
    def __init__(self, name: str, description: str, system_prompt: str, tools: Any) -> None:
        """
        Initialize the ProteomeExchangeAgent.

        Args:
            name (str): The name of the agent.
            description (str): A brief description of the agent.
            system_prompt (str): The system prompt for the agent.
            tools (Any): Tools available to the agent.
        """
        super().__init__(name=name, description=description, system_prompt=system_prompt, tools=tools)

    def post_run_agent_output(self, output: AgentOutput) -> ProcessedOutput:
        """
        Convert a raw AgentOutput into a ProcessedOutput by applying ProteomeXchange
        specific transformations (linking study IDs and the first ProteomeXchange mention).

        This hook is called by the base `ProcessedWorkflowHandler` after the underlying
        handler completes and the full `AgentOutput` (including tool calls) is available.
        """
        # Extract the actual content from AgentOutput
        content_str = output.response.content if output.response else ""

        # Apply transformations
        content_str = self._convert_study_ids_to_links(content_str)
        content_str = self._link_first_proteome_exchange(content_str)

        # Return a ProcessedOutput using the AgentOutput fields plus our processed content
        return ProcessedOutput(
            agent_output=output,
            processed_response=content_str,
        )

    @staticmethod
    def _convert_study_ids_to_links(text: str) -> str:
        """
        Converts ProteomeXchange study IDs (PXD\d{6}) to Markdown links.

        Example: PXD000123 -> [PXD000123](https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD000123)

        Args:
            text (str): The text containing study IDs.

        Returns:
            str: The text with study IDs converted to Markdown links.
        """
        study_id_pattern = r"PXD\d{6}"
        return re.sub(
            study_id_pattern,
            lambda match: f"[{match.group(0)}](https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID={match.group(0)})",
            text,
        )

    @staticmethod
    def _link_first_proteome_exchange(text: str) -> str:
        """
        Link the first instance of 'Proteome Exchange' or 'ProteomeXchange' to the ProteomeXchange homepage
        using a Markdown-style link.

        Example: ProteomeXchange -> [ProteomeXchange](https://www.proteomexchange.org/)

        Args:
            text (str): The text containing the phrase 'Proteome Exchange'.

        Returns:
            str: The text with the first instance of 'Proteome Exchange' linked as Markdown.
        """
        pattern = r"(?i)(Proteome[ ]?Xchange)"
        return re.sub(pattern, lambda m: f"[{m.group(1)}](https://www.proteomexchange.org/)", text, count=1)
