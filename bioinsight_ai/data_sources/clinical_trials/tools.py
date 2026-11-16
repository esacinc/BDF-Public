import json
from typing import Optional

import requests
from llama_index.core.tools import FunctionTool

# Helper functions for retrieving data from the ClinicalTrials.gov REST API v2
# API docs: https://clinicaltrials.gov/data-api/api

BASE_URL = "https://clinicaltrials.gov/api/v2"
REQUEST_TIMEOUT = 30
MAX_OUTPUT_CHARS = 30000

DEFAULT_SEARCH_FIELDS = (
    "NCTId|BriefTitle|OverallStatus|Condition|Phase|StudyType|InterventionName|"
    "LeadSponsorName|StartDate|PrimaryCompletionDate|EnrollmentCount"
)


def _flatten(value, prefix: str = "", out: Optional[dict] = None) -> dict:
    """Flatten nested dicts to {dotted.path: scalar}; lists of scalars are joined with '; '."""
    out = {} if out is None else out
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(value, list):
        if all(not isinstance(v, (dict, list)) for v in value):
            out[prefix] = "; ".join(str(v) for v in value)
        else:
            out[prefix] = json.dumps(value)
    else:
        out[prefix] = value
    return out


# Friendly, unambiguous column names for common fields (path is relative to 'protocolSection').
COLUMN_NAMES = {
    "identificationModule.nctId": "nct_id",
    "identificationModule.briefTitle": "title",
    "statusModule.overallStatus": "status",
    "statusModule.startDateStruct.date": "start_date",
    "statusModule.primaryCompletionDateStruct.date": "primary_completion_date",
    "statusModule.completionDateStruct.date": "completion_date",
    "statusModule.lastUpdatePostDateStruct.date": "last_update_date",
    "sponsorCollaboratorsModule.leadSponsor.name": "lead_sponsor",
    "conditionsModule.conditions": "conditions",
    "designModule.studyType": "study_type",
    "designModule.phases": "phases",
    "designModule.enrollmentInfo.count": "enrollment",
}
DATE_COLUMNS = ("start_date", "primary_completion_date", "completion_date", "last_update_date")
INTERVENTIONS_PATH = "armsInterventionsModule.interventions"


def _normalize_date(value):
    """ClinicalTrials.gov dates may be 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD'; return full 'YYYY-MM-DD' (or None)."""
    if not isinstance(value, str) or not value:
        return None
    parts = value.split("-")
    if len(parts[0]) != 4 or not parts[0].isdigit():
        return None
    month = parts[1] if len(parts) > 1 else "01"
    day = parts[2] if len(parts) > 2 else "01"
    return f"{parts[0]}-{month}-{day}"


def _study_to_row(study: dict) -> dict:
    """Convert one nested study into a flat, plot-ready row."""
    row, seen = {}, set()
    for path, val in _flatten(study).items():
        rel = path[len("protocolSection."):] if path.startswith("protocolSection.") else path
        if rel == INTERVENTIONS_PATH:
            continue
        if rel in COLUMN_NAMES:
            name = COLUMN_NAMES[rel]
        else:
            parts = rel.split(".")
            name = parts[-1]
            if name in seen or name in COLUMN_NAMES.values():
                name = "_".join(parts[-2:])
        seen.add(name)
        row[name] = val

    interventions = study.get("protocolSection", {}).get("armsInterventionsModule", {}).get("interventions")
    if interventions:
        row["interventions"] = "; ".join(str(i.get("name")) for i in interventions if i.get("name"))

    for col in DATE_COLUMNS:
        if col in row:
            row[col] = _normalize_date(row[col])
    if row.get("start_date"):
        row["start_year"] = int(row["start_date"][:4])
    if "enrollment" in row:
        try:
            row["enrollment"] = int(row["enrollment"])
        except (TypeError, ValueError):
            row["enrollment"] = None
    if "phases" in row:
        row["phase"] = row["phases"].replace("; ", "/") if row["phases"] else "NA"
    return row


def _flatten_studies(payload: dict) -> dict:
    """
    Convert {'studies': [nested...]} into {'data': [flat rows], 'metadata': {...}} so that the
    PlottingAgent parser (which expects tabular 'data' rows) can build a DataFrame.
    Columns: nct_id, title, status, start_date (YYYY-MM-DD), start_year, primary_completion_date,
    lead_sponsor, conditions, study_type, phases, phase (single label, e.g. 'PHASE2/PHASE3'),
    enrollment (int), interventions. Other requested fields keep their leaf field names.
    """
    rows = [_study_to_row(study) for study in payload.get("studies", [])]
    metadata = {k: payload[k] for k in ("totalCount", "nextPageToken") if k in payload}
    return {"data": rows, "metadata": metadata}


def _dump_limited(payload: dict) -> str:
    """Serialize a {'data': rows, 'metadata': ...} payload, dropping rows (never cutting JSON) if too large."""
    text = json.dumps(payload)
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    total_rows = len(payload["data"])
    while payload["data"] and len(json.dumps(payload)) > MAX_OUTPUT_CHARS:
        payload["data"] = payload["data"][: max(1, len(payload["data"]) // 2)] if len(payload["data"]) > 1 else []
    payload["metadata"]["note"] = (
        f"Only {len(payload['data'])} of {total_rows} rows returned on this page because of size limits; "
        "use a smaller page_size or fewer fields."
    )
    return json.dumps(payload)


def _get(path: str, params: Optional[dict] = None, flatten: bool = False) -> str:
    """Call the ClinicalTrials.gov API and return a JSON string (or an error message)."""
    params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    try:
        response = requests.get(f"{BASE_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        return f"Error calling ClinicalTrials.gov: {e}"
    if response.status_code == 404:
        return f"No data found on ClinicalTrials.gov for request: {path} {params}"
    if not response.ok:
        return f"ClinicalTrials.gov returned HTTP {response.status_code}: {response.text[:500]}"
    if flatten:
        return _dump_limited(_flatten_studies(response.json()))
    text = json.dumps(response.json())
    if len(text) > MAX_OUTPUT_CHARS:
        text = (
            text[:MAX_OUTPUT_CHARS]
            + "... [output truncated; narrow the request using 'fields', a smaller 'page_size', or more specific filters]"
        )
    return text


def search_clinical_trials(
    condition: Optional[str] = None,
    intervention: Optional[str] = None,
    term: Optional[str] = None,
    title: Optional[str] = None,
    outcome: Optional[str] = None,
    sponsor: Optional[str] = None,
    location: Optional[str] = None,
    patient: Optional[str] = None,
    overall_status: Optional[str] = None,
    advanced_filter: Optional[str] = None,
    nct_ids: Optional[str] = None,
    fields: Optional[str] = None,
    sort: Optional[str] = None,
    page_size: int = 10,
    page_token: Optional[str] = None,
) -> str:
    """
    Searches ClinicalTrials.gov studies (GET /studies).
    Parameters:
        condition: Condition or disease query (query.cond), e.g. 'lung cancer'
        intervention: Intervention/treatment query (query.intr), e.g. 'pembrolizumab'
        term: Other free-text terms (query.term)
        title: Title/acronym query (query.titles)
        outcome: Outcome measure query (query.outc)
        sponsor: Sponsor/collaborator query (query.spons)
        location: Location query (query.locn), e.g. 'Boston'
        patient: Patient-related query (query.patient)
        overall_status: Pipe-separated status filter (filter.overallStatus), e.g. 'RECRUITING|NOT_YET_RECRUITING'
        advanced_filter: Advanced filter expression (filter.advanced), e.g. 'AREA[StartDate]RANGE[2023-01-01,MAX]'
        nct_ids: Pipe- or comma-separated NCT IDs (filter.ids)
        fields: Pipe-separated list of fields to return. Defaults to a compact summary field set.
        sort: Sort order, e.g. 'LastUpdatePostDate:desc' or 'EnrollmentCount:desc'
        page_size: Number of studies to return (1-100)
        page_token: nextPageToken from a previous response to get the next page
    Returns:
        JSON string {"data": [flat study rows], "metadata": {totalCount, nextPageToken}}; flat rows can be plotted directly.
        Row columns: nct_id, title, status, start_date, start_year, primary_completion_date, lead_sponsor, conditions,
        study_type, phases, phase, enrollment (integer), interventions
    """
    params = {
        "query.cond": condition,
        "query.intr": intervention,
        "query.term": term,
        "query.titles": title,
        "query.outc": outcome,
        "query.spons": sponsor,
        "query.locn": location,
        "query.patient": patient,
        "filter.overallStatus": overall_status,
        "filter.advanced": advanced_filter,
        "filter.ids": nct_ids.replace(",", "|") if nct_ids else None,
        "fields": fields or DEFAULT_SEARCH_FIELDS,
        "sort": sort,
        "pageSize": max(1, min(int(page_size), 100)),
        "pageToken": page_token,
        "countTotal": "true",
        "format": "json",
    }
    return _get("/studies", params, flatten=True)


def get_clinical_trial(nct_id: str, fields: Optional[str] = None) -> str:
    """
    Returns the full record of a single study (GET /studies/{nctId}).
    Parameters:
        nct_id: A valid NCT number, e.g. 'NCT04280705'
        fields: Optional pipe-separated list of fields or modules to return (e.g. 'NCTId|BriefTitle|EligibilityModule').
                If omitted, the complete record is returned.
    Returns:
        JSON string of the study record
    """
    nct_id = nct_id.strip().upper()
    return _get(f"/studies/{nct_id}", {"fields": fields, "format": "json"})


def get_clinical_trials_metadata(include_indexed_only: bool = False, include_historic_only: bool = False) -> str:
    """
    Returns the data model field metadata (GET /studies/metadata): field names, piece names, types,
    and source data types. Useful for choosing valid values for the 'fields' and 'sort' parameters.
    Parameters:
        include_indexed_only: Only include fields that are indexed for searching
        include_historic_only: Include only historic fields
    Returns:
        JSON string of field metadata
    """
    return _get(
        "/studies/metadata",
        {
            "includeIndexedOnly": "true" if include_indexed_only else None,
            "includeHistoricOnly": "true" if include_historic_only else None,
        },
    )


def get_clinical_trials_search_areas() -> str:
    """
    Returns the search documents and search areas (GET /studies/search-areas), i.e. which fields
    are searched by each query parameter and their weights.
    Returns:
        JSON string of search areas
    """
    return _get("/studies/search-areas")


def get_clinical_trials_enums() -> str:
    """
    Returns enumeration types and their allowed values (GET /studies/enums), e.g. Status, Phase,
    StudyType. Useful for building valid status or phase filters.
    Returns:
        JSON string of enums
    """
    return _get("/studies/enums")


clinical_trials_search_tool = FunctionTool.from_defaults(
    name="search_clinical_trials",
    fn=search_clinical_trials,
    description=(
        """Useful for searching ClinicalTrials.gov for clinical studies by condition/disease, intervention/drug,
        sponsor, location, title, outcome, recruitment status, or advanced filters. Returns a compact summary per study
        (NCT ID, title, status, conditions, phase, interventions, sponsor, dates, enrollment) plus totalCount and
        nextPageToken for paging. Use the 'fields' parameter to request other fields, and get_clinical_trial for details
        of one study. Use overall_status values such as RECRUITING, COMPLETED, TERMINATED (see get_clinical_trials_enums)."""
    ),
)
clinical_trial_tool = FunctionTool.from_defaults(
    name="get_clinical_trial",
    fn=get_clinical_trial,
    description=(
        """Useful for getting the full record of one ClinicalTrials.gov study given its NCT ID (format NCT followed by
        8 digits, e.g. NCT04280705): eligibility, design, arms, interventions, outcomes, locations, results, etc.
        Pass 'fields' to limit the response to specific fields or modules."""
    ),
)
clinical_trials_metadata_tool = FunctionTool.from_defaults(
    name="get_clinical_trials_metadata",
    fn=get_clinical_trials_metadata,
    description=(
        """Useful for discovering the ClinicalTrials.gov data model: available field names, their types and
        descriptions. Use it to find valid names for the 'fields' and 'sort' parameters of other tools."""
    ),
)
clinical_trials_search_areas_tool = FunctionTool.from_defaults(
    name="get_clinical_trials_search_areas",
    fn=get_clinical_trials_search_areas,
    description=(
        """Useful for learning which fields each ClinicalTrials.gov search area (query.cond, query.intr, etc.)
        searches, and for writing advanced filter expressions using AREA[...]."""
    ),
)
clinical_trials_enums_tool = FunctionTool.from_defaults(
    name="get_clinical_trials_enums",
    fn=get_clinical_trials_enums,
    description=(
        """Useful for listing the allowed values of ClinicalTrials.gov enumerations such as overall status, phase,
        study type, and intervention type, to build valid filters."""
    ),
)

tools = [
    clinical_trials_search_tool,
    clinical_trial_tool,
    clinical_trials_metadata_tool,
    clinical_trials_search_areas_tool,
    clinical_trials_enums_tool,
]
