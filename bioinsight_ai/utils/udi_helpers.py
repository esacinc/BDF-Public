import json
import pandas as pd
from typing import Optional


def build_heatmap_udi_spec(
    data_url: str,
    x_field: str,
    y_field: str,
    color_field: str,
    title: str = "Heatmap",
    colorscale: str = "RdBu",
    zmin: Optional[float] = None,
    zmax: Optional[float] = None,
    description: Optional[str] = None
) -> dict:
    """
    Build a HMS-style UDI spec for a heatmap with dynamic fields.

    Args:
        data_url: URL of the uploaded CSV file.
        x_field: Name of the x-axis column.
        y_field: Name of the y-axis column.
        color_field: Name of the value/color column.
        title: Optional chart title.
        colorscale: Plotly colorscale name.
        zmin: Optional minimum for color scale.
        zmax: Optional maximum for color scale.
        description: Optional description block.

    Returns:
        dict: Complete UDI spec as a Python dictionary.
    """

    udi_spec = {
        "source": {
            "name": "heatmap_source",
            "source": data_url
        },
        "transformation": [],
        "representation": {
            "mark": "bar",
            "mapping": [
                {
                    "encoding": "x",
                    "field": x_field,
                    "type": "ordinal" if "Index" in x_field else "nominal"
                },
                {
                    "encoding": "y",
                    "field": y_field,
                    "type": "nominal"
                },
                {
                    "encoding": "color",
                    "field": color_field,
                    "type": "quantitative",
                    "scale": {
                        "colorscale": colorscale
                    }
                }
            ],
            "layout": {
                "title": title,
                "xaxis_title": x_field,
                "yaxis_title": y_field
            }
        }
    }

    # Add zmin/zmax if given
    if zmin is not None or zmax is not None:
        scale_block = udi_spec["representation"]["mapping"][2]["scale"]
        if zmin is not None:
            scale_block["zmin"] = zmin
        if zmax is not None:
            scale_block["zmax"] = zmax

    if description:
        udi_spec["description"] = description

    return udi_spec


def infer_heatmap_fields(df: pd.DataFrame) -> dict:
    """
    Smart helper to infer heatmap axes and color fields.
    Uses explicit column names if available, else falls back to position.
    """

    # Preferred names
    expected_x = "Sample_Index"
    expected_y = "Gene"
    expected_color = "Expression"

    # Fallbacks
    possible_x = df.columns[0]
    possible_y = df.columns[1]
    possible_color = df.columns[-1]

    x_field = expected_x if expected_x in df.columns else possible_x
    y_field = expected_y if expected_y in df.columns else possible_y
    color_field = expected_color if expected_color in df.columns else possible_color

    result = {
        "x_field": x_field,
        "y_field": y_field,
        "color_field": color_field
    }

    print(f"[HEATMAP] Inferred fields: {result}")
    return result
