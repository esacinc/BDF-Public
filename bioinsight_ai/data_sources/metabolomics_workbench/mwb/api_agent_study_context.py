import data_sources.metabolomics_workbench.mwb.api_validation_input_output as io_validation
import data_sources.metabolomics_workbench.mwb.api_validation_permutation as validation
from llama_index.core.agent.workflow import FunctionAgent
from typing import Literal, Annotated
from workflow_config.default_settings import Settings
from .tools import call_rest_endpoint

#
# MWB sub-agent specializing in one of seven context areas of the MWB REST API
#

context = "study"

# Annotated tool specifically for formulating a study endpoint
def endpoint_kwargs(
    input_item: Annotated[Literal["study_id", "study_title", "institute", "last_name", "analysis_id", "metabolite_id", "kegg_id", "refmet_name"],
                          """One of study_id | study_title | institute | last_name | analysis_id | metabolite_id | kegg_id | refmet_name. 
                          study_id: A study ID in one of the following formats. 
                          1) ST<6 digit integer> is a single study ID. This will return information about a single study.
                          2) ST<1-5 digit integer> is a substring representing a range of study IDs. For example, ST0004 (ST<4 digit integer)
                          will retrieve study information for studies ST000400 to ST000499. ST00004 (ST<5 digit integer>) will retrieve study information 
                          for studies ST000040 to ST000049 and so forth.
                          3) ST' will retrieve the summary information for all studies."""
    ],
    input_value: Annotated[str, """An appropriate input value for given the input_item. Examples of an input specification are {"input_item":"study_id", "input_value":"ST000001"} 
                           or {"input_item":"study_title", "input_value":"diabetes"}"""
    ],
    output_item: Annotated[
    Literal[
        "summary", 
        "factors", 
        "analysis", 
        "metabolites", 
        "mwtab", 
        "source", 
        "species", 
        "disease", 
        "number_of_metabolites", 
        "data", 
        "datatable", 
        "untarg_studies", 
        "untarg_factors", 
        "untarg_data", 
        "available"
    ], 
    """One of  
    summary: The 'summary' output item retrieves the following information for a specified input name and value: study_id, study_title, study_type, institute, department, last_name, first_name, email, phone, submit_date, study_summary, subject_species.  
    factors: The 'factors' output item refers to the experimental conditions for each sample in the study and retrieves the following information for a specified input name and value: study_id, local_sample_id, subject_type, factors.
    analysis: The 'analysis' output item accesses a number of key instrumentation parameters and retrieves the following information for a specified input name and value: study_id, analysis_id, analysis_summary, analysis_type, MS instrument_name, MS instrument_type, MS type, MS ion_mode, NMR instrument_type, NMR experiment_type, NMR spectrometer_frequency, NMR solvent.
    metabolites: The 'metabolites' output item exposes details for each named metabolite in a particular study or analysis. The input item must be either a study_id or analysis_id. The REST request retrieves the following information for the specified study/analysis ID: study_id, analysis_id, analysis summary, metabolite_name, refmet_name, pubchem_id, other_id, other_id_type.
    mwtab: The 'study_id' or 'analysis_id' input item is required for the 'mwtab' output item. The mwTab file may be downloaded in JSON or txt format.
    source: The 'source' output item retrieves the following information for the specified study: Study ID, Sample source (e.g. blood, urine, liver, etc.). For example: https://www.metabolomicsworkbench.org/rest/study/study_id/ST000001/source retrieves the sample source information for all study ST000001. https://www.metabolomicsworkbench.org/rest/study/study_id/ST/source retrieves the sample source information for all studies using 'ST' as a wildcard.
    species: The 'species' output item retrieves the following information for the specified study: Study ID, Latin name, Common name. 
    disease: The 'disease' output item retrieves the following information for the specified study: Study ID, Disease.
    number_of_metabolites: The 'number_of_metabolites' output item retrieves the following information for a specified study, study title, last name or institute: study_id, analysis_id, study title, number of metabolites, analysis summary.
    data: The 'study_id' or 'analysis_id' input item is required for the 'data' output item. The REST request retrieves the following information for the specified study ID : study_id, analysis_id, analysis_summary, metabolite_name, metabolite_id, refmet_name, units. In addition, the following results information is retrieved for each metabolite: local sample_ID and measured values.
    datatable: The 'analysis_id' input item is required for the 'datatable' output item. The value of the output format is ignored. A tab delimited data table is generated containing available results for the metabolites. The header line includes sample IDs, class, and metabolite names. For example: https://www.metabolomicsworkbench.org/rest/study/analysis_id/AN000001/datatable
    untarg_studies: The 'untarg_studies' output item retrieves the following information for all untargeted MS studies in the data repository: study_id, analysis_id, analysis_summary, study_title, subject_species, institute. The input item and value parameter are ignored, but a study_id 'placeholder' must specified to create a valid REST request.
    untarg_factors: The 'analysis_id' input item is required for the 'untarg_factors' output item. The 'untarg_factors' output item retrieves a listing of the experimental conditions (factors) for untargeted MS studies. If more than one factor is present the factors are separated by '|' symbols. The integer at the end of each factor grouping indicates the number of sample replicates for that group. The output is displayed in JSON format.
    untarg_data: The 'analysis_id' input item is required for the 'untarg_data' output item. The 'untarg_data' output item retrieves the table of measurements for the selected analysis. The untargeted data is downloaded as a tab delimited text file.
    available: The 'metabolite_id' input item retrieves the following information for a Metabolomics Workbench metabolite ID in a study: metabolite_id, metabolite_name, refmet_name, pubchem_id, other_id, other_id_type, kegg_id, ri, ri_type, moverz_quant. The output item is ignored, but an output item 'placeholder' must be specified to create a valid REST request."""
    ],
    output_format: Annotated[Literal["txt", "file", "json"],
        "Return format of data. Can be one of the following: txt | file | json. If unsure use json."
    ] = "json"
) -> str: 
    f"""Function to validate keywords needed to construct a valid REST API URL path to retrieve {context} context data from the Metabolomics Workbench website. 
    Avoid running with input_value='ST' since this will return too much data."""
    
    if input_value == 'ST':
            raise ValueError("Using 'ST' as input_value will return too much data. Please specify a more precise study ID or range.")

    return f"{{'context': {context}, 'input_item': {input_item}, 'input_value': {input_value}, 'output_item': {output_item}, 'output_format': {output_format}}}"


study_agent = FunctionAgent(
    name=f"{context.title()} Agent",
    description=(
        "Take a user plain language question, translate it appropriately into Metabolomics Workbench REST API endpoint keywords, call the API to get data, "
        f"and use the data to respond. Specializes in the {context} context area of the API. The 'study' context refers to the studies available in the Metabolomics "
        "Workbench (www.metabolomicsworkbench.org), a public repository for metabolomics metadata and experimental data spanning various species and experimental "
        "platforms, metabolite standards, metabolite structures, protocols, tutorials and training material, and other educational resources. It provides a "
        "computational platform to integrate, analyze, track, deposit, and disseminate large volumes of heterogeneous data from a wide variety of metabolomics "
        "studies including Mass Spectrometry (MS) and Nuclear Magnetic Resonance (NMR) spectrometry data spanning a variety of species covering all the major "
        "taxonomic categories including humans and other mammals, plants, insects, invertebrates, and microorganisms. This context provides access to a variety of "
        "data associated with studies such as study summary, experimental factors for study design, analysis information, metabolites and results data, sample "
        "source and species etc."
    ),
    system_prompt=(
        f"You are an expert on the Metabolomics Workbench data source, specifically the {context} context of the REST API. Do not use outside knowledge.\n"
        ""
       "Step 1: Determine if the user is asking a follow up question about about data you've already retrieved. "
        "If your memory provides enough detail then stop immediately and respond directly to the user. Do NOT proceed to the remaining steps.\n"
        "Step 2: If you cannot answer the question using memory then use the following context: \n"
        f"{io_validation.study}"
        "and the 'endpoint_kwargs' tool to translate the plain language user query into appropriate endpoint keywords.\n"
        ""
        "Step 3: You must verify the output of 'endpoint_kwargs' against the following criteria and confirm for correctness:\n"
        f"{validation.study}"
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