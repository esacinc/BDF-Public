"""
AWS Bedrock Knowledge Base Retrieval Engine with source-specific filtering and reranking.

This module provides enhanced retrieval capabilities with:
1. HYBRID search (vector + keyword) for better technical term matching
2. Source-specific metadata filtering (PDC, GDC, IDC, Publications)
3. Native Cohere Rerank 3.5 for improved relevance
4. Configurable result counts

Improvements over previous versions:
- Targeted search space with metadata filters
- Advanced reranking (state-of-the-art Cohere model)
- Configurable candidate:result ratios
- Better citation and source attribution
"""

from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, PUBLICATIONS_KB_ID
from workflow_config.default_settings import Settings
from llama_index.retrievers.bedrock import AmazonKnowledgeBasesRetriever
from llama_index.core import get_response_synthesizer
from llama_index.core.query_engine import RetrieverQueryEngine
from .retrieval_filters import get_filter_for_source
from typing import Literal, Optional


def build_retrieval_config(
    data_source: Literal["pdc", "gdc", "idc", "publications", "all"] = "pdc",
    num_results: int = 10,
    num_candidates: int = 30,
    enable_reranking: bool = True,
    search_type: Literal["HYBRID", "SEMANTIC"] = "HYBRID",
    pdc_study_id: Optional[str] = None
) -> dict:
    """
    Build AWS Bedrock retrieval configuration with filtering and reranking.
    
    Args:
        data_source: Which data source to search
            - "pdc": PDC documentation and FAQs
            - "gdc": GDC documentation
            - "idc": IDC documentation
            - "publications": Research publications with study metadata
            - "all": Search all sources (not recommended)
        num_results: Final number of results to return (1-100)
        num_candidates: Number of candidates to retrieve before reranking (1-100)
            Ignored if enable_reranking=False
        enable_reranking: Whether to use Cohere Rerank 3.5
        search_type: Search strategy
            - "HYBRID": Vector + keyword (recommended for scientific content)
            - "SEMANTIC": Vector embeddings only
        pdc_study_id: Optional PDC study ID (e.g., "PDC000123") to filter publications
            Only used when data_source="publications"
    
    Returns:
        dict: AWS Bedrock retrieval configuration
        
    Example:
        >>> config = build_retrieval_config(
        ...     data_source="publications",
        ...     num_results=10,
        ...     num_candidates=50,
        ...     enable_reranking=True,
        ...     search_type="HYBRID",
        ...     pdc_study_id="PDC000239"
        ... )
    """
    # Get source-specific filter
    source_filter = get_filter_for_source(data_source, pdc_study_id=pdc_study_id)
    
    # Base configuration
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults": num_candidates if enable_reranking else num_results,
            "overrideSearchType": search_type
        }
    }
    
    # Add filter if not searching all sources
    if source_filter is not None:
        config["vectorSearchConfiguration"]["filter"] = source_filter
    
    # Add native reranking if enabled
    if enable_reranking:
        config["vectorSearchConfiguration"]["rerankingConfiguration"] = {
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "numberOfRerankedResults": num_results,
                "modelConfiguration": {
                    # Cohere Rerank 3.5 (available in us-east-1)
                    "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"
                }
            }
        }
    
    return config


def get_query_engine(
    data_source: Literal["pdc", "gdc", "idc", "publications", "all"] = "pdc",
    num_results: int = 10,
    num_candidates: int = 30,
    enable_reranking: bool = True,
    search_type: Literal["HYBRID", "SEMANTIC"] = "HYBRID",
    response_mode: str = "tree_summarize",
    pdc_study_id: Optional[str] = None
) -> RetrieverQueryEngine:
    """
    Get a query engine configured for a specific data source.
    
    This is the main function to create retrieval engines. It builds a complete
    query engine with:
    - Source-specific filtering
    - HYBRID search (vector + keyword)
    - Native Cohere Rerank 3.5
    - Enhanced response synthesis
    
    Args:
        data_source: Which data source to search (pdc, gdc, idc, publications, all)
        num_results: Final number of results (1-100, default: 10)
        num_candidates: Candidates before reranking (default: 30)
        enable_reranking: Use Cohere Rerank 3.5 (default: True, recommended)
        search_type: HYBRID or SEMANTIC (default: HYBRID, recommended)
        response_mode: LlamaIndex response synthesis mode
            - "tree_summarize": Best for multiple sources (default)
            - "compact": Faster, simpler
            - "refine": Iterative refinement
        pdc_study_id: Optional PDC study ID to filter publications (e.g., "PDC000123")
            Only used when data_source="publications"
    
    Returns:
        RetrieverQueryEngine: Configured query engine ready to use
        
    Example:
        >>> # PDC documentation search
        >>> pdc_engine = get_query_engine("pdc", num_results=10)
        >>> response = pdc_engine.query("How do I submit data to PDC?")
        
        >>> # Research publications with study ID filter
        >>> pub_engine = get_query_engine(
        ...     "publications",
        ...     num_results=15,
        ...     num_candidates=50,
        ...     pdc_study_id="PDC000239"
        ... )
        >>> response = pub_engine.query("CPTAC breast cancer proteomics")
    """
    # Build retrieval configuration
    retrieval_config = build_retrieval_config(
        data_source=data_source,
        num_results=num_results,
        num_candidates=num_candidates,
        enable_reranking=enable_reranking,
        search_type=search_type,
        pdc_study_id=pdc_study_id
    )
    
    # Create retriever
    retriever = AmazonKnowledgeBasesRetriever(
        knowledge_base_id=PUBLICATIONS_KB_ID,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        retrieval_config=retrieval_config
    )
    
    # Create response synthesizer
    response_synthesizer = get_response_synthesizer(
        response_mode=response_mode,
        use_async=True
    )
    
    # Build and return query engine
    return RetrieverQueryEngine(
        retriever=retriever,
        response_synthesizer=response_synthesizer
    )


# Pre-configured engines for common use cases
def get_pdc_engine(num_results: int = 10, num_candidates: int = 30) -> RetrieverQueryEngine:
    """Get query engine for PDC documentation and FAQs."""
    return get_query_engine(
        data_source="pdc",
        num_results=num_results,
        num_candidates=num_candidates,
        enable_reranking=True,
        search_type="HYBRID"
    )


def get_gdc_engine(num_results: int = 10, num_candidates: int = 30) -> RetrieverQueryEngine:
    """Get query engine for GDC documentation."""
    return get_query_engine(
        data_source="gdc",
        num_results=num_results,
        num_candidates=num_candidates,
        enable_reranking=True,
        search_type="HYBRID"
    )


def get_idc_engine(num_results: int = 10, num_candidates: int = 30) -> RetrieverQueryEngine:
    """Get query engine for IDC documentation."""
    return get_query_engine(
        data_source="idc",
        num_results=num_results,
        num_candidates=num_candidates,
        enable_reranking=True,
        search_type="HYBRID"
    )


def get_publications_engine(num_results: int = 15, num_candidates: int = 50) -> RetrieverQueryEngine:
    """
    Get query engine for research publications.
    
    Uses higher candidate count (50) for better coverage of research papers.
    """
    return get_query_engine(
        data_source="publications",
        num_results=num_results,
        num_candidates=num_candidates,
        enable_reranking=True,
        search_type="HYBRID"
    )


# Default engines (lazy initialization for backward compatibility)
_pdc_engine = None
_gdc_engine = None
_idc_engine = None
_publications_engine = None


def pdc_engine() -> RetrieverQueryEngine:
    """Get default PDC query engine (lazy initialization)."""
    global _pdc_engine
    if _pdc_engine is None:
        _pdc_engine = get_pdc_engine()
    return _pdc_engine


def gdc_engine() -> RetrieverQueryEngine:
    """Get default GDC query engine (lazy initialization)."""
    global _gdc_engine
    if _gdc_engine is None:
        _gdc_engine = get_gdc_engine()
    return _gdc_engine


def idc_engine() -> RetrieverQueryEngine:
    """Get default IDC query engine (lazy initialization)."""
    global _idc_engine
    if _idc_engine is None:
        _idc_engine = get_idc_engine()
    return _idc_engine


def publications_engine() -> RetrieverQueryEngine:
    """Get default publications query engine (lazy initialization)."""
    global _publications_engine
    if _publications_engine is None:
        _publications_engine = get_publications_engine()
    return _publications_engine
