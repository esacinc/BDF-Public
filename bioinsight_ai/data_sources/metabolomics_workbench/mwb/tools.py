import aiohttp
from typing import Literal
from workflow_config.default_settings import Settings
from llama_index.core.workflow import Event
from typing import Literal, Annotated
from log_helper.logger import get_logger

logger = get_logger()

#
# Common tools used across many MWB agents
#

# Async MWB REST endpoint API calling function
async def call_rest_endpoint(context: Literal["study", "compound", "refmet", "protein", "gene"], 
                             input_item: str, 
                             input_value: str, 
                             output_item: str, 
                             output_format: str) -> str:
    """Make a call to a Metabolomic REST endpoint to fetch data."""    
    baseURL = "https://www.metabolomicsworkbench.org/rest"
    endpoint = f"{baseURL}/{context}/{input_item}/{input_value}/{output_item}/{output_format}"
    logger.info(f"[MWB REST API] Calling endpoint: {endpoint}")
    if output_item == "png":
        # Compound agent can return PNG endpoint for compound structure. This should be displayed in UI if 
        # returned as markdown.
        return f"Return the following URL in markdown format: {endpoint}"
    else: 
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint) as response:
                if response.ok:
                    try:
                        data = await response.json()
                    except:
                        data = await response.text()
                    return data
                else:
                    logger.error(f"[MWB REST API] Call failed with response: {response.status}:{response.reason}")
                    return response.reason
                
class MolView(Event):
    """
    Represents a 3D molecular view element.

    Compatibility note:
    LlamaIndex Context JsonSerializer expects component-like objects to expose 
    a `class_name` attribute (or property) and to provide `to_dict()` and 
    `from_dict()` methods. These exact names are relied on by the serializer's 
    detection and reconstruction paths.
    """
    def __init__(self, cid: str, regno: str, title: str, mode: str = "balls", bg: str = "black", **kwargs):
        super().__init__(**kwargs)
        self.cid = cid
        self.regno = regno
        self.title = title
        self.mode = mode
        self.bg = bg
        
    def __repr__(self):
        return f"MolView(cid='{self.cid}', regno='{self.regno}', title='{self.title}', mode='{self.mode}', bg='{self.bg}')"

    # __hash__ and __eq__ implemented to deduplicate MolView instances if tool called multiple times
    def __hash__(self) -> int:
        """Hash by canonical identifier (cid preferred, then regno)."""
        key = self.cid or self.regno
        return hash(key)

    def __eq__(self, other: object) -> bool:
        """
        Equality by canonical identifier: prefer cid, otherwise regno.
        """
        if not isinstance(other, MolView):
            return NotImplemented

        self_key = self.cid or self.regno
        other_key = other.cid or other.regno

        return self_key == other_key

    # JSON-serializer compatibility for Context serialization
    @property
    def class_name(self) -> str:
        """
        Qualified class name used by the JsonSerializer detection path.
        
        The presence of a `class_name` attribute signals to JsonSerializer 
        that it should package the result of `to_dict()` in a component 
        envelope and call `MolView.from_dict()` on deserialization.
        """
        return f"{self.__class__.__module__}.{self.__class__.__name__}"

    def to_dict(self):
        """
        Produce a JSON-serializable dict representing this MolView.
        
        Returns:
            dict: Dictionary with all required fields for reconstruction
        """
        return {
            "cid": self.cid,
            "regno": self.regno,
            "title": self.title,
            "mode": self.mode,
            "bg": self.bg,
        }

    @classmethod
    def from_dict(cls, data):
        """
        Reconstruct a MolView instance from a dictionary.
        
        Args:
            data: Dictionary produced by `to_dict()`
            
        Returns:
            MolView: Reconstructed instance
        """
        return cls(
            cid=data.get("cid", ""),
            regno=data.get("regno", ""),
            title=data.get("title", ""),
            mode=data.get("mode", "balls"),
            bg=data.get("bg", "black"),
        )

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
    Useful for summarizing and providing general information about a compound.
    """ 
    mol_view = MolView(cid=cid, regno=regno, title=title, mode=mode, bg=bg)
    return(mol_view)