"""
Unified RAG query function with source selection and configurable retrieval.

This module provides the core query_knowledge_base() function that allows:
1. Specifying which data source to search (PDC, GDC, IDC, Publications, or All)
2. Controlling the number of results
3. Benefiting from HYBRID search, filtering, and reranking automatically

The FunctionTool definition is in the parent tools.py for proper code organization.
"""

from .kb_retrieval_engine import get_query_engine
from typing import Literal


def query_knowledge_base(
    question: str,
    data_source: Literal["pdc", "gdc", "idc", "publications", "all"] = "pdc",
    num_results: int = 10,
    pdc_study_id: str = None
) -> str:
    """
    Query the knowledge base with source-specific filtering and reranking.
    
    This function provides access to documentation and publications across multiple
    cancer data commons with advanced retrieval features:
    - HYBRID search (vector + keyword matching)
    - Source-specific metadata filtering
    - Native Cohere Rerank 3.5 for improved relevance
    
    Args:
        question: The user's question
        data_source: Which data source to search
            - "pdc": PDC documentation and FAQs (default)
            - "gdc": GDC documentation
            - "idc": IDC documentation  
            - "publications": Research papers with study IDs and citations
            - "all": Search all sources (not recommended)
        num_results: Number of final results to return (1-20, default: 10)
        pdc_study_id: Optional PDC study ID (e.g., "PDC000123") to filter publications
            Only used when data_source="publications"
            Filters publications to only those associated with the specified study
    
    Returns:
        str: Answer with source citations
        
    Example:
        >>> # General publication search
        >>> answer = query_knowledge_base(
        ...     question="CPTAC breast cancer findings",
        ...     data_source="publications",
        ...     num_results=10
        ... )
        
        >>> # Publications for specific study
        >>> answer = query_knowledge_base(
        ...     question="What proteomics methods were used?",
        ...     data_source="publications",
        ...     num_results=10,
        ...     pdc_study_id="PDC000239"
        ... )
    
    Raises:
        ValueError: If pdc_study_id is provided but data_source is not "publications"
    """
    # Validate pdc_study_id only used with publications
    if pdc_study_id and data_source != "publications":
        raise ValueError(
            f"pdc_study_id can only be used when data_source='publications', "
            f"but data_source='{data_source}' was provided. "
            f"To filter publications by study ID, set data_source='publications'."
        )
    
    # Calculate candidate count (3x for reranking)
    num_candidates = min(num_results * 3, 50)
    
    # Get appropriate query engine
    engine = get_query_engine(
        data_source=data_source,
        num_results=num_results,
        num_candidates=num_candidates,
        enable_reranking=True,
        search_type="HYBRID",
        pdc_study_id=pdc_study_id
    )
    
    # Execute query and return full response object (preserves metadata)
    response = engine.query(question)
    
    return response
