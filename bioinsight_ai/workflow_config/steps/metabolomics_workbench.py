from __future__ import annotations
from llama_index.core.agent.workflow.workflow_events import AgentOutput, ToolCallResult
from llama_index.core.llms.llm import ToolSelection
from data_sources.metabolomics_workbench.mwb.chat_agent import MolView
import re


class MWBOutput(AgentOutput):
    @classmethod
    def convert(cls, output: AgentOutput) -> MWBOutput:
        """
        Convert an AgentWorkflow output object, AgentOutput, to a subclass with extension for specific Metabolomics Workbench post-processing.
        """
        instance = cls.model_validate(output.model_dump())
        instance._hyperlink_study_ids()
        instance._fetch_elements()
        instance._hyperlink_PNG_URLs()
        return instance
    def _hyperlink_study_ids(self) -> None:   
        """
        Replaces all occurrences of Metabolomics Workbench study IDs (ST######)
        with HTML hyperlinks to the corresponding study page.
        """
        pattern = r"\bST\d{6}\b"
        self.modified_response_content = re.sub(pattern, self._replace_study_ids, self.response.content)

    @staticmethod
    def _replace_study_ids(match) -> str:
        """
        Replace matched study IDs with HTML hyperlink notation to study URL.
        """
        study_id = match.group(0)
        url = f"https://metabolomicsworkbench.org/data/DRCCMetadata.php?Mode=Study&StudyID={study_id}"
        return f'<a href="{url}">{study_id}</a>'
    
    def _fetch_elements(self) -> list[MolView]:
        """
        Check for certain element generating tool calls to pass on to Chainlit UI for rendering. 
        Currently only implemented for MolView (subclass event to trigger custom element generation).
        """
        toolcallresults = {}
        toolselection = {}
  
        # tool_calls doesn't always store results
        # 1) check for both calls generating functions (function names are known ahead of time e.g. "generate_molecule_view()")
        # 2) check tool call results emitted output (event classes that trigger UI elements known ahead of time e.g. "MolView")
        for i in self.tool_calls:
            toolcallresults.update(self._toolcallresults_elements(i))
            toolselection.update(self._toolselection_elements(i))
        
        el_dict = toolcallresults | toolselection # prioritize results over selection if same tool ID 
        self.elements = list(el_dict.values())
        
    @staticmethod
    def _toolcallresults_elements(tool_call) -> dict[str, MolView]:
        """
        Search ToolCallResults for elements.
        """
        if isinstance(tool_call, ToolCallResult) and isinstance(tool_call.tool_output.raw_output, MolView):
            return {tool_call.tool_id: tool_call.tool_output.raw_output} 
        else:
            return {}
        
    @staticmethod
    def _toolselection_elements(tool_call) -> dict[str, MolView]:
        """
        Search ToolSelection for element generating functions.
        """
        if isinstance(tool_call, ToolSelection) and tool_call.tool_name == "generate_molecule_view":
            return {tool_call.tool_id: MolView(**tool_call.tool_kwargs)}
        else:
            return {}
    
    def _hyperlink_PNG_URLs(self) -> None:
        """
        LLM does not consistently hyperlink PNG URLs from Compound context of Metabolomics Workbench API. 
        Capture image text, if created by LLM, and URL and replace with markdown syntax for image rendering in UI.
        """
        
        # 1) !? Matches an optional exclamation mark at the beginning (used in Markdown for images)
        # 2) (?:\[(.*?)\])?
        #   Non-capturing group for optional square brackets:
        #   \[ and \] match literal square brackets
        #   (.*?) captures any characters inside the brackets (non-greedy)
        #   The entire group is optional due to the trailing ?
        # 3) \s* Matches zero or more whitespace characters
        # 4) \(? Matches an optional opening parenthesis (used in Markdown links/images)
        # 5) https?:\/\/ Matches the protocol part of the URL: "http://" or "https://"
        # 6) \S*? Matches any non-whitespace characters (non-greedy), representing the start of the URL
        # 7) (rest\/compound\S*?png\S*?)
        #   Capturing group:
        #   Matches "rest/compound" followed by any non-whitespace characters (non-greedy)
        #   Must include "png" somewhere in the path
        #   This group captures the specific part of the URL path of interest
        # 8) \)?
        # Matches an optional closing parenthesis (used in Markdown links/images)
        # The intention of this is to fix the following examples: 
        # 1) ![](https://www.metabolomicsworkbench.org/rest/compound/regno/37288/png) - no description
        # 2) [some text](https://www.metabolomicsworkbench.org/rest/compound/regno/37288/png) - missing !, but has description and URL
        # 3) https://www.metabolomicsworkbench.org/rest/compound/regno/37288/png - not formatted at all but has URL
        # 4) https://www.metabolomics-workbench.org/rest/compound/regno/37288/png - typo in URL

        pattern = r"""!?(?:\[(.*?)\])?\s*\(?https?:\/\/\S*?(rest\/compound\S*?png\S*?)\)?"""

        self.modified_response_content = re.sub(pattern, self._replace_PNG_URLs, self.modified_response_content, flags=re.IGNORECASE)
        
    @staticmethod
    def _replace_PNG_URLs(match: re.Match) -> str:
        """
        Match markdown link label and URL from text if available.
        """
        label = match.group(1) if match.group(1) else "Metabolomics Workbench Compound Structure"
        url = match.group(2)
        # REST URL is used because sometimes LLM incorrectly renders URL
        return f"![{label}](https://www.metabolomicsworkbench.org/{url})"