# Architecture

## Component diagram

```
                                  ┌──────────────────────────────────────┐
                                  │              AWS                     │
                                  │                                      │
   ┌──────────┐                   │  Bedrock     DynamoDB    S3          │
   │ Browser  │                   │  (Claude,    (threads,  (plots,      │
   │          │                   │   Cohere,    feedback,   attachments,│
   └────┬─────┘                   │   3 KBs)     users)      KB sources) │
        │ HTTPS                   │                                      │
        ▼                         │  SES (transactional email)           │
   ┌─────────────────────────────────────────────────────────────────┐   │
   │                         Container (port 80)                    ▲│   │
   │                                                                ││   │
   │   ┌─────────────┐                                              ││   │
   │   │   Nginx     │ ── /                ─► Next.js (3000)        ││   │
   │   │ (port 80)   │ ── /chat            ─► Chainlit (8000) ──────┼┼───┤
   │   │             │ ── /api/auth, /api/admin ─► FastAPI (7000) ──┼┼───┤
   │   │             │ ── /admin           ─► Next.js (3000)        ││   │
   │   │             │ ── auth_request     ─► FastAPI (7000)        ││   │
   │   └─────────────┘                                              ││   │
   │                                                                ││   │
   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            ││   │
   │   │  Next.js    │  │   FastAPI   │  │  Chainlit   │            ││   │
   │   │  (3000)     │  │   (7000)    │  │   (8000)    │            ││   │
   │   │             │  │             │  │             │            ││   │
   │   │ - landing   │  │ - login     │  │ - chat UI   │            ││   │
   │   │ - login UI  │  │ - OAuth cb  │  │ - workflow  │────────────┘│   │
   │   │ - /admin    │  │ - JWT issue │  │ - agents    │             │   │
   │   │             │  │ - admin     │  │ - plotting  │             │   │
   │   └─────────────┘  └─────────────┘  └─────────────┘             │   │
   └─────────────────────────────────────────────────────────────────┘   │
                                  └──────────────────────────────────────┘
```

## Process layout

The Docker image runs four cooperating processes started by
[entrypoint.sh](../entrypoint.sh):

| Process | Listens on | Purpose | Code |
|---|---|---|---|
| **Nginx** | `0.0.0.0:80` | Reverse proxy, JWT auth gate, WebSocket upgrade | [nginx.conf](../nginx.conf) |
| **Chainlit** | `127.0.0.1:8000` (root path `/chat`) | Chat UI, LlamaIndex workflow runtime, FastAPI mounts | [chainlit_app.py](../chainlit_app.py) |
| **FastAPI auth backend** | `127.0.0.1:7000` | Login, Google OAuth callback, JWT issuance, user admin, internal `/auth/verify` and `/admin/verify` endpoints | [web_auth/main.py](../web_auth/main.py) |
| **Next.js frontend** | `127.0.0.1:3000` | Landing page, login form, admin panel | [frontend/](../frontend/) |

Only Nginx is exposed outside the container. The other three are reachable only
on the loopback interface, with all external traffic routed through Nginx.

`entrypoint.sh` traps `TERM`/`INT` to shut all four down cleanly, and exits if
disk usage on `/` exceeds 95% at startup.

## Chainlit startup checks

Before serving requests, [chainlit_app.py](../chainlit_app.py) runs two
module-level startup routines:

- **`validate_environment_configuration()`** — fails fast with a clear error
  if any required env var (`FEEDBACK_TABLE`, `DATA_LAYER_TABLE`,
  `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`,
  `CHAINLIT_STORAGE_BUCKET`) is missing.
- **S3 CORS configuration** — calls `configure_s3_cors()` (from
  [storage/s3_cors_config.py](../storage/s3_cors_config.py)) to set the
  allowed-origins CORS policy on the storage bucket so the browser can fetch
  presigned plot/attachment URLs, then verifies it with `verify_s3_cors()`.
  Allowed origins come from the `ALLOWED_CORS_ORIGINS` env var.

## Nginx routing

[nginx.conf](../nginx.conf) makes the routing decisions for incoming requests.
Highlights:

| Path | Routed to | Auth |
|---|---|---|
| `/` (exact) | redirect → `/login` | none |
| `/health` | FastAPI `/health` | none |
| `/login`, `/`, other | Next.js `:3000` | none |
| `/admin` | Next.js `:3000` | `auth_request /admin_check` (admin-only JWT) |
| `/api/auth/...` | FastAPI `:7000/auth/...` | none (login flow itself) |
| `/api/admin/...` | FastAPI `:7000/admin/...` | none (handler enforces) |
| `/chat`, `/chat/...` | Chainlit `:8000` | `auth_request /auth_check` |
| `/chat/ws` | Chainlit `:8000/chat/ws` (WebSocket) | `auth_request /auth_check` |
| `/auth_check`, `/admin_check` | FastAPI `:7000/auth/verify`, `/admin/verify` | internal-only |

The `auth_request` directive is the linchpin of the auth model: every
`/chat/*` request triggers a subrequest to FastAPI's `/auth/verify`, which
inspects the `token` cookie and returns 200 or 401. On 401, Nginx returns a
302 to `/login`. The same pattern guards `/admin` via `/admin/verify`.

WebSocket upgrades on `/chat/ws` are explicitly handled with `Upgrade` /
`Connection` headers and a 24-hour `proxy_read_timeout`, since Chainlit's
chat is WebSocket-driven.

## Auth model

A single JWT in the `token` cookie authenticates the user across all four
processes:

1. User hits `/login` (Next.js).
2. User submits credentials or completes Google OAuth → FastAPI
   ([auth_routes.py](../web_auth/auth_routes.py)) issues a signed JWT and
   sets it as the `token` cookie.
3. Subsequent requests to `/chat/*` or `/admin` carry the cookie.
4. Nginx's `auth_request` calls FastAPI's `/auth/verify`, which validates the
   JWT signature and returns 200/401.
5. If the request reaches Chainlit, Chainlit's `@cl.header_auth_callback`
   (in [chainlit_app.py](../chainlit_app.py)) decodes the *same*
   JWT itself to populate the `cl.User` object — so Chainlit knows who the
   user is without making its own auth call.

The JWT carries `sub` (user id), `full_name`, and `role`. Claims are signed
with `JWT_SECRET` using `JWT_ALGORITHM` (HS256). See
[09-auth.md](09-auth.md) for the full flow including OAuth and the
approved/pending user tables.

## Request lifecycle: a chat message

1. **Browser** sends a message over the WebSocket connection at
   `/chat/ws`.
2. **Nginx** runs `auth_request /auth_check`; if the JWT is valid, the
   message frame is forwarded to **Chainlit** on `:8000`.
3. **Chainlit's `@cl.on_message`** handler in [chainlit_app.py](../chainlit_app.py)
   receives the message, looks up the per-session
   [`BioInsightWorkflow`](../bioinsight_workflow.py) instance from the
   user session, and calls `workflow.run(query=...)`.
4. **The workflow** runs through its steps (see [02-workflow.md](02-workflow.md)).
   Each step writes intermediate events back to the chat UI via
   `ctx.write_event_to_stream(...)` — the user sees the orchestrator's plan
   render as a Chainlit `TaskList`, with each `Action` updating from
   `running` → `done` as the agents execute.
5. **Agent calls** go to **AWS Bedrock** (Claude Sonnet 4.6) for LLM
   inference, and to public biomedical APIs (GDC, PDC, MWB, ProteomeXchange,
   Ensembl) for data retrieval.
6. **If a plot is produced**, the [PlottingAgent](../agents/plotting_agent.py)
   uploads the rendered image to **S3** via
   [`PreSignedS3Client`](../storage/presigned_s3_client.py) and returns a
   presigned URL.
7. **The final answer** is returned from the workflow's `conclude` step.
   Chainlit renders the answer text, attaches any graphs/elements, and shows
   the feedback widget.
8. **The conversation turn** is persisted to **DynamoDB** via Chainlit's
   data layer ([data_layer_manager.py](../integrations/chainlit/on_feedback/data_layer_manager.py)).
   When the user clicks 👍 or 👎, the feedback handler
   ([feedback_handler.py](../integrations/chainlit/on_feedback/feedback_handler.py))
   writes a separate record to the feedback table.

## Session lifecycle in Chainlit

Chainlit's session lifecycle hooks in [chainlit_app.py](../chainlit_app.py)
manage the workflow instance:

| Hook | Role |
|---|---|
| `@cl.header_auth_callback` | JWT cookie → `cl.User` |
| `@cl.set_starters` | Suggested starter queries |
| `@cl.on_chat_start` | Create a new `BioInsightWorkflow`, store it on `cl.user_session` |
| `@cl.on_message` | Run the workflow against the user's query |
| `@cl.on_chat_end` | Flush workflow Memory to `ctx.store`, serialize `Context` to JSON, persist |
| `@cl.on_chat_resume` | Reload serialized `Context`, rehydrate workflow Memory |
| `@cl.on_stop` | User-initiated cancellation |
| `@cl.on_feedback` | Persist 👍/👎 to feedback table |
| `@cl.action_callback("logout")` | Clear session, redirect to login |

The `on_chat_end` / `on_chat_resume` pair is what lets a user close the
browser tab and come back later to a thread that still remembers what was
said. Memory contents (active messages plus the `FactExtractionMemoryBlock`
fact list) are flushed into the workflow `Context` store before
serialization, then loaded back on resume — see
[12-data-and-persistence.md](12-data-and-persistence.md) for the
serialization details.

## Configuration boundaries

| What | Loaded from | Read by |
|---|---|---|
| AWS credentials, region | `.env` (gitignored) | [config.py](../config.py) → all AWS clients |
| Bedrock model id | `DEFAULT_MODEL` env var | [workflow_config/default_settings.py](../workflow_config/default_settings.py) |
| DynamoDB table names | `DATA_LAYER_TABLE`, `FEEDBACK_TABLE`, `APPROVED_USERS_TABLE`, `PENDING_USERS_TABLE` | [chainlit_app.py](../chainlit_app.py), [web_auth/](../web_auth/) |
| Bedrock KB IDs | `MWB_KB_ID`, `PUBLICATIONS_KB_ID` | per-source RAG agents in [data_sources/](../data_sources/) |
| S3 bucket | `CHAINLIT_STORAGE_BUCKET` | [storage/presigned_s3_client.py](../storage/presigned_s3_client.py) |
| JWT secret + algorithm | `JWT_SECRET`, `JWT_ALGORITHM` | [chainlit_app.py](../chainlit_app.py), [web_auth/](../web_auth/) |
| Google OAuth | `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`, `OAUTH_GOOGLE_REDIRECT_URI` | [web_auth/auth_routes.py](../web_auth/auth_routes.py) |

A complete env var reference is in [11-configuration.md](11-configuration.md).
