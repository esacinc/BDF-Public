from .cancer_research_data_commons_agent import CancerResearchDataCommonsAgent
from .proteomic_data_commons.tools import tools as pdc_tools
from .imaging_data_commons.tools import tools as idc_tools
from .genomic_data_commons.tools import tools as gdc_tools
from workflow_config.default_settings import Settings

agent = CancerResearchDataCommonsAgent(
    name="CancerResearchDataCommonsAgent",
    description="Handles queries related to the NCI Cancer Research Data Commons (CRDC) and its data nodes: proteomics (PDC), genomics (GDC), and imaging (IDC). Each node hosts distinct datasets by data type, but some programs, such as CPTAC, contain matched multiomic data across these nodes for the same cohorts. Not all programs include cross-node data, so relationships depend on program design and data availability.",
    system_prompt="You are a helpful biomedial research assistant specializing in cancer research data commons resources, including proteomics (PDC), imaging (IDC), and genomic (GDC) data.",
    tools=pdc_tools + idc_tools + gdc_tools
    )