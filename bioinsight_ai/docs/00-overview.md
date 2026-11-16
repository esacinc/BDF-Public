# BioInsight AI — Overview

## What it is

BioInsight AI is a biomedical research chatbot. Users ask natural-language
questions about cancer genomics, proteomics, imaging, and metabolomics; the
system plans which specialized data-source agents to call, executes them,
synthesizes a final answer, and (when relevant) renders plots inline in the
chat UI.

The product is a single web application backed by AWS. It was developed under
the ARPA-H Biomedical Data Fabric program at ICF.

## What a user sees

A Chainlit chat interface served at `/chat` on the deployment domain. After
authenticating (Google OAuth via the custom auth backend, or email/password
where enabled), the user gets:

- A chat thread with conversation history persisted across sessions
- Suggested starter queries (defined in
  [chainlit_app.py](../chainlit_app.py) via `@cl.set_starters`)
- Answers from Claude with citations to the source data commons
- Inline Plotly visualizations (heatmaps, bar/line charts) when the question
  calls for them
- A thumbs-up / thumbs-down feedback widget on every assistant message

## What runs where

The Docker image bundles four processes started by
[entrypoint.sh](../entrypoint.sh):

| Process | Port | Role |
|---|---|---|
| Nginx | 80 | Reverse proxy; routes `/chat` to Chainlit, `/api` to FastAPI, everything else to Next.js |
| Chainlit | 8000 | Chat UI and the LlamaIndex workflow runtime ([chainlit_app.py](../chainlit_app.py)) |
| FastAPI auth backend | 7000 | Login, OAuth callback, JWT issuance, admin user management ([web_auth/](../web_auth/)) |
| Next.js frontend | 3000 | Marketing/landing pages and login UI ([frontend/](../frontend/)) |

All four share the same JWT cookie. Chainlit's built-in auth is disabled
(`CHAINLIT_AUTH_DISABLE=true`); the FastAPI backend is the source of truth
for sessions.

## Core engine

The chat backend is a [LlamaIndex
Workflow](https://docs.llamaindex.ai/en/stable/module_guides/workflow/) class,
[`BioInsightWorkflow`](../bioinsight_workflow.py), with four `@step`-decorated
methods:

```
StartEvent
    │
    ▼
  plan ──────► (direct answer / clarification → StopEvent)
    │
    ▼
  execute_plan ──► ResponseEvent   (or ConcludeEvent for a single action)
    │
    ▼
  synthesize ──► ConcludeEvent
    │
    ▼
  conclude ──► StopEvent
```

The `plan` step uses a "thinking LLM" (Claude with extended thinking enabled)
to decide which agents to call; `execute_plan` runs them (plotting is just
another agent, the `PlottingAgent`); `synthesize` combines their outputs;
`conclude` emits the final assistant message.
Conversation history is managed by a `Memory` object with a
`FactExtractionMemoryBlock` that condenses old turns into a list of facts when
the token budget is exceeded. See [02-workflow.md](02-workflow.md) for the
full step-by-step description.

## Specialized agents

Each biomedical data source has its own agent. The orchestrator picks one or
more per query.

| Agent | Source | Code |
|---|---|---|
| `CancerResearchDataCommonsAgent` | NCI Cancer Research Data Commons — federates Genomic (GDC), Proteomic (PDC), and Imaging (IDC) Data Commons | [data_sources/cancer_research_data_commons/](../data_sources/cancer_research_data_commons/) |
| `MetabolomicsWorkbenchAgent` | NIH Metabolomics Workbench — studies, compounds, proteins, genes, RefMet, MetStat, MoverZ, plus a RAG agent over the MWB knowledge base | [data_sources/metabolomics_workbench/](../data_sources/metabolomics_workbench/) |
| `ProteomeExchangeAgent` | ProteomeXchange consortium — PXD dataset metadata | [data_sources/proteome_exchange/](../data_sources/proteome_exchange/) |
| `PlottingAgent` | Generates Plotly visualizations and uploads them to S3 as presigned PNGs | [agents/plotting_agent.py](../agents/plotting_agent.py) |

See [03-agent-architecture.md](03-agent-architecture.md) and [04-agents.md](04-agents.md).

## External services

| Service | Used for |
|---|---|
| **AWS Bedrock** | Claude Sonnet 4.6 for all LLM calls; Cohere Rerank v3.5 for KB retrieval; three managed Knowledge Bases (general context, Metabolomics Workbench, Publications) |
| **AWS DynamoDB** | Conversation/thread persistence (Chainlit data layer), feedback collection, approved/pending users tables |
| **AWS S3** | Plot images and chat attachments, served via presigned URLs |
| **AWS SES** | Transactional email (user approval notifications) |
| **Google OAuth** | Primary login flow |
| **Ensembl REST** | Gene-name → Ensembl ID resolution (CRDC agent) |
| **GDC / PDC / IDC public APIs** | Cancer data commons queries |
| **Metabolomics Workbench REST** | Metabolomics queries |
| **ProteomeXchange** | Proteomics dataset queries |

See [07-aws-services.md](07-aws-services.md) for table schemas and bucket
layout, and [05-knowledge-bases.md](05-knowledge-bases.md) for the Bedrock
Knowledge Bases.

## Repository layout (tracked content only)

```
bioinsight_ai/
├── chainlit_app.py            # Chainlit UI, lifecycle hooks, FastAPI mounts
├── bioinsight_workflow.py     # LlamaIndex Workflow class — the orchestrator
├── config.py                  # Env var loading
├── authentication.py          # Legacy auth helpers (mostly disabled)
├── Dockerfile                 # Multi-stage build (frontend + Python + s5cmd)
├── Jenkinsfile                # CI/CD pipeline → AWS CodeDeploy
├── nginx.conf                 # Reverse proxy config
├── entrypoint.sh              # Runs all four processes
├── chainlit.md                # Chainlit welcome screen content
├── agents/                    # Agent base classes, registry, plotting agent
├── data_sources/              # Per-source agents (CRDC, MWB, ProteomeXchange)
├── integrations/chainlit/     # Chainlit hook implementations
├── workflow_config/           # Workflow events, step prompts, memory prompts
├── utils/                     # Plotting helpers, tracing, transforms
├── storage/                   # PreSignedS3Client wrapper
├── web_auth/                  # FastAPI auth backend
├── frontend/                  # Next.js app
├── public/                    # Static assets
├── log_helper/                # Structured logger with contextvars
├── scripts/                   # One-off ops scripts
└── docs/                      # ← this directory
```

## How to read these docs

If you've never seen this codebase before, read in order:

1. **00-overview.md** (this file)
2. **[01-architecture.md](01-architecture.md)** — component diagram, request lifecycle
3. **[02-workflow.md](02-workflow.md)** — the LlamaIndex workflow in detail
4. **[03-agent-architecture.md](03-agent-architecture.md)** — agent framework: base classes, hooks, registry
5. **[04-agents.md](04-agents.md)** — the four agents: data sources, tools, post-processing
6. **[05-knowledge-bases.md](05-knowledge-bases.md)** — Bedrock Knowledge Bases: build + retrieval config, filters, rerank
7. **[06-imaging-server.md](06-imaging-server.md)** — partial imaging integration + the standalone VoxelInsight server
8. **[07-aws-services.md](07-aws-services.md)** — Bedrock, DynamoDB, S3, SES
9. **[08-frontend-and-ui.md](08-frontend-and-ui.md)** — Chainlit hooks, Next.js, Nginx
10. **[09-auth.md](09-auth.md)** — JWT/OAuth flow
11. **[10-deployment.md](10-deployment.md)** — Docker, Jenkins, CodeDeploy
12. **[11-configuration.md](11-configuration.md)** — env var reference
13. **[12-data-and-persistence.md](12-data-and-persistence.md)** — DynamoDB schemas, S3 layout, memory serialization

If you're trying to debug a specific area, jump to the doc and follow the
file links from there.
