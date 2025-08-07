import data_sources.cancer_research_data_commons.proteomic_data_commons.pdc_api as pdc_api
from ..ensembl_api import gene_name_to_ensembl_mapping
from .rag_retriever import website_journal_engine
from llama_index.core.tools import FunctionTool
from llama_index.core.tools import QueryEngineTool

disease_tools = FunctionTool.from_defaults(
    name=f"list_all_diseases",
    fn=pdc_api.list_all_diseases,
        
    description=(
        f"Useful for finding all the matching diseases in the question"
    ),
)
sites_or_organ_tools = FunctionTool.from_defaults(
     name=f"list_all_primary_sites",
    fn=pdc_api.list_all_primary_sites,
    description=(
        f"Useful for finding all the disease sites or organs studied in PDC"
    ),
)
list_study_tools = FunctionTool.from_defaults(
     name=f"list_studies",
    fn=pdc_api.list_studies,
    description=(f"""Useful for finding a study matching a disease and/or site. The disease names 
        and primary sites must be mapped to PDC terms using the list all disease tools and sites_or_organ tools first
        respectively before calling this function. 
        Use the values returned by these tools as the input to the list studies tool
        for the disease_type and primary site parameters.
        It expects an input object with two attribute lists: disease_type and primary_site"""
    ),
)

study_detail_tools = FunctionTool.from_defaults(
    name="get_study_details",
    fn = pdc_api.get_study_details,
    description = (f"""Useful for getting details of a given study including all demographic data 
                   age, gender, disease type, and other demographics for a given study ID 
                   or study name"""),
)

study_name_tool = FunctionTool.from_defaults(
    name="get_study_name",
    fn = pdc_api.get_study_name,

    description = (f"Useful for getting the name of the study based on the study ID")
)

gene_detail_tools = FunctionTool.from_defaults(
    name="get_gene_details",
    fn = pdc_api.get_gene_details,
  
    description = (f"Useful for finding all the data about genes and chromosomes given study ID or study name"),
)    
gene_expression_tools = FunctionTool.from_defaults(
    name = "get_gene_expression_data", 
    fn = pdc_api.get_gene_expression_data,
    description = (f"""Useful for getting individual gene level expression for a given study and a list of gene names from PDC. 
                    Use this function only for getting gene expression values from PDC. 
                   Gene names can be arbitrarily long list of gene names separated by commas or spaces.
                   Gene names should be converted to upper case before calling this tool and passed in as a list object.
                   If no genes are specified then just let the user know that you can only work with up to 20 genes at
                   a time due to memory restrictions and that you will do a search in the publications database for the answer.""")
)
external_genomic_data_tools = FunctionTool.from_defaults(
    name = "has_external_genomic_data", 
    fn = pdc_api.has_external_genomic_data,
  
    description = (f"""Useful for checking if a given study has external genomic data in GDC. Do not call this
                   tool if user only wants study details.
                   Return false if a valid ID is not provided""")
)

external_data_tool = FunctionTool.from_defaults(
    name = "get_extenal_genomic_data", 
    fn = pdc_api.get_external_genomic_data,
    description = (f"""
        Useful for getting gene expression data from GDC
        Parameters:
            gene_name (list): A list of gene names to convert. This must be an array of strings.
            PDC_study_ID: A valid PDC study ID that has corrosponding patients in GDC.
            Maximum number of genes is five.
            DO NOT USE THIS UNLESS THE USER EXPLICITLY ASKS FOR EXTERNAL or data from GDC
        Returns: Gene expression data directly from GDC.
    """)
)
biospecimen_data_tools = FunctionTool.from_defaults(
    name = "get_biospecimen_data", 
    fn = pdc_api.get_biospecimen_data,
  
    description = (f"""Useful for getting sample or biospecimen or aliquot information for a given study. Study IDs are
                   specified by PDC000XXX where XXX is are numbers only. Use this function if the user
                   wants to know about samples, specimen IDs, cases, sample types. """)
)

get_ensembl_ids = FunctionTool.from_defaults(
    name = "get_ensembl_ids", 
    fn = gene_name_to_ensembl_mapping,
    description = (f"""
        Useful for converting a list of gene names to Ensembl ID using the Ensembl REST API.
        Parameters:
            gene_name (list): A list of gene names to convert. This must be an array of strings.
        Returns:
            list: A list of matching gene_name ensemble_id pairs as a list.
    """)
)

website_and_journal_info_tool = QueryEngineTool.from_defaults(
    name="PDCRAGTool",
    description=
        """This tool can be used to get two types of PDC information: 
        1) General information about PDC from the website, such as PDC FAQs, harmonization information, data submission details, download data details, and analyze PDC data in the cloud
        2) PDC published journal articles""",
    query_engine=website_journal_engine
)

tools = [disease_tools, 
         sites_or_organ_tools,
         list_study_tools, 
         study_detail_tools, 
         gene_expression_tools,
         biospecimen_data_tools,
         get_ensembl_ids,
         external_data_tool,
         website_and_journal_info_tool
        ]