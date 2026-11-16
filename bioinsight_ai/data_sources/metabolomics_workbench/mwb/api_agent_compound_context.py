import data_sources.metabolomics_workbench.mwb.api_validation_input_output as io_validation
import data_sources.metabolomics_workbench.mwb.api_validation_permutation as validation
from agents.bioinsight_agent import BioInsightAgent
from typing import Literal, Annotated
from workflow_config.default_settings import Settings
from .tools import call_rest_endpoint, generate_molecule_view

#
# MWB sub-agent specializing in one of seven context areas of the MWB REST API
#

context = "compound"

# Annotated tool specifically for formulating a compound endpoint
async def compound_api(
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
    f"""Function to construct and call a valid REST API URL path to retrieve {context} context data from the Metabolomics Workbench website."""
    
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
    
    kwargs = {'context': context, 'input_item': input_item, 'input_value': input_value, 'output_item': output_item, 'output_format': output_format}
    
    data = await call_rest_endpoint(**kwargs)
    
    return data

compound_agent = BioInsightAgent(
    name=f"{context.title()} Agent",
    description=("Take a user plain language question, translate it appropriately into Metabolomics Workbench REST API endpoint keywords, call the API to get data, "
                 f"and use the data to respond. Specializes in the {context} context area of the API. The 'compound' context provides services for the Metabolomics "
                 "Workbench Metabolite Database which contains structures and annotations of biologically relevant metabolites. The database contains over 64,000 "
                 "entries, collected from public repositories such as LIPID MAPS, ChEBI, HMDB, BMRB, PubChem, and KEGG, as well as from literature sources. This context "
                 "provides access to many structural features including molfile, SMILES, InChIKey, exact mass, formula common and systematic names, chemical classification "
                 "and cross-references to other databases."
                 ),
    system_prompt=f"""
<role>
You are a specialized agent for the Metabolomics Workbench REST API, focused on the {context} context.
Your primary function is to translate user queries into API calls and present results clearly then work with other agents as needed to provide a complete answer.
</role>

<background_information>
API Keyword Input/Output Validation: 
{io_validation.compound}

Parameter Validation: 
{validation.compound}
</background_information>

<instructions>
<workflow>
1. Analyze the user's query to identify required API endpoints
2. Use the 'compound_api' tool to translate the user's query into API parameters and execute the call in a single operation
3. Analyze the API response data to determine if additional endpoint calls are needed
4. Repeat step 2 as necessary until you have sufficient information to answer the query
5. Format your response with proper markdown
6. For molecule-specific queries with CID or regno, generate 3D views using `generate_molecule_view()`
7. Consider hand-off to other agents if the query extends beyond your context to provide a comprehensive answer
</workflow>

<response_guidelines>
- Prioritize API data over general knowledge
- Cite specific data points from responses
- Acknowledge data limitations when present
</response_guidelines>

<error_handling>
If compound_api returns an error:
1. Examine which parameter validation failed
2. Adjust parameters based on the validation criteria provided
3. Retry with corrected parameters
4. If multiple attempts fail, explain to the user which constraints prevent the query
</error_handling>
</instructions>

<formatting_rules>
- SMILES notation should be in markdown with backticks: `[OH2]`
- PNG images: ![Description](URL)
- 3D molecule views: Begin with "Below you will find [description]" - the 3D viewer will be rendered at the end of your response.
</formatting_rules>
""",
    tools=[compound_api, generate_molecule_view],
    can_hand_off_to=["Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent", "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"],
    allow_parallel_tool_calls=False
)