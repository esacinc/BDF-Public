import asyncio
import ast
import json
import re
import uuid
from io import StringIO
import logging
from typing import List, Any, Dict, Optional

import pandas as pd
import plotly.graph_objects as go

from utils.transform import transform_wide_to_long
from utils.udi_helpers import build_heatmap_udi_spec, infer_heatmap_fields
from utils.tracing import Tracer

# llama_index ChatMessage objects expected by llm.achat
from llama_index.core.llms import ChatMessage

logger = logging.getLogger(__name__)


def flatten_km_data(data_obj, logger=None):
    """
    Converts nested survival JSON/dicts into a tidy DataFrame with 
    'time', 'survivalEstimate', 'censored', and 'group' columns.
    """
    log = logger or logging.getLogger(__name__)
    all_dfs = []
    
    # data_obj might be a list of strings, a dict, or a DataFrame with dicts
    items = []
    log.info("flatten_km_data: received data_obj of type %s", type(data_obj))
    if isinstance(data_obj, (list, tuple)):
        items = data_obj
    elif isinstance(data_obj, dict):
        items = [data_obj]
    elif isinstance(data_obj, pd.DataFrame):
        # Handle the case from logs: DataFrame with column 'group_1' containing dicts
        for col in data_obj.columns:
            for val in data_obj[col].dropna():
                if isinstance(val, dict):
                    # If the dict has a key like 'time', it's a single record
                    if "time" in val:
                        temp_df = pd.DataFrame([val])
                        temp_df['group'] = col
                        all_dfs.append(temp_df)
                    else:
                        # It might be a dict like {"group_name": [...list of records...]}
                        for group_label, records in val.items():
                            if isinstance(records, list):
                                temp_df = pd.DataFrame(records)
                                temp_df['group'] = group_label
                                all_dfs.append(temp_df)
        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
        return data_obj

    for item in items:
        if isinstance(item, pd.DataFrame):
            all_dfs.append(item)
            continue
        try:
            if isinstance(item, str):
                item = json.loads(item)
            
            if isinstance(item, dict):
                for group_name, records in item.items():
                    if isinstance(records, list):
                        temp_df = pd.DataFrame(records)
                        temp_df['group'] = group_name
                        all_dfs.append(temp_df)
        except Exception as e:
            log.warning(f"flatten_km_data: item skipped due to error: {e}")

    # return pd.concat(all_dfs, ignore_index=True) if all_dfs else data_obj
    result_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else data_obj

    # ============================================
    # NORMALIZE AND MAP COMMON ALIASES TO CANONICAL NAMES
    # ============================================
    # Defensive: ensure result is a DataFrame
    if not isinstance(result_df, pd.DataFrame):
        try:
            log.warning("flatten_km_data: result is not a DataFrame, attempting to convert. Type: %s", type(result_df))
            result_df = pd.DataFrame(result_df)
        except Exception:
            log.warning("flatten_km_data: failed to convert result to DataFrame")
            return result_df

    # Normalize column names
    result_df.columns = [str(c).lower() for c in result_df.columns]

    # Map common aliases to canonical names
    alias_map = {
        'survivalestimate': ['survivalestimate', 'survival_estimate', 'survivalprob', 'survival_prob', 'surv'],
        'time': ['time', 'time_days', 'days', 'followup_time'],
        'submitter_id': ['submitter_id', 'submitterId', 'id', 'case_id', 'caseid']
    }
    # Try to rename found aliases
    for canonical, candidates in alias_map.items():
        for c in candidates:
            if c in result_df.columns and c != canonical:
                result_df = result_df.rename(columns={c: canonical})
                break

    return result_df


def is_base64_image_string(s: str) -> bool:
    """
    Lightweight check if a string looks like base64-encoded image data (prefix heuristics).
    """
    if not isinstance(s, str) or len(s) < 100:
        return False
    base64_headers = [r"^iVBOR", r"^/9j/", r"^R0lGOD", r"^Qk"]
    return any(re.match(p, s) for p in base64_headers)

async def parse_response_content(response, index: int = 0, logger: logging.Logger | None = None):
    """
    Portable parsing helper: convert a tool_call output into a pandas.DataFrame or None.
    Mirrors the logic in the original workflow but kept independent for reuse by the plotting agent.
    """
    log = logger or logging.getLogger(__name__)

    # Accept either:
    #  - the full response object (with .tool_calls[index])
    #  - a single tool_call-like object (has .tool_output)
    #  - a raw string payload
    raw_content = ""
    try:
        if index is None and hasattr(response, "tool_output"):
            raw_content = getattr(response, "tool_output").content
        elif isinstance(response, (str, bytes)):
            raw_content = response
        else:
            # default: assume response is the full response container with .tool_calls
            raw_content = response.tool_calls[index].tool_output.content
        if raw_content is None:
            raw_content = ""
        raw_content = raw_content.strip()
    except Exception as e:
        log.exception("parse_response_content: couldn't access content: %s", e)
        return None

    log.debug("parse_response_content: preview=%s", repr(raw_content)[:200])

    if is_base64_image_string(raw_content):
        log.info("parse_response_content: Detected pre-rendered base64 image.")
        return {"_is_pre_rendered_image": True, "data": raw_content}

    # Try JSON first (most robust), then ast.literal_eval, then fallbacks.
    parsed_object = None
    try:
        parsed_object = json.loads(raw_content)
        log.debug("parse_response_content: json.loads success: %s", type(parsed_object))
    except Exception:
        try:
            parsed_object = ast.literal_eval(raw_content)
            log.debug("parse_response_content: ast.literal_eval success: %s", type(parsed_object))
        except Exception as e:
            log.debug("parse_response_content: ast literal eval failed: %s", e)

    # If parsed_object is None and raw_content looks like a python repr of a dict-of-columns
    if parsed_object is None:
        # Last-ditch: try to read as newline-delimited JSON or a simple list
        try:
            return await asyncio.to_thread(pd.read_json, StringIO(raw_content))
        except Exception:
            log.debug("parse_response_content: fallback read_json failed")
            log.error("parse_response_content: all parse attempts failed for index=%s", index)
            return None

    # === Handle dict-like payloads ===
    try:
        # Detect pre-uploaded plot metadata (from tools that upload figures to S3 and return a small dict)
        if isinstance(parsed_object, dict):
            if ("url" in parsed_object) and ("format" in parsed_object or "objectKey" in parsed_object or "type" in parsed_object):
                # Return a sentinel dict to indicate this is a pre-uploaded plot descriptor
                return {
                    "_is_preuploaded_plot": True,
                    "format": parsed_object.get("format") or parsed_object.get("type"),
                    "url": parsed_object.get("url"),
                    "objectKey": parsed_object.get("objectKey"),
                    "artifacts": parsed_object.get("artifacts"),
                }

        # Special-case: dict mapping group names to list-of-records (e.g., {"group_1": [{...}, {...}]})
        # Many tools (including GDC helpers) return this shape for KM data. Expand into a tidy DataFrame.
        if isinstance(parsed_object, dict):
            try:
                # detect dict-of-lists-of-dicts
                if any(isinstance(v, list) and all(isinstance(r, dict) for r in v) for v in parsed_object.values()):
                    all_parts = []
                    for group_name, records in parsed_object.items():
                        if isinstance(records, list):
                            try:
                                temp_df = pd.DataFrame(records)
                                temp_df['group'] = group_name
                                all_parts.append(temp_df)
                            except Exception:
                                # fallback: skip problematic group
                                continue
                    if all_parts:
                        return pd.concat(all_parts, ignore_index=True)
            except Exception:
                # non-fatal; continue with other parsing attempts
                pass
        # Case A: wrapper with 'data' or 'data_matrix' keys (common from MCP / PDC)
        if isinstance(parsed_object, dict):
            # Special-case: dict mapping group names to list-of-dict records,
            # e.g. {"group_1": [{...}, {...}], "group_2": [{...}]}
            # Convert to a tidy concatenated DataFrame with a 'group' column.
            try:
                values = parsed_object.values()
                if values and all(isinstance(v, list) for v in values) and any(any(isinstance(el, dict) for el in v) for v in values):
                    all_dfs = []
                    for group_name, records in parsed_object.items():
                        if isinstance(records, list) and any(isinstance(el, dict) for el in records):
                            try:
                                temp_df = pd.json_normalize(records)
                                temp_df['group'] = group_name
                                all_dfs.append(temp_df)
                            except Exception:
                                # skip problematic group
                                continue
                    if all_dfs:
                        return pd.concat(all_dfs, ignore_index=True)
            except Exception:
                # fall through to other handlers
                pass
            # 'data' -> list of dict rows
            if "data" in parsed_object and isinstance(parsed_object["data"], list):
                df = pd.json_normalize(parsed_object["data"])
                # If metadata present, attach as columns (broadcast small scalars)
                meta = parsed_object.get("mdata") or parsed_object.get("meta") or parsed_object.get("metadata")
                if isinstance(meta, dict):
                    for k, v in meta.items():
                        if not isinstance(v, list):
                            df[k] = v
                return df

            # 'data_matrix' -> records or empty
            if "data_matrix" in parsed_object and isinstance(parsed_object["data_matrix"], list):
                try:
                    return pd.json_normalize(parsed_object["data_matrix"])
                except Exception:
                    return pd.DataFrame(parsed_object["data_matrix"])

            # Case B: dict of columns where values are dicts {index: value}
            if parsed_object and all(isinstance(v, dict) for v in parsed_object.values()):
                # convert each inner dict to a Series then build DataFrame (align on inner keys)
                ser_map = {col: pd.Series(v) for col, v in parsed_object.items()}
                return pd.DataFrame(ser_map)

            # Generic dict -> try direct DataFrame construction (may work for column->list)
            try:
                return pd.DataFrame(parsed_object)
            except Exception as e:
                log.debug("parse_response_content: pd.DataFrame(dict) failed: %s", e)

        # === Handle list-of-dicts (records) ===
        if isinstance(parsed_object, list):
            return pd.DataFrame(parsed_object)

        # === Handle tuple that contains JSON string as first element ===
        if isinstance(parsed_object, tuple) and len(parsed_object) > 0 and isinstance(parsed_object[0], str):
            return await asyncio.to_thread(pd.read_json, StringIO(parsed_object[0]), orient="records")
    except Exception as e:
        log.debug("parse_response_content: post-parse handling failed: %s", e)

    log.error("parse_response_content: all parse attempts failed for index=%s", index)
    return None


def sanitize_llm_code(code: str) -> str:
    """
    Remove markdown fences, numeric lists, and extra noise from LLM generated code.
    """
    if not isinstance(code, str):
        return ""
    code = re.sub(r"```(?:python)?", "", code, flags=re.IGNORECASE)
    code = re.sub(r"```", "", code)
    cleaned_lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if re.match(r"^(\d+[\.\)]|[-*•])\s", stripped):
            continue
        if re.search(r"[✓✔❌✅📊📈📉]", stripped):
            continue
        if re.match(r"^(Note|Tip|Explanation|Remember|Make sure|Always|Ensure)\b", stripped, re.IGNORECASE):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()

    # Defensive: drop any trailing conversational text that may have been appended
    # by the LLM (e.g., "Human: ...", "Provide the full code...").
    if not cleaned:
        return ""

    lines = cleaned.splitlines()

    # If a speaker label appears (e.g., 'Human:' or 'Assistant:'), cut there
    for i, l in enumerate(lines):
        if re.match(r"^[A-Za-z]{2,20}:\s", l):
            lines = lines[:i]
            break

    # Identify last line that looks like code. Keep up to that line.
    code_like_re = re.compile(r"\b(import|from|def|class|for|while|if|elif|else|return|with|try|except|assert|fig\b|pd\.|np\.|go\.|plt\.|=|\(|\)|\[|\]|\{|\}|\.|,|:\s*$)")
    last_code_idx = -1
    for i, l in enumerate(lines):
        if code_like_re.search(l):
            last_code_idx = i

    if last_code_idx >= 0:
        lines = lines[: last_code_idx + 1 ]

    return "\n".join(lines).strip()


def _balance_code_brackets(code: str) -> str:
    """Append closing brackets/parentheses/braces if unbalanced to reduce SyntaxError from truncated LLM output."""
    if not isinstance(code, str) or not code:
        return code
    opens = {'(': code.count('('), '[': code.count('['), '{': code.count('{')}
    closes = {')': code.count(')'), ']': code.count(']'), '}': code.count('}')}
    append = []
    if opens['('] > closes[')']:
        append.append(')' * (opens['('] - closes[')']))
    if opens['['] > closes[']']:
        append.append(']' * (opens['['] - closes[']']))
    if opens['{'] > closes['}']:
        append.append('}' * (opens['{'] - closes['}']))
    if append:
        try:
            logger.debug("_balance_code_brackets: appending closers: %s", ''.join(append))
        except Exception:
            pass
        return code + '\n' + ''.join(append)
    return code


# --------------------
# New helpers for validating requested plot type and produced figure
# --------------------
def detect_requested_plot_type(query: str) -> str | None:
    """
    Very small heuristic extractor for requested plot type from user query.
    Returns a lowercase canonical type like 'violin', 'box', 'heatmap', 'scatter', 'bar', 'line', 'pie', 'histogram'
    or None if no clear request found.
    """
    log = logger or logging.getLogger(__name__)
    log.debug("detect_requested_plot_type: analyzing query: %s of type %s", query, str(type(query)))

    if not isinstance(query, str):
        return None
    q = query.lower()
    mapping = {
        # montage and interactive/scrollable/slider-style viewer
        "montage": "montage",
        "montage of": "montage",
        "slider": "slider",
        "slice": "slider",
        "slice slider": "slider",
        "slice-slider": "slider",
        "scroll": "slider",
        "viewer": "slider",
        "ohif": "slider",
        "violin": "violin",
        "box": "box",
        "boxplot": "box",
        "heatmap": "heatmap",
        "heat map": "heatmap",
        "scatter": "scatter",
        "scatterplot": "scatter",
        "bar": "bar",
        "bar chart": "bar",
        "stacked bar": "stacked_bar",
        "stacked_bar": "stacked_bar",
        "line": "line",
        "lineplot": "line",
        "hist": "histogram",
        "histogram": "histogram",
        # Added pie/donut synonyms
        "pie": "pie",
        "pie chart": "pie",
        "piechart": "pie",
        "donut": "pie",
        "donut chart": "pie",
        "donutchart": "pie",
    }
    for k, v in mapping.items():
        if k in q:
            logger.debug("detect_requested_plot_type: detected plot type '%s' from query", v)
            return v
    # Additional heuristics if none of previous worked
    query = query.lower()
    if any(word in query for word in ["heatmap", "matrix", "density map"]):
        return "heatmap"
    if any(word in query for word in ["km", "kaplan", "survival"]):
        return "km"
    if any(word in query for word in ["pie", "donut"]):
        return "pie"
    if any(word in query for word in ["violin", "distribution"]):
        return "violin"
    if any(word in query for word in ["box", "whisker"]):
        return "box"
    if "stacked" in query and "bar" in query:
        return "stacked_bar"
    if "bar" in query:
        return "bar"
    if any(word in query for word in ["scatter", "bubble"]):
        return "scatter"
    # return "line" # Default    

    return None


def select_best_dataset_for_plot_type(valid_datasets: List[tuple], plot_type: str | None, logger: logging.Logger | None = None) -> tuple:
    """
    Intelligently select the best dataset from multiple options based on plot type requirements.
    Scores datasets by presence of relevant columns and absence of irrelevant columns.

    Args:
        valid_datasets: List of (index, DataFrame) tuples from parse_response_content
        plot_type: The requested plot type (e.g., 'pie', 'km', 'scatter', etc.)
        logger: Optional logger instance

    Returns:
        Tuple of (best_dataset_index, best_dataset_dataframe)
    """
    log = logger or logging.getLogger(__name__)

    if not valid_datasets:
        return 0, None

    if len(valid_datasets) == 1:
        return 0, valid_datasets[0][1]

    # Define column preferences for each plot type
    # Format: (preferred_cols, avoid_cols) - higher weights on preferred columns
    plot_type_requirements = {
        "pie": (
            ["gender", "age", "race", "ethnicity", "age_at_diagnosis", "diagnosis", "stage", "grade", "category", "type"],
            ["tumor_grade", "tumor_stage", "morphology", "primary_diagnosis", "aliquot", "sample_type"]
        ),
        "km": (
            ["time", "survivalestimate", "survival_prob", "days", "status", "event", "group"],
            ["gender", "age_at_diagnosis", "race", "ethnicity"]
        ),
        "heatmap": (
            ["gene", "protein", "sample", "case", "aliquot", "expression", "value"],
            []
        ),
        "violin": (
            ["expression", "value", "gene", "protein", "category", "group"],
            []
        ),
        "scatter": (
            ["expression", "value", "sample", "case"],
            []
        ),
        "bar": (
            ["category", "count", "frequency", "group"],
            []
        ),
    }

    best_dataset_idx = 0
    best_score = -float('inf')
    scores_debug = []

    for dataset_pos, (orig_idx, dataset) in enumerate(valid_datasets):
        score = 0
        if isinstance(dataset, pd.DataFrame):
            df_cols_lower = [str(c).lower() for c in dataset.columns]

            # Get plot type requirements
            if plot_type in plot_type_requirements:
                preferred, avoid = plot_type_requirements[plot_type]
            else:
                # Default: prefer datasets with more columns (more complete data)
                preferred, avoid = [], []

            # Score based on preferred columns (higher weight)
            for col in preferred:
                if col in df_cols_lower:
                    score += 3

            # Penalize datasets with many avoid columns
            for col in avoid:
                if col in df_cols_lower:
                    score -= 2

            # Bonus for dataset completeness (fewer null values)
            null_ratio = dataset.isnull().sum().sum() / (dataset.shape[0] * dataset.shape[1])
            score += (1 - null_ratio)

            # Store debug info
            pref_match = sum(1 for col in preferred if col in df_cols_lower)
            avoid_match = sum(1 for col in avoid if col in df_cols_lower)
            scores_debug.append({
                'pos': dataset_pos,
                'cols': len(df_cols_lower),
                'pref_match': pref_match,
                'avoid_match': avoid_match,
                'score': score
            })

            if score > best_score:
                best_score = score
                best_dataset_idx = dataset_pos

    if best_dataset_idx > 0:
        log.info(
            f"select_best_dataset_for_plot_type: Selected dataset at position {best_dataset_idx} for plot type '{plot_type}'. "
            f"Scores: {scores_debug}"
        )
    else:
        log.debug(
            f"select_best_dataset_for_plot_type: Dataset 0 is best for plot type '{plot_type}'. "
            f"Scores: {scores_debug}"
        )

    return best_dataset_idx, valid_datasets[best_dataset_idx][1]


def validate_figure_matches_type(fig: go.Figure, plot_type: str)-> tuple[bool, list[str]]:
    """
    Lightweight validation: inspect fig.data traces for expected trace types.
    Returns (bool, list_of_detected_types).
    """
    log = logger or logging.getLogger(__name__)

    if fig is None or plot_type is None:
        return True, []
        
    trace_types = []
    try:
        for t in fig.data:
            t_type = getattr(t, "type", None) or t.__class__.__name__.lower()
            trace_types.append(str(t_type).lower())
        
        # Mapping of expected strings for validation
        is_valid = False
        if plot_type == "violin":
            is_valid = any("violin" in tt for tt in trace_types)
        elif plot_type == "box":
            is_valid = any("box" in tt for tt in trace_types)
        elif plot_type == "heatmap":
            is_valid = any("heatmap" in tt for tt in trace_types)
        elif plot_type == "scatter":
            is_valid = any("scatter" in tt for tt in trace_types)
        elif plot_type == "bar":
            is_valid = any("bar" in tt for tt in trace_types)
        elif plot_type == "line":
            is_valid = any("scatter" in tt or "line" in tt for tt in trace_types)
        elif plot_type == "montage":
            # Montage validation: accept multiple heatmap/image traces arranged as subplots
            try:
                is_heatmap_like = any("heatmap" in tt or "image" in tt or "imshow" in tt for tt in trace_types)
                is_valid = is_heatmap_like or (len(trace_types) > 1)
            except Exception:
                is_valid = False
        elif plot_type == "slider":
            # Slider-style viewer validation: accept if figure has frames or layout.sliders or updatemenus
            try:
                has_frames = hasattr(fig, "frames") and len(getattr(fig, "frames", [])) > 0
                has_sliders = hasattr(fig.layout, "sliders") and len(getattr(fig.layout, "sliders", [])) > 0
                has_updatemenus = hasattr(fig.layout, "updatemenus") and len(getattr(fig.layout, "updatemenus", [])) > 0
                # Accept slider-like figures OR simple montages composed of multiple heatmap/image traces
                has_image_traces = any("heatmap" in tt or "image" in tt for tt in trace_types)
                is_valid = bool(has_frames or has_sliders or has_updatemenus or (has_image_traces and len(trace_types) > 1))
            except Exception:
                is_valid = False
        elif plot_type == "pie" or plot_type == "donut":
            is_valid = any("pie" in tt for tt in trace_types)
        elif plot_type == "histogram":
            is_valid = any("histogram" in tt or "hist" in tt for tt in trace_types)
        else:
            is_valid = True # Default to True if type is unknown
        
        log.debug(f"validate_figure_matches_type: valid: {is_valid}, trace_types: {trace_types}")
        return is_valid, trace_types
    except Exception as e:
        log.error(f"validate_figure_matches_type Exception occured: {e}")
        return False, trace_types


async def exec_plot_code(code: str, context: dict | None, presigned_s3_client, logger: logging.Logger | None = None):
    """
    Execute python code expected to produce a Plotly Figure named `fig`.
    Upload resulting plot JSON to S3 using presigned_s3_client and return metadata dict.

    Returns dict that includes the produced Figure in key 'figure' and S3 metadata
    as 'url' and 'objectKey' so callers can validate the figure before returning URLs.
    """
    log = logger or logging.getLogger(__name__)
    logger.debug("exec_plot_code: received code of type: %s", repr(code))
    # Single namespace (globals only): names defined by the generated code at top level must be visible
    # inside its comprehensions, lambdas and helper functions (separate locals would cause NameError).
    exec_ns = {"go": go, "__name__": "__plot_exec__", **(context or {})}
    # Execute with small auto-repair attempts for common truncation errors (unclosed parens/brackets)
    max_attempts = 3
    attempt = 0
    last_err = None
    code_to_exec = code
    while attempt < max_attempts:
        try:
            exec(code_to_exec, exec_ns)
            log.debug("exec_plot_code: code executed successfully on attempt %s, namespace keys: %s", attempt, list(exec_ns.keys()))
            log.debug("exec_plot_code: namespace preview: %s", {k: str(type(v)) for k, v in exec_ns.items() if isinstance(v, (go.Figure, pd.DataFrame))})
            log.debug("exec_plot_code: code %s", code_to_exec)
            last_err = None
            break
        except SyntaxError as se:
            last_err = se
            msg = str(se)
            log.debug("exec_plot_code: SyntaxError on attempt %s: %s", attempt, msg)
            # Heuristic: if error indicates unclosed bracket/parenthesis or unexpected EOF, try appending closers
            if any(tok in msg for tok in ("was never closed", "EOL while scanning string literal", "unexpected EOF while parsing", "EOF")):
                # append balanced closers and retry
                code_to_exec = _balance_code_brackets(code_to_exec)
                attempt += 1
                continue
            else:
                # Not a truncation-related SyntaxError: re-raise
                log.exception("exec_plot_code: non-recoverable SyntaxError: %s", se)
                raise
        except Exception as e:
            last_err = e
            error_type = type(e).__name__
            error_msg = str(e)
            log.error("exec_plot_code: execution failed on attempt %s: %s: %s", attempt, error_type, error_msg)
            log.debug("exec_plot_code: failed code was:\n%s", code_to_exec)
            # Do not attempt to auto-fix non-syntax exceptions
            raise

    if last_err is not None:
        # All attempts failed; raise the last exception
        raise last_err

    fig = exec_ns.get("fig") if isinstance(exec_ns.get("fig"), go.Figure) else next(
        (v for v in exec_ns.values() if isinstance(v, go.Figure)), None
    )
    log.debug("exec_plot_code: detected fig: %s", fig)
    # The caller pre-seeds an empty `fig` default; treat a figure without traces as "not produced"
    if fig is None or len(fig.data) == 0:
        raise TypeError("exec_plot_code: No plotly.graph_objects.Figure object named `fig` was produced by executed code")

    # Tweak layout to be sized reasonably
    try:
        num_traces = max(1, len(fig.data))
        estimated_height = 400 + (150 * (num_traces // 3 or 1))
        fig.update_layout(
            autosize=True,
            height=min(900, estimated_height),
            width=1200,
            margin=dict(l=40, r=40, t=80, b=60),
        )
    except Exception:
        # Non-fatal
        log.debug("exec_plot_code: failed to update layout safely, continuing")

    fig_json = fig.to_json().encode("utf-8")
    object_key = f"plots/{uuid.uuid4()}.json"

    try:
        upload_result = await presigned_s3_client.upload_file(object_key=object_key, mime="application/json", data=fig_json)
        s3_url = upload_result["url"]
    except Exception as e:
        log.warning("exec_plot_code: S3 upload failed: %s, falling back to local save", e)
        local_path = f"/tmp/{object_key.split('/')[-1]}"
        with open(local_path, "wb") as fh:
            fh.write(fig_json)
        s3_url = f"file://{local_path}"

    log.info("exec_plot_code: uploaded plot to %s", s3_url)
    log.debug("exec_plot_code: returning figure and metadata: url=%s, object_key=%s, type=plotly", s3_url, object_key)
    # Return both figure and metadata (backward-compatible keys present)
    return {"figure": fig, "type": "plotly", "format": "json", "objectKey": object_key, "url": s3_url}

async def draw_graph_two_datasets(response, query: str, indices: List[int], llm: Any, presigned_s3_client, logger: logging.Logger | None = None):
    """
    Parse two datasets from `response` (using indices) and generate a plot.
    This function follows the original flow: request code from llm, reflect, sanitize, execute.
    Returns a plotly Figure (or -1 on error).
    """
    log = logger or logging.getLogger(__name__)
    tracer = Tracer(label="draw_graph_two_datasets")

    if llm is None:
        log.error("draw_graph_two_datasets: llm is None")
        return -1

    try:
        log.debug("draw_graph_two_datasets: starting to parse datasets at indices %s", indices)
        async with tracer.async_step("parse_response_content_1"):
            df1 = await parse_response_content(response, index=indices[0], logger=log)
        async with tracer.async_step("parse_response_content_2"):
            df2 = await parse_response_content(response, index=indices[1], logger=log)
    except Exception as final_e:
        log.warning("draw_graph_two_datasets: parsing failed: %s", final_e)
        return None

    if df1 is None or df2 is None:
        log.error("draw_graph_two_datasets: one or both DataFrames could not be parsed.")
        return -1

    if len(df1.index) < 1 or len(df2.index) < 1:
        log.debug("draw_graph_two_datasets: empty dataframe(s).")
        return -1

    head1 = str(df1.head().to_dict())
    head2 = str(df2.head().to_dict())
    desc1 = str(df1.describe().to_dict())
    desc2 = str(df2.describe().to_dict())
    cols1 = str(df1.columns.to_list())
    cols2 = str(df2.columns.to_list())
    dtype1 = str(df1.dtypes.to_dict())
    dtype2 = str(df2.dtypes.to_dict())

    log.debug("draw_graph_two_datasets: df1 cols=%s, dtypes=%s, desc=%s; df2 cols=%s, dtypes=%s desc=%s", cols1, dtype1,desc1, cols2, dtype2, desc2)
    final_query = f"""The dataframe names are 'df1' and 'df2'. 
            df1 has the columns {cols1} and their datatypes are {dtype1}. 
            df2 has the columns {cols2} and their datatypes are {dtype2}. 
            df1 is in the following format: {desc1}. The head of df1 is: {head1}.
            df2 is in the following format: {desc2}. The head of df2 is: {head2}.
            You cannot use data_frame.info() or any command that cannot be printed. 
            Do not use print() in the generated code. 
            Always name the graph object as fig. Do not do fig.show()
            Use plotly for any graphing or drawing commands.
            Write python code using plotly for graphs for this query on the dataframes df1 and df2: {query}"""

    # Ask LLM for initial code
    try:
        # Build llama_index ChatMessage objects (system + user)
        message = [
            ChatMessage(role="system", content="You are an expert Python developer who works with pandas and plotly. Just output the code, nothing else."),
            ChatMessage(role="user", content=final_query),
        ]
        resp = await llm.achat(messages=message)
        command = resp.message.blocks[0].text
        log.debug("draw_graph_two_datasets: llm initial code response: %s", command)
    except Exception as e:
        log.exception("draw_graph_two_datasets: llm initial code gen failed: %s", e)
        return -1

    # Reflect/validate and sanitize as original
    try:
        reflection_query = f"""The user was asking: {final_query}. You answered with the python code: {command}.
            Please check if this was the correct code and you followed the instructions properly.
            Do not use ``` and the word python in the code.
            Change update_xaxis to update_xaxes if using this function.
            Respond with the correct python code. Do not output anything else.
            Do not include any explanations, markdown, or numbered steps."""
        message = [
            ChatMessage(role="system", content="Your task is to review and correct the Python code snippet if necessary."),
            ChatMessage(role="user", content=reflection_query),
        ]
        resp = await llm.achat(messages=message)
        command = resp.message.blocks[0].text
        command = sanitize_llm_code(command)
        log.debug("draw_graph_two_datasets: llm reflected code: %s", command)
    except Exception as e:
        log.exception("draw_graph_two_datasets: llm reflection failed: %s", e)
        return -1

    # Execution loop with error-aware retry (similar to draw_graph)
    max_retries = 1
    attempt = 0
    last_command = command

    while attempt <= max_retries:
        try:
            # Provide context variables expected by executed code
            # context = {"df1": df1, "df2": df2}
            safe_defaults = {
                "fig": go.Figure(),
                "expanded_df": pd.DataFrame(),
                "filtered_df": pd.DataFrame(),
                "res_query": "",
                "pd": pd,
                "go": go,
            }
            context = {**safe_defaults, "df1": df1, "df2": df2, "df": df1}

            logger.debug("draw_graph_two_datasets: attempt %s executing code with context keys: %s", attempt, list(context.keys()))
            logger.debug("draw_graph_two_datasets: executing code: %s", last_command)
            exec_result = await exec_plot_code(last_command, context, presigned_s3_client, logger=log)
            log.debug("draw_graph_two_datasets: exec_plot_code result: %s", exec_result)
            # exec_plot_code now returns dict that includes 'figure' and S3 metadata; callers may want either
            return exec_result
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            log.error("draw_graph_two_datasets: attempt %s failed with %s: %s", attempt, error_type, error_msg)
            log.debug("draw_graph_two_datasets: failed code was:\n%s", last_command)

            # Only retry if we have attempts left AND it's a potentially fixable error
            fixable_errors = ["KeyError", "ValueError", "IndexError", "AttributeError", "NameError", "TypeError"]
            is_fixable = any(fixable_err in error_type for fixable_err in fixable_errors)

            if attempt < max_retries and is_fixable:
                log.info("draw_graph_two_datasets: Retrying with error context for fixable error: %s", error_type)
                reflection_msg = f"""Your previous code failed with a {error_type}: {error_msg}
                                    The user requested to plot two datasets (df1 and df2) for query: "{query}"
                                    Please fix the code to handle this error and produce the correct plot.
                                    Return ONLY code, no markdown."""

                messages = [ChatMessage(role="system", content="Fix the plotting code based on the runtime error."),
                            ChatMessage(role="user", content=reflection_msg + "\n\nPrevious Code:\n" + last_command)]
                resp = await llm.achat(messages=messages)
                last_command = sanitize_llm_code(resp.message.blocks[0].text)
                attempt += 1
            else:
                log.error("draw_graph_two_datasets: Error not retryable (type=%s) or max attempts reached (attempt=%s, max=%s)", 
                          error_type, attempt, max_retries)
                return -1

    return -1


# ==============================================================================
# REFACTORED: draw_graph
# ==============================================================================
async def draw_graph(response, query: str, llm: Any, presigned_s3_client, logger: logging.Logger | None = None):
    log = logger or logging.getLogger(__name__)
    tracer = Tracer(label="draw_graph")
    
    # 1. Validation & Source Extraction (Preserved Logic)
    if llm is None: 
        log.error("draw_graph: llm is None")
        return -1
    
    # 1. IDENTIFY PLOT TYPE
    requested_type = detect_requested_plot_type(query)
    log.info(f"draw_graph: Identified plot type '{requested_type}' from query.")

    # 2. SOURCE EXTRACTION & FILTERING
    source = response
    # ProcessedOutput wrapper (has .agent_output)
    try:
        from agents.processed_output import ProcessedOutput
        if isinstance(response, ProcessedOutput):
            source = getattr(response, "agent_output", response)
    except Exception: pass

    tool_calls = getattr(source, "tool_calls", [])
    aux_tools = [
        "pdc_list_studies", "pdc_list_diseases", "pdc_list_primary_sites", "describe",
        "get_clinical_trials_metadata", "get_clinical_trials_search_areas", "get_clinical_trials_enums",
    ]

    # Filter for data-providing tools and parse them
    valid_datasets = []
    for i, tool_call in enumerate(tool_calls):
        if getattr(tool_call, "tool_name", "") in aux_tools:
            continue
            
        parsed_df = await parse_response_content(source, index=i, logger=log)
        # If the tool returned a pre-uploaded plot descriptor, return it immediately so callers
        # (e.g., PlottingAgent) can forward the S3 URL to the frontend without rehydrating.
        if isinstance(parsed_df, dict) and parsed_df.get("_is_preuploaded_plot"):
            log.info("draw_graph: Detected pre-uploaded plot metadata from a tool. Forwarding metadata.")
            return parsed_df
        if parsed_df is not None and not (isinstance(parsed_df, pd.DataFrame) and parsed_df.empty):
            valid_datasets.append((i, parsed_df))

        # Check if the first dataset is actually a pre-rendered image
        if isinstance(parsed_df, dict) and parsed_df.get("_is_pre_rendered_image"):
            log.info("draw_graph: Input is already an image. Bypassing Plotly generation.")
            return parsed_df["data"]
    
    if not valid_datasets:
        log.error("draw_graph: No valid non-empty datasets found.")
        return -1

    log.info(f"draw_graph: Found {len(valid_datasets)} non-empty datasets.")

    # Handle Multi-dataset vs Single-dataset
    if len(valid_datasets) >= 2 and requested_type not in ["km", "violin", "stacked_bar", "pie"]:
        valid_indices = [idx for idx, _ in valid_datasets]
        return await draw_graph_two_datasets(source, query, indices=valid_indices, llm=llm, 
                                           presigned_s3_client=presigned_s3_client, logger=log)

    # 4. PREPARE PRIMARY DATASET (Use intelligent dataset selection for best match)
    # For single-plot types (pie, violin, stacked_bar, km when not merging), select the dataset most relevant to the plot type
    best_dataset_idx, data_frame = select_best_dataset_for_plot_type(valid_datasets, requested_type, log)
    if data_frame is None:
        log.error("draw_graph: No valid dataset found after intelligent selection")
        return -1

    # KM specific merging if the data is split across sources or lists
    if requested_type == "km" and len(valid_datasets) > 1:
        log.info("draw_graph: Processing KM survival data.")

        # Filter out metadata sentinel dicts, keep only real DataFrames
        km_datasets = []
        for idx, dataset in valid_datasets:
            # Skip sentinel dicts that represent pre-uploaded plots or pre-rendered images
            if isinstance(dataset, dict) and ("_is_preuploaded_plot" in dataset or "_is_pre_rendered_image" in dataset):
                log.debug("draw_graph: Skipping metadata sentinel dict at index %s", idx)
                continue
            km_datasets.append(dataset)

        if not km_datasets:
            log.error("draw_graph: KM processing found no valid data after filtering metadata dicts")
            return -1

        # Flatten all found datasets into one tidy DataFrame
        data_frame = flatten_km_data(km_datasets, logger=log)
        # Ensure we received a DataFrame
        if not isinstance(data_frame, pd.DataFrame):
            log.warning("draw_graph: flatten_km_data did not return a DataFrame. Received type: %s", type(data_frame))
            return -1

        df_flat = data_frame
        df_flat_cols = [str(c).lower() for c in df_flat.columns]
        required = ['time', 'survivalestimate', 'submitter_id']
        missing = [c for c in required if c not in df_flat_cols]
        if missing:
            log.warning("draw_graph: KM dataframe missing required columns: %s. Columns present: %s; sample rows: %s", missing, df_flat_cols, df_flat.head(3).to_dict())
            # Return an error to avoid attempting to plot incomplete KM data
            return -1

    # 5. CONSTRUCT PLOT-SPECIFIC INSTRUCTIONS
    cols = str(data_frame.columns.tolist())

    specific_instructions = {
        "km": f"This is survival data. Columns: {cols}. Create Kaplan-Meier curves using 'time' for x-axis, 'survivalEstimate' for y-axis, and 'group' for stratification. Plot as step function (shape='hv'). CRITICAL: Initialize all intermediate variables BEFORE use. If you need to filter data or create groups, initialize empty containers first: `filtered_data = pd.DataFrame()`, `time_vals = []`, `survival_vals = []`, etc. THEN assign values with explicit loops, not comprehensions. For example: WRONG: `times = [row['time'] for row in filtered_data if 'time' in row]` where filtered_data doesn't exist yet. RIGHT: `filtered_data = data_frame[data_frame['group'] == 'groupA']; times = []; for _, row in filtered_data.iterrows(): times.append(row['time'])`. Always explicitly create a for loop with assignments, never use comprehensions with undefined variables.",
        "pie": f"Create a pie chart. Available columns: {cols}. Use categorical columns for labels and numeric columns for values. CRITICAL: Initialize labels and values BEFORE creating the pie trace. Do NOT use comprehensions or filtering until the variable exists. Example: WRONG: `labels = [row['category'] for row in filtered_df]` where filtered_df doesn't exist. RIGHT: `filtered_df = data_frame[...]; labels = []; for _, row in filtered_df.iterrows(): labels.append(row['category'])`.",
        "violin": f"Create a violin plot. Available columns: {cols}. Put the gene/feature names on the X-axis and expression values on the Y-axis. Set box_visible=True. CRITICAL: Initialize all x and y value lists BEFORE use. Do NOT use comprehensions with undefined variables.",
        "stacked_bar": f"Create a stacked bar chart. Available columns: {cols}. Use categorical columns for x-axis and aggregate numeric data by category. Set barmode='stack' in fig.update_layout(). CRITICAL: Initialize intermediate dataframes and value lists BEFORE use. Explicitly create groups and sums with loops, not comprehensions.",
        "heatmap": f"Create a heatmap visualization. Available columns: {cols}. Identify appropriate columns for rows (samples, case IDs, aliquots) and columns (genes, proteins, features), then pivot the data. Strategy: (1) First, explicitly create and assign pivot_table using df.pivot_table() or similar, assigning it to a variable. (2) Extract z_values, x_labels, y_labels from the pivot table using explicit assignment (NOT comprehensions with undefined variables). (3) Pass these to go.Heatmap(z=z_values, x=x_labels, y=y_labels). Always define all variables BEFORE using them in comprehensions. Use colorscale='RdBu' or another appropriate colorscale.",
    }.get(requested_type, "Choose appropriate columns for the requested plot.")

    log.info("draw_graph: Successfully parsed DataFrame with shape %s", data_frame.shape)
    # Prepare metadata for LLM prompt
    # data_frame = df
    head = str(data_frame.head().to_dict())
    desc = str(data_frame.describe().to_dict())
    cols = str(data_frame.columns.to_list())
    dtype = str(data_frame.dtypes.to_dict())
    # 2. Plot Type Detection
    requested_plot_type = detect_requested_plot_type(query)
    log.info("draw_graph: Detected requested plot type: %s", requested_plot_type)
    log.debug("draw_graph: DataFrame columns: %s with description %s", cols, desc)
    final_query = f"""
                    The dataframe name is 'data_frame'. The dataframe has the columns {cols} and their datatypes are {dtype}. 
                    The format of data_frame is: {desc}. The head of df is: {head}.

                    User Request: "{query}"

                    Instructions:
                    - {specific_instructions}
                    - Assign the result to `fig`. 
                    - Return ONLY the python code.

                    **TECHNICAL PLOTTING REQUIREMENTS:**
                    1. **Output:** Assign the final Plotly Figure to `fig`. Return ONLY Python code. No markdown.
                    2. **MULTI-VARIABLE HANDLING:** If the request mentions multiple parameters (e.g., "gender, age, and ethnicity"), you MUST use `plotly.subplots.make_subplots` to create a grid of charts. Do not just plot one and ignore the others.
                    3. **SPECIFICITY:** Use the EXACT columns mentioned in the User Request. Do not default to "primary diagnosis" if the user asked for demographics or specific gene expression.
                    3.a **MEDICAL IMAGE NOTE:** For medical image slice visualizations (CT/MR/PET), use Plotly `go.Image` traces to render image data. Do NOT use `go.Heatmap` for image slices — `go.Image` preserves correct image semantics and avoids unintended color-scaling.
                    4. **CODE QUALITY & ROBUSTNESS (VERY IMPORTANT):**
                        - **Initialization:** Initialize `fig = go.Figure()` at the very beginning of the script. This ensures `fig` exists even if all checks fail.
                        - **Safe Variable Initialization:** Initialize any intermediate variables at the top of the code before they are referenced. Examples: `expanded_df = pd.DataFrame()`, `filtered_df = pd.DataFrame()`, `pivot_table = None`, `z_values = None`. If you create a new variable to hold transformed data, initialize it first.
                        - **NO COMPREHENSIONS WITH UNDEFINED VARIABLES (CRITICAL):** List comprehensions and generator expressions evaluate in a different scope. NEVER use comprehensions that reference variables that haven't been defined yet. WRONG: `result = [x for x in pivot_table]` where pivot_table doesn't exist yet. RIGHT: `pivot_table = df.pivot_table(...); result = [x for x in pivot_table]` OR use explicit loops: `result = []; for x in pivot_table: result.append(x)`. Always use explicit assignment first.
                        - Do NOT use generator expressions or comprehensions that reference variables defined later in the script (these are evaluated lazily and can raise NameError). Prefer explicit loops and explicit if-checks. 
                          Always include necessary imports at the top of the code (for example `import pandas as pd` and `import plotly.graph_objects as go`).
                        - **Handle Empty DataFrames:** After filtering, check `if filtered_df.empty:`.
                        - **Scope Safety (DO NOT UNINDENT):** 
                        - **Provide Error Messages:** If a DataFrame is empty after filtering, DO NOT proceed with plotting. Instead, assign a user-friendly error string to the `res_query` variable (e.g., `res_query = "Error: No data found for the specified filter."`).
                        - **Strict Else-Block Logic:** All operations that rely on variables validated in an if/else block (like `expanded_df`) must occur entirely inside the else block. Do NOT reference these variables outside the else block unless you have verified they exist.
                            This ensures no NameError occurs if the data check fails.
                        - If data is valid (in the `else` block): ALL logic including pivoting, calculating metrics, creating traces, and `fig.update_layout` MUST be indented inside the `else` block.
                        - **NEVER** reference variables that you have not explicitly created or initialized in your code. If you need intermediate variables (like a pivot table or transformed data), create and initialize them within the code block where they are used.
                    5. **ACCURACY:** Use `colorscale='RdBu'` for heatmaps and standard markers like 'cross' or 'circle'. Include legends and axis titles.
                    6. **DO NOT DEFAULT:** Do not use 'primary_diagnosis' unless it is explicitly requested.
                    
                    **OUTPUT FORMAT (STRICT):**
                    - Return ONLY valid Python code. NO backticks (```), NO markdown, NO introductory text.
                    - Import all needed modules: pandas, plotly.graph_objects, plotly.subplots, etc.
                   """

    # 4. The Reflection & Execution Loop
    max_retries = 2
    attempt = 0
    system_prompt = "You are an expert Python developer. Just output pure Python code, no markdown or text."
    last_command = ""

    while attempt <= max_retries:
        try:
            log.info("draw_graph: Attempt %s to generate and execute plotting code.", attempt)
            # Get code from LLM
            if attempt == 0:
                messages = [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=final_query)]
                resp = await llm.achat(messages=messages)
                last_command = sanitize_llm_code(resp.message.blocks[0].text)
            
            # Execute
            # context = {"data_frame": data_frame}
            # defensive runtime defaults to prevent NameError in LLM-generated code
            safe_defaults = {
                "fig": go.Figure(),
                "expanded_df": pd.DataFrame(),
                "filtered_df": pd.DataFrame(),
                "pivot_table": pd.DataFrame(),  
                "z_values": [],    
                "x_labels": [],
                "y_labels": [],
                "res_query": "",
                # expose helpers commonly expected byLLM snippets
                "pd": pd,
                "go": go,
            }
            context = {**safe_defaults, "data_frame": data_frame, "df": data_frame}
            log.debug("draw_graph (in plotting_agent_helpers.py) attempting to execute code: %s", str(last_command))
            # Final sanitation: balance brackets to recover from truncated LLM outputs and ensure valid code
            try:
                final_code = _balance_code_brackets(last_command)
            except Exception:
                final_code = last_command
            exec_result = await exec_plot_code(final_code, context, presigned_s3_client, logger=log)
            
            if exec_result == -1 or exec_result is None:
                raise Exception("Execution failed")

            fig = exec_result.get("figure")
            # If user requested an image-like visualization (slider/montage), ensure image traces are used.
            # Convert any LLM-produced Heatmap traces into go.Image where possible so validation and
            # downstream renderers treat the content as image data (CT/MR slices) rather than heatmaps.
            try:
                if requested_plot_type in ("slider", "montage") and fig is not None:
                    new_traces = []
                    converted = False
                    for t in fig.data:
                        t_type = (getattr(t, "type", "") or "").lower()
                        if "heatmap" in t_type:
                            try:
                                z = getattr(t, "z", None)
                                # If z is present, convert to Image trace
                                if z is not None:
                                    new_traces.append(go.Image(z=z))
                                    converted = True
                                else:
                                    new_traces.append(t)
                            except Exception:
                                new_traces.append(t)
                        else:
                            new_traces.append(t)
                    if converted:
                        fig.data = tuple(new_traces)
                        log.debug("exec_plot_code: converted heatmap traces to Image traces for image-like visualization")
            except Exception as e:
                log.debug("exec_plot_code: failed to convert heatmap to image traces: %s", e)
            
            # 5. FIXED VALIDATION UNPACKING
            is_valid, produced_types = validate_figure_matches_type(fig, requested_plot_type)

            if is_valid or not requested_plot_type:
                log.info("draw_graph: Success on attempt %s", attempt)
                return exec_result
            
            # 6. ENHANCED REFLECTION PROMPT
            log.warning("draw_graph: Validation failure. Requested: %s, Produced: %s", requested_plot_type, produced_types)
            reflection_msg = f"""Your previous code produced a figure with trace types: {produced_types}. 
The user specifically requested a '{requested_plot_type}' plot for the query: "{query}".
Please correct the code to produce a '{requested_plot_type}' using the correct columns.
Return ONLY code, no markdown."""
            
            messages = [ChatMessage(role="system", content="Correct the plotting code based on the error."),
                        ChatMessage(role="user", content=reflection_msg + "\n\nPrevious Code:\n" + last_command)]
            resp = await llm.achat(messages=messages)
            last_command = sanitize_llm_code(resp.message.blocks[0].text)
            attempt += 1

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            log.error("Attempt %s failed with %s: %s", attempt, error_type, error_msg)
            log.debug("draw_graph: failed code was:\n%s", last_command)

            # Only retry if we have attempts left AND it's a potentially fixable error
            fixable_errors = ["KeyError", "ValueError", "IndexError", "AttributeError", "NameError", "TypeError"]
            is_fixable = any(fixable_err in error_type for fixable_err in fixable_errors)

            if attempt < max_retries and is_fixable:
                log.info("draw_graph: Retrying with error context for fixable error: %s", error_type)
                reflection_msg = f"""Your previous code failed with a {error_type}: {error_msg}
                                    The user requested a '{requested_plot_type}' plot for: "{query}"
                                    Please fix the code to handle this error and produce the correct plot.
                                    Return ONLY code, no markdown."""

                messages = [ChatMessage(role="system", content="Fix the plotting code based on the runtime error."),
                            ChatMessage(role="user", content=reflection_msg + "\n\nPrevious Code:\n" + last_command)]
                resp = await llm.achat(messages=messages)
                last_command = sanitize_llm_code(resp.message.blocks[0].text)
                attempt += 1
            else:
                log.error("draw_graph: Error not retryable (type=%s) or max attempts reached (attempt=%s, max=%s)", 
                          error_type, attempt, max_retries)
                return -1

    return -1