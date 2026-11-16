from data_sources.metabolomics_workbench.mwb_agent_workflow import MWBAgentWorkflow
from data_sources.metabolomics_workbench.mwb.router_agent import router_agent
from data_sources.metabolomics_workbench.mwb.api_agent_compound_context import compound_agent
from data_sources.metabolomics_workbench.mwb.api_agent_gene_context import gene_agent
from data_sources.metabolomics_workbench.mwb.api_agent_metstat_context import metstat_agent
from data_sources.metabolomics_workbench.mwb.api_agent_moverz_context import moverz_agent
from data_sources.metabolomics_workbench.mwb.api_agent_protein_context import protein_agent
from data_sources.metabolomics_workbench.mwb.api_agent_refmet_context import refmet_agent
from data_sources.metabolomics_workbench.mwb.api_agent_study_context import study_agent
from data_sources.metabolomics_workbench.mwb.rag_agent import rag_agent
from data_sources.metabolomics_workbench.prompts import DEFAULT_HANDOFF_OUTPUT_PROMPT

# Create an instance of MWBAgentWorkflow
agent = MWBAgentWorkflow(
    agents=[
        router_agent,
        compound_agent,
        gene_agent,
        metstat_agent,
        moverz_agent,
        protein_agent,
        refmet_agent,
        study_agent,
        rag_agent,
    ],
    root_agent=router_agent.name,
    timeout=None,
    verbose=False,
    handoff_output_prompt=DEFAULT_HANDOFF_OUTPUT_PROMPT,
    name="MetabolomicsWorkbenchAgent",
    description="""
    Study Context
    Serves as the primary access point for metabolomics studies and their associated data. Offers access to complete study metadata, experimental data, study design details, analysis results, and sample source information. Handles MS and NMR spectrometry data, experimental factors, results data, species information, and disease associations.

    Compound Context
    Access to a comprehensive metabolite structure database, including detailed compound information, structure visualization, chemical classifications, and cross-reference lookups. Supports molecular structures (molfiles), SMILES notation, InChIKeys, systematic names, and external database references.

    RefMet Context
    Manages standardized metabolite nomenclature with naming conventions, chemical classification systems, database cross-references, and name standardization services. Works with standardized metabolite names, chemical formulas, exact masses, classification hierarchies, and database links.

    Gene Context
    Access to gene information related to the metabolome, including gene identification, metabolic pathway associations, and gene-metabolite relationships. Handles gene symbols, Entrez gene IDs, gene names and synonyms, and gene-related metadata.

    Protein Context
    Manages protein-related metabolomics data, supporting protein identification, protein-metabolite associations, and mRNA relationships. Works with UniProt IDs, RefSeq IDs, protein sequences, and protein-related metadata.

    Moverz Context
    Facilitates mass spectrometry-based searches with precursor ion searching, mass tolerance specifications, and multi-database support. Handles m/z values, ion types, mass tolerances, and search results in various formats.

    Metstat Context
    Provides statistical analysis and metadata summaries across metabolomics studies. Enables cross-study analysis, parameter-based searching, and comparisons of experimental conditions. Works with analysis types, polarity information, chromatography data, species data, disease associations, and metabolite identifiers.
    """,
)