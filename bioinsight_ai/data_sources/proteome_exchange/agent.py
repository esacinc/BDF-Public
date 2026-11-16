from workflow_config.default_settings import Settings
from .tools import tools
from .proteome_exchange_agent import ProteomeExchangeAgent

agent = ProteomeExchangeAgent(
    name="ProteomeXchangeAgent",
    description="An agent that answers questions about ProteomeXchange, a global consortium for mass spectrometry proteomics data.",
    system_prompt="""You are an expert on ProteomeXchange (PX), a global consortium that provides 
                             standardized data submission and dissemination of mass spectrometry proteomics data across multiple 
                             partner repositories. Your job is to answer questions related to this source. Use only the information 
                             from your tools. Do not use outside knowledge. Currently, your tool set is limited, which is something 
                             you can acknowledge in your response.""",
    tools=tools
)