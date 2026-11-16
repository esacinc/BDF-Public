import aiohttp
import data_sources.metabolomics_workbench.mwb.api_validation_input_output as io_validation
from agents.bioinsight_agent import BioInsightAgent
from typing import Literal, Annotated
from workflow_config.default_settings import Settings
from log_helper.logger import get_logger

logger = get_logger()

#
# MWB sub-agent specializing in one of seven context areas of the MWB REST API
#

context = "moverz"

async def call_moverz_endpoint(input_item: str, 
                               input_value1: str, 
                               input_value2: str, 
                               input_value3: str,
                               output_format: str) -> str:
    """Make a call to a Metabolomic REST endpoint to fetch data."""    
    baseURL = "https://www.metabolomicsworkbench.org/rest"
    endpoint = f"{baseURL}/{context}/{input_item}/{input_value1}/{input_value2}/{input_value3}/{output_format}"
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

# Annotated tool specifically for formulating a moverz endpoint
async def moverz_api(
    input_item: Annotated[
        Literal["LIPIDS", "MB", "REFMET", "exactmass"], 
        "One of LIPIDS | MB | REFMET | exactmass."
    ],
    input_value1: Annotated[
        str, 
        """m/z value or lipid abbreviation. The following head groups are currently supported as abbreviations for lipids when using the 'exactmass' 
        input item: ArthroCer, asialo-GM2Cer, CAR, CE, Cer, CerP, CoA, DG, DGDG, FA, GalCer, GB3Cer, GlcCer, GM3Cer, GM4Cer, iGB3Cer, LacCer, Lc3Cer, 
        Manb1-4GlcCer, MG, MGDG, MolluCer, PA, PC, PE, PE-Cer, PG, PGP, PI, PI-Cer, PIP, PIP2, PIP3, PS, SM, SQDG, TG."""
    ],
    input_value2: Annotated[
        str, 
        """ion type value. The following ion types (adducts) are currently supported: M+H, M+H-H2O, M+2H, M+3H, M+4H, M+K, M+2K, M+Na, M+2Na, M+Li, M+2Li, M+NH4, 
        M+H+CH3CN, M+Na+CH3CN, M.NaFormate+H, M.NH4Formate+H, M.CH3, M.TMSi, M.tBuDMSi, M-H, M-H-H2O, M+Na-2H, M+K-2H, M-2H, M-3H, M-4H, M.Cl, M.F, M.HF2, M.OAc, M.Formate, 
        M.NaFormate-H, M.NH4Formate-H, Neutral."""
    ],
    input_value3: Annotated[
        str, 
        "m/z tolerance value."
    ],
    output_format: Annotated[
        Literal["txt"], 
        "Return format of data. Can only be txt."
    ] = "txt"
) -> str:
    f"""Function to construct and call a valid REST API URL path to retrieve {context} context data from the Metabolomics Workbench website."""
    kwargs = {'input_item': {input_item}, 'input_value1': {input_value1}, 'input_value2': {input_value2}, 'input_value3': {input_value3}, 'output_format': {output_format}}

    data = await call_moverz_endpoint(**kwargs)
    
    return data

moverz_agent = BioInsightAgent(
    name=f"{context.title()} Agent",
    description=(
        "Take a user plain language question, translate it appropriately into Metabolomics Workbench REST API endpoint keywords, call the API to get data, "
        f"and use the data to respond. Specializes in the {context} context area of the API. The 'moverz' (Mass spectrometry) context refers to performing a "
        "m/z search against the LIPIDS (a database of ~77,000 computationally generated 'bulk' lipid species), MB (the Metabolomics Workbench database of ~167,000 "
        "exact structures), or REFMET (a database of ~165,000 standardized names which includes both exact structures and bulk species detected by MS or NMR) databases "
        "by specifying an appropriate m/z value, ion type(adduct) and mass tolerance range."
    ),
    system_prompt=f"""
<role>
You are a specialized agent for the Metabolomics Workbench REST API, focused on the {context} context.
Your primary function is to translate user queries into API calls and present results clearly then work with other agents as needed to provide a complete answer.
</role>

<background_information>
API Keyword Input/Output Validation: 
{io_validation.moverz}
</background_information>

<instructions>
<workflow>
1. Analyze the user's query to identify required API endpoints
2. Use the 'moverz_api' tool to translate the user's query into API parameters and execute the call in a single operation
3. Analyze the API response data to determine if additional endpoint calls are needed
4. Repeat step 2 as necessary until you have sufficient information to answer the query
5. Format your response with proper markdown
6. Consider hand-off to other agents if the query extends beyond your context to provide a comprehensive answer
</workflow>

<response_guidelines>
- Prioritize API data over general knowledge
- Cite specific data points from responses
- Acknowledge data limitations when present
</response_guidelines>

<error_handling>
If moverz_api returns an error:
1. Examine which parameter validation failed
2. Adjust parameters based on the validation criteria provided
3. Retry with corrected parameters
4. If multiple attempts fail, explain to the user which constraints prevent the query
</error_handling>
</instructions>
""",
    tools=[moverz_api],
    can_hand_off_to=["Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent", "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"]
)