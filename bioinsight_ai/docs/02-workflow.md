# The LlamaIndex Workflow

The chat backend is a single
[LlamaIndex Workflow](https://docs.llamaindex.ai/en/stable/module_guides/workflow/)
class, [`BioInsightWorkflow`](../bioinsight_workflow.py), with four
`@step`-decorated methods. One workflow instance lives per Chainlit session.

## Flow diagram

```
                       StartEvent (query)
                              │
                              ▼
                          ┌────────┐
                          │  plan  │  thinking_llm parses the query
                          └────────┘  and emits one of three shapes
                              │
            ┌─────────┬───────┼──────────┐
            ▼         ▼       ▼          ▼
        <answer>  <clarify> <plan>    (parse error)
            │         │       │          │
            ▼         ▼       ▼          ▼
        StopEvent  StopEvent  Plan    StopEvent
                               │      (default error msg)
                               ▼
                       ┌─────────────────┐
                       │  execute_plan   │
                       │                 │
                       │ For each Action:│
                       │  - lookup agent │
                       │  - run agent    │   (plotting runs here too,
                       │  - collect resp │    via the PlottingAgent)
                       └─────────────────┘
                               │
                        ┌──────┴──────┐
                        ▼             ▼
                   1 action,     N actions OR
                   no error      input-too-long
                        │             │
                        ▼             ▼
                   ConcludeEvent   ResponseEvent
                        │             │
                        │             ▼
                        │       ┌─────────────┐
                        │       │  synthesize │
                        │       │  llm.achat  │
                        │       └─────────────┘
                        │             │
                        ▼             ▼
                   ┌─────────────────────┐
                   │      conclude       │
                   │  persist to memory  │
                   └─────────────────────┘
                            │
                            ▼
                        StopEvent
```

## Workflow construction

[`BioInsightWorkflow.new_session`](../bioinsight_workflow.py) is the factory
called from [`bioinsight_session()`](../bioinsight_workflow.py) at the bottom
of the same file. It:

1. Instantiates `BioInsightWorkflow` with the four agents
   (`PlottingAgent`, `CancerResearchDataCommonsAgent`,
   `ProteomeExchangeAgent`, `MetabolomicsWorkbenchAgent`),
   the Bedrock LLM from `Settings.llm`, and a `PreSignedS3Client`.
2. Sets `timeout=600` and `verbose=True`.
3. Wires `llm` and `presigned_s3_client` into the `PlottingAgent` so it can
   stream LLM output and upload images.

The workflow is constructed once per Chainlit chat session in
[`@cl.on_chat_start`](../chainlit_app.py) and stored on `cl.user_session`.

## Two LLMs

Defined in [workflow_config/default_settings.py](../workflow_config/default_settings.py):

| LLM | Model | Settings | Used by |
|---|---|---|---|
| `Settings.llm` | `DEFAULT_MODEL` (Claude Sonnet 4.6 via Bedrock) | `max_tokens=15000`, `system_prompt_caching=True`, `tool_caching=True`, 1M-context beta header | All agent calls, synthesis step |
| `Settings.thinking_llm` | Same model | `max_tokens=20000`, `temperature=1.0`, `thinking={'type': 'enabled', 'budget_tokens': 2000}`, system prompt caching | The `plan` step only — uses Claude's extended thinking to choose which agents to call |

Both share the same Bedrock credentials and region from
[config.py](../config.py).

## Events

Defined in [workflow_config/events.py](../workflow_config/events.py):

| Event | Carries | Emitted by | Consumed by |
|---|---|---|---|
| `StartEvent` (LlamaIndex built-in) | `query: str` | `workflow.run(query=...)` caller | `plan` |
| `Plan` (in [plan.py](../workflow_config/steps/orchestration/plan.py)) | XML string + parsed `actions: List[Action]` | `plan` | `execute_plan` |
| `ResponseEvent` | (empty marker; data lives on `ctx.store`) | `execute_plan` (multi-action case) | `synthesize` |
| `ConcludeEvent` | (empty marker) | `execute_plan` (single-action case) and `synthesize` | `conclude` |
| `StopEvent` (LlamaIndex built-in) | `result: dict` (response, optional graph/elements) | `plan`, `conclude` (and error paths) | Caller |

`Plan` and `Action` implement `class_name`/`to_dict`/`from_dict` so they
survive `Context` serialization/deserialization across `on_chat_end` →
`on_chat_resume`. See [12-data-and-persistence.md](12-data-and-persistence.md).

## The `Plan` and `Action` objects

The orchestrator emits XML; `Plan.parse_xml` turns it into ordered `Action`
objects:

```xml
<plan>
  <action agent="MetabolomicsWorkbenchAgent" action_id="uuid-1">
    Look up the compound 'glucose' and return its KEGG ID.
  </action>
  <action agent="ProteomeExchangeAgent" action_id="uuid-2">
    Find PXD datasets that reference this compound.
  </action>
</plan>
```

Each `Action` has:
- `description`: the natural-language sub-task to hand the agent
- `agent_name`: which registered agent to invoke (validated against `agent_names`)
- `action_id`: UUID
- `status`: `ready` → `running` → `done` (or `failed`)

`Plan.to_tasklist()` converts the actions into a Chainlit `TaskList` so the
user sees each sub-task render and update in real time as
`execute_plan` works through it.

## Step 1: `plan`

Source: `BioInsightWorkflow.plan` in [bioinsight_workflow.py](../bioinsight_workflow.py)

**Input**: `StartEvent(query=...)`
**Output**: `Plan` | `StopEvent`

What it does:

1. Pulls the chat history from `Memory` via `get_chat_history()`, sanitizing
   any prior assistant messages to strip embedded code/image blobs.
2. Clears any old execution state on `ctx.store` (`responses`, `plan`,
   `last_agent_output`).
3. Calls `thinking_llm.achat(...)` with:
   - `ORCHESTRATION_SYSTEM_PROMPT` (from
     [workflow_config/steps/orchestration/prompts.py](../workflow_config/steps/orchestration/prompts.py))
   - the sanitized message history
   - an `ORCHESTRATION_TEMPLATE` filled with the user query and the
     registered agent schema (`AgentRegistry.agent_schema_str`)
4. Parses the response, looking for one of three wrapper tags:

   | Tag | Meaning | Returned event |
   |---|---|---|
   | `<answer>...</answer>` | Orchestrator can answer directly without calling agents | `StopEvent(result={"response": ...})` |
   | `<clarify>...</clarify>` | Orchestrator needs more information from the user | `StopEvent(result={"response": ...})` |
   | `<plan>...</plan>` | One or more agent actions to run | `Plan(...)` (also written to event stream) |

   When the response is a `<plan>`, the step builds a `Plan` and returns it
   to `execute_plan`. On parse failure, the workflow returns the default
   error `StopEvent` via `_handle_error()`.

   Plotting requests are handled within the plan as a regular action assigned
   to the `PlottingAgent` — there is no separate plot branch in this step.

The `thinking_llm`'s extended thinking content is logged but not surfaced to
the user.

## Step 2: `execute_plan`

Source: `BioInsightWorkflow.execute_plan` in [bioinsight_workflow.py](../bioinsight_workflow.py)

**Input**: `Plan`
**Output**: `ResponseEvent` | `ConcludeEvent` | `StopEvent`

For each `Action` in the plan, in order:

1. Mark the action `running`, push the updated `Plan` to the event stream
   (the Chainlit `TaskList` re-renders).
2. Look up the agent by name in `self.agents` (an
   [`AgentRegistry`](../agents/agent_registry.py)).
3. Format an `AGENT_PROMPT` (from
   [workflow_config/steps/execute_plan/prompts.py](../workflow_config/steps/execute_plan/prompts.py))
   with the user query and action description.
4. Run the agent under a [`Tracer`](../utils/tracing.py):
   - **Default path**: `agent.run(message, chat_history=...)`, streaming
     `ToolCall` and other events back to the UI via
     `ctx.write_event_to_stream(...)`.
   - **`PlottingAgent` special case**: if a previous action produced a
     `last_agent_output` on `ctx.store`, the workflow calls
     `agent.post_run_agent_output(last_agent_output, query=...)` directly
     instead of going through the streaming run, which avoids a Bedrock
     `ConverseStream` caching/validation issue triggered by re-streaming.
     If no prior output is found (e.g., PlottingAgent invoked first), it falls
     back to the standard streaming `agent.run()` path, and the LLM must parse
     the plotting request from the message text alone.
5. Validate the return is a [`ProcessedOutput`](../agents/processed_output.py),
   sanitize the response text, attach any `elements` and `graphs`, and append
   to `responses`.
6. On `is_input_too_long_error`, record a per-action error message and
   continue (rather than aborting the whole plan).

After the loop:

- **Single-action plan, no errors** → set `response = responses[0]` and emit
  `ConcludeEvent` (skip synthesis — there's nothing to synthesize).
- **Multi-action plan, or any input-too-long** → emit `ResponseEvent` to
  trigger the `synthesize` step.

## Step 3: `synthesize`

Source: `BioInsightWorkflow.synthesize` in [bioinsight_workflow.py](../bioinsight_workflow.py)

**Input**: `ResponseEvent`
**Output**: `ConcludeEvent` | `StopEvent`

Combines multiple agent responses into a single answer:

1. Reads `responses` and `query` from `ctx.store`.
2. Aggregates each response's `assistant` text, `elements`, and `graphs`
   into a `chat_info` dict.
3. Wraps each agent reply in `<response>...</response>` and renders the
   `SYNTHESIZE_TEMPLATE` (from
   [workflow_config/steps/synthesize.py](../workflow_config/steps/synthesize.py)).
4. Calls `llm.achat(...)` with `SYNTHESIZE_SYSTEM_PROMPT` + history +
   the templated user message.
5. Extracts the first `<answer>...</answer>` block from the LLM response.
6. Stores the result on `ctx.store` and emits `ConcludeEvent`.

If the LLM fails to produce an `<answer>` block, the response text is `None`
and an error is logged — `conclude` will store an empty answer in memory.

## Step 4: `conclude`

Source: `BioInsightWorkflow.conclude` in [bioinsight_workflow.py](../bioinsight_workflow.py)

**Input**: `ConcludeEvent`
**Output**: `StopEvent`

The terminator:

1. Reads `response` and `query` from `ctx.store`.
2. Calls `append_to_history(ctx, query, answer_text)` to persist the turn
   into `Memory` (which may trigger fact extraction if the token budget
   is exceeded).
3. Returns `StopEvent(result=response)` — this is what
   `@cl.on_message` receives and renders in the chat UI.

## Conversation memory

`BioInsightWorkflow` instantiates a LlamaIndex `Memory` object in
`__init__`:

```python
self.memory = Memory.from_defaults(
    session_id=session_id,
    token_limit=500_000,
    token_flush_size=50_000,
    memory_blocks=[
        FactExtractionMemoryBlock(
            name="condensed_conversation_history",
            llm=self.llm,
            max_facts=50,
            priority=0,
            fact_extraction_prompt_template=FACT_EXTRACTION_PROMPT,
            fact_condense_prompt_template=FACT_CONDENSE_PROMPT,
        ),
    ],
)
```

How it behaves:

- **Active messages** are kept verbatim up to the 500 K-token budget.
- When the budget is exceeded, the oldest 50 K tokens are flushed and passed
  to the `FactExtractionMemoryBlock`, which extracts up to 50 distilled
  facts using `FACT_EXTRACTION_PROMPT` (and condenses them with
  `FACT_CONDENSE_PROMPT` once `max_facts` is reached).
- Future LLM calls see both the active messages and the condensed fact list,
  so old context isn't lost — it's just compressed.

Prompts live in
[workflow_config/memory/prompts.py](../workflow_config/memory/prompts.py).

### Two history slices

| Method | Returns | Used for |
|---|---|---|
| `get_chat_history()` | All currently-active messages | Injected into orchestration and synthesis LLM calls |
| `get_agent_history()` | Last `agent_history_turns * 2` messages (default 2 turns = 4 messages) | Passed to individual agents during `execute_plan` to keep their token usage bounded |

### Memory persistence across sessions

`Memory` is in-process by default, so closing the chat would lose it.
`flush_memory_to_context()` and `load_memory_from_context()` solve that:

- `on_chat_end` calls `flush_memory_to_context(ctx)` before serializing
  `Context`, which dumps the active messages and the
  `FactExtractionMemoryBlock.facts` into `ctx.store`.
- `on_chat_resume` calls `load_memory_from_context(ctx)` after rehydrating
  `Context`, which loads them back.

The full serialization round-trip is described in
[12-data-and-persistence.md](12-data-and-persistence.md).

## Error handling

`_handle_error()` is the canonical error path. It:

1. Logs the exception with a step-specific prefix.
2. Calls `append_to_history(ctx, query, default_error_msg)` so the user's
   message and the apology are still persisted (otherwise the chat history
   would have an unanswered turn).
3. Returns `StopEvent(result={"response": <error message>})`, terminating
   the workflow gracefully.

`is_input_too_long_error()` distinguishes Bedrock context-overflow errors
from generic exceptions (searching for `ValidationException` with 'input is
too long' in the error message). In `execute_plan`, these errors are caught
per-action rather than aborting the whole run, so a too-long query against one
agent doesn't kill responses from the others. The workflow appends a
user-friendly message to responses suggesting the user rephrase their query,
then continues to synthesis (if multi-action) or conclusion (if single-action),
ensuring feedback is delivered even when the input exceeds the model's token limit.
