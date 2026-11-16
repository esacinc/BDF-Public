# AWS Bedrock Knowledge Bases

The chatbot uses two Amazon Bedrock Knowledge Bases for retrieval-augmented
generation (RAG). Both are vector knowledge bases backed by OpenSearch
Serverless, in **`<AWS_REGION>`**. (AWS account IDs are redacted throughout this
doc; full ARNs live in the AWS console.)

> The build configuration below (embedding model, vector store, data sources,
> chunking, crawl scope) was captured from the Bedrock Agent control-plane API
> (`aws bedrock-agent get-knowledge-base` / `get-data-source`). The retrieval
> configuration (search type, filters, reranking) comes from the application
> code under [data_sources/](../data_sources/).

## At a glance

| Knowledge Base | Name | KB ID | Env var | Used by | Reranking |
|---|---|---|---|---|---|
| Metabolomics Workbench | `metabolomics-workbench` | `<MWB_KB_ID value>` | `MWB_KB_ID` | MWB RAG agent | No |
| ARPA-H / Publications | `arpah-knowledge-base` | `<PUBLICATIONS_KB_ID value>` | `PUBLICATIONS_KB_ID` | CRDC (PDC/GDC/IDC docs + publications) | Yes — Cohere Rerank v3.5 |

Shared build characteristics (identical across both KBs):

- **Type**: `VECTOR`
- **Embedding model**: `amazon.titan-embed-text-v2:0` (Titan Text Embeddings V2), **1024 dimensions**
- **Vector store**: OpenSearch Serverless, index `bedrock-knowledge-base-default-index`
  - field mapping: vector `bedrock-knowledge-base-default-vector`, text `AMAZON_BEDROCK_TEXT`, metadata `AMAZON_BEDROCK_METADATA`
- **Data deletion policy**: `DELETE` on every data source (deleting a data source removes its vectors from the collection)

---

## KB 1 — `metabolomics-workbench` (`MWB_KB_ID`)

### Build configuration

| Setting | Value |
|---|---|
| KB ID | `<MWB_KB_ID value>` |
| Embedding | `amazon.titan-embed-text-v2:0`, 1024 dims |
| Vector store | OpenSearch Serverless collection `<vector store id>` (`<AWS region>`) |
| Execution role | `service-role/AmazonBedrockExecutionRoleForKnowledgeBase_sr9ff` |

**Data source** — `website` (`<Data Source ID>`, type `WEB`):

- **Seed URLs**:
  - `https://www.metabolomicsworkbench.org/data`
  - `https://www.metabolomicsworkbench.org/databases`
  - `https://www.metabolomicsworkbench.org/protocols`
  - `https://www.metabolomicsworkbench.org/tools`
  - `https://www.metabolomicsworkbench.org/about`
  - `https://www.metabolomicsworkbench.org/tools/MWRestAPIv1.1.pdf`
- **Inclusion filters** (regex): scoped to the `data`, `databases` (incl. `refmet`), `protocols`, and `tools` index/help pages.
- **Exclusion filters**: `search/*` and auth pages (`login`, `register`, `forgotpassword`, etc.).
- **Crawler limit**: rate limit 300.
- **Chunking**: `HIERARCHICAL` — parent 1500 tokens / child 500 tokens, overlap 60.

The `MWB_SOURCE_ID` env var holds this data source ID (`<Data Source ID>`); the
retrieval filter uses it (see below).

### Retrieval configuration

Defined in
[data_sources/metabolomics_workbench/mwb/rag_agent.py](../data_sources/metabolomics_workbench/mwb/rag_agent.py).

- Uses LlamaIndex `AmazonKnowledgeBasesRetriever` against `MWB_KB_ID`.
- **Search type**: `HYBRID` (vector + keyword).
- **Filter**: `equals` on `x-amz-bedrock-kb-data-source-id` = `MWB_SOURCE_ID` —
  scopes retrieval to the website data source.
- **No reranking.**
- **Response synthesis**: `compact` mode, with `structured_answer_filtering=True`.
- Wrapped as the `MetabolomicsRAGTool` and exposed through the
  `Metabolomics RAG Agent`, which answers general "how do I use the platform"
  questions about Metabolomics Workbench (not data retrieval/analysis).

---

## KB 2 — `arpah-knowledge-base` (`PUBLICATIONS_KB_ID`)

This KB federates four data sources covering the three cancer data commons'
documentation plus research publications. The application addresses them as
four logical sources — `pdc`, `gdc`, `idc`, `publications` — via metadata
filters.

### Build configuration

| Setting | Value |
|---|---|
| KB ID | `<PUBLICATIONS_KB_ID value>` |
| Embedding | `amazon.titan-embed-text-v2:0`, 1024 dims |
| Vector store | OpenSearch Serverless collection `<vector store id>` (`<AWS region>`) |
| Execution role | `service-role/AmazonBedrockExecutionRoleForKnowledgeBase_8jao0` |

**Data sources** (4):

| Data source ID | Name | Type | Source | Chunking |
|---|---|---|---|---|
| `<Data Source ID>` | `Data-Commons-Website-Docs` | WEB | Crawls `pdc.cancer.gov/pdc-docs/`, `docs.gdc.cancer.gov/`, `learn.canceridc.dev/` (rate 300, max 25 000 pages) | HIERARCHICAL 1500/300, overlap 60; **Bedrock Data Automation** parsing |
| `<Data Source ID>` | `faq-knowledge-base-…` | S3 | bucket `arpah-faq-knowledge-base` | default (fixed) |
| `<Data Source ID>` | `knowledge-base-quick-start-…` | S3 | bucket `arpah-bedrock-knowledge-base`, prefix `publications/` (research publication PDFs + `.metadata.json` sidecars) | default (fixed) |
| `<Data Source ID>` | `arpah-faq-data-source` | WEB | Crawls `proteomic.datacommons.cancer.gov/pdc/faq` (rate 10, max 25 000 pages) | default (fixed) |

Note that a single crawler data source (`<Data Source ID>`) ingests all three
commons' documentation sites. The application separates them at query time
using `x-amz-bedrock-kb-source-uri` prefix filters (next section).

### Retrieval configuration

Defined in
[data_sources/cancer_research_data_commons/proteomic_data_commons/knowledge_base/](../data_sources/cancer_research_data_commons/proteomic_data_commons/knowledge_base/):

- **`kb_retrieval_engine.py`** — builds the retrieval config and query engines.
  - **Search type**: `HYBRID` (default; `SEMANTIC` also supported).
  - **Reranking**: native Bedrock **Cohere Rerank v3.5**
    (`cohere.rerank-v3-5:0`, `us-east-1`), enabled by default.
  - **Candidate→result funnel**: retrieves `num_candidates` (default 30, 50 for
    publications), reranks down to `num_results` (default 10, 15 for
    publications). When reranking is disabled, it retrieves `num_results`
    directly.
  - **Response synthesis**: `tree_summarize` by default.
  - Exposes per-source helpers `get_pdc_engine()`, `get_gdc_engine()`,
    `get_idc_engine()`, `get_publications_engine()`, plus lazily-initialized
    singletons.
- **`retrieval_filters.py`** — the metadata filters that carve the four logical
  sources out of the KB:

  | Logical source | Filter |
  |---|---|
  | `pdc` | `orAll` of: data-source-id `<Data Source ID>` (FAQ S3), `<Data Source ID>` (FAQ web), or (`<Data Source ID>` **and** source-uri starts with `https://pdc.cancer.gov/`) |
  | `gdc` | data-source-id `<Data Source ID>` **and** source-uri starts with `https://docs.gdc.cancer.gov/` |
  | `idc` | data-source-id `<Data Source ID>` **and** source-uri starts with `https://learn.canceridc.dev/` |
  | `publications` | data-source-id `<Data Source ID>`; optionally **and** `listContains(studyIds, <pdc_study_id>)` |
  | `all` | no filter (discouraged) |

- **`knowledge_base_tool.py`** — `query_knowledge_base(question, data_source,
  num_results, pdc_study_id)`. Validates that `pdc_study_id` is only used with
  `data_source="publications"`, auto-sizes candidates as
  `min(num_results * 3, 50)`, always enables HYBRID + reranking, and returns the
  full LlamaIndex response (preserving citations/metadata).
- The agent-facing `knowledge_base_search` FunctionTool wraps this in
  [proteomic_data_commons/tools.py](../data_sources/cancer_research_data_commons/proteomic_data_commons/tools.py)
  — used for documentation Q&A and publication-backed study context, not live
  data queries.

The `publications` source carries rich metadata (`studyIds`, `studyNames`,
`citation`, `journal_url`), which is what enables study-scoped publication
retrieval via the `listContains` filter on `studyIds`.

---

## Where the code references these KBs

| Env var | Value | Read by |
|---|---|---|
| `MWB_KB_ID` | `<MWB_KB_ID>` | [mwb/rag_agent.py](../data_sources/metabolomics_workbench/mwb/rag_agent.py) |
| `MWB_SOURCE_ID` | `<MWB_SOURCE_ID>` | [mwb/rag_agent.py](../data_sources/metabolomics_workbench/mwb/rag_agent.py) (retrieval filter) |
| `PUBLICATIONS_KB_ID` | `<PUBLICATIONS_KB_ID>` | [knowledge_base/kb_retrieval_engine.py](../data_sources/cancer_research_data_commons/proteomic_data_commons/knowledge_base/kb_retrieval_engine.py) |

The data source IDs for `PUBLICATIONS_KB_ID` are env-driven
(`PUBLICATIONS_DOCS_SOURCE_ID`, `PUBLICATIONS_FAQ_S3_SOURCE_ID`,
`PUBLICATIONS_FAQ_WEB_SOURCE_ID`, `PUBLICATIONS_PAPERS_SOURCE_ID`) and consumed in
[retrieval_filters.py](../data_sources/cancer_research_data_commons/proteomic_data_commons/knowledge_base/retrieval_filters.py).
The reranker model ARN is hard-coded in
[kb_retrieval_engine.py](../data_sources/cancer_research_data_commons/proteomic_data_commons/knowledge_base/kb_retrieval_engine.py).

## Reproducing the build-config lookup

The build configuration above can be re-retrieved with the Bedrock Agent
control-plane API (read-only):

```sh
aws bedrock-agent list-knowledge-bases --profile bdf_user --region <AWS_REGION>
aws bedrock-agent get-knowledge-base   --knowledge-base-id <KB_ID> --profile bdf_user --region <AWS_REGION>
aws bedrock-agent list-data-sources    --knowledge-base-id <KB_ID> --profile bdf_user --region <AWS_REGION>
aws bedrock-agent get-data-source      --knowledge-base-id <KB_ID> --data-source-id <DS_ID> --profile bdf_user --region <AWS_REGION>
```
