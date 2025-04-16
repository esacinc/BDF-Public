from typing import List
import requests
from pydantic.fields import Field
from pydantic import BaseModel
from llama_index.core.tools import FunctionTool
import PDC_tools

# This a set of helper functions that process and retrive data from various data sources such as PDC and GDC

def gene_name_to_ensembl_mapping(gene_name: List):
    """
    Convert a list of gene names to Ensembl ID using the Ensembl REST API.
    Parameters:
        gene_name (str): The gene name to convert.
        species (str): The species (default: "human").
        
    Returns:
        list: A list of matching gene_name ensemble_id pairs as a list or an empty list if none are found.
    """
    ret_val = []
    
    for g in gene_name:
        url = f"https://rest.ensembl.org/xrefs/symbol/human/{g}?"
        headers = {"Content-Type": "application/json"}

        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()            
            ensembl_ids = [entry["id"] for entry in data if entry["type"] == "gene"]
            for e in ensembl_ids:
                if "ENS" in e:
                    ret_val.append({'gene_name':g, 'ensembl_id':e})
                    break
    return ret_val


disease_tools = FunctionTool.from_defaults(
    name=f"list_all_diseases",
    fn=PDC_tools.list_all_diseases,
        
    description=(
        f"Useful for finding all the matching diseases in the question"
    ),
)
sites_or_organ_tools = FunctionTool.from_defaults(
     name=f"list_all_primary_sites",
    fn=PDC_tools.list_all_primary_sites,
    description=(
        f"Useful for finding all the disease sites or organs studied in PDC"
    ),
)
list_study_tools = FunctionTool.from_defaults(
     name=f"list_studies",
    fn=PDC_tools.list_studies,
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
    fn = PDC_tools.get_study_details,
    description = (f"""Useful for getting details of a given study including all demographic data 
                   age, gender, disease type, and other demographics for a given study ID 
                   or study name"""),
)

study_name_tool = FunctionTool.from_defaults(
    name="get_study_name",
    fn = PDC_tools.get_study_name,

    description = (f"Useful for getting the name of the study based on the study ID")
)

gene_detail_tools = FunctionTool.from_defaults(
    name="get_gene_details",
    fn = PDC_tools.get_gene_details,
  
    description = (f"Useful for finding all the data about genes and chromosomes given study ID or study name"),
)    
gene_expression_tools = FunctionTool.from_defaults(
    name = "get_gene_expression_data", 
    fn = PDC_tools.get_gene_expression_data,
    description = (f"""Useful for getting individual gene level expression for a given study and a list of gene names from PDC. 
                    Use this function only for getting gene expression values from PDC. 
                   Gene names can be arbitrarily long list of gene names separated by commas or spaces.
                   Gene names should be converted to upper case before calling this tool and passed in as a list object.
                   If no genes are specified then just let the user know that you can only work with up to 20 genes at
                   a time due to memory restrictions and that you will do a search in the publications database for the answer.""")
)
external_genomic_data_tools = FunctionTool.from_defaults(
    name = "has_external_genomic_data", 
    fn = PDC_tools.has_external_genomic_data,
  
    description = (f"""Useful for checking if a given study has external genomic data in GDC. Do not call this
                   tool if user only wants study details.
                   Return false if a valid ID is not provided""")
)

external_data_tool = FunctionTool.from_defaults(
    name = "get_extenal_genomic_data", 
    fn = PDC_tools.get_external_genomic_data,
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
    fn = PDC_tools.get_biospecimen_data,
  
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

tools = [disease_tools, sites_or_organ_tools,
         list_study_tools, 
         study_detail_tools, 
         gene_expression_tools,
         biospecimen_data_tools,
         get_ensembl_ids,
         external_data_tool
        ]

class Metadata(BaseModel):
    """Metadata like disease names and organ sites detected from a question"""
    disease_type: str = Field(default=None, description="All the disease types mentioned in the message as a comma separated list. Here are some possible disease types : 'breast cancer', 'colon cancer', 'melanoma', 'GBM', 'sarcoma' or 'glioblastoma'")
    primary_site: str = Field(default=None, description="All the primary site or organ mentioned in the message as a comma separated list. Here are some possible organs: 'kidney', 'colon', 'breast', 'lung'")

class PDCMetadata(BaseModel):
    """Metadata like disease names and organ sites detected from a question"""
    disease_type: List[str] = Field(default=None, description="All the disease types matched as a list. ")
    primary_site: List[str] = Field(default=None, description="All the primary site or organ matched as a list.")
