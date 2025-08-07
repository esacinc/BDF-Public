# import sys
# sys.path.append("C:/Users/56824/OneDrive - ICF/Documents/arpa-h/arpah-bdf-bioinsight/bioinsight_ai")
from workflow_config.default_settings import Settings
llm = Settings.llm

import sys
import json
import logging
import pandas as pd
import openpyxl
import xlrd
from typing import Any, Dict, List, Optional, Union, Literal, Annotated
import chainlit.types as cl_types
from llama_index.core.workflow import Context, HumanResponseEvent
from agents.biomedical_data_integration.interaction.chainlit_interaction_event import ChainlitInteractionEvent
from agents.biomedical_data_integration.prompts.templates import MATCH_PROMPT_TEMPLATE
from agents.biomedical_data_integration.utils.context_keys import (
    CURRENT_USER_DATA, 
    CURRENT_SCHEMA_MATCHES, 
    CURRENT_VALUE_MATCHES, 
    RANKED_SCHEMA_MATCHES
    )

logger = logging.getLogger()


async def get_current_user_dataframe(ctx: Context) -> pd.DataFrame:
    """Returns current state of user data as a DataFrame object."""
    data = await get_current_state_user_data(ctx=ctx)
    return pd.DataFrame(data['data'])

def read_uploaded_data(user_file_response: cl_types.AskFileResponse) -> Dict:
    """
    Reads uploaded file content into a pandas DataFrame based on file extension.

    Parameters:
        user_file_response (cl_types.AskFileResponse): File metadata from Chainlit upload.

    Returns:
        Dictionary containing a data key with a row oriented dict object and a metadata key.
    """
    file_name = user_file_response.name
    file_ext = file_name.lower().split('.')[-1]
    file_path = user_file_response.path
    
    if file_ext == 'csv':
        data = pd.read_csv(file_path)
    elif file_ext == 'tsv':
        data = pd.read_csv(file_path, sep='\t')
    elif file_ext == 'txt':
        data = pd.read_csv(file_path, sep=None, engine='python')
    elif file_ext == 'xlsx':
        data = pd.read_excel(file_path, engine='openpyxl')
    elif file_ext == 'xls':
        data = pd.read_excel(file_path, engine='xlrd')
    else:
        raise ValueError(f"Unsupported file type: {file_ext}")
    
    return {"data": data.to_dict(orient='records'), 'metadata': {'name': file_name, 'path': file_path, 'ext': file_ext}}
    

async def request_user_data_for_harmonization(request: Annotated[str, "A friendly, context aware message to user requesting they upload data for harmonization. Mention the target schema available for matching."],
                                              ctx: Context) -> Dict:
        """Tool to request data from a user in order to harmonize."""
        # wait until we see a HumanResponseEvent
        response = await ctx.wait_for_event(
            HumanResponseEvent,
            waiter_event=ChainlitInteractionEvent(
                message_type='AskFileMessage',
                message_args={
                    'content': request,
                    'accept': [
                        "text/csv",  # CSV
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # Excel (.xlsx)
                        "text/plain",  # TXT
                        "text/tab-separated-values"  # TSV
                        ]
                    }        
                )
        )
        user_data = read_uploaded_data(response.response[0])
        await ctx.set("initial_user_data", user_data)
        await ctx.set(CURRENT_USER_DATA, user_data)
        
        # reset in the event another dataset is uploaded
        await ctx.set(CURRENT_SCHEMA_MATCHES, None)
        await ctx.set(CURRENT_VALUE_MATCHES, None)
        await ctx.set(RANKED_SCHEMA_MATCHES, None)
        return user_data['data']
    
async def get_current_state_user_data(ctx: Context) -> dict:
        """Get the current state of the user data."""
        user_data = await ctx.get(CURRENT_USER_DATA)
        return user_data
    

async def set_current_state_user_data(
    ctx: Context,
    data: List[Dict[str, Any]]
) -> str:
    """
    Stores the provided dataset as the current state of user data.

    Args:
        data: A list of dictionaries representing the dataset to store.

    Returns:
        A confirmation message indicating the data has been stored.

    Raises:
        ValueError: If the new data has fewer rows than the current state.
    """
    
    current_user_data = await get_current_state_user_data(ctx=ctx)
    current_data = current_user_data.get('data', [])
    
    nrow_data = len(pd.DataFrame(data))
    nrow_current_data = len(pd.DataFrame(current_data))
    if nrow_data != nrow_current_data:
        raise ValueError(
            f"New data has fewer rows ({nrow_data}) than the current state ({nrow_current_data}). Provide the entire dataset to `data` argument to update state."
        )

    current_user_data['data'] = data
    await ctx.set(CURRENT_USER_DATA, current_user_data)
    
    return f"User data successfully updated to\n\n{current_user_data}"

    
from typing import Literal, Annotated
import pandas as pd

async def request_user_validate_data(
    response: Annotated[str, "A friendly, context-aware message about displaying data to the user."],
    request: Annotated[str, "A friendly, context-aware message to request user validation after showing data."],
    data: Annotated[
        Literal["current_user_data", "current_schema_matches", "current_value_matches", "ranked_schema_matches"],
        "A string key indicating which dataset to retrieve from context."
    ],
    ctx: Context
) -> str:
    """
    Displays a dataset from context to the user and requests validation. Message will be displayed in the following Chainlit format: 
    
    <response>
    <pd.DataFrame>
    <request>

    Args:
        response: Message shown before the data.
        request: Message shown after the data.
        data: One of 'current_user_data', 'current_schema_matches', 'current_value_matches', 'ranked_schema_matches'.
        ctx: The current workflow context.

    Returns:
        The user's response as a string.

    Raises:
        ValueError: If the data key is invalid.
        RuntimeError: If the data cannot be converted to a DataFrame.
    """
    
    try:
        if data == CURRENT_USER_DATA:
            context_data = await ctx.get(CURRENT_USER_DATA)
            df = pd.DataFrame(context_data["data"])
        else:
            matches = await ctx.get(data)
            df = pd.DataFrame(matches)
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"Invalid data key or structure: {e}")


    if not isinstance(df, pd.DataFrame):
        raise RuntimeError("Failed to convert context data to DataFrame.")

    response_event = await ctx.wait_for_event(
        HumanResponseEvent,
        waiter_event=ChainlitInteractionEvent(
            message_type='Message',
            message_args={
                'content': response,
                'elements': [{
                    'type': 'Dataframe',
                    'name': 'dataframe',
                    'display': 'inline',
                    'data': df
                }]
            },
            followup_type='AskUserMessage',
            followup_args={'content': request}
        )
    )
    
    prompt = f"""
    The user was just shown the following data from {data}: 
    
    <Data>
    {df.to_dict(orient='records')}
    </Data>
    
    They gave the following feedback: 
    \"{response_event.response["output"]}\"
    
    --------------
    
    Consider this feedback to decide your next step.    
    """
    
    return prompt


async def return_data_to_user(
    response: Annotated[str, "A friendly, context aware message to user that their data request is available for download."],
    request: Annotated[str, "A friendly, context aware message to user requesting they acknowledge their data is ready for download."],
    ctx: Context,
    kwargs: Annotated[
        Optional[Dict[str, Any]],
        (
            "Arguments passed to pd.DataFrame.to_csv method. "
            "Signature: (path_or_buf=None, *, sep=',', na_rep='', float_format=None, "
            "columns=None, header=True, index=True, index_label=None, mode='w', "
            "encoding=None, compression='infer', quoting=None, quotechar='\"', "
            "lineterminator=None, chunksize=None, date_format=None, doublequote=True, "
            "escapechar=None, decimal='.', errors='strict', storage_options=None) -> str | None"
        )
    ] = None
) -> str:
    """Generates a message to the user with a download button to return data. Response is in the form:
    <response>
    <download button for data>
    <request>
    """
    
    if kwargs is None:
        kwargs = {}

    user_data = await get_current_state_user_data(ctx=ctx)
    df = pd.DataFrame(user_data['data'])
    logger.info(f"[BDI] Returning the following data: \n\n{df}")
    file_name = user_data['metadata']['name']
    file_loc = "harmonized_" + file_name
    df.to_csv(file_loc, **kwargs)
    response = await ctx.wait_for_event(
            HumanResponseEvent,
            waiter_event=ChainlitInteractionEvent(
                message_type='Message',
                message_args={
                    'content': response,
                    'elements': [
                        {
                            'type': 'File',
                            'name': file_loc,
                            'path': file_loc,
                            'display': 'inline'}
                        
                    ]
                    },
                followup_type='AskUserMessage',
                followup_args={
                    'content': request
                }
            )
                )
    
    return response.response['output']

async def process_schema_match_feedback(
    ctx: Context,
    user_feedback: str,
    source_columns: Optional[List[str]] = None
) -> str:
    """
    Processes user feedback on schema match alternatives and updates the current schema matches in context.

    Args:
        ctx (Context): The workflow context containing current and ranked schema matches.
        user_feedback (str): The user's natural language response after viewing ranked schema matches.
        source_columns (Optional[List[str]]): The list of source column names for which the user requested alternative matches.
                                             If empty or None, the function assumes no update is requested.

    Returns:
        str: A message indicating whether updates were made to the schema matches.
    """


    if not source_columns:
        return "No source columns specified. Assuming user does not want to modify schema mappings."

    current_matches = await ctx.get(CURRENT_SCHEMA_MATCHES, [])
    ranked_matches = await ctx.get(RANKED_SCHEMA_MATCHES, [])

    response = await llm.apredict(
        prompt = MATCH_PROMPT_TEMPLATE,
        match_type="schema",
        source_columns=json.dumps(source_columns, indent=2),
        ranked_matches=json.dumps(ranked_matches, indent=2),
        user_feedback=user_feedback,
        current_matches=json.dumps(current_matches, indent=2)
    )

    try:
        updates = json.loads(response)
    except json.JSONDecodeError:
        return "Could not parse LLM response. No updates made."

    if not isinstance(updates, list) or not all("source" in u and "target" in u for u in updates):
        return "LLM response format invalid. No updates made."

    # Step 4: Apply updates to current matches
    updated = False
    for update in updates:
        source_col = update["source"]
        new_target = update["target"]
        for match in current_matches:
            if match["source"] == source_col:
                match["target"] = new_target
                updated = True
                break
        else:
            current_matches.append({
                "source": source_col,
                "target": new_target,
                "similarity": None
            })
            updated = True

    if updated:
        await ctx.set(CURRENT_SCHEMA_MATCHES, current_matches)
        return f"""
    User schema matches have been updated in context and are now the following: 
    
    <Current Schema Mappings>
    {current_matches}
    </Current Schema Mappings>
    
    Updated schema matches for: {', '.join([u['source'] for u in updates])}
    
    ---------------
    
    Next steps: 
    
    1. Conclude schema mappings unless user has any more feedback
    2. Only materialize these updates with materialize_mapping if the user has specifically requested to only map schema/columns
    3. Otherwise, the next step should be to map values    
    """
    else:
        return "No updates made to schema matches."
    
tools = [
    process_schema_match_feedback,
    return_data_to_user,
    request_user_validate_data,
    get_current_state_user_data,
    request_user_data_for_harmonization
]