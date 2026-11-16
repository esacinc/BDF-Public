# Frontend & UI

The product has **two** user-facing web layers behind Nginx:

- **Chainlit** (`/chat`) — the chat experience and the workflow runtime.
- **Next.js** (`/`, `/login`, `/admin`, …) — landing, login, password, and admin
  pages.

Nginx routes between them and enforces the JWT gate; the full routing table and
process layout are in [01-architecture.md](01-architecture.md).

## Chainlit chat UI

The chat UI is driven by the lifecycle hooks in
[chainlit_app.py](../chainlit_app.py). Their session/persistence roles are
tabled in [01-architecture.md](01-architecture.md); here's what they do from a
*UI* perspective:

- **`@cl.on_chat_start`** — immediately sends a startup **loader** element
  (`cl.CustomElement(name="loader")`) so the user sees progress while the
  workflow initializes, then shows the cached **opening message** with suggested
  action buttons.
- **`@cl.set_starters`** — defines the suggested starter prompts shown on an
  empty thread (e.g. "GBM Datasets in PDC", "Generate a Plot for Gene
  Expression…").
- **`@cl.on_message`** — the primary hook: runs the workflow and renders its
  output. Detailed flow in [The `on_message` flow](#the-on_message-flow) below.
- **`@cl.on_feedback`** — persists 👍/👎 to the feedback table.
- **`@cl.on_chat_end` / `@cl.on_chat_resume`** — serialize/restore the workflow
  `Context` so a reopened thread keeps its plots and memory.
- **`@cl.on_stop`**, **`@cl.action_callback("logout")`** — cancellation and
  logout.

### The `on_message` flow

`@cl.on_message` in [chainlit_app.py](../chainlit_app.py) is where a user message
becomes a rendered answer. The flow, in order:

1. **Concurrency guard** — a per-session `running` flag rejects overlapping
   requests; if one is already in flight, the user is told to wait.
2. **Setup** — restore logger context (thread/user), clear the previous plan,
   remove any leftover `TaskList` from a prior turn, and store the query.
3. **Loader** — send a "Thinking about your query…" loader element.
4. **Run the workflow** — `handler = wf.run(query=..., ctx=ctx)`; the handler is
   stored on the session so it can be cancelled on error.
5. **Stream events** — iterate `handler.stream_events()` and translate workflow
   events into UI updates (driven by the workflow in
   [02-workflow.md](02-workflow.md)):
   - `Action` → loader "Executing tasks…"
   - `Plan` → render it as a Chainlit **`TaskList`** and store it on the session
     (`current_plan`) for later linking and feedback.
   - `AgentStream` → map specific tool calls to friendly status text (e.g.
     schema-matching / harmonization / "Preparing dataset for download…"),
     de-duplicated via a `seen_agent_tools` set.
   - `ResponseEvent` → loader "Synthesizing results…"
   - `ConcludeEvent` → loader "Finalizing response…"
6. **Await the result** — `result = await handler`, then remove the loader.
7. **Snapshot context** — `flush_memory_to_context()` + store
   `serialized_ctx` so `on_chat_end` always has a complete snapshot to persist,
   even if a later step errors.
8. **Render graphs & elements** — branch on the result's shape and build a list
   of Chainlit elements plus a `graph_meta` dict for persistence:
   - `graph` / `graphs` — a list or single **S3 plot reference**
     (`{"type":"plotly_url","url":...,"objectKey":...}`); the figure JSON is
     fetched from the presigned URL via `_fig_from_url` and rendered as
     `cl.Plotly`. Raw Plotly `Figure` objects are also handled.
   - `graph_data` — an S3 dict, a figure dict, a JSON string, a base64 PNG
     (`cl.Image`), or a gzip+base64 Plotly blob.
   - `graph_path` — a path to a saved figure JSON, read and rendered.
   - `elements` — `MolView` objects → `cl.CustomElement(name="MolView", …)`.
9. **Extract & sanitize text** — pull `processed_response`/`response` and strip
   embedded JSON/code blocks (`wf._sanitize_assistant_content`) so raw Plotly
   JSON never shows in chat. If there's no text *and* no elements, send the
   default error and bail.
10. **Send the message** — `cl.Message(content=..., elements=...)` with
    `metadata = graph_meta`.
11. **Persist plot metadata** — write `plots_by_message[msg.id] = msg.metadata`
    into the thread metadata so plots **rehydrate on resume**
    (see [12-data-and-persistence.md](12-data-and-persistence.md)).
12. **Clear the `running` flag**, then `link_plan_to_message(...)` to associate
    the stored plan with the sent assistant message.

**Error path** — on any exception the handler removes the loader, calls
`handler.cancel_run()`, removes the `TaskList`, appends the failed exchange to
memory (so history stays complete), rebuilds a fresh `Context` while preserving
store state, clears the `running` flag, and sends the default error message.

### Session serialization & resume

A user can close a tab and reopen a thread later, and Chainlit reconnects
sessions across disconnects. To survive that, the **entire workflow `Context`
is serialized to the thread's DynamoDB metadata and restored on resume** — and a
fair amount of code exists purely to keep that round-trip from breaking the
conversation.

**When it serializes:**
- **Every successful turn** — `on_message` calls `wf.flush_memory_to_context(ctx)`
  then `ctx.to_dict(serializer=JsonSerializer())` and stores the result as
  `serialized_ctx`, so there's always a complete, current snapshot.
- **`@cl.on_chat_end`** — does the same as a top-up; Chainlit's disconnect
  handler then auto-persists the session (including `serialized_ctx`) into the
  thread metadata. A `ContextStateError` (workflow not running) is caught and
  skipped rather than clobbering the existing snapshot.

**When it deserializes — `@cl.on_chat_resume`:**
- Reconfigures the data layers, builds a fresh workflow, reads
  `metadata['serialized_ctx']`, and restores it with
  `Context.from_dict(workflow=wf, data=ctx_dict, serializer=JsonSerializer())`
  (starting fresh if none exists).

**Why there's so much supporting code:** the `Context` holds objects that aren't
natively JSON-serializable — the orchestration `Plan` and its `Action`s,
`ProcessedOutput` (which wraps a LlamaIndex `AgentOutput`), `MolView` elements,
and the conversation memory. To make them round-trip, each implements the
LlamaIndex `JsonSerializer` protocol — a `class_name` property plus
`to_dict()` / `from_dict()` (see [03-agent-architecture.md](03-agent-architecture.md)
and [02-workflow.md](02-workflow.md)). Specific tricky cases:

- **Graphs** — Plotly `Figure`s are encoded to JSON (rebuilt with
  `pio.from_json`); S3-URL reference dicts pass through unchanged.
- **Memory** — the in-process `Memory` (active messages + extracted facts) is
  flushed into / loaded from `ctx.store` via
  `flush_memory_to_context` / `load_memory_from_context`, since it lives outside
  the serialized event state.
- **Plots** — too large to keep in the `Context`, so they're uploaded to S3 and
  only **references** are persisted (in `metadata['plots_by_message']`, keyed by
  message ID). On resume, `on_chat_resume` re-fetches each figure from its
  presigned URL (`_fig_from_url`) and re-attaches it as a `cl.Plotly` element so
  past charts reappear.

The net effect: reopening a thread restores the conversation memory, the
per-message plans, and the rendered plots, so the flow continues uninterrupted.
Full serialization mechanics and the DynamoDB/S3 layout are in
[12-data-and-persistence.md](12-data-and-persistence.md).

### Chainlit integration modules

UI logic is organized under [integrations/chainlit/](../integrations/chainlit/):

**`on_chat_start/`** — session opening:
- [opening_message.py](../integrations/chainlit/on_chat_start/opening_message.py) —
  generates the welcome message with an **LLM** (it introduces BioInsight,
  reviews the registered agents/tools, and states capabilities + limitations),
  emits it as JSON with action buttons, and **caches** it for fast subsequent
  loads. Retries up to 3× if the LLM output isn't valid JSON.
- [salutation.py](../integrations/chainlit/on_chat_start/salutation.py),
  [greeting.py](../integrations/chainlit/on_chat_start/greeting.py),
  [cache.py](../integrations/chainlit/on_chat_start/cache.py) — read/write and
  deserialize the cached opening message into a Chainlit `Message`.
- [parse_examples.py](../integrations/chainlit/on_chat_start/parse_examples.py) —
  the pool of example queries the opening message may turn into action buttons.
- [suggested_query_callback.py](../integrations/chainlit/on_chat_start/suggested_query_callback.py) —
  registers an action callback per suggested query (using the query text as the
  action name so the thread gets a meaningful sidebar name on first click).

**`on_message/`** — [plan_storage.py](../integrations/chainlit/on_message/plan_storage.py)'s
`link_plan_to_message()` runs once at the end of `on_message`. The orchestration
plan was stashed on the session (`current_plan`) during event streaming; this
function finds the **last `assistant_message`** step in the thread, serializes
the plan to JSON (`plan.to_dict()`), and writes it into the thread metadata
keyed by that message ID — `metadata['plans'][message_id]` (plus a
`current_plan` pointer). Messages where the orchestrator answered without a plan
store `None`. This per-message record is what feedback reads back later.

**`on_feedback/`** — when the user clicks 👍/👎, `@cl.on_feedback` calls
`process_feedback(feedback, feedback_layer, conversation_layer)`
([feedback_handler.py](../integrations/chainlit/on_feedback/feedback_handler.py)).
Because the feedback callback has **no access to `cl.user_session`**, everything
is reconstructed by reading the conversation data layer:

1. **Collect** ([data_collector.py](../integrations/chainlit/on_feedback/data_collector.py)) —
   builds a `FeedbackData` (thread/message IDs, binary `rating` 0/1, comment,
   timestamp; model in [data_models.py](../integrations/chainlit/on_feedback/data_models.py))
   and enriches it from the thread's steps + metadata:
   - `extract_message_data` — the user + assistant message text and timestamps,
     computing a response time (mapping a `run` step to the following
     `assistant_message` when needed).
   - `extract_user_id` — from the thread's `userId`.
   - `extract_orchestration_plan` — reads back `metadata['plans'][message_id]`
     (the record `link_plan_to_message` wrote), so each feedback row carries the
     exact plan that produced the rated answer.
2. **Store** ([feedback_data_layer.py](../integrations/chainlit/on_feedback/feedback_data_layer.py)) —
   writes the record to the feedback DynamoDB table, with retry
   ([retry_utils.py](../integrations/chainlit/on_feedback/retry_utils.py)).
3. **Graceful degradation** — on failure it logs a minimal fallback record, and
   error messages are scrubbed of AWS credentials / user data before logging.

(Table schema and the `DataLayerManager` wiring are in
[07-aws-services.md](07-aws-services.md) / [12-data-and-persistence.md](12-data-and-persistence.md).)

### UI building blocks

- **Loader** — a custom element shown during startup and long operations
  (helper in [utils/chainlit_loader.py](../utils/chainlit_loader.py)).
- **Plan / TaskList** — the orchestrator's plan renders as a live task list.
- **Graphs** — Plotly figures (or presigned S3 image URLs) returned by agents.
- **Custom elements** — e.g. `MolView` molecule-structure views from the
  Metabolomics Workbench agent.
- **[chainlit.md](../chainlit.md)** — the Chainlit welcome-screen markdown.
- **[public/](../public/)** — static assets and custom-element definitions.
- **`.chainlit/`** — Chainlit project config (gitignored).

Chainlit's own auth is disabled; identity comes from the shared JWT cookie via
`@cl.header_auth_callback` (see [09-auth.md](09-auth.md)).

## Next.js frontend

A Next.js (App Router, TypeScript) app in [frontend/](../frontend/) serves
everything outside `/chat`:

| Route | Page | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Landing (redirects to `/login`) |
| `/login` | `app/login/` | Email/password + Google sign-in |
| `/auth` | `app/auth/` | OAuth callback handling |
| `/forgot-password`, `/change-password` | resp. dirs | Password flows |
| `/admin` | `app/admin/` | Admin panel (user approval) — gated to admin role |

- **[app/middleware.ts](../frontend/app/middleware.ts)** — a client-side JWT
  gate matching `/chat/*` and `/chainlit/*`: it reads the `token` cookie (or a
  query-param token for iframe embeds), redirects to `/login` if missing or
  expired. This complements Nginx's `auth_request` server-side gate.
- **Components** — shared `Button.tsx`, `FormField.tsx`; password helpers in
  `utils/passwordUtils.ts`.
- **Styling** — Tailwind CSS (`tailwind.config.js`, `styles/globals.css`).
- The frontend calls the FastAPI auth backend under `/api/auth/...` for login,
  registration, and OAuth (see [09-auth.md](09-auth.md)).

## Nginx (UI routing summary)

Nginx is the single public entrypoint (port 80). The UI-relevant routes:

- `/` and other non-`/chat`, non-`/api` paths → Next.js (`:3000`)
- `/chat`, `/chat/ws` → Chainlit (`:8000`), gated by `auth_request`
- `/admin` → Next.js, gated by an admin-role `auth_request`
- `/api/auth/...`, `/api/admin/...` → FastAPI (`:7000`)

Full routing and the `auth_request` mechanism are in
[01-architecture.md](01-architecture.md).
