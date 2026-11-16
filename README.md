# BioInsight AI

**Status:** Project concluded

**Project:** ARPA-H Biomedical Data Fabric

## Overview

BioInsight is an exploratory, AI-enabled chatbot intended to support discovery and exploration of publicly available biomedical data using natural language queries. The tool allows users to ask questions in plain English to facilitate high-level exploration and summarization of public cancer datasets, rather than directly querying APIs or navigating complex data interfaces.

### Capabilities

- **Discovery** – Find cancer data across proteomics, genomics, imaging, metabolomics, and lipidomics resources
- **Exploration** – Explore study-level metadata, demographics, biospecimens, and experimental strategies
- **Visualization** – View interactive summaries, expression plots, heatmaps, and Kaplan–Meier survival curves
- **Analysis** – Perform lightweight exploratory analyses to assess dataset relevance

### Supported Data Sources

| Source | Description |
|--------|-------------|
| **Proteomic Data Commons (PDC)** | Mass spectrometry datasets from CPTAC and other proteogenomic programs |
| **Genomic Data Commons (GDC)** | Genomic, transcriptomic, and clinical data from TCGA, TARGET, CPTAC |
| **Imaging Data Commons (IDC)** | Cancer imaging collections and metadata (incl. MIDRC) |
| **ProteomeXchange / PRIDE** | Proteomics datasets and metadata |
| **Metabolomics Workbench** | Metabolomics studies with cancer focus |

---

## AWS Services Used

This repo expects an AWS account with access to the following services:

| Service | Used for |
|---|---|
| **Bedrock** | LLM inference (Claude via `BedrockConverse`), KB retrieval reranking (Cohere Rerank), and two managed **Knowledge Bases** (publications/CRDC and Metabolomics Workbench) backed by OpenSearch Serverless |
| **DynamoDB** | Conversation/thread history, feedback collection, and approved/pending user records |
| **S3** | Generated plots and chat attachments (presigned URLs); also the source documents for the knowledge bases |
| **SES** | Transactional emails from the auth backend (account approval, temporary passwords) |

The Knowledge Bases must already exist in your account; the table names, bucket, and KB IDs are supplied via environment variables (see below).

---

## Installation

### Prerequisites

- Python 3.11
- Node.js 20+ (for the Next.js frontend)
- An AWS account with access to the services listed above
- (Optional, for the full local stack) nginx

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/ICF-Corp/arpah-bdf-bioinsight.git
   cd arpah-bdf-bioinsight/bioinsight_ai
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements_python311.txt
   ```

4. **Install frontend dependencies**
   ```bash
   cd frontend && npm install && cd ..
   ```

5. **Configure environment variables** — create a `.env` file in `bioinsight_ai/` using the example below.

6. **Run the application** — for the full stack (Chainlit + FastAPI auth backend + Next.js + Nginx), use the helper:
   ```bash
   ./run_local.sh        # macOS / Linux
   .\run_local.bat       # Windows
   ```
   Or, to run only the Chainlit chat UI on its own:
   ```bash
   chainlit run chainlit_app.py
   ```

---

## Environment Variables

Create `bioinsight_ai/.env` with the following. Replace placeholder values (in `<…>`) with real values for your environment. **Never commit this file** — `.env*` is gitignored.

```dotenv
# --- Core application ---
APP_ENV=<local|dev|stage|prod>
DEPLOY_ENV=<deployment-name>
LOG_LEVEL=<debug|info|warning|error>
MODEL_ID=<model-id-label>

# --- AWS credentials & region ---
AWS_ACCESS_KEY_ID=<your-aws-access-key-id>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-access-key>
AWS_REGION=<aws-region>

# --- LLMs ---
DEFAULT_MODEL=<bedrock-model-id>
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_MODEL_NAME=<openai-model-name>

# --- Bedrock Knowledge Bases ---
PUBLICATIONS_KB_ID=<publications-kb-id>
MWB_KB_ID=<metabolomics-workbench-kb-id>
MWB_SOURCE_ID=<mwb-kb-data-source-id>

# --- DynamoDB tables ---
DATA_LAYER_TABLE=<conversation-table-name>
FEEDBACK_TABLE=<feedback-table-name>
APPROVED_USERS_TABLE=<approved-users-table-name>
PENDING_USERS_TABLE=<pending-users-table-name>

# --- S3 ---
CHAINLIT_STORAGE_BUCKET=<chainlit-storage-bucket-name>
ALLOWED_CORS_ORIGINS=<comma-separated-allowed-origins>

# --- External data APIs ---
GDC_BASE_API=<gdc-api-base-url>

# --- Chainlit & frontend ---
CHAINLIT_HOST=<chainlit-host>
CHAINLIT_PORT=<chainlit-port>
CHAINLIT_URL=<chainlit-url>
CHAINLIT_AUTH_SECRET=<random-long-string>
NEXT_PUBLIC_API_BASE=<frontend-api-base-url>

# --- Auth (JWT + cookies) ---
JWT_SECRET=<random-long-string>
JWT_ALGORITHM=<jwt-algorithm>
COOKIE_SECURE=<0-or-1>
COOKIE_DOMAIN=<cookie-domain>

# --- Google OAuth ---
OAUTH_GOOGLE_CLIENT_ID=<your-google-oauth-client-id>
OAUTH_GOOGLE_CLIENT_SECRET=<your-google-oauth-client-secret>
OAUTH_GOOGLE_REDIRECT_URI=<google-oauth-redirect-uri>

# --- App URLs (used in emails / redirects) ---
APP_LOGIN_URL=<app-login-url>
APP_LOGO_URL=<app-logo-url>
```

---

## Project Structure

```
bioinsight_ai/
├── agents/                 # Agent definitions and workflows
├── data_sources/           # Data source integrations (PDC, GDC, IDC, etc.)
├── frontend/               # Next.js frontend application
├── integrations/           # Chainlit and external integrations
├── storage/                # S3 and storage utilities
├── utils/                  # Helper utilities
├── web_auth/               # Authentication routes and utilities
├── workflow_config/        # Workflow steps, prompts, and events
├── bioinsight_workflow.py  # Main workflow orchestrator
├── chainlit_app.py         # Chainlit application entry point
├── config.py               # Environment configuration loader
└── requirements.txt        # Python dependencies
```

---

## License

See [LICENSE](LICENSE) for details.
