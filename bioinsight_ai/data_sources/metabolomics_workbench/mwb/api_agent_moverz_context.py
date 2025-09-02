import aiohttp
import data_sources.metabolomics_workbench.mwb.api_validation_input_output as io_validation
from llama_index.core.agent.workflow import FunctionAgent
from typing import Literal, Annotated
from workflow_config.default_settings import Settings

#
# MWB sub-agent specializing in one of seven context areas of the MWB REST API
#

context = "moverz"

# Annotated tool specifically for formulating a moverz endpoint
def endpoint_kwargs(
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
    f"""Function to validate keywords needed to construct a valid REST API URL path to retrieve {context} context data from the Metabolomics Workbench website."""
    return f"{{'input_item': {input_item} 'input_value1': {input_value1}, 'input_value': {input_value2}, 'input_value2': {input_value3}, 'input_value3': {output_format}}}"


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
                print(f"Error: {response.status}")
                return None


moverz_agent = FunctionAgent(
    name=f"{context.title()} Agent",
    description=(
        "Take a user plain language question, translate it appropriately into Metabolomics Workbench REST API endpoint keywords, call the API to get data, "
        f"and use the data to respond. Specializes in the {context} context area of the API. The 'moverz' (Mass spectrometry) context refers to performing a "
        "m/z search against the LIPIDS (a database of ~77,000 computationally generated 'bulk' lipid species), MB (the Metabolomics Workbench database of ~167,000 "
        "exact structures), or REFMET (a database of ~165,000 standardized names which includes both exact structures and bulk species detected by MS or NMR) databases "
        "by specifying an appropriate m/z value, ion type(adduct) and mass tolerance range."
    ),
    system_prompt=(
        f"You are an expert on the Metabolomics Workbench data source, specifically the {context} context of the REST API. Do not use outside knowledge.\n"
        ""
        "Step 1: Determine if the user is asking a follow up question about about data you've already retrieved. "
        "If your memory provides enough detail then stop immediately and respond directly to the user. Do NOT proceed to the remaining steps.\n"
        "Step 2: If you cannot answer the question using memory then use the following context: \n"
        f"{io_validation.moverz}"
        "and the 'endpoint_kwargs' tool to translate the plain language user query into appropriate endpoint keywords.\n"
        ""
        "Step 3: Use the tool 'call_moverz_endpoint' to fetch data and answer the query. If clarification is needed from the user be then ask for "
        "clarification. If you have made ANY corrections to the user's query mention that in your response.\n"
    ),
    tools=[endpoint_kwargs, call_moverz_endpoint],
    can_hand_off_to=["Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent", "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"]
)