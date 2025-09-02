from llama_index.core.memory import Memory
from llama_index.core.workflow import Context
from log_helper.logger import get_logger
logger = get_logger()
from data_sources.metabolomics_workbench.retry_agent_workflow import RetryAgentWorkflow
from data_sources.metabolomics_workbench.prompts import DEFAULT_HANDOFF_OUTPUT_PROMPT
from data_sources.metabolomics_workbench.mwb.router_agent import router_agent
from data_sources.metabolomics_workbench.mwb.api_agent_compound_context import compound_agent
from data_sources.metabolomics_workbench.mwb.api_agent_gene_context import gene_agent
from data_sources.metabolomics_workbench.mwb.api_agent_metstat_context import metstat_agent
from data_sources.metabolomics_workbench.mwb.api_agent_moverz_context import moverz_agent
from data_sources.metabolomics_workbench.mwb.api_agent_study_context import study_agent
from data_sources.metabolomics_workbench.mwb.api_agent_protein_context import protein_agent
from data_sources.metabolomics_workbench.mwb.api_agent_refmet_context import refmet_agent
from data_sources.metabolomics_workbench.mwb.rag_agent import rag_agent

def create_mwb_workflow(session_id: str) -> dict:
    agent_workflow = RetryAgentWorkflow(
        agents=[
            router_agent,
            compound_agent,
            gene_agent,
            metstat_agent,
            moverz_agent,
            protein_agent,
            refmet_agent,
            study_agent,
            rag_agent
        ],
        root_agent=router_agent.name,
        timeout=None,
        verbose=False,
        handoff_output_prompt=DEFAULT_HANDOFF_OUTPUT_PROMPT
    )

    memory = Memory.from_defaults(session_id=session_id,
                                  token_limit=100000)
    context = Context(agent_workflow)
    
    logger.info(f"[MWB workflow]: Created memory for session:{session_id}")

    return {
        "agent_workflow": agent_workflow,
        "context": context,
        "memory": memory
    }
