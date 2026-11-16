# Agent Architecture

This doc describes the **agent framework** — the base classes, the hooks every
agent implements, the shared output types, the registry, and the run handler.
It's about *how agents are built*, not *which agents exist*: for a catalog of
the four concrete agents (what data sources they connect to, their tools, and
their post-processing), see [04-agents.md](04-agents.md).

Every data source the chatbot can query is exposed as an agent. The
orchestrator (`plan` step) chooses one or more agents per query, and
`execute_plan` runs them (see [02-workflow.md](02-workflow.md)).

## Two base hierarchies

There are two flavors of agent, depending on whether the data source is a single
tool-calling agent or a multi-agent sub-workflow:

| Base class | Extends (LlamaIndex) | Concrete subclass | Used when |
|---|---|---|---|
| `BaseBioInsightAgent` | `FunctionAgent` | `BioInsightAgent` | A single ReAct/function-calling agent with a set of tools |
| `BaseBioInsightAgentWorkflow` | `AgentWorkflow` | `BioInsightAgentWorkflow` | A group of sub-agents that hand off to each other (e.g. the Metabolomics Workbench router) |

Both bases live in [agents/](../agents/):
- [base_bioinsight_agent.py](../agents/base_bioinsight_agent.py) / [bioinsight_agent.py](../agents/bioinsight_agent.py)
- [base_bioinsight_agent_workflow.py](../agents/base_bioinsight_agent_workflow.py) / [bioinsight_agent_workflow.py](../agents/bioinsight_agent_workflow.py)

Both are abstract (`ABC`) and require three things on every agent: a `name`, a
`description`, and implementations of two abstract methods — `generate_schema()`
and `post_run_agent_output()`. Both also define a shared
`DEFAULT_ERROR_RESPONSE` string.

## The agent contract

### `generate_schema() -> dict`

Produces the machine-readable description the **orchestrator** sees when
deciding which agent to call. For a `BioInsightAgent` it's:

```json
{ "name": "...", "description": "...",
  "tools": [ { "tool_name": "...", "tool_description": "..." }, ... ] }
```

For a `BioInsightAgentWorkflow` it nests each sub-agent's schema under
`"agents"` instead of `"tools"`. The registry aggregates all schemas into the
`agent_schema_str` JSON that gets injected into the orchestration prompt.

### `post_run_agent_output(output) -> ProcessedOutput`

The hook that runs **after** the agent's `run()` finishes. The framework's
`run()` yields a raw LlamaIndex `AgentOutput` (text + tool-call results); this
hook converts it into the project's [`ProcessedOutput`](#processedoutput),
where subclasses do domain-specific work — normalize text, add hyperlinks to
source databases, extract UI elements, attach Plotly graphs, etc. The default
implementation on `BioInsightAgent`/`BioInsightAgentWorkflow` is a passthrough
(`ProcessedOutput(agent_output=output)`); data-source agents override it.

## `ProcessedOutput`

Defined in [agents/processed_output.py](../agents/processed_output.py). It's a
**composition wrapper** around `AgentOutput` (deliberately *not* a subclass, to
avoid interfering with Pydantic validation). It adds three fields on top of the
wrapped output:

| Field | Purpose |
|---|---|
| `processed_response` | The post-processed answer text (preferred over the raw output when present) |
| `elements` | Extra UI elements extracted during processing |
| `graphs` | Visualizations — Plotly `Figure` objects **or** S3-URL reference dicts (`{"type": "plotly_url", "url": ..., "objectKey": ...}`) |

Unknown attribute access falls through to the wrapped `AgentOutput` via
`__getattr__`, so a `ProcessedOutput` behaves like the original output for
fields like `response` and `tool_calls`.

It implements `class_name` / `to_dict` / `from_dict` so it survives `Context`
serialization (chat resume). Graphs are encoded as Plotly JSON on the way out
and rebuilt with `pio.from_json` on the way back; S3-URL dicts pass through
unchanged. Nested `AgentOutput` and component-typed `elements` (e.g.
[`MolView`](../data_sources/metabolomics_workbench/)) are delegated to the
LlamaIndex `JsonSerializer`.

## `ProcessedWorkflowHandler` and the `run()` wrapper

Defined in [agents/processed_workflow_handler.py](../agents/processed_workflow_handler.py).

`BioInsightAgent.run()` (and the workflow variant) accept a `post_process` flag,
defaulting to `True`. When true, `run()` wraps the framework's `WorkflowHandler`
in a `ProcessedWorkflowHandler`. That wrapper:

- **delegates everything** to the underlying handler (including
  `stream_events()`, so streaming to the UI is unaffected), and
- **intercepts the awaited result**: when you `await` the handler, it runs the
  agent's `post_run_agent_output()` on the final `AgentOutput` and returns a
  `ProcessedOutput` instead.

This is why `execute_plan` can write `agent_output = await handler` and reliably
get a `ProcessedOutput`. A double-wrap guard prevents re-wrapping, and
`post_process=False` returns the raw framework handler.

## `AgentRegistry`

Defined in [agents/agent_registry.py](../agents/agent_registry.py). A Pydantic
model that holds the list of agents and is the orchestrator's view of "what
agents exist."

- **Unique-name validation** — rejects duplicate agent names at construction.
- **Dict-like access** — `registry["AgentName"]` and `registry.get(name)`.
- **`names()`** — list of agent names (used to validate the orchestration plan's
  `agent` attributes).
- **`add_agent()` / `remove_agent()`** — mutate and re-validate the registry.
- **`gather_agent_schemas()`** — builds `agent_schema` (list of dicts) and
  `agent_schema_str` (indented JSON). `agent_schema_str` is exactly what the
  `plan` step feeds the orchestration LLM.

`BioInsightWorkflow` constructs one registry from the four registered agents in
its `new_session` factory.

## The registered agents

`bioinsight_session()` registers four agents. Their base class determines which
hierarchy above they use; the full catalog (data sources, tools, post-processing)
is in [04-agents.md](04-agents.md).

| Agent | Base class |
|---|---|
| `CancerResearchDataCommonsAgent` | `BioInsightAgent` |
| `MetabolomicsWorkbenchAgent` | `BioInsightAgentWorkflow` (`MWBAgentWorkflow`) |
| `ProteomeExchangeAgent` | `BioInsightAgent` |
| `PlottingAgent` | `BioInsightAgent` |

The `PlottingAgent` is worth describing here as well, because it's the clearest
example of overriding the framework hooks.

## The `PlottingAgent`

Defined in [agents/plotting_agent_workflow.py](../agents/plotting_agent_workflow.py)
(the singleton instance is built in [agents/plotting_agent.py](../agents/plotting_agent.py)).
It's a `BioInsightAgent` subclass, but it behaves differently from the
data-source agents:

- **Injected dependencies** — it carries an `llm`, `presigned_s3_client`, and
  `logger` (all wired in by `new_session`), declared as pydantic-compatible
  fields. These enable LLM streaming, S3 image uploads, and structured logging.
- **Overridden `run()`** — sanitizes the incoming message and chat history
  (strips fenced code, large JSON/XML blobs) before delegating to the framework
  `run()`. This prevents non-string payloads from reaching the Bedrock
  `ConverseStream` path, which was triggering caching/validation errors.
- **Overridden `post_run_agent_output(output, query, attachments)`** — the real
  work. Signature:
  - `output`: The upstream agent's `ProcessedOutput` or `AgentOutput`.
  - `query`: User query string to contextualize plot generation.
  - `attachments`: Optional list of structured payloads extracted from output
    (format: `[{"type": "code"|"json"|"xml", "content": ...}, ...]`).

  Tries code attachments first (via `exec_plot_code`), then JSON/XML
  attachments (via `draw_graph`), then falls back to `draw_graph` on the
  original output text. Generated Plotly figures are uploaded to S3 through
  the presigned client and returned as S3-URL reference dicts. Result comes
  back as a `ProcessedOutput` carrying the `graphs`. The plotting helpers
  live in [utils/plotting_agent_helpers.py](../utils/plotting_agent_helpers.py).

Because of this, `execute_plan` **special-cases** the `PlottingAgent`: if a
prior agent output is available on `ctx.store`, the workflow calls
`post_run_agent_output(last_agent_output, query=...)` directly instead of the
streaming path (see [02-workflow.md](02-workflow.md) for full details). If no
prior output exists (e.g., PlottingAgent is the first action), it falls back to
the standard streaming `agent.run()` path. The plotting agent consumes another
agent's data rather than fetching data itself.
