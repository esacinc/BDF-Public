# KB `<KB ID>` — ARPA-H / Publications

Bedrock Knowledge Base behind the **Cancer Research Data Commons (CRDC) agent**.
Covers documentation for the three data commons (PDC, GDC, IDC) plus a corpus of
cancer research publications. Retrieval uses hybrid search + Cohere reranking,
with metadata filters that scope queries to a specific source.

- **Env var**: `PUBLICATIONS_KB_ID`
- **Sources**: 4 — two web crawlers (commons docs + PDC FAQ) and two S3 buckets (below).

## Contents

| Path | What it is |
|---|---|
| `config.json` | Full KB + all 4 data-source build configs. Account IDs redacted. |
| `PDC_FAQ_docs/` | S3 data source: **PDC FAQ documents** (5 PDFs, archived as loose files). |
| `Other_publications/` | S3 data source: **research publications** (live source scoped to the `publications/` prefix of the bucket) — `OtherPublications.zip` (5 orphan PDFs + 61 metadata sidecars). |

The two web-crawler sources have no subdir (nothing to download; their crawl
scope is captured in `config.json`).

Full details: [../../05-knowledge-bases.md](../../05-knowledge-bases.md)