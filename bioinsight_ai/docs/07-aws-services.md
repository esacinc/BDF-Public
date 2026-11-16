# AWS Services

BioInsight runs entirely on AWS. Everything is in **`us-east-1`** (set in
[config.py](../config.py) via `AWS_REGION` and pinned in the
[Jenkinsfile](../Jenkinsfile)). All SDK calls authenticate with
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from the environment (see
[11-configuration.md](11-configuration.md)).

| Service | Used for |
|---|---|
| **Bedrock** | LLM inference (Claude), KB retrieval reranking (Cohere), managed Knowledge Bases |
| **DynamoDB** | Conversation/thread history, feedback, user records |
| **S3** | Plot images and chat attachments (presigned URLs); KB source documents |
| **SES** | Transactional email from the auth backend |

There is **no Amazon Cognito** in this system — user auth is Google OAuth +
JWT, handled by the FastAPI backend (see [09-auth.md](09-auth.md)).

## Bedrock

- **Claude (Anthropic) via `BedrockConverse`** — the `DEFAULT_MODEL`
  (Claude Sonnet 4.6) backs all LLM calls. Two configurations are defined in
  [workflow_config/default_settings.py](../workflow_config/default_settings.py):
  a standard `llm` (15k max tokens, prompt + tool caching, 1M-context beta) and
  a `thinking_llm` (extended thinking) used by the orchestrator. Full detail in
  [02-workflow.md](02-workflow.md).
- **Cohere Rerank v3.5** (`cohere.rerank-v3-5:0`) — native Bedrock reranking
  for the publications knowledge base retrieval.
- **Bedrock Knowledge Bases** — two managed vector KBs (`MWB_KB_ID`,
  `PUBLICATIONS_KB_ID`) on OpenSearch Serverless with Titan v2 embeddings.
  Fully documented in [05-knowledge-bases.md](05-knowledge-bases.md).

## DynamoDB

Three logical datasets, all reached through a boto3 `dynamodb` client built in
[chainlit_app.py](../chainlit_app.py) (and a separate one in the auth backend):

| Dataset | Env var | Layer | Notes |
|---|---|---|---|
| Conversation / threads | `DATA_LAYER_TABLE` | Chainlit `DynamoDBDataLayer` | Chat history, threads, steps, and element rows. Configured by [data_layer_manager.py](../integrations/chainlit/on_feedback/data_layer_manager.py); uses the `PreSignedS3Client` as its storage provider for attachments. |
| Feedback | `FEEDBACK_TABLE` | Custom `FeedbackDataLayer` | 👍/👎 plus plan/message metadata. Schema: `PK`/`SK` primary key + three GSIs (`UserFeedbackIndex`, `ThreadFeedbackIndex`, `TimestampIndex`), `PAY_PER_REQUEST`. Created by [create_feedback_table.py](../integrations/chainlit/on_feedback/create_feedback_table.py). |
| Users | `APPROVED_USERS_TABLE`, `PENDING_USERS_TABLE` | Direct boto3 in [web_auth/utils/dynamo.py](../web_auth/utils/dynamo.py) | Approved vs. pending registrations for the approval workflow. |

`DataLayerManager` validates each table exists and is `ACTIVE` at startup before
wiring it into Chainlit. Full item shapes and access patterns are in
[12-data-and-persistence.md](12-data-and-persistence.md).

## S3

- **`CHAINLIT_STORAGE_BUCKET`** — stores generated plots and chat attachments.
  Accessed through [`PreSignedS3Client`](../storage/presigned_s3_client.py),
  which wraps boto3 S3 with `upload_file`, `get_read_url`, and `get_write_url`,
  issuing **presigned URLs with a 7-day expiry** (`604800` s). The Chainlit data
  layer stores `objectKey` + presigned `url` on element rows so plots survive
  thread resume.
- **CORS** — on startup, [chainlit_app.py](../chainlit_app.py) calls
  `configure_s3_cors()` / `verify_s3_cors()`
  ([storage/s3_cors_config.py](../storage/s3_cors_config.py)) to allow the
  browser to fetch presigned URLs. Allowed origins come from
  `ALLOWED_CORS_ORIGINS`.
- **KB source buckets** — the knowledge-base data sources also read from S3
  buckets; those are covered in [05-knowledge-bases.md](05-knowledge-bases.md).

## SES

The FastAPI auth backend sends transactional email through SES from
[web_auth/utils/email.py](../web_auth/utils/email.py) (boto3 `ses` client,
`send_email`). The sender is `SES_SOURCE` (`no-reply@bioinsight-ai.com`,
defined in [config.py](../config.py)). Emails include temporary passwords,
account-approval notifications to users, and new-registration notifications to
admins (see [auth_routes.py](../web_auth/auth_routes.py) and
[admin_routes.py](../web_auth/admin_routes.py)). The auth flow itself is in
[09-auth.md](09-auth.md).
