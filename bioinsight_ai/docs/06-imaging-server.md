# Imaging Server (VoxelInsight) — partial integration

> **Status: incomplete.** BioInsight has only a *partial* imaging integration.
> Advanced imaging analysis lives in a separate application (**VoxelInsight**)
> that was deployed to its own temporary domain while a full in-app integration
> was being developed. That integration was **not finished** — work stopped when
> the project ended abruptly. This doc records what exists so the state is clear.

## What exists inside BioInsight

The chatbot's imaging capability is limited to the **IDC node** of the Cancer
Research Data Commons agent (see [04-agents.md](04-agents.md)). Two tools, in
[data_sources/cancer_research_data_commons/imaging_data_commons/](../data_sources/cancer_research_data_commons/imaging_data_commons/):

- **`idc_query`** — answers natural-language questions about imaging *metadata*
  from IDC / MIDRC / TCIA by running generated code against indexed dataframes
  (`df_IDC`, `df_MIDRC`) and returning records or Plotly JSON. The MIDRC side is
  backed by a local dataset (`midrc_distributed_subjects.csv`).
- **`idc_slider_visualization`** — a small, self-contained `VizSliderAgent`
  ([viz_slider_tool.py](../data_sources/cancer_research_data_commons/imaging_data_commons/viz_slider_tool.py))
  that loads a NIfTI/DICOM volume and produces an interactive Plotly slice
  slider (or montage) with optional mask overlays, uploaded to S3 via the
  presigned client.

When `idc_query` runs, the CRDC agent **appends a link** to the standalone
imaging server (`https://imaging.bioinsight-ai.com`) telling the user to go
there for "more advanced IDC/MIDRC based analysis and visualization."

A telling detail: `VizSliderAgent` is written against a
`Task` / `ConversationState` / `TaskResult` dataclass interface that mirrors
VoxelInsight's agent pattern. It's effectively a minimal placeholder shaped to
match VoxelInsight, in anticipation of the fuller integration that was never
completed.

## The standalone imaging server (VoxelInsight)

Advanced imaging analysis was handled by a separate application, deployed
temporarily at **`https://imaging.bioinsight-ai.com`**, with the chatbot
linking out to it rather than embedding it.

- **Code**: <https://github.com/BioIntelligence-Lab/VoxelInsight> (BioIntelligence-Lab)
- **Broad overview** (per its README — *not* documented in full here):
  - A conversational AI assistant for biomedical imaging, with a Chainlit UI.
  - Natural-language querying of imaging repositories (**MIDRC**, **IDC**, **TCIA**) over indexed metadata.
  - AI-powered imaging analysis: segmentation (**TotalSegmentator**, **MONAI**), radiomics (**PyRadiomics**), and clinical modeling.
  - Works with **DICOM** and **NIfTI** inputs.

## Integration status

The intended end state was to bring VoxelInsight's imaging analysis into
BioInsight so users could do imaging work in one place. As an interim step, the
imaging app was stood up on its own domain and the chatbot linked out to it,
while the in-app `idc_query` / `idc_slider_visualization` tools provided a
limited preview of imaging functionality. The full integration was **never
completed** — the project ended before that work was finished. The link-out and
the local slider tool are the visible remnants of that in-progress effort.
