import data_sources.cancer_research_data_commons.proteomic_data_commons.pdc_api as pdc_api
from ..ensembl_api import gene_name_to_ensembl_mapping
from .knowledge_base import query_knowledge_base
from llama_index.core.tools import FunctionTool
from llama_index.core.tools import QueryEngineTool

disease_tools = FunctionTool.from_defaults(
    name="pdc_list_diseases",
    fn=pdc_api.pdc_list_diseases,
    description="""
    <Summary>
        Resolve disease mentions to canonical PDC disease terms. Useful for finding all matching disease names referenced
        in a user's question so downstream tools can query PDC using canonical terms.
    </Summary>

    <Input>
        query_text (string, required): The free-text disease query to resolve (e.g., 'glioblastoma multiforme').
        Returns canonical disease terms suitable for use with study listing tools.
    </Input>

    <Output>
        diseases (array of {name, pdc_term_id?}): Resolved disease names and optional PDC term ids.
    </Output>

    <Examples>
        {'query_text': 'glioblastoma multiforme'}
    </Examples>
    """
)
disease_tools.subnode = "PDC"

sites_or_organ_tools = FunctionTool.from_defaults(
    name="pdc_list_primary_sites",
    fn=pdc_api.pdc_list_primary_sites,
    description="""
    <Summary>
        Resolve organ/site mentions to PDC primary_site terms. Useful for extracting body site/organ mentions from user queries
        and mapping them to canonical PDC primary_site values before study lookup.
    </Summary>

    <Input>
        query_text (string, required): The free-text organ/site query (e.g., 'breast, ovary').
        Returns canonical primary_site terms which should be supplied to study-listing functions.
    </Input>

    <Output>
        primary_sites (array of {name}): Resolved primary site names.
    </Output>

    <Examples>
        {'query_text': 'breast, ovary'}
    </Examples>
    """,
)
sites_or_organ_tools.subnode = "PDC"

list_study_tools = FunctionTool.from_defaults(
    name="pdc_list_studies",
    fn=pdc_api.pdc_list_studies,
    description="""
    <Summary>
        Find PDC studies by disease and/or primary site. Expects canonical disease and primary_site terms returned
        from the resolver tools; use those outputs as inputs to this function.
    </Summary>

    <Input>
        disease_type (array<string>, optional): Canonical disease terms (prefer outputs from pdc_list_diseases). Example: ['Glioblastoma']
        primary_site (array<string>, optional): Canonical primary site terms (prefer outputs from pdc_list_primary_sites). Example: ['Brain']
        Note: This tool expects an object with two lists (disease_type, primary_site) or similarly-structured inputs.
    </Input>

    <Output>
        studies (array of {study_id, study_name, disease_type, primary_site}): Matching PDC studies and their metadata.
        Use the returned study_id (PDC000XXX) for study-level detail and expression queries.
    </Output>

    <Examples>
        {'disease_type': ['Glioblastoma'], 'primary_site': ['Brain']}
    </Examples>
    """,
)
list_study_tools.subnode = "PDC"

study_detail_tools = FunctionTool.from_defaults(
    name="pdc_get_study_details",
    fn = pdc_api.pdc_get_study_details,
    description = """
    <Summary>
        Return demographics, metadata, and omic data availability for a PDC study. Provides age, sex, disease_type and other study-level demographic fields and availability of genomic, imaging, metabolomic, and other omic data for a given study ID.
    </Summary>

    <Input>
        study_id (string, required): PDC study identifier (PDC000XXX) OR study_name (string). Example: 'PDC000123'
    </Input>

    <Output>
        study ({demographics, age, sex, disease_type, ...}): Study-level metadata and demographics. Useful for cohort summaries and eligibility checks.
    </Output>

    <Examples>
        {'study_id': 'PDC000123'}
    </Examples>
    """
)
study_detail_tools.subnode = "PDC"

study_name_tool = FunctionTool.from_defaults(
    name="get_study_name",
    fn = pdc_api.get_study_name,
    description = (f"Useful for getting the name of the study based on the study ID")
)
study_name_tool.subnode = "PDC"

gene_detail_tools = FunctionTool.from_defaults(
    name="get_gene_details",
    fn = pdc_api.get_gene_details,
  
    description = (f"Useful for finding all the data about genes and chromosomes given study ID or study name"),
)    
gene_detail_tools.subnode = "PDC"

gene_expression_tools = FunctionTool.from_defaults(
    name = "pdc_get_expression", 
    fn = pdc_api.pdc_get_expression,
    description = """
    <Summary>
        Retrieve gene/protein-level expression values from PDC for a study. Use for per-gene expression lookups within a study cohort.
    </Summary>

    <Input>
        study_id (string, required): PDC study identifier (PDC000XXX).
        genes (array<string>, required for gene queries; 1-20, uppercase symbols): List of uppercase gene symbols (max 20). Example: ['TP53','EGFR']
        If more than 20 genes are requested, instruct the user and suggest batching or searching publications instead.
    </Input>

    <Output>
        expression (array of {gene, sample_id, value, units?}): Expression values per sample for requested genes. Values are returned at gene/protein level as provided by PDC.
    </Output>

    <Notes>
        Constraint: Max 20 genes; gene symbols must be uppercase. If the user provides none, explain the 20-gene limit and offer alternatives.
    </Notes>

    <Examples>
        {'study_id': 'PDC000321', 'genes': ['TP53', 'EGFR', 'PTEN']}
    </Examples>
    """
)
gene_expression_tools.subnode = "PDC"

external_genomic_data_tools = FunctionTool.from_defaults(
    name = "has_external_genomic_data", 
    fn = pdc_api.has_external_genomic_data,
  
    description = (f"""Useful for checking if a given study has external genomic data in GDC. Do not call this
                   tool if user only wants study details.
                   Return false if a valid ID is not provided""")
)
external_genomic_data_tools.subnode = "PDC"

get_external_resources_data_tool = FunctionTool.from_defaults(
    name = "get_external_resources_data",
    fn = pdc_api.get_external_resources_data,
    description = """
    <Summary>
        Retrieve external resource references (e.g., GDC, IDC, TCIA) associated with a given PDC study. 
        Use this to determine whether a study has linked data in external repositories.
    </Summary>

    <Input>
        study_id (string, required): PDC study identifier (PDC000XXX).
    </Input>

    <Output>
        If external references (e.g., GDC) exist:
            Full JSON response containing:
                - biospecimen-level metadata (aliquot_id, sample_id, case_id, submitter IDs, statuses, project_name, sample_type, disease_type, primary_site, pool, taxon)
                - externalReferences (array of {
                    external_reference_id,
                    reference_resource_shortname,
                    reference_resource_name,
                    reference_entity_location
                  })
        If no external references are found:
            {"external_resources": "No external references were found"}
        If the study_id is invalid:
            "Not a valid study"
    </Output>

    <Notes>
        Constraint: Requires a valid PDC study identifier.
        The function checks for external references at the biospecimen level.
        Currently, only studies with external references (e.g., GDC) return full data.
        If no external references exist, a structured message is returned instead. 
    </Notes>

    <Examples>
        {'study_id': 'PDC000321'}
    </Examples>
    """
)
get_external_resources_data_tool.subnode = "PDC"

gdc_get_external_expression_tool = FunctionTool.from_defaults(
    name = "gdc_get_external_expression", 
    fn = pdc_api.get_external_genomic_data,
    description = """
    <Summary>
        Retrieve gene expression from GDC for PDC-matched patients when explicitly requested. Use only when the user asks for external (GDC) expression data.
    </Summary>

    <Input>
        genes (array<string>, required, 1-5, uppercase): Genes to retrieve (uppercase symbols). Max 5.
        pdc_study_id (string) OR gdc_project_id (string, e.g., 'TCGA-GBM'): Identifier linking to the cohort (use one). Provide valid IDs to map cases across resources.
    </Input>

    <Output>
        expression (array of {gene, case_id, value, units?, source: 'GDC'}): Expression values from GDC for matched cases, labeled with source 'GDC'.
        Use this only when user explicitly requests external GDC data.
    </Output>

    <Notes>
        Constraint: Use only if the user explicitly requests GDC/external data.
    </Notes>

    <Examples>
        {'genes': ['TP53', 'EGFR'], 'gdc_project_id': 'TCGA-GBM'}
    </Examples>
    """
)
gdc_get_external_expression_tool.subnode = "GDC"

biospecimen_data_tools = FunctionTool.from_defaults(
    name = "pdc_get_biospecimens", 
    fn = pdc_api.pdc_get_biospecimens,
    description = """
        <Summary>
            Return PDC biospecimen/case/aliquot details for a study including links to external resources such as GDC, TCIA, and IDC. Use this to find sample_ids, case_ids and aliquot information linked to a study or to determine cross-references and multiomic data availability at the case level.
        </Summary>

        <Input>
            study_id (string, required): PDC study identifier (PDC000XXX). Example: 'PDC000201'
        </Input>

        <Output>
            biospecimens (array of {case_id, sample_id, sample_type, aliquot_id, ...}): Biospecimen and sample metadata for the study. Use these identifiers to cross-reference files or external data.
        </Output>

        <Examples>
            {'study_id': 'PDC000201'}
        </Examples>
        """
)
biospecimen_data_tools.subnode = "PDC"

study_or_case_reference = FunctionTool.from_defaults(
    name="get_references",
    fn=pdc_api.get_references,
    description="""
    <Summary>
        Retrieve internal or external references for either a study or a case.
    </Summary>

    <Input>
        reference_type (string, required): Value is either 'internal' or 'external'.
        study_id (string, optional): PDC study ID. Can be empty if case_id has a value.
        case_id (string, optional): PDC case ID. Can be empty if study_id has a value.
    </Input>

    <Output>
        references (array of pdcEntityReference): List of PDC entity reference structures that are either internal or external references.
    </Output>
    """
)
study_or_case_reference.subnode = "PDC"

pdc_get_cases_by_study = FunctionTool.from_defaults(
    name="get_cases_by_study",
    fn=pdc_api.get_cases_by_study,
    description="""
        <Summary>
            Filter and retrieve specific case-level demographics and biospecimen details (samples, aliquots) data for any PDC study based on study_submitter_id. 
            The list can be filtered by disease_type, primary_site, sex, min_age_years, and max_age_years.
            This is the primary tool for detailed case subsetting and filtering by **age range, sex, disease, or primary site**.
        </Summary>

        <Input>
            study_submitter_id ( string, required): The study ID (e.g., "CPTAC-GBM").
            disease_type (string, optional): Filter by disease type (e.g., "Glioblastoma"). 
            primary_site (string, optional): Filter by primary site (e.g., "Brain"). 
            sex (string, optional): Filter by sex (e.g., "Male", "Female"). 
            min_age_years (integer, optional): Minimum age at diagnosis (in years). 
            max_age_years (integer, optional): Maximum age at diagnosis (in years).
        </Input>

        <Output>
            filtered_cases (array of allCases): A list of case objects that match all filters.
        </Output>

        <Examples>
            {'study_submitter_id':'CPTAC-GBM', 'sex':'Female', 'min_age_years':'50', 'max_age_years':'60'}
        </Examples>

    """   
)

pdc_get_cases_by_study.subnode = "PDC"


pdc_get_study_files_tool = FunctionTool.from_defaults(
     fn=pdc_api.pdc_get_study_files,
     name="pdc_get_study_files",
     description="""
            <Summary>
                Retrieves file metadata (ID, name, size, type) for a PDC study. Supports filtering by file type (e.g., 'PSM', 'SIT_FILE').
            </Summary>
            
            <Input>
                study_submitter_id (str, required): Study submitter id
                file_type (str, optional): File type
                offset (int, optional, default 0): For paginated data.
                limit (int, optional, default 50): Number of records per page. 
            </Input>

            <Output>
                file_data in JSON format: {"files": file_data}
            </Output>

            <Examples>
                {'study_submitter_id': 'PDC000173', 'file_type': 'PSM', 'offset':'10', 'limit': '20'}
            </Examples>
                """
)

pdc_get_study_files_tool.subnode = "PDC"

pdc_get_quantitative_data_tool = FunctionTool.from_defaults(
     fn=pdc_api.pdc_get_quantitative_data,
     name="pdc_get_quantitative_data",
     description="""
                <Summary>
                    Retrieves quantitative data matrices (gene abundance/expression) for specific genes within a study. Requires a gene_list argument.
                </Summary>
            
                <Input>
                    study_submitter_id (str, required): Study submitter id
                    gene_list (list[str], required): Retrieve data matrices for specific genes.
                    offset (int, optional, default 0): For paginated data.
                    limit (int, optional, default 50): Number of records per page. 
                </Input>

                <Output>
                    data_matrix in JSON format {"data_matrix": data_matrix}
                </Output>

                <Examples>
                    {'study_submitter_id': 'S015-1', 'gene_list': ['TP53','EGFR'], 'offset': 0, 'limit': 50}
                </Examples>
                """
)

pdc_get_quantitative_data_tool.subnode = "PDC"

get_ensembl_ids = FunctionTool.from_defaults(
    name = "ensembl_ids_from_genes", 
    fn = gene_name_to_ensembl_mapping,
    description = """
    <Summary>
        Map gene symbols to Ensembl IDs via the Ensembl REST API. Converts gene symbols into stable Ensembl identifiers for cross-resource linking.
    </Summary>

    <Input>
        genes (array<string>, required): List of gene symbols to map (e.g., ['TP53','EGFR','PTEN']). Provide standard gene symbols (HGNC) where possible.
    </Input>

    <Output>
        mappings (array of {gene, ensembl_id}): Mapping from input gene symbols to Ensembl IDs. May return empty or partial mappings for ambiguous/invalid symbols.
    </Output>

    <Examples>
        {'genes': ['TP53', 'EGFR', 'PTEN']}
    </Examples>
    """
)
get_ensembl_ids.subnode = "Shared"

# NEW: Unified Knowledge Base Search Tool with source-specific filtering
knowledge_base_search_tool = FunctionTool.from_defaults(
    fn=query_knowledge_base,
    name="knowledge_base_search",
    description="""
    <Summary>
        Search documentation and research publications across Cancer Research Data Commons (CRDC) nodes.
        Uses advanced retrieval with HYBRID search (vector + keyword matching), metadata filtering, and Cohere Rerank 3.5 for optimal relevance.
        
        This tool provides access to TWO types of indexed content:
        1) CRDC Documentation: Official web documentation from PDC, GDC, and IDC portals
        2) Research Publications: Scientific publications associated with PDC studies, with rich metadata including study IDs and citations
        
        **Available Data Sources:**
        - **pdc** (default): PDC documentation, FAQs, data submission guides, API docs, CDAP workflows
        - **gdc**: GDC documentation, genomic data access, portal usage, harmonization pipelines  
        - **idc**: IDC documentation, DICOM imaging data, BigQuery integration, viewer tools
        - **publications**: Research publications with PDC study associations, citations, and journal URLs
        - **all**: Search all sources (use sparingly - less accurate than source-specific searches)
    </Summary>

    <When_To_Use>
        **Use this tool for:**
        
        1) Documentation Questions (how-to, concepts, workflows):
           - API usage guidance and examples
           - Portal navigation and features
           - Data submission workflows
           - Download and access methods
           - Harmonization pipeline descriptions
           - Data model and dictionary concepts
           - Authentication and authorization
           - Troubleshooting and FAQs
        
        2) Publication-Backed Study Context:
           - Scientific hypothesis and rationale
           - Experimental design and methodology
           - Analysis approaches and techniques
           - Key findings and biological interpretation
           - Study limitations and caveats
           - Citation information for PDC studies
           - Research context for specific PDC accessions
        
        **Do NOT use this tool for:**
        - Executing API calls or data queries
        - Returning real-time dataset listings or counts
        - Computing cohort results or analytical outputs
        - Retrieving live quantitative data (expression values, protein abundance, PTM sites)
        - Constructing cohorts or performing statistical analyses
        
        → For live data retrieval and computation, use the appropriate CRDC node-specific data/API agent tools.
    </When_To_Use>

    <Documentation_Coverage>
        **PDC Documentation includes:**
        - Submission workflows and requirements
        - Harmonization processes and Common Data Analysis Pipeline (CDAP)
        - Data access methods and API usage guidance
        - Download and cloud analysis workflows
        - PDC-specific tools (PepQuery, cProsite, Morpheus)
        - Policy, governance, and FAQ content
        - Cohort creation in PDC portal
        
        **GDC Documentation includes:**
        - REST API endpoints, filter DSL syntax, and query structure
        - Data model (projects, cases, samples, files, annotations)
        - Data dictionary documentation
        - Authentication and token usage
        - Download clients and tools
        - Harmonization pipelines and policies
        - BAM, VCF, MAF file formats and access
        
        **IDC Documentation includes:**
        - DICOM hierarchy (collections, studies, series, instances)
        - Imaging collections and metadata concepts
        - Segmentations and annotations
        - IDC viewer and visualization tools
        - BigQuery integration for imaging metadata
        - Cloud access workflows and portal navigation
        
        **Publications Knowledge Base includes:**
        - Research publications from PDC-associated studies
        - Study-specific experimental methodologies
        - Published findings and biological interpretations
        - Citations mapped to PDC study accessions
        - Journal articles with rich metadata (studyIds, studyNames, citation, journal_url)
    </Documentation_Coverage>

    <Input>
        question (string, required): The user's question about CRDC documentation or research publications.
        
        data_source (string, optional): Which data source to search. Options:
            - "pdc": PDC documentation and FAQs (default, recommended for PDC-specific questions)
            - "gdc": GDC documentation (for genomic data questions)
            - "idc": IDC documentation (for imaging data questions)
            - "publications": Research publications (for experimental findings, study context, citations)
            - "all": All sources (less accurate, use only for broad exploratory queries)
        
        num_results (integer, optional): Number of results to return (1-20, default: 10).
            - Use 5-10 for focused answers
            - Use 15-20 for comprehensive research queries
        
        pdc_study_id (string, optional): PDC study accession (e.g., "PDC000262") to filter publications.
            - ONLY used when data_source="publications"
            - Filters to publications explicitly associated with the specified study in metadata
            - Useful for retrieving papers about a specific PDC study
            - When provided, ONLY returns papers where studyIds metadata contains this accession
    </Input>

    <Output>
        answer (string/markdown): Human-readable answer grounded in indexed documentation or publications.
        Includes source URLs and citations when available from the knowledge base metadata.
    </Output>

    <Examples>
        # PDC documentation question
        {
            'question': 'How do I submit proteomics data to PDC?',
            'data_source': 'pdc',
            'num_results': 10
        }
        
        # GDC API usage question
        {
            'question': 'How do I construct a filter for the GDC files endpoint?',
            'data_source': 'gdc',
            'num_results': 10
        }
        
        # IDC DICOM concepts question
        {
            'question': 'What is the DICOM hierarchy in IDC (series vs instances)?',
            'data_source': 'idc',
            'num_results': 10
        }
        
        # Research publications - general query
        {
            'question': 'What are the key findings in CPTAC breast cancer proteogenomics studies?',
            'data_source': 'publications',
            'num_results': 15
        }
        
        # Research publications - study-specific query
        {
            'question': 'What experimental methodology and findings are reported for PDC000262?',
            'data_source': 'publications',
            'num_results': 10,
            'pdc_study_id': 'PDC000262'
        }
         }
    </Examples>
    
    <Usage_Guidelines>
        **When to use each data_source:**
        
        1. Use "pdc" for:
           - PDC data submission, download, and access workflows
           - PDC API usage and examples
           - Common Data Analysis Pipeline (CDAP) descriptions
           - PDC-specific tools (PepQuery, cProsite, Morpheus)
           - PDC portal features and cohort creation
           - PDC harmonization processes
           
        2. Use "gdc" for:
           - Genomic data access and download workflows
           - GDC portal navigation and features
           - BAM, VCF, MAF file formats and handling
           - Mutation and variant data concepts
           - GDC harmonization pipelines
           - GDC API filter syntax and queries
           
        3. Use "idc" for:
           - DICOM imaging data access and structure
           - IDC viewer and visualization tools
           - BigQuery integration for imaging metadata
           - Radiology and pathology image collections
           - Cloud-based imaging analysis workflows
           
        4. Use "publications" for:
           - Study scientific context and rationale
           - Experimental design and research methodologies
           - Published findings and biological interpretations
           - Study limitations and caveats from authors
           - Citation information and journal references
           - Mapping PDC accessions to research papers
           
        5. Use "all" sparingly:
           - Only for broad exploratory questions spanning multiple nodes
           - When source is genuinely ambiguous
           - Less accurate than source-specific searches due to broader search space
    </Usage_Guidelines>
    
    <Critical_Boundaries>
        **This is a DOCUMENTATION and PUBLICATION CONTEXT tool.**
        
        It retrieves and summarizes information from:
        ✓ Indexed documentation web pages (PDC/GDC/IDC official docs)
        ✓ Indexed research publication PDFs and their metadata
        ✓ Static content about workflows, concepts, and published research
        
        It CANNOT and must NOT be used to:
        ✗ Execute API calls to CRDC nodes
        ✗ Return real-time dataset counts or listings
        ✗ Retrieve live quantitative data (gene expression, protein abundance, PTM sites)
        ✗ Compute cohort statistics or analytical results
        ✗ Access current database state or perform live queries
        ✗ Substitute for node-specific data retrieval tools
        
        **For live data needs, redirect to appropriate tools:**
        - Live PDC data → Use PDC-specific data/API tools
        - Live GDC data → Use GDC-specific data/API tools  
        - Live IDC data → Use IDC-specific data/API tools
        - Cohort construction → Use cohort-building tools
        - Quantitative analysis → Use analytical/statistical tools
    </Critical_Boundaries>
    """
)
knowledge_base_search_tool.subnode = "Shared"

tools = [disease_tools, 
         sites_or_organ_tools,
         list_study_tools, 
         study_detail_tools, 
         gene_expression_tools,
         biospecimen_data_tools,
         get_ensembl_ids,
         pdc_get_cases_by_study,
         pdc_get_study_files_tool,
         pdc_get_quantitative_data_tool,
         gdc_get_external_expression_tool,
         get_external_resources_data_tool,
         knowledge_base_search_tool
        ]