from llama_index.core.workflow import Event
from llama_index.core.agent.workflow import FunctionAgent
from typing import Annotated, Literal
from workflow_config.default_settings import Settings

#
# Primary Chat Agent that takes user query and hands off to an appropriate
# sub-agent specializing in a context area of the MWB REST API to get data
# or the RAG Agent for general questions
#

class VerboseMessage(Event):
    verbose: bool = False

def verbose_message(verbose: bool) -> VerboseMessage:
    """Return more information to the user if requested."""
    return(VerboseMessage(verbose=verbose))

class MolView(Event):
    def __init__(self, cid: str, regno: str, title: str, mode: str = "balls", bg: str = "black", **kwargs):
        super().__init__(**kwargs)
        self.cid = cid
        self.regno = regno
        self.title = title
        self.mode = mode
        self.bg = bg
    def __repr__(self):
        return f"MolView(cid='{self.cid}', regno='{self.regno}'title='{self.title}', mode='{self.mode}', bg='{self.bg}')"

def generate_molecule_view(
    cid: Annotated[str, "PubChem Compound Identifier"],
    regno: Annotated[str, "Metabolomics Workbench Registry Number (used as fallback if CID fails)"],
    title: Annotated[str, "Title of 3-D viewer"],
    mode: Annotated[
        Literal[
            'stick',     # Bonds as cylinders (default)
            'line',      # Lightweight lines
            'wireframe', # Thinner, faster lines
            'sphere',    # Atoms as spheres (space-filling)
            'vdw',       # Alias for sphere
            'cross',     # Atoms as crosses
            'balls',     # Custom: stick + sphere (ball-and-stick)
            'cartoon'    # Only for biomolecules (e.g., PDB)
        ],
        "Molecule representation style. Defaults to 'balls'. 'balls' is a custom ball-and-stick combo. 'cartoon' only works for biomolecules."
    ] = "balls",
    bg: Annotated[
        Literal['0x000000', '0xC0C0C0', '0xFFFFFF'],
        "Background color in hex. Defaults to '0x000000' (black)."
    ] = "0x000000"
) -> MolView:
    """Render an interactive 3-D view of a molecule from a PubChem Compound ID (CID) or Metabolomics Workbench registry number (regno). 
    Useful for summarizing and providing general information about a compound. Consider using this if `Compound Agent` was used to answer a query.
    """ 
    mol_view = MolView(cid=cid, regno=regno, title=title, mode=mode, bg=bg)
    return(mol_view)

chat_agent = FunctionAgent(
    name="Chat Agent",
    description="Top level agent used to route user queries to appropriate agents and provide a polished response to user.",
    system_prompt=(
        "You are a friendly, informative, and knowledgeable chat agent that specializes in providing information from Metabolomics "
        "Workbench only using information provided by agents or memory! Your response will be provided directly to the user so it needs to be clear. "
        "When taking steps to answer a user query do NOT mention specifics like which agents you are working with or what tools you are using. For "
        "example do not say 'hand this off to'. Instead you can provide a very basic description of what steps you are taking to answer the query, "
        "ensuring it is understandable to a basic user."
        ""
        "After receiving a user query you should consider the following:"
        "First, decide if the user is asking for general information or requires specific data from the website API. "
        "If the user query requires both then split the query up and pass it off to the appropriate agent and compile their responses into a final answer. "
        "Preserve any markdown formatting from other agents. "
        "If using `generate_molecule_view()` tool the 3D image will be generated below your response is displayed. Any references to the 3D model should start "
        "with a phrase like, 'Below you will find`, but still include the other information gathered from other agents in your response."
    ),
    tools=[verbose_message, generate_molecule_view],
    can_hand_off_to=["Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent", "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"]
)