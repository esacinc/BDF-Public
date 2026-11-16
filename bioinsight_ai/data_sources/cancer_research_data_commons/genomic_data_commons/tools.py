from llama_index.core.tools import FunctionTool
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import Context
import data_sources.cancer_research_data_commons.genomic_data_commons.gdc_apis as gdc_apis


gdc_survival_analysis_project_genes = FunctionTool.from_defaults(
    name = "gdc_km_data_for_gene_mutations",
    fn = gdc_apis.gdc_km_data_for_gene_mutations,
    description = """
                     <Summary>
                        Returns data needed for survival analysis plots given gene names list and GDC study ID. 
                        Returns 2 datasets which contain survivalEstimate and related content needed for Kaplan-Meier plotting.
                    </Summary>

                    <Input>
                        gene_names (array<string>, required, uppercase): Genes for mutation stratification. Example: ['TP53']
                        gdc_project_id (string, required, e.g., 'TCGA-OV'): GDC project identifier to build KM data for.
                    </Input>

                    <Output>
                        df1_json, df2_json (2 JSON lists): SurvivalEstimate JSON lists and grouping metadata suitable to create Kaplan-Meier plots.
                    </Output>

                    <Examples>
                        {'gene_names': ['BRCA1', 'PTEN'], 'gdc_project_id': 'TCGA-BRCA'}
                    </Examples>
                    """
)
gdc_survival_analysis_project_genes.subnode = "GDC"

gdc_survival_analysis_by_project = FunctionTool.from_defaults(
    name = "gdc_survival_by_project",
    fn = gdc_apis.gdc_survival_by_project,
    description = """
                <Summary>
                    Gets data needed for survival analysis plot given GDC project ID 
                    returns one dataset with aggregated survivalEstimate and related content needed for Kaplan-Meier plotting.
                </Summary>

                <Input>
                    gdc_project_id (string, required): GDC project identifier (e.g., 'TCGA-LUAD').
                </Input>

                <Output>
                    survival ({time, censored, survivalEstimate, n_risk?, strata?}): Aggregated survival estimates for the project; ready for KM plotting or downstream risk summaries.
                </Output>

                <Examples>
                    {'gdc_project_id': 'TCGA-LUAD'}
                </Examples>
                        """
)
gdc_survival_analysis_by_project.subnode = "GDC"

gdc_map_pdc_cases = FunctionTool.from_defaults(
    name = "gdc_get_gdc_case_submitter_ids",
    fn = gdc_apis.get_gdc_case_submitter_ids,
    description = """
                    <Summary>
                        Map PDC case submitter IDs to GDC case submitter IDs for cross-resource case matching.
                    </Summary>

                    <Input>
                        pdc_case_submitter_ids (list[str], required): List of PDC case submitter IDs to map.
                    </Input>

                    <Output>
                        gdc_submitter_ids (array of {pdc_case_submitter_id, gdc_case_submitter_id}): Mapping from PDC ids to corresponding GDC ids suitable for downstream analyses. Returns an empty
                                   list if no matches are found or an error occurs during the API call.
                    </Output>

                    <Examples>
                        {'pdc_case_submitter_ids': ['caseA','caseB']}
                    </Examples>
                  """
)
gdc_map_pdc_cases.subnode = "GDC"

gdc_survival_analysis_by_cases = FunctionTool.from_defaults(   
    name = "gdc_survival_by_cases",
    fn = gdc_apis.get_survival_analysis_by_cases,
    description = """
                    <Summary>
                        Get data needed for Kaplan-Meier survival analysis plots stratified by provided PDC case lists.
                        Returns 2 datasets which contain survivalEstimate and related content needed for KM plotting.
                    </Summary>

                    <Input>
                        pdc_case_list1 (list[str], required): First list of PDC case submitter ids for group A.
                        pdc_case_list2 (list[str], required): Second list of PDC case submitter ids for group B.
                    </Input>

                    <Output>
                        km_datasets (object): SurvivalEstimate arrays for each group and grouping metadata suitable to create Kaplan-Meier plots.
                    </Output>

                    <Examples>
                        {'pdc_case_list1': ['case1','case2'], 'pdc_case_list2': ['case3','case4']}
                    </Examples>
                  """
)
gdc_survival_analysis_by_cases.subnode = "GDC"

project_tools = FunctionTool.from_defaults(
    fn = gdc_apis.get_gdc_studies,
    name = "gdc_get_studies",
    description = """
                    <Summary>
                        List all GDC projects (studies) available in the GDC API. Useful for discovering project IDs to use with other GDC tools.
                    </Summary>

                    <Output>
                        gdc_list (array of {id, primary_site, dbgap_accession_number, project_id, disease_type, name, releasable, state, released}): Project metadata useful for contextualizing study cohorts.
                    </Output>

                  """,
)
project_tools.subnode = "GDC"

gdc_project_meta_by_project_id = FunctionTool.from_defaults(
    name = "gdc_project_meta",
    fn = gdc_apis.get_project_meta_by_project_id,
    description = """
                <Summary>
                    Return metadata for a GDC project ID. Useful for retrieving project-level details (disease_type, primary_site, summary) used in reporting.
                </Summary>

                <Input>
                    gdc_project_id (string, required): GDC project identifier (e.g., 'TCGA-GBM').
                </Input>

                <Output>
                    project ({id, name, disease_type, primary_site, summary, ...}): Project metadata useful for contextualizing study cohorts or None if not found.
                </Output>

                <Examples>
                    {'gdc_project_id': 'TCGA-GBM'}
                </Examples>
                  """
)
gdc_project_meta_by_project_id.subnode = "GDC"

gdc_case_tools = FunctionTool.from_defaults(
    fn = gdc_apis.gdc_cases,
    name = "gdc_cases",
    description = """
                <Summary>
                    Retrieve detailed case-level (patient) information via filters and selected fields from GDC.
                    Use for demographic, clinical, or diagnosis-based patient queries.
                </Summary>

                <Input>
                    filters (dict, required): A dictionary to filter results. GDC filter DSL specifying case selection criteria. Example: project.project_id or diagnoses.age_at_diagnosis comparisons.
                    fields (list, optional): A list of GDC fields to return (e.g., case_id, demographic.gender).
                    size (int, optional; default 10): Number of cases to return.
                </Input>

                <Output>
                    cases (list of field maps): Case-level records with requested fields suitable for cohort construction and downstream analyses.
                </Output>

                <Examples>
                    {'filters': {'op': 'and', 'content': [{'op': '=', 'content': {'field': 'project.project_id', 'value': 'TCGA-BRCA'}}, {'op': '>', 'content': {'field': 'diagnoses.age_at_diagnosis', 'value': 21915}}]}, 'fields': ['case_id', 'demographic.gender']}
                </Examples>
                   """,
)
gdc_case_tools.subnode = "GDC"

gdc_file_tools = FunctionTool.from_defaults(
    fn = gdc_apis.gdc_files,
    name = "gdc_files",
    description = """
    <Summary>
        List files with flexible filters and selected fields from GDC. Use to locate file_ids and metadata for specific data types, experimental strategies or file formats.
    </Summary>

    <Input>
        filters (dict, required):  A dictionary to filter results. Keys are GDC field names. Example: filter by project.project_id or data_category.
        fields (list, optional): A list of GDC fields to return. Example: ['file_name', 'data_category'].
        size (int, optional; default 10): Number of records to return.
    </Input>

    <Output>
        files (array of field maps): Array of file records containing requested fields (file_id, file_name, data_format, etc.).
    </Output>

    <Examples>
        {'filters': {'op': 'and', 'content': [{'op': '=', 'content': {'field': 'cases.project.project_id', 'value': 'TCGA-OV'}}]}, 'fields': ['file_id', 'file_name', 'data_format'], 'size': 25}
    </Examples>
    """,
)
gdc_file_tools.subnode = "GDC"


# <Examples>
#    {'entity': 'files', 'filters': {'op': 'and', 'content': [{'op': '=', 'content': {'field': 'files.data_category', 'value': 'Transcriptome Profiling'}}]}, 'group_by': 'experimental_strategy'}
# </Examples>

gdc_aggregation_tools = FunctionTool.from_defaults(
    fn = gdc_apis.gdc_aggregations,
    name = "gdc_aggregations",
    description = """
                <Summary>
                    Get counts of items (cases, files, projects, mutations, CNVs) that match a set of filters.
                    It can provide a simple total count or group the counts by a specific field.
                    Use this to answer "how many" or "top N" questions.
                </Summary>
            
                <Input>
                    entity (enum['cases', 'files', 'projects', 'ssm_occurrences', 'cnvs'], required): The type of entity to aggregate.
                    filters (dict, optional): A SIMPLE dictionary of filters to apply.
                        - Do NOT use GDC's complex "op" and "content" format.
                        - The keys are the field names and the values are what they should match.
                    group_by (str, optional): A field name to group the counts by. Example: 'demographic.gender' or 'samples.preservation_method'.
                </Input>

                <Output>
                    counts (total or grouped counts): Aggregated total or grouped counts depending on 'group_by'.
                </Output>

                <Examples>
                    1. How many cases are in TCGA-BRCA:
                       {'entity': 'cases', 'filters': {'project.project_id': 'TCGA-BRCA'}}
                    2. Top 3 studies with the most CNV loss events:
                       {'entity': 'cnvs', 'filters': {'cnv_type': 'loss'}, 'group_by': 'project.project_id'}
                    3. Top 5 mutated genes in TCGA-BRCA:
                       {'entity': 'ssm_occurrences', 'filters': {'project.project_id': 'TCGA-BRCA'}, 'group_by': 'ssm.consequence.transcript.gene.symbol'}
                </Examples>
                """,
)
gdc_aggregation_tools.subnode = "GDC"

gdc_annotation_tools = FunctionTool.from_defaults(
    fn = gdc_apis.gdc_annotations,
    name = "gdc_annotations",
    description = """
                <Summary>
                    Find information about annotations, which are special flags or notes attached to data like cases, samples, or files. 
                    This is the primary tool for answering questions about data quality control (QC), flagged issues, problems, warnings, or redactions.
                </Summary>

                <Input>
                    filters (dict, required): A dictionary to filter annotations. To find issues for a project, filter by 'project.project_id'. Example: {'project.project_id': 'TCGA-OV'}
                    fields (list, optional): A list of annotation fields to return.
                    size (int, optional; default 100): The number of annotations to return. 
                </Input>
                
                <Output>
                    annotations (list of annotation records): Matching annotation records describing QC flags, redactions, or notes.
                </Output>

                <Examples>
                    {'filters': {'project.project_id': 'TCGA-OV'}, 'size': 100}
                </Examples>
                """,
)
gdc_annotation_tools.subnode = "GDC"

gdc_somatic_mutation_tool = FunctionTool.from_defaults(
    fn=gdc_apis.get_gdc_mutation_status,
    name="get_gdc_mutation_status",
    description="""
                <Summary>
                    Fetches somatic mutation status for a list of gene symbols from a specific GDC project.
                </Summary>

                <Input>
                    gene_symbols (List[str], required): A list of gene symbols to query, e.g., ['TP53', 'PIK3CA'].
                    project_id (str, required): The GDC project ID to search within, e.g., 'TCGA-BRCA'.
                </Input>

                <Output>
                    case_mutations (Dict[str, List[str]]): A dictionary mapping case_ids (patient UUIDs) to a list of
                                           the genes from the input list that are mutated in that case.
                                           Returns an empty dictionary if no mutations are found.
                </Output>
                
                <Examples>
                    {'gene_symbols': ['TP53', 'PIK3CA'], 'project_id': 'TCGA-BRCA'}
                </Examples>
                """,
)

gdc_somatic_mutation_tool.subnode = "GDC"

gdc_variant_cooccurrence_tool = FunctionTool.from_defaults(
    fn=gdc_apis.gdc_variant_cooccurrence,
    name="gdc_variant_cooccurrence",
    description="""
                <Summary>
                    Computes the co-occurrence frequency and overlap statistics between two specific 
                    amino acid variants (e.g., IDH1 R132H and TP53 R273C) within a given GDC project.
                    Use this tool to answer questions about how often two specific mutations appear together 
                    in the same patient cases.
                </Summary>

                <Input>
                    project_id (str, required): The GDC project ID (e.g., 'TCGA-LGG').
                    variant_1 (dict, required): A dictionary representing the first variant.
                        - gene_symbol (str): The Hugo symbol (e.g., 'IDH1').
                        - aa_change (str): The amino acid change (e.g., 'R132H' or 'p.R132H').
                    variant_2 (dict, required): A dictionary representing the second variant.
                        - gene_symbol (str): The Hugo symbol (e.g., 'TP53').
                        - aa_change (str): The amino acid change (e.g., 'R273C' or 'p.R273C').
                </Input>

                <Output>
                    cooccurrence_data (Dict): A dictionary containing:
                        - project_id: The queried project.
                        - counts: Dictionary with 'A' (variant 1 count), 'B' (variant 2 count), 
                          'A_and_B' (intersection), and 'total_profiled' (denominator).
                        - percentages: Overlap percentages (A∩B of total, A∩B of A, A∩B of B).
                        - p_value: p value
                        - odds_ratio: odds ratio,
                        - interpretation: significance of association"
                </Output>
                
                <Examples>
                    {
                        'project_id': 'TCGA-LGG', 
                        'variant_1': {'gene_symbol': 'IDH1', 'aa_change': 'R132H'}, 
                        'variant_2': {'gene_symbol': 'TP53', 'aa_change': 'R273C'}
                    }
                </Examples>
                """,
)

gdc_variant_cooccurrence_tool.subnode = "GDC"

gdc_cnv_tool = FunctionTool.from_defaults(
    fn=gdc_apis.get_gdc_cnv_status,
    name="get_gdc_cnv_status",
    description="""
                <Summary>
                    Fetches Copy Number Variation (CNV) events (e.g., amplification, loss) for specific genes and projects from the GDC.
                </Summary>

                <Input>
                    gene_symbols (List[str], required): A list of gene symbols to query, e.g., ["ERBB2", "MYC"].
                    project_id (str, required): The GDC project ID to search within, e.g., "TCGA-BRCA".
                    cnv_type (Optional[str], optional; default None): Specific CNV type to filter for, e.g.,"amplification" or "loss". If None, returns all types.
                </Input>

                <Output>
                    case_cnvs (Dict[str, List[Dict]]): A dictionary mapping case_ids (patient UUIDs) to a list of CNV events. 
                                                    Each event is a dictionary containing the gene, CNV type, and log2 ratio value.
                                                    e.g., {"case-uuid-1": [{"gene": "ERBB2", "cnv_type": "amplification", "value": 2.1} ]}
                </Output>

                <Examples>
                    {'gene_symbols': ['TP53', 'PIK3CA'], 'project_id': 'TCGA-BRCA', 'cnv_type': 'amplification'}
                </Examples>
                """,
)

gdc_cnv_tool.subnode = "GDC"

tools = [gdc_survival_analysis_project_genes,
         gdc_survival_analysis_by_cases,
         gdc_survival_analysis_by_project,
         gdc_aggregation_tools,
         gdc_file_tools,
         gdc_case_tools,
         gdc_project_meta_by_project_id,
         gdc_annotation_tools,
         gdc_somatic_mutation_tool,
         gdc_variant_cooccurrence_tool,
         gdc_cnv_tool,
         ]