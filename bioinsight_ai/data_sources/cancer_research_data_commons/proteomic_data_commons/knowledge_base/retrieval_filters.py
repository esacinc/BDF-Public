"""
Metadata filter configurations for AWS Bedrock Knowledge Base retrieval.

This module provides pre-configured filters to target specific data sources
within the Publications Knowledge Base (PUBLICATIONS_KB_ID).

Data Source Mapping (IDs are read from environment variables via config):
- PUBLICATIONS_DOCS_SOURCE_ID: Data-Commons-Website-Docs (multi-site web crawler)
  - PDC: https://pdc.cancer.gov/pdc-docs/
  - GDC: https://docs.gdc.cancer.gov/
  - IDC: https://learn.canceridc.dev/
- PUBLICATIONS_FAQ_S3_SOURCE_ID: S3 FAQ documents
- PUBLICATIONS_PAPERS_SOURCE_ID: S3 research publications
- PUBLICATIONS_FAQ_WEB_SOURCE_ID: web PDC FAQ
"""

from config import (
    PUBLICATIONS_DOCS_SOURCE_ID,
    PUBLICATIONS_FAQ_S3_SOURCE_ID,
    PUBLICATIONS_FAQ_WEB_SOURCE_ID,
    PUBLICATIONS_PAPERS_SOURCE_ID,
)


def get_pdc_filter() -> dict:
    """
    Filter for PDC (Proteomic Data Commons) documentation and FAQs.
    
    Includes:
    - PDC website documentation (https://pdc.cancer.gov/pdc-docs/)
    - PDC FAQ pages (web + S3)
    
    Returns:
        dict: AWS Bedrock retrieval filter configuration
    """
    return {
        "orAll": [
            # FAQ S3 bucket
            {
                "equals": {
                    "key": "x-amz-bedrock-kb-data-source-id",
                    "value": PUBLICATIONS_FAQ_S3_SOURCE_ID
                }
            },
            # FAQ web crawler
            {
                "equals": {
                    "key": "x-amz-bedrock-kb-data-source-id",
                    "value": PUBLICATIONS_FAQ_WEB_SOURCE_ID
                }
            },
            # PDC documentation from multi-site crawler
            {
                "andAll": [
                    {
                        "equals": {
                            "key": "x-amz-bedrock-kb-data-source-id",
                            "value": PUBLICATIONS_DOCS_SOURCE_ID
                        }
                    },
                    {
                        "startsWith": {
                            "key": "x-amz-bedrock-kb-source-uri",
                            "value": "https://pdc.cancer.gov/"
                        }
                    }
                ]
            }
        ]
    }


def get_gdc_filter() -> dict:
    """
    Filter for GDC (Genomic Data Commons) documentation only.
    
    Includes:
    - GDC website documentation (https://docs.gdc.cancer.gov/)
    
    Returns:
        dict: AWS Bedrock retrieval filter configuration
    """
    return {
        "andAll": [
            {
                "equals": {
                    "key": "x-amz-bedrock-kb-data-source-id",
                    "value": PUBLICATIONS_DOCS_SOURCE_ID
                }
            },
            {
                "startsWith": {
                    "key": "x-amz-bedrock-kb-source-uri",
                    "value": "https://docs.gdc.cancer.gov/"
                }
            }
        ]
    }


def get_idc_filter() -> dict:
    """
    Filter for IDC (Imaging Data Commons) documentation only.
    
    Includes:
    - IDC website documentation (https://learn.canceridc.dev/)
    
    Returns:
        dict: AWS Bedrock retrieval filter configuration
    """
    return {
        "andAll": [
            {
                "equals": {
                    "key": "x-amz-bedrock-kb-data-source-id",
                    "value": PUBLICATIONS_DOCS_SOURCE_ID
                }
            },
            {
                "startsWith": {
                    "key": "x-amz-bedrock-kb-source-uri",
                    "value": "https://learn.canceridc.dev/"
                }
            }
        ]
    }


def get_publications_filter(pdc_study_id: str = None) -> dict:
    """
    Filter for research publications only.
    
    Includes:
    - Research papers and publications from S3 (PDFs)
    - Contains rich metadata: studyIds, studyNames, citation, journal_url
    
    Args:
        pdc_study_id: Optional PDC study ID (e.g., "PDC000123") to filter publications
                      to only those associated with that specific study
    
    Returns:
        dict: AWS Bedrock retrieval filter configuration
    """
    base_filter = {
        "equals": {
            "key": "x-amz-bedrock-kb-data-source-id",
            "value": PUBLICATIONS_PAPERS_SOURCE_ID
        }
    }
    
    # If pdc_study_id provided, add study ID filter
    # Using listContains because studyIds is an array in the metadata
    if pdc_study_id:
        return {
            "andAll": [
                base_filter,
                {
                    "listContains": {
                        "key": "studyIds",
                        "value": pdc_study_id
                    }
                }
            ]
        }
    
    return base_filter


def get_all_sources_filter() -> dict:
    """
    No filtering - search all data sources.
    
    Use sparingly. Prefer source-specific filters for better accuracy.
    
    Returns:
        None: No filter applied
    """
    return None


# Mapping for easy lookup
FILTER_MAP = {
    "pdc": get_pdc_filter,
    "gdc": get_gdc_filter,
    "idc": get_idc_filter,
    "publications": get_publications_filter,
    "all": get_all_sources_filter
}


def get_filter_for_source(source: str, pdc_study_id: str = None) -> dict:
    """
    Get the appropriate filter for a data source.
    
    Args:
        source: One of "pdc", "gdc", "idc", "publications", "all"
        pdc_study_id: Optional PDC study ID (only used when source="publications")
    
    Returns:
        dict: AWS Bedrock retrieval filter configuration
        
    Raises:
        ValueError: If source is not recognized
    """
    if source not in FILTER_MAP:
        raise ValueError(
            f"Unknown source: {source}. "
            f"Must be one of: {', '.join(FILTER_MAP.keys())}"
        )
    
    filter_func = FILTER_MAP[source]
    
    # Pass pdc_study_id to publications filter if applicable
    if source == "publications" and pdc_study_id:
        return filter_func(pdc_study_id=pdc_study_id)
    
    return filter_func()
