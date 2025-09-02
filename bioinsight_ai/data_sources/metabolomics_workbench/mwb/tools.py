import aiohttp
from typing import Literal
from utils.token_counter import check_token_limit
from workflow_config.default_settings import Settings
from log_helper.logger import get_logger

logger = get_logger()

#
# Common tools used across many MWB agents
#

# Async MWB REST endpoint API calling function
async def call_rest_endpoint(context: Literal["study", "compound", "refmet", "protein", "gene"], 
                             input_item: str, 
                             input_value: str, 
                             output_item: str, 
                             output_format: str) -> str:
    """Make a call to a Metabolomic REST endpoint to fetch data."""    
    baseURL = "https://www.metabolomicsworkbench.org/rest"
    endpoint = f"{baseURL}/{context}/{input_item}/{input_value}/{output_item}/{output_format}"
    logger.info(f"[MWB REST API] Calling endpoint: {endpoint}")
    if output_item == "png":
        # Compound agent can return PNG endpoint for compound structure. This should be displayed in UI if 
        # returned as markdown.
        return f"Return the following URL in markdown format: {endpoint}"
    else: 
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint) as response:
                if response.ok:
                    try:
                        data = await response.json()
                    except:
                        data = await response.text()
                    exceed_limit_msg = check_token_limit(Settings.llm, text = str(data))
                    if exceed_limit_msg:
                        return exceed_limit_msg
                    return data
                else:
                    logger.error(f"[MWB REST API] Call failed with response: {response.status}:{response.reason}")
                    return None