import data_sources.metabolomics_workbench.mwb.api_validation_input_output as io_validation
import data_sources.metabolomics_workbench.mwb.api_validation_permutation as validation
from llama_index.core.agent.workflow import FunctionAgent
from typing import Literal, Annotated
from workflow_config.default_settings import Settings
from .tools import call_rest_endpoint

#
# MWB sub-agent specializing in one of seven context areas of the MWB REST API
#

context = "protein"

# Annotated tool specifically for formulating a protein endpoint
def endpoint_kwargs(
    input_item: Annotated[
        Literal["mgp_id", "gene_id", "gene_name", "gene_symbol", "taxid", "mrna_id", "refseq_id", "protein_gi", "uniprot_id", "protein_entry", "protein_name"], 
        "One of mgp_id | gene_id | gene_name | gene_symbol | taxid | mrna_id | refseq_id | protein_gi | uniprot_id | protein_entry | protein_name."
    ],
    input_value: Annotated[
        str, 
        "An appropriate input value for given the input_item."
    ],
    output_item: Annotated[
        str, 
        """Either any of the following:
        all: The 'all' output item is automatically expanded to include the following items: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name, seqlength, seq, is_identical_to.
        mgp_id:
        gene_id:
        gene_name:
        gene_symbol:
        taxid:
        species:
        species_long:
        mrna_id:
        refseq_id:
        protein_gi:
        uniprot_id:
        protein_entry:
        protein_name:
        seqlength:
        seq:
        is_identical_to:
        
        Or multiple output items separated by commas with no spaces."""
    ],
    output_format: Annotated[
        Literal["txt", "json"], 
        "Return format of data. Can be one of the following: txt json. If unsure use json."
    ] = "json"
) -> str:
    f"""Function to validate keywords needed to construct a valid REST API URL path to retrieve {context} context data from the Metabolomics Workbench website."""
    return f"{{'context': {context}, 'input_item': {input_item}, 'input_value': {input_value}, 'output_item': {output_item}, 'output_format': {output_format}}}"


protein_agent = FunctionAgent(
    name=f"{context.title()} Agent",
    description=(
        "Take a user plain language question, translate it appropriately into Metabolomics Workbench REST API endpoint keywords, call the API to get data, "
        f"and use the data to respond. Specializes in the {context} context area of the API. The 'protein' context refers to a Human Metabolome Gene/Protein "
        "Database (MGP) of metabolome-related genes and proteins contains data for over 7300 genes and over 15,500 proteins. In addition to gene information, "
        "it provides access to protein related information such as MGP ID, various protein IDs, protein name, protein sequence, etc."
    ),
    system_prompt=(
        f"You are an expert on the Metabolomics Workbench data source, specifically the {context} context of the REST API. Do not use outside knowledge.\n"
        ""
        "Step 1: Determine if the user is asking a follow up question about about data you've already retrieved. "
        "If your memory provides enough detail then stop immediately and respond directly to the user. Do NOT proceed to the remaining steps.\n"
        "Step 2: If you cannot answer the question using memory then use the following context: \n"
        f"{io_validation.protein}"
        "and the 'endpoint_kwargs' tool to translate the plain language user query into appropriate endpoint keywords.\n"
        ""
        "Step 3: You must verify the output of 'endpoint_kwargs' against the following criteria and confirm for correctness:\n"
        f"{validation.protein}"
        ""
        "Step 4: If the criteria in Step 3 is met then use the tool 'call_rest_endpoint' to fetch data and answer the query. "
        "If clarification is needed from the user be then ask for clarification. If you have made ANY corrections to the user's query " 
        "mention that in your response.\n"
        "Step 5: If the criteria in Step 3 is violated then restart at Step 1, but reconsider the arguments passed to 'endpoint_kwargs' or "
        "if clarification is needed from the user be then ask for clarification but be direct.\n"
    ),
    tools=[endpoint_kwargs, call_rest_endpoint],
    can_hand_off_to=["Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent", "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"]
)