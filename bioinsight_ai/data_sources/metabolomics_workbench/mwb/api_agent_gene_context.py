import data_sources.metabolomics_workbench.mwb.api_validation_input_output as io_validation
import data_sources.metabolomics_workbench.mwb.api_validation_permutation as validation
from agents.bioinsight_agent import BioInsightAgent
from typing import Literal, Annotated
from workflow_config.default_settings import Settings
from .tools import call_rest_endpoint

#
# MWB sub-agent specializing in one of seven context areas of the MWB REST API
#

context = "gene"

# Annotated tool specifically for formulating a gene endpoint
async def gene_api(
    input_item: Annotated[
        Literal["mgp_id", "gene_id", "gene_name", "gene_symbol", "taxid"], 
        "One of mgp_id | gene_id | gene_name | gene_symbol | taxid."
    ],
    input_value: Annotated[
        str, 
        "An appropriate input value for given the input_item."
    ],
    output_item: Annotated[
        str, 
        """Either any of the following:
        all: The 'all' output item is automatically expanded to include the following items: mgp_id, gene_id, gene_name, gene_symbol, gene_synonyms, alt_names, chromosome, map_location, summary, taxid, species, species_long. These output items should not be specified with 'all' output item.
        lmp_id:
        mgp_id:
        gene_name:
        gene_symbol:
        gene_synonyms:
        alt_names:
        chromosome:
        map_location:
        summary:
        taxid:
        species:
        species_long:
        
        Or multiple output items separated by commas with no spaces."""
    ],
    output_format: Annotated[
        Literal["txt", "json"], 
        "Return format of data. Can be one of the following: txt json. If unsure use json."
    ] = "json"
) -> str:
    f"""Function to construct and call a valid REST API URL path to retrieve {context} context data from the Metabolomics Workbench website."""
    
    kwargs = {'context': {context}, 'input_item': {input_item}, 'input_value': {input_value}, 'output_item': {output_item}, 'output_format': {output_format}}
    
    data = await call_rest_endpoint(**kwargs)

    return data


gene_agent = BioInsightAgent(
    name=f"{context.title()} Agent",
    description=(
        "Take a user plain language question, translate it appropriately into Metabolomics Workbench REST API endpoint keywords, call the API to get data, "
        f"and use the data to respond. Specializes in the {context} context area of the API. The 'gene' context refers to a Human Metabolome Gene/Protein "
        "Database (MGP) of metabolome-related genes and proteins contains data for over 7300 genes and over 15,500 proteins. It provides access to gene "
        "related information such as MGP ID, gene ID and, symbols, gene names and synonyms, alternate gene names, taxonomy ID, species, etc."
    ),
    system_prompt=f"""
<role>
You are a specialized agent for the Metabolomics Workbench REST API, focused on the {context} context.
Your primary function is to translate user queries into API calls and present results clearly then work with other agents as needed to provide a complete answer.
</role>

<background_information>
API Keyword Input/Output Validation: 
{io_validation.gene}

Parameter Validation: 
{validation.gene}
</background_information>

<instructions>
<workflow>
1. Analyze the user's query to identify required API endpoints
2. Use the 'gene_api' tool to translate the user's query into API parameters and execute the call in a single operation
3. Analyze the API response data to determine if additional endpoint calls are needed
4. Repeat step 2 as necessary until you have sufficient information to answer the query
5. Format your response with proper markdown
7. Consider hand-off to other agents if the query extends beyond your context to provide a comprehensive answer
</workflow>

<response_guidelines>
- Prioritize API data over general knowledge
- Cite specific data points from responses
- Acknowledge data limitations when present
</response_guidelines>

<error_handling>
If gene_api returns an error:
1. Examine which parameter validation failed
2. Adjust parameters based on the validation criteria provided
3. Retry with corrected parameters
4. If multiple attempts fail, explain to the user which constraints prevent the query
</error_handling>
</instructions>
""",
    tools=[gene_api],
    can_hand_off_to=["Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent", "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"]
)