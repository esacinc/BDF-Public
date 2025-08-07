import data_sources.metabolomics_workbench.mwb.api_validation_input_output as io_validation
import data_sources.metabolomics_workbench.mwb.api_validation_permutation as validation
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow import Event
from typing import Literal, Annotated
from workflow_config.default_settings import Settings
from .tools import call_rest_endpoint

#
# MWB sub-agent specializing in one of seven context areas of the MWB REST API
#

context = "compound"

# Annotated tool specifically for formulating a compound endpoint
def endpoint_kwargs(
    input_item: Annotated[
        Literal["regno", "formula", "inchi_key", "lm_id", "pubchem_cid", "hmdb_id", "kegg_id", "chebi_id", "metacyc_id", "abbrev"], 
        """One of regno | formula | inchi_key | lm_id | pubchem_cid | hmdb_id | kegg_id | chebi_id | metacyc_id | abbrev. 
        regno: The 'regno' input item refers to the Metabolomics Workbench Metabolite database internal identifier. It specifies a unique metabolite structure. The 'regno' input item is required for the 'png' output item."""
    ],
    input_value: Annotated[
        str, 
        "An appropriate input value for given the input_item."
    ],
    output_item: Annotated[
        str, 
        """Either any of the following: 
        * all: The 'all' output item is automatically expanded to include the following items: regno, formula, exactmass, inchi_key, name, sys_name, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, smiles. These output items should not be individually specified with the 'all' output item.
        * regno: The 'regno' input item refers to the Metabolomics Workbench Metabolite database internal identifier. It specifies a unique metabolite structure.
        * formula: 
        * exactmass:
        * inchi_key:
        * name:
        * sys_name:
        * smiles:
        * lm_id:
        * pubchem_cid:
        * hmdb_id:
        * kegg_id:
        * chebi_id:
        * metacyc_id:
        * classification: The 'classification' output item is automatically expanded to include the following items: regno, name, sys_name, cf_superclass, cf_class, cf_subclass, cf_direct_parent, cf_alternative_parents, lm_category, lm_main_class, lm_sub_class, lm_class_level4. These output items should not be individually specified with the 'classification' output item. The 'cf' and 'lm' correspond to ClassyFire and LIPID MAPS classification systems respectively.
        * molfile: The 'regno' input item is required for the 'molfile' and 'sdf' output items. No other comma delimited output items are allowed alongside 'molfile' and 'sdf'. The user is given the option to download the molfile as a text file.
        * sdf: The 'regno' input item is required for the 'molfile' and 'sdf' output items. No other comma delimited output items are allowed alongside 'molfile' and 'sdf'. The user is given the option to download the molfile as a text file.
        * png: The 'regno' input item is required for the 'png' output item. No other comma delimited output items are allowed alongside 'png'. The PNG image is displayed in the browser.    
        
        Or multiple items from the following list may be specified as output by placing commas between the items: regno, formula, exactmass, inchi_key, name, sys_name, lm_id, 
        pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, smiles. For example an output item name,formula,exactmass will display those 3 fields in the REST output."""
    ],
    output_format: Annotated[
        Literal["txt", "json"], 
        "Return format of data. Can be one of the following: txt | json. If unsure use json."
    ] = "json"
) -> str: 
    f"""Function to validate keywords needed to construct a valid REST API URL path to retrieve {context} context data from the Metabolomics Workbench website."""
    
    if "," in output_item:
        multi_item_set = ["regno", "formula", "exactmass", "inchi_key", "name", "sys_name", "lm_id", "pubchem_cid", "hmdb_id", "kegg_id", "chebi_id", "metacyc_id", "smiles"]
        output_list = output_item.split(",")
        valid_multi_item = [output in multi_item_set for output in output_list]
        if not all(valid_multi_item):
            invalid_items = [f"'{value}'" for value, valid in zip(output_list, valid_multi_item) if not valid]
            raise ValueError(
                    f"Invalid 'output_item' format. {', '.join(invalid_items)} not found. "
                    f"Only valid values are: {', '.join(multi_item_set)} separated by a comma without any space."
            )        
    return f"{{'context': 'compound', 'input_item': {input_item}, 'input_value': {input_value}, 'output_item': {output_item}, 'output_format': {output_format}}}"

class MolView(Event):
    def __init__(self, cid: str, regno: str, title: str, mode: str = "balls", bg: str = "black", **kwargs):
        super().__init__(**kwargs)
        self.cid = cid
        self.regno = regno
        self.title = title
        self.mode = mode
        self.bg = bg
    def __repr__(self):
        return f"MolView(cid='{self.cid}', regno='{self.regno}, 'title='{self.title}', mode='{self.mode}', bg='{self.bg}')"

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


compound_agent = FunctionAgent(
    name=f"{context.title()} Agent",
    description=("Take a user plain language question, translate it appropriately into Metabolomics Workbench REST API endpoint keywords, call the API to get data, "
                 f"and use the data to respond. Specializes in the {context} context area of the API. The 'compound' context provides services for the Metabolomics "
                 "Workbench Metabolite Database which contains structures and annotations of biologically relevant metabolites. The database contains over 64,000 "
                 "entries, collected from public repositories such as LIPID MAPS, ChEBI, HMDB, BMRB, PubChem, and KEGG, as well as from literature sources. This context "
                 "provides access to many structural features including molfile, SMILES, InChIKey, exact mass, formula common and systematic names, chemical classification "
                 "and cross-references to other databases."
                 ),
    system_prompt=(
        f"You are an expert on the Metabolomics Workbench data source, specifically the {context} context of the REST API. Do not use outside knowledge.\n"
        ""
        "Step 1: Determine if the user is asking a follow up question about about data you've already retrieved. "
        "If your memory provides enough detail then stop immediately and respond directly to the user. Do NOT proceed to the remaining steps.\n"
        "Step 2: If you cannot answer the question using memory then use the following context: \n"
        f"{io_validation.compound}"
        "and the 'endpoint_kwargs' tool to translate the plain language user query into appropriate endpoint keywords.\n"
        "Step 3: You must verify the output of 'endpoint_kwargs' against the following criteria and confirm for correctness:\n"
        f"{validation.compound}"
        ""
        "Step 4: If the criteria in Step 3 is met then use the tool 'call_rest_endpoint' to fetch data and answer the query. If requesting an image then return the URL. "
        "If clarification is needed from the user be then ask for clarification. If you have made ANY corrections to the user's query " 
        "mention that in your response. Any SMILES notation should be returned in markdown format (e.g. `[OH2]`). Any png URLs should be displayed in markdown (e.g. [<Image description>](<Image URL>). "
        "Step 5: If the criteria in Step 3 is violated then restart at Step 1, but reconsider the arguments passed to 'endpoint_kwargs' or "
        "if clarification is needed from the user be then ask for clarification but be direct.\n"
        "If using `generate_molecule_view()` tool the 3D molecule view will be generated below your response. Therefore, any references to the 3D model should start "
        "with a phrase like, 'Below you will find <3D molecule view description>`"
    ),
    tools=[endpoint_kwargs, call_rest_endpoint, generate_molecule_view],
    can_hand_off_to=["Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent", "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"]
)