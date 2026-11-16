"""
Knowledge Base retrieval components for AWS Bedrock.

This package provides:
- kb_retrieval_engine: Query engine configuration with HYBRID search and reranking
- retrieval_filters: Source-specific metadata filters
- knowledge_base_tool: Main query function for agent use
"""

from .kb_retrieval_engine import (
    build_retrieval_config,
    get_query_engine,
    get_pdc_engine,
    get_gdc_engine,
    get_idc_engine,
    get_publications_engine,
    pdc_engine,
    gdc_engine,
    idc_engine,
    publications_engine
)

from .retrieval_filters import (
    get_pdc_filter,
    get_gdc_filter,
    get_idc_filter,
    get_publications_filter,
    get_all_sources_filter,
    get_filter_for_source
)

from .knowledge_base_tool import query_knowledge_base

__all__ = [
    # Query engines
    'build_retrieval_config',
    'get_query_engine',
    'get_pdc_engine',
    'get_gdc_engine',
    'get_idc_engine',
    'get_publications_engine',
    'pdc_engine',
    'gdc_engine',
    'idc_engine',
    'publications_engine',
    # Filters
    'get_pdc_filter',
    'get_gdc_filter',
    'get_idc_filter',
    'get_publications_filter',
    'get_all_sources_filter',
    'get_filter_for_source',
    # Main tool function
    'query_knowledge_base'
]
