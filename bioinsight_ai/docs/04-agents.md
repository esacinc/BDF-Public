# Agents

The catalog of the four agents the orchestrator can call. For *how* agents are
built (base classes, hooks, output types, registry), see
[03-agent-architecture.md](03-agent-architecture.md). All four are registered in
`bioinsight_session()` ([bioinsight_workflow.py](../bioinsight_workflow.py)).

| Agent | Base class | Data source | Fetches data? |
|---|---|---|---|
| `CancerResearchDataCommonsAgent` | `BioInsightAgent` | NCI Cancer Research Data Commons (PDC + GDC + IDC) + Publications KB | Yes |
| `MetabolomicsWorkbenchAgent` | `BioInsightAgentWorkflow` (`MWBAgentWorkflow`) | NIH Metabolomics Workbench + MWB KB | Yes |
| `ProteomeExchangeAgent` | `BioInsightAgent` | ProteomeXchange (via EBI PRIDE) | Yes |
| `PlottingAgent` | `BioInsightAgent` | none — consumes other agents' outputs | No |

A recurring pattern: every data-fetching agent's `post_run_agent_output`
converts source identifiers into Markdown hyperlinks and links the first mention
of the source name (see [Common post-processing](#common-post-processing)).

---

## CancerResearchDataCommonsAgent

- **Class**: `CancerResearchDataCommonsAgent(BioInsightAgent)` —
  [cancer_research_data_commons_agent.py](../data_sources/cancer_research_data_commons/cancer_research_data_commons_agent.py); instance built in
  [agent.py](../data_sources/cancer_research_data_commons/agent.py)
- **Data source**: NCI Cancer Research Data Commons (CRDC), spanning three data
  nodes plus shared utilities and the publications knowledge base.

### Nodes, APIs, and tools

| Node | External API | Tools |
|---|---|---|
| **PDC** (Proteomic Data Commons) | GraphQL — `proteomic.datacommons.cancer.gov/graphql`, `pdc.cancer.gov/graphql` ([pdc_api.py](../data_sources/cancer_research_data_commons/proteomic_data_commons/pdc_api.py)) | `pdc_list_diseases`, `pdc_list_primary_sites`, `pdc_list_studies`, `pdc_get_study_details`, `get_study_name`, `get_gene_details`, `pdc_get_expression`, `has_external_genomic_data`, `get_external_resources_data`, `pdc_get_biospecimens`, `get_references`, `get_cases_by_study`, `pdc_get_study_files`, `pdc_get_quantitative_data` |
| **GDC** (Genomic Data Commons) | REST — `api.gdc.cancer.gov` (`GDC_BASE_API`) ([gdc_apis.py](../data_sources/cancer_research_data_commons/genomic_data_commons/gdc_apis.py)) | `gdc_get_studies`, `gdc_project_meta`, `gdc_cases`, `gdc_files`, `gdc_aggregations`, `gdc_annotations`, `gdc_km_data_for_gene_mutations`, `gdc_survival_by_project`, `gdc_survival_by_cases`, `gdc_get_gdc_case_submitter_ids`, `get_gdc_mutation_status`, `gdc_variant_cooccurrence`, `get_gdc_cnv_status`, `gdc_get_external_expression` |
| **IDC** (Imaging Data Commons) | DICOM/imaging query + visualization ([imaging_data_commons/tools.py](../data_sources/cancer_research_data_commons/imaging_data_commons/tools.py)) | `idc_query`, `idc_slider_visualization` |
| **Shared** | Ensembl REST ([ensembl_api.py](../data_sources/cancer_research_data_commons/ensembl_api.py)); Bedrock Publications KB | `ensembl_ids_from_genes`, `knowledge_base_search` |

Each tool carries a `.subnode` attribute (`PDC`/`GDC`/`IDC`/`Shared`) used by the
custom schema below. The `knowledge_base_search` tool queries the
`PUBLICATIONS_KB_ID` knowledge base — its retrieval config (hybrid search,
Cohere rerank, per-source filters) is documented in
[05-knowledge-bases.md](05-knowledge-bases.md).

### Behavior specifics

- **Custom `generate_schema()`** — unlike the default schema, this groups tools
  by subnode, attaches human-readable `SUBNODE_DESCRIPTIONS`, and embeds a
  `CROSS_NODE_REASONING` block. That guidance tells the orchestrator how to
  reason about multi-omic queries across nodes (e.g. matching a CPTAC program
  across PDC/GDC/IDC, preferring the PDC multiomic-availability API over string
  matching, flagging inferred overlaps).
- **Overridden `run()`** — prepends a strict instruction prompt: run the
  appropriate tools and return data only, don't emit Python or apologies,
  preserve identifiers exactly, query only the named source when one is
  specified, and don't fetch external data unless explicitly asked.
- **`post_run_agent_output()`**:
  - If `idc_query` ran → appends a pointer to the dedicated imaging server.
  - If `knowledge_base_search` ran → appends **Citations** and **Journal URLs**
    pulled from the KB results' source metadata.
  - Hyperlinks PDC study IDs (`PDC000###`) and the first mention of PDC / GDC /
    IDC / TCIA to their respective sites.
  - Runs `detect_requested_plot_type()` on the text and, if a plot type is
    found, attaches it as a `requested_plot_type` element so the `PlottingAgent`
    can honor it.

---

## MetabolomicsWorkbenchAgent

- **Class**: `MWBAgentWorkflow(BioInsightAgentWorkflow)` —
  [mwb_agent_workflow.py](../data_sources/metabolomics_workbench/mwb_agent_workflow.py); instance built in
  [agent.py](../data_sources/metabolomics_workbench/agent.py)
- **Data source**: NIH Metabolomics Workbench REST API
  (`www.metabolomicsworkbench.org/rest`) plus the MWB knowledge base
  (`MWB_KB_ID`).

This is a **multi-agent workflow** (not a single agent). A router dispatches to
context-specialized sub-agents that hand off to one another:

| Sub-agent | Role |
|---|---|
| `router_agent` | Root — routes the query to the right context sub-agent ([mwb/router_agent.py](../data_sources/metabolomics_workbench/mwb/router_agent.py)) |
| `study_agent` | Study metadata, design, results, sample sources (MS & NMR) |
| `compound_agent` | Metabolite structures, SMILES/InChIKey, classifications, cross-refs |
| `refmet_agent` | Standardized metabolite nomenclature, formulas, exact masses |
| `gene_agent` | Gene ↔ metabolome associations, pathways |
| `protein_agent` | Protein ↔ metabolite associations (UniProt/RefSeq) |
| `moverz_agent` | m/z precursor-ion search across databases |
| `metstat_agent` | Cross-study statistical summaries and comparisons |
| `rag_agent` | RAG over the MWB website KB for "how do I use the platform" questions (see [05-knowledge-bases.md](05-knowledge-bases.md)) |

### Behavior specifics

- **Overridden `run()`** — formats the `handoff_output_prompt` with the user
  query before delegating to the framework workflow.
- **`post_run_agent_output()`**:
  - Hyperlinks Metabolomics Workbench study IDs (`ST######`) to their study
    pages (guarding against double-linking IDs already inside links/URLs).
  - Converts compound-structure PNG URLs into Markdown **images**.
  - Hyperlinks the first mention of "Metabolomics Workbench".
  - Extracts **`MolView` elements** from tool calls (compound-structure views),
    including the `generate_molecule_view` tool selection. `MolView`
    ([mwb/tools.py](../data_sources/metabolomics_workbench/mwb/tools.py)) is a
    serializable component that renders a molecule in the UI.

---

## ProteomeXchangeAgent

- **Class**: `ProteomeExchangeAgent(BioInsightAgent)` —
  [proteome_exchange_agent.py](../data_sources/proteome_exchange/proteome_exchange_agent.py); instance built in
  [agent.py](../data_sources/proteome_exchange/agent.py)
- **Data source**: ProteomeXchange consortium, accessed through the **EBI PRIDE
  Archive API** (`www.ebi.ac.uk/pride/ws/archive/v3`) plus the `ppx` and
  `pyteomics` libraries for downloading and parsing mzTab files
  ([tools.py](../data_sources/proteome_exchange/tools.py)).

### Tools

| Tool | What it does |
|---|---|
| `get_data_from_proteome_exchange` | Project/dataset info for a PXD accession |
| `get_peptide_from_proteome_exchange` | Looks up a peptide in a study's mzTab files (downloads + parses via `ppx`/`pyteomics`) |
| `get_disease_based_data_from_px` | Last 10 studies for a disease keyword, newest first |

Its system prompt explicitly notes the toolset is limited and tells the agent
it may acknowledge that to the user.

### Behavior specifics

- **`post_run_agent_output()`** — hyperlinks ProteomeXchange dataset IDs
  (`PXD######`) to ProteomeCentral and links the first mention of
  "ProteomeXchange".

---

## PlottingAgent

- **Class**: `PlottingAgent(BioInsightAgent)` —
  [plotting_agent_workflow.py](../agents/plotting_agent_workflow.py); instance built in
  [plotting_agent.py](../agents/plotting_agent.py)
- **Data source**: none. It does **not** fetch data — it consumes another
  agent's tool output and turns it into a visualization.
- **Tools**: none. Instead it carries injected `llm` and `presigned_s3_client`
  dependencies.
- **Utils**: `exec_plot_code` in [utils/plotting_agent_helpers.py](../utils/plotting_agent_helpers.py) for generating code to convert input data from other agents into Plotly figures.
  `draw_graph` in the same file for processing the input from other agents and provide specific instructions on how the code should be generated for creation of plots, includes couple of attempts if generated code resulted in error.
  `detect_requested_plot_type` in the same file detects plot type hints in the text.'requested_plot_type' is attached as an element to the agent output for the `PlottingAgent` to consume and honor.
  `flatten_km_data` in the same file flattens GDC KM data that might come from multiple data sources into a format the plotting agent
  can build a correct Kaplan-Meier plot. `parse_response_content` in the same file parses the LLM response content to extract the plot code and metadata.
  `sanitize_llm_code` in the same file cleans code attachments to make them safe for execution (e.g., stripping imports, file I/O, and system commands).
  `upload_plot_to_s3` in the same file handles uploading generated Plotly figures to S3 via the presigned client and returns the accessible URL.
  `select_best_dataset_for_plot_type` in the same file selects the most appropriate dataset for a given plot type when multiple datasets are available in the agent output.


### Behavior specifics

- **Overridden `run()`** — sanitizes the message and chat history (strips fenced
  code and large JSON/XML blobs) to avoid Bedrock `ConverseStream` cache errors.
- **`post_run_agent_output(output, query, attachments)`** — generates a Plotly
  figure (via `exec_plot_code` for code attachments, else `draw_graph`), uploads
  it to S3 through the presigned client, and returns a `ProcessedOutput` carrying
  the `graphs`. Helpers live in
  [utils/plotting_agent_helpers.py](../utils/plotting_agent_helpers.py).
- It is **special-cased** in `execute_plan`: instead of the streaming run path,
  the workflow calls `post_run_agent_output(last_agent_output, query=...)`
  directly on the previous agent's output. See
  [02-workflow.md](02-workflow.md) and the mechanics in
  [03-agent-architecture.md](03-agent-architecture.md).

---

## Common post-processing

The data-fetching agents share a consistent post-processing pattern in
`post_run_agent_output`:

- **Identifier hyperlinking** — source IDs become Markdown links: `PDC000###` →
  PDC study pages, `ST######` → MWB study pages, `PXD######` → ProteomeCentral.
- **Source-name linking** — the first textual mention of the data source's name
  (PDC, GDC, IDC, TCIA, Metabolomics Workbench, ProteomeXchange) is linked to its
  homepage.
- **Elements** — UI components are attached to the `ProcessedOutput.elements`
  list: `MolView` molecule views (MWB) and `requested_plot_type` hints (CRDC →
  PlottingAgent).
- **Citations** — the CRDC agent appends citations/journal URLs when the
  knowledge base was queried.

All of this is carried on the [`ProcessedOutput`](03-agent-architecture.md)
returned to `execute_plan`, which then renders the text, elements, and graphs in
the Chainlit UI.
