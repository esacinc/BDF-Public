from llama_index.core.agent import FunctionCallingAgent
from .proteomic_data_commons.tools import tools as pdc_tools
from .imaging_data_commons.tools import tools as idc_tools
from .genomic_data_commons.GDC_tools import gdc_tools
from workflow_config.default_settings import Settings

agent = FunctionCallingAgent.from_tools(
        tools=pdc_tools + idc_tools + gdc_tools,
        verbose=True
    )