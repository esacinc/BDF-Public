# Data & Persistence

**In plain terms:** three things get stored. **DynamoDB** holds conversations,
feedback, and user accounts. **S3** holds generated plots and file attachments.
And because a chat can be closed and reopened, the live state of a conversation
is **serialized into the thread's DynamoDB record** and restored on resume — the
machinery that makes that work without breaking the conversation is the last
section here.

Tables are referred to by their env-var name (values in
[11-configuration.md](11-configuration.md)); the service-level overview is in
[07-aws-services.md](07-aws-services.md).

## DynamoDB

### Conversation / threads — `DATA_LAYER_TABLE`

Managed by Chainlit's built-in `DynamoDBDataLayer` (a single-table design holding
threads, **steps** — user messages, assistant messages, and `run` steps —
elements, and users). The app layers its own data into each thread's
**`metadata`** object:

| Metadata key | Contents | Written / read by |
|---|---|---|
| `serialized_ctx` | The serialized workflow `Context` for this thread (see below) | `on_message` / `on_chat_end` write it; `on_chat_resume` reads it |
| `plans` | `{ message_id → plan JSON }` — the orchestration plan behind each answer | `link_plan_to_message` writes; the feedback collector reads |
| `current_plan` | Pointer to the most recent plan (back-compat) | `link_plan_to_message` |
| `plots_by_message` | `{ message_id → graph metadata }` — S3 references for rendered plots | `on_message` writes; `on_chat_resume` reads to re-render |

Element rows store an `objectKey` + a presigned `url` so attachments and plots
resolve on reload.

### Feedback — `FEEDBACK_TABLE`

A custom single-table design (created by
[create_feedback_table.py](../integrations/chainlit/on_feedback/create_feedback_table.py),
`PAY_PER_REQUEST`). Each 👍/👎 is one item; the key design supports several
query patterns:

| Key / index | Partition → Sort | Query it answers |
|---|---|---|
| Primary | `PK = FEEDBACK#<feedback_id>` → `SK = METADATA` | Fetch one feedback record |
| `UserFeedbackIndex` (GSI) | `USER#<user_id>` → `FEEDBACK#<timestamp>` | All feedback from a user, time-ordered |
| `ThreadFeedbackIndex` (GSI) | `THREAD#<thread_id>` → `FEEDBACK#<timestamp>` | All feedback in a thread |
| `TimestampIndex` (GSI) | `FEEDBACK` → `<timestamp>` | All feedback globally, time-ordered |

Item attributes (from `FeedbackData`,
[data_models.py](../integrations/chainlit/on_feedback/data_models.py)):
`rating` (0 = 👎, 1 = 👍), `comment`, `user_message`, `assistant_message`,
`response_time`, `feedback_timestamp`, and **`serialized_plan`** — the exact plan
that produced the rated answer (read back from `metadata['plans']`). See the
collection flow in [08-frontend-and-ui.md](08-frontend-and-ui.md).

### Users — `APPROVED_USERS_TABLE` / `PENDING_USERS_TABLE`

Two tables, both keyed on **`user_email`** (partition key; no sort key), managed
in [web_auth/utils/dynamo.py](../web_auth/utils/dynamo.py):

- **Pending** — applicants: `user_email`, `full_name`, `organization`,
  `job_title`, `additional_info`, `auth_provider` (`password`/`google`),
  `status` (`pending` / `denied`).
- **Approved** — active accounts: the above plus `role` (`user`/`admin`),
  `allowed_environments` (list), `must_change_pw` (bool), and `password_hash`
  (bcrypt; password accounts only — Google accounts have none).

Access patterns: `get_item` by email; `scan` + filter for pending users
(`status = pending`) and admins (`role = admin`); approval writes to Approved and
deletes from Pending; denial is a soft delete (`status = denied`). Auth context:
[09-auth.md](09-auth.md).

## S3 — `CHAINLIT_STORAGE_BUCKET`

Holds generated visualizations and chat attachments, accessed through
[`PreSignedS3Client`](../storage/presigned_s3_client.py):

- **Plots** — uploaded under the `plots/` prefix as `plots/<uuid>.json` (Plotly
  figure JSON) or `plots/<uuid>.png` (Matplotlib), by the plotting agent and the
  IDC slider tool.
- **Attachments** — written by Chainlit's S3 storage client (the conversation
  data layer's storage provider).
- **Access** — everything is served via **presigned URLs (7-day expiry)**; CORS
  is configured at startup so the browser can fetch them
  ([07-aws-services.md](07-aws-services.md)).
- Plots are deliberately kept **out** of the serialized Context (too large) —
  only their S3 references are persisted (in `plots_by_message`).

The knowledge-base **source** buckets are separate and covered in
[05-knowledge-bases.md](05-knowledge-bases.md).

## Session serialization round-trip

This is the deep version of the lifecycle summarized in
[08-frontend-and-ui.md](08-frontend-and-ui.md). The goal: a user can disconnect
and resume a thread with its memory, plans, and plots intact.

**What's in the `Context`:** the LlamaIndex workflow `Context` carries the event
state plus a `store` holding the turn's working data — `query`, `responses`,
`plan`, `last_agent_output`, and the conversation `memory_snapshot` /
`fact_block_facts`.

**Serialize (every successful turn + `on_chat_end`):**
1. `wf.flush_memory_to_context(ctx)` copies the in-process `Memory` (active
   messages + the `FactExtractionMemoryBlock` facts) into `ctx.store`, since
   memory lives outside the event state.
2. `ctx.to_dict(serializer=JsonSerializer())` produces a JSON-safe dict.
3. It's stored as `metadata['serialized_ctx']` on the thread.

**Deserialize (`on_chat_resume`):**
1. Build a fresh workflow, read `metadata['serialized_ctx']`.
2. `Context.from_dict(workflow=wf, data=ctx_dict, serializer=JsonSerializer())`.
3. Re-render past plots from `metadata['plots_by_message']` by re-fetching each
   figure from its presigned URL.

**Why custom objects survive:** `JsonSerializer` detects a `class_name` property
on an object and routes it through `to_dict()` / `from_dict()`. The project's
non-trivial objects implement exactly this:

| Object | Where | Serialization note |
|---|---|---|
| `Plan`, `Action` | [workflow_config/steps/orchestration/plan.py](../workflow_config/steps/orchestration/plan.py) | Round-trips via stored XML + action list |
| `ProcessedOutput` | [agents/processed_output.py](../agents/processed_output.py) | Delegates nested `AgentOutput`/elements to a sub-`JsonSerializer`; encodes graphs (Plotly `Figure` → JSON, S3-URL dicts pass through) |
| `MolView` | [data_sources/metabolomics_workbench/mwb/tools.py](../data_sources/metabolomics_workbench/mwb/tools.py) | Compound-structure element |

If any of these dropped their `class_name`/`to_dict`/`from_dict` members,
`Context` serialization would break and resuming a chat would fail — which is why
the [agent architecture](03-agent-architecture.md) and
[workflow](02-workflow.md) docs call those members load-bearing.

## What lives where — summary

| Data | Store | Key/Location |
|---|---|---|
| Chat history, threads, steps | DynamoDB (`DATA_LAYER_TABLE`) | Chainlit data layer |
| Per-message plans, plot refs, serialized context | DynamoDB | thread `metadata` |
| Feedback | DynamoDB (`FEEDBACK_TABLE`) | `FEEDBACK#…` + 3 GSIs |
| User accounts | DynamoDB (`APPROVED_/PENDING_USERS_TABLE`) | keyed by `user_email` |
| Plots & attachments | S3 (`CHAINLIT_STORAGE_BUCKET`) | `plots/<uuid>.{json,png}`, presigned URLs |
| Conversation memory (in-flight) | in-process `Memory` → flushed into serialized `Context` | `ctx.store` |
| KB source documents | S3 (separate buckets) | see [05-knowledge-bases.md](05-knowledge-bases.md) |
