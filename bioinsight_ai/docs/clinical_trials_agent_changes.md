# ClinicalTrials.gov Data Source Agent - Change Log

## Summary
Adds a `ClinicalTrialsAgent` backed by the ClinicalTrials.gov REST API v2 (https://clinicaltrials.gov/data-api/api).
It is modeled on the ProteomeXchange agent and uses the base `BioInsightAgent` (no custom subclass).

## New files
| File | Purpose |
|---|---|
| `bioinsight_ai/data_sources/clinical_trials/__init__.py` | Package marker |
| `bioinsight_ai/data_sources/clinical_trials/tools.py` | API helper functions and LlamaIndex `FunctionTool`s |
| `bioinsight_ai/data_sources/clinical_trials/agent.py` | Defines `agent = BioInsightAgent(name="ClinicalTrialsAgent", ...)` |
| `docs/clinical_trials_agent_changes.md` | This document |

## Endpoints covered (base URL `https://clinicaltrials.gov/api/v2`)
| Tool | Endpoint |
|---|---|
| `search_clinical_trials` | `GET /studies` (query.cond/intr/term/titles/outc/spons/locn/patient, filter.overallStatus/advanced/ids, fields, sort, pageSize, pageToken) |
| `get_clinical_trial` | `GET /studies/{nctId}` |
| `get_clinical_trials_metadata` | `GET /studies/metadata` |
| `get_clinical_trials_search_areas` | `GET /studies/search-areas` |
| `get_clinical_trials_enums` | `GET /studies/enums` |

## Design notes
- Uses `requests` (already a dependency); no new packages.
- Search returns a compact default field set to limit LLM context; callers can override `fields`.
- Responses over 30,000 characters are truncated with a hint to narrow the request.
- Errors (HTTP errors, 404, network) are returned as strings rather than raised, so the agent can report them.
- Search results (`search_clinical_trials`) are flattened into `{"data": [flat rows], "metadata": {totalCount, nextPageToken}}`
  (plot-ready columns, see below). Large pages drop whole rows instead of cutting JSON, so the output always stays valid JSON.
- Search row columns: `nct_id`, `title`, `status`, `start_date` (normalized to YYYY-MM-DD; month-only dates become the 1st),
  `start_year` (int), `primary_completion_date`, `lead_sponsor`, `conditions`, `study_type`, `phases`,
  `phase` (single label such as `PHASE2/PHASE3`, `NA` if missing), `enrollment` (int), `interventions` (names joined by `; `).
  Other requested fields keep leaf names (prefixed with their parent on collision). This makes scatter/bar/box/histogram
  plots (e.g. enrollment vs start_date colored by phase) work without extra parsing by the LLM-generated plotting code.
- No API key is required.

## Plotting agent compatibility
- `execute_plan` in `bioinsight_workflow.py` is agent-agnostic: it stores each agent's output in `ctx.store["last_agent_output"]`,
  and `PlottingAgent` consumes it via `draw_graph`, which parses each `tool_calls[i].tool_output.content`.
- The parser (`parse_response_content`) needs JSON with tabular `data` rows. Raw ClinicalTrials.gov output
  (`{"studies": [{"protocolSection": {...}}]}`) would have produced a single unusable column, hence the flattening above.
- `get_clinical_trial` (single study) still returns the raw nested record; it is intended for reading, not plotting.
- Limitation: plotting uses the *last* agent's output only, so a plan must put `PlottingAgent` immediately after `ClinicalTrialsAgent`.
- The metadata/search-areas/enums tools are now excluded from plotting via `aux_tools` in `draw_graph`
  (`utils/plotting_agent_helpers.py`, approved and applied), so they are never parsed as datasets.

## Changes to existing files (approved and applied)
1. `bioinsight_ai/bioinsight_workflow.py`
   - Added import: `from data_sources.clinical_trials.agent import agent as ct_agent`
   - Added `, ct_agent` to the `agents=[...]` list in `bioinsight_session`.
   - Effect: the agent appears in the planner's `AVAILABLE_AGENTS` / `AGENT_NAMES`, is valid in plans, and its output flows into `responses` and synthesis.
2. `bioinsight_ai/utils/plotting_agent_helpers.py`
   - Extended `aux_tools` in `draw_graph` with `get_clinical_trials_metadata`, `get_clinical_trials_search_areas`, `get_clinical_trials_enums`.
   - `exec_plot_code`: generated plotting code now runs in a single namespace (`exec(code, exec_ns)`) instead of separate
     globals/locals. Fixes `NameError` (e.g. `name 'colors' is not defined`) when top-level variables are used inside
     comprehensions/lambdas (seen with "scatter plot ... colored by phase"). The figure is taken from `exec_ns["fig"]`
     (falling back to any `go.Figure`), and a figure without traces is treated as "not produced" so the retry logic still triggers.
     Security note: no change in risk profile; code is still executed in-process via `exec` (sandboxing / AST allowlist not part of this change).

## Status
- [x] New package created
- [x] Registration in `bioinsight_workflow.py` (applied)
- [x] Plot-friendly output for search results
- [ ] Tests / end-to-end verification
- [ ] Tests / end-to-end verification
