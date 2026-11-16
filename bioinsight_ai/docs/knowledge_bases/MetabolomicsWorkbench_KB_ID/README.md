# KB `<KB ID>` — Metabolomics Workbench

Bedrock Knowledge Base behind the **Metabolomics Workbench RAG agent**. Answers
general "how do I use the platform" questions using content crawled from the
Metabolomics Workbench website.

- **Env var**: `MWB_KB_ID`
- **Sources**: one web crawler (metabolomicsworkbench.org) — no S3 data to archive.

## Contents

| Path | What it is |
|---|---|
| `config.json` | Full KB + data-source build config (embedding model, vector store, crawl scope, chunking). Account IDs redacted. |

Full details: [../../05-knowledge-bases.md](../../05-knowledge-bases.md)
