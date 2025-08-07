import bdikit as bdi
import pandas as pd
from agents.biomedical_data_integration.interaction.tools import set_current_state_user_data, get_current_user_dataframe
from agents.biomedical_data_integration.utils.context_keys import (
    CURRENT_SCHEMA_MATCHES, 
    CURRENT_VALUE_MATCHES, 
    RANKED_SCHEMA_MATCHES
)
from llama_index.core.workflow import Context
from typing import Any, Optional, Dict, List

async def match_schema(
    ctx: Context,
    target_dataset_path: Optional[str] = "gdc",
    method: Optional[str] = "magneto_ft_bp",
) -> str:
    """Performs schema matching task between the source table and the given target schema

    Args:
        target_dataset_path: Optional path to target schema (default is "gdc", which uses the GDC schema)
        method: Optional method to use for schema matching (default is "magneto_ft_bp")

    Returns:
        Dictionary with schema matching results
    """
    
    source_dataset = await get_current_user_dataframe(ctx=ctx)

    if target_dataset_path == "gdc":
        target_dataset = target_dataset_path
    else:
        target_dataset = pd.read_csv(target_dataset_path)

    matches = bdi.match_schema(source_dataset, target=target_dataset, method=method)

    response = matches.to_dict(orient="records")
    
    await ctx.set(CURRENT_SCHEMA_MATCHES, response)
    
    prompt = f"""
    The following schema matches have been generated: 
    
    <Schema Matches>
    {response}
    </Schema Matches> 
    
    Use the request_user_validate_data tool to show these matches to the user and request feedback.
    For example, request_user_validate_data(response=<response>, request=<request>, data='current_schema_matches', ctx=<ctx>)
    """
    
    return prompt

async def rank_schema_matches(
    ctx: Context,
    target_dataset_path: Optional[str] = "gdc",
    columns: Optional[List[str]] = None,
    top_k: Optional[int] = 10,
    method: Optional[str] = "magneto_ft_bp",
) -> List[Dict[str, Any]]:
    """Returns the top-k matches between the source and target tables. Where k is a value specified by the user.

    Args:
        target_dataset_path: Optional path to target schema (default is "gdc", which uses the GDC schema)
        columns: Optional list of columns to match
        top_k: Optional number of top matches to return (default is 10)
        method: Optional method to use for schema matching (default is "magneto_ft_bp")

    Returns:
        Dictionary with schema matching results
    """
    
    source_dataset = await get_current_user_dataframe(ctx=ctx)

    if target_dataset_path == "gdc":
        target_dataset = target_dataset_path
    else:
        target_dataset = pd.read_csv(target_dataset_path)

    matches = bdi.rank_schema_matches(
        source_dataset,
        target=target_dataset,
        columns=columns,
        top_k=top_k,
        method=method,
    )

    response = matches.to_dict(orient="records")
    
    await ctx.set(RANKED_SCHEMA_MATCHES, response)

    return response


async def match_values(
    ctx: Context,
    target_dataset_path: str,
    method: Optional[str] = "tfidf",
) -> List[Dict[str, Any]]:
    """
    Finds matches between attribute/column values from the source dataset and attribute/column
    values of the target schema.

    Args:
        target_dataset_path: Path to the target schema or a standard vocabulary name 
            (e.g., "gdc", which uses the GDC schema).
        method: Optional method to use for value matching (default is "tf-idf").

    Returns:
        A list of dictionaries with value matching results.

    Raises:
        ValueError: If attribute_matches is not convertible to a DataFrame or does not contain
                    the required 'source' and 'target' columns.
    """

    source_dataset = await get_current_user_dataframe(ctx=ctx)
    
    attribute_matches = await ctx.get(CURRENT_SCHEMA_MATCHES, None)

    if target_dataset_path == "gdc":
        target_dataset = target_dataset_path
    else:
        target_dataset = pd.read_csv(target_dataset_path)

    if attribute_matches is None:
        attribute_matches = bdi.match_schema(
            source_dataset,
            target=target_dataset,
        )

    df_matches = pd.DataFrame(attribute_matches)
    matches = bdi.match_values(
        source_dataset,
        target_dataset,
        df_matches,
        method=method,
    )

    response = matches.to_dict(orient="records")
    
    await ctx.set(CURRENT_VALUE_MATCHES, response)

    prompt = f"""
    The following value matches have been generated: 
    
    <Value Matches>
    {response}
    </Value Matches> 
    
    Use the request_user_validate_data tool to show these matches to the user and request feedback.
    For example, request_user_validate_data(response=<response>, request=<request>, data='current_value_matches', ctx=<ctx>)
    """
    
    return prompt

async def rank_value_matches(
    ctx: Context,
    target_dataset_path: str,
    attribute_matches: Optional[List[str]] = None,
    top_k: Optional[int] = 5,
    method: Optional[str] = "tfidf",
) -> List[Dict[str, Any]]:
    """Returns the top-k value matches between the source and target attributes/columns. Where k is a value specified by the user.

    Args:
        target_dataset_path: Path to target schema or a standard vocabulary name (e.g. "gdc", which uses the GDC schema)
        attribute_matches: The attribute/column of the source and target dataset for which to find value matches for.
            If not provided, it will be calculated using all attributes/columns. Should be length 2.
        top_k: Optional number of top matches to return (default is 5)
        method: Optional method to use for value matching (default is "tf-idf")

    Returns:
        Dictionary with value matching results
    """
    source_dataset = await get_current_user_dataframe(ctx=ctx)

    if target_dataset_path == "gdc":
        target_dataset = target_dataset_path
    else:
        target_dataset = pd.read_csv(target_dataset_path)

    if attribute_matches is None:
        attribute_matches = bdi.match_schema(
            source_dataset,
            target=target_dataset,
        )

    if not isinstance(attribute_matches, list) or len(attribute_matches) != 2:
        raise ValueError("attribute_matches must be a list of two strings: [source_attribute, target_attribute]")

    source_attr, target_attr = attribute_matches
    matches = bdi.rank_value_matches(
        source_dataset,
        target_dataset,
        (source_attr, target_attr),
        top_k=top_k,
        method=method,
    )

    response = matches.to_dict(orient="records")

    return response


async def materialize_mapping(
    ctx: Context,
) -> Dict[str, Any]:
    """
    Harmonizes the source dataset using a mapping specification that may include
    column mappings, value mappings, or both.

    Returns:
        A dictionary with a success message and the harmonized dataset as a list of records.

    Raises:
        ValueError: If the mapping_spec is not in a supported format or is missing required fields.
    """
    
    source_dataset = await get_current_user_dataframe(ctx=ctx)
    
    schema_mapping = await ctx.get(CURRENT_SCHEMA_MATCHES, None)
    value_mapping = await ctx.get(CURRENT_VALUE_MATCHES, None)
    
    schema_mapping = pd.DataFrame(schema_mapping)
    value_mapping = pd.DataFrame(value_mapping)

    try:
        if not schema_mapping.empty and value_mapping.empty:
            materialized_data = bdi.materialize_mapping(source_dataset, schema_mapping)
        elif not value_mapping.empty:
            materialized_data = bdi.materialize_mapping(source_dataset, value_mapping)
        else:
            raise ValueError("No valid mapping provided for materialization.")
    except Exception as e:
        raise RuntimeError(f"Failed to materialize data due to: {str(e)}")
            

    response = {
        "message": "Data successfully harmonized.",
        "data": materialized_data.to_dict(orient="records"),
    }
    
    await set_current_state_user_data(ctx=ctx, data=response["data"])

    return response

bdi_tools = [match_schema, rank_schema_matches, match_values, rank_value_matches, materialize_mapping]
