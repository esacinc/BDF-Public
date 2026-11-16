import os
import json, requests
from io import StringIO
import pandas as pd
import numpy as np
import re
import traceback # Import traceback to get detailed error info
from typing import List, Dict, Optional, Any
from scipy.stats import fisher_exact
from urllib.parse import urlencode, quote
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import Context
from log_helper.logger import get_logger
from ..ensembl_api import gene_name_to_ensembl_mapping
from config import GDC_BASE_API, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, DEFAULT_MODEL
from workflow_config.default_settings import Settings


logger = get_logger()

base_api = GDC_BASE_API

def extract_and_parse_json(text: str) -> dict:
    """
    Extracts a JSON string from a markdown code block and parses it.
    Returns the parsed JSON object or None if extraction/parsing fails.
    """
    logger.info(f"Inside extract_and_parse_json for {text}")
    # Regex to find a JSON block, optionally with the 'json' language identifier
    # This pattern is robust to variations like ```json ... ``` or just ``` ... ```
    match = re.search(r'```(json)?\s*([\s\S]*?)\s*```', text)
    
    json_string = text
    if match:
        # If a markdown block is found, use its content
        json_string = match.group(2)
    else:
        # If no markdown block is found, assume the whole string is the JSON
        json_string = text

    try:
        # Attempt to parse the extracted string
        return json_string
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON: {e}")
        logger.error(f"Problematic string: {json_string}")
        return json_string
    except NameError as e:
        # This is a very common error in generated code
        logger.error(f"Execution failed due to a NameError: {e}. A variable or library was likely used before it was defined. Please ensure all variables are assigned and libraries are imported.")
        return json_string
    except SyntaxError as e:
        # Catches badly formed Python code
        logger.error(f"Execution failed due to a SyntaxError: {e}. The generated Python code is invalid. Please correct the syntax.")
        return json_string
    except Exception as e:
        # A general catch-all for any other errors
        # Using traceback gives the LLM more context
        error_details = traceback.format_exc()
        logger.error(f"An unexpected error occurred during code execution:\n```\n{error_details}\n```")
        return json_string

# Returns the list of GDC Studies and their descriptions
def get_gdc_studies():
    url = base_api + "projects?size=100&pretty=true"
    logger.info(f"GDC APIs: {url}")
    response = requests.get(url)
    resp = response.json()
    resp = resp['data']['hits']
    gdc_list = [ {'id': obj['id'], 'primary_site':obj['primary_site']} for obj in resp]
    return gdc_list

# Returns project ID that a specific study has
def get_gdc_study_by_id(study_id):
    url = base_api + "projects/" + study_id + "?expand=summary,summary.experimental_strategies,summary.data_categories&pretty=true"
    logger.info(f"GDC APIs: {url}")
    response = requests.get(url)
    resp = response.json()
    project_id = resp['data']['project_id']
    return project_id

# Retrieves project metadata from the GDC API for a given project ID.
#    Args: project_id: The project ID to query (e.g., "TCGA-LUAD").
#    Returns: a dictionary containing the project's metadata if found, otherwise None.
def get_project_meta_by_project_id(project_id: str) -> dict:
    endpoint =  base_api + "projects/" + project_id
    # Parameters to request all available fields
    params = {
        "pretty": "true",
        "expand": "summary,summary.experimental_strategies,summary.data_categories"
    }
    try:
        logger.info(f"GDC APIs: {endpoint}")
        # Perform the GET request
        response = requests.get(endpoint, params=params)

        # Check if the request was successful
        response.raise_for_status()  # This will raise an exception for HTTP error codes

        logger.info(f"Successfully retrieved data for project: {project_id}")
        logger.info(response[:100])
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            logger.info(f"Error: Project with ID '{project_id}' not found.")
        else:
            logger.error(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"An error occurred with the request: {req_err}")
    return None


# Returns the list of GDC cases and their descriptions
def get_gdc_cases():
    cases_api_url = base_api + "cases?pretty=true"
    logger.info(f"GDC APIs: {cases_api_url}")
    response = requests.get(cases_api_url)
    resp = response.json()
    resp = resp['data']['hits']
    cases_list = [ {'id': obj['id'], 'primary_site':obj['primary_site'], 'disease_type':obj['disease_type']} for obj in resp]
    return cases_list

def get_gdc_case_submitter_ids(pdc_submitter_ids: list[str]) -> list[str]:
    """
    Given a list of PDC case submitter IDs, this function constructs a GDC API URL,
    queries the GDC API, and returns a list of matching GDC case submitter IDs.

    Args:
        pdc_submitter_ids (list[str]): A list of PDC case submitter IDs (e.g., ["01OV008"]).

    Returns:
        list[str]: A list of matching GDC case submitter IDs. Returns an empty
                   list if no matches are found or an error occurs during the API call.
    """
    if not pdc_submitter_ids:
        logger.error("Input list of PDC submitter IDs is empty. Returning an empty list.")
        return []

    base_url = "https://api.gdc.cancer.gov/cases"
    
    # Construct the filters JSON object.
    # This filters for cases where the 'submitter_id' matches any of the provided PDC IDs.
    filter_content = {
        "op": "=",
        "content": {
            "field": "submitter_id",
            "value": pdc_submitter_ids
        }
    }
    
    # Convert the filters dictionary to a JSON string and URL-encode it.
    filters_json_string = json.dumps(filter_content)
    encoded_filters = quote(filters_json_string)

    # Define the fields to retrieve from the GDC API response.
    # We are interested in 'case_id', 'submitter_id', and 'project.project_id'.
    fields = "case_id,submitter_id,project.project_id"
    
    # Specify the desired response format.
    data_format = "JSON"
    
    # Set the 'size' parameter to a sufficiently large number to retrieve all
    # potential matches for the given submitter IDs in a single request.
    # The GDC API typically limits the maximum 'size' for a single query (e.g., 10,000).
    # Using 1000 here as a safe upper limit for common scenarios.
    size = len(pdc_submitter_ids)

    # Construct the complete API URL using f-strings for readability.
    api_url = (
        f"{base_url}"
        f"?filters={encoded_filters}"
        f"&fields={fields}"
        f"&format={data_format}"
        f"&size={size}"
    )

    gdc_submitter_ids = [] # Initialize an empty list to store the results

    try:
        # Make the HTTP GET request to the GDC API.
        logger.info(f"Attempting to query GDC API: {api_url}")
        response = requests.get(api_url)
        
        # Raise an HTTPError for bad responses (4xx or 5xx status codes).
        response.raise_for_status() 

        # Parse the JSON response from the API.
        response_json = response.json()

        # Navigate through the JSON structure to extract the 'submitter_id' from each 'hit'.
        # The expected path is 'data' -> 'hits' -> each dictionary containing 'submitter_id'.
        if 'data' in response_json and 'hits' in response_json['data']:
            for hit in response_json['data']['hits']:
                if 'submitter_id' in hit:
                    gdc_submitter_ids.append(hit['submitter_id'])
            logger.info(f"Successfully retrieved {len(gdc_submitter_ids)} matching GDC submitter IDs.")
        else:
            logger.error("Warning: 'data' or 'hits' not found in the GDC API response, or unexpected JSON structure.")
            logger.error(f"Full response received: {response_json}")

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error occurred while querying GDC API: {e}")
        logger.error(f"Response content: {e.response.text}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error occurred while querying GDC API: {e}")
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout occurred while querying GDC API: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"An unknown requests error occurred: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from GDC API: {e}")
        logger.error(f"Raw response text: {response.text}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

    return gdc_submitter_ids

def extract_case_ids_from_gdc_response(api_url):
    """
    Fetches data from the GDC API and extracts the case_id from the response.

    Args:
        api_url (str): The URL of the GDC API endpoint.

    Returns:
        list: A list of unique case IDs found in the API response, or an empty list
              if there's an error or no case IDs are found.
    """
    try:
        logger.info(f"GDC APIs: {api_url}")
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception for bad status codes

        data = response.json()
        case_ids = set()  # Use a set to store unique case IDs

        if "data" in data and "hits" in data["data"]:
            for hit in data["data"]["hits"]:
                if "cases" in hit and isinstance(hit["cases"], list):
                    for case in hit["cases"]:
                        if "case_id" in case:
                            case_ids.add(case["case_id"])
        return list(case_ids)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error during API request: {e}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response: {e}")
        return []
    except KeyError as e:
        logger.error(f"Error accessing key in JSON response: {e}")
        return []

def get_gdc_cases_by_project(project_id):
    """
    Generates a GDC API URL to get file information, including case IDs,
    for a specific project and Gene Expression Quantification data.

    Args:
        project_id (str): The GDC project ID (e.g., "TCGA-GBM").

    Returns:
        str: The GDC API URL.
    """
    filters_data = {
        "op": "and",
        "content": [
            {
                "op": "in",
                "content": {
                    "field": "cases.project.project_id",
                    "value": [project_id]
                }
            },
            {
                "op": "in",
                "content": {
                    "field": "data_type",
                    "value": ["Gene Expression Quantification"]
                }
            }
        ]
    }
    fields = "file_id,file_name,cases.case_id"  # Corrected fields format
    format_val = "JSON"
    size = "100"

    params = {
        "filters": json.dumps(filters_data),
        "fields": fields,
        "format": format_val,
        "size": size,
    }
    url = f"https://api.gdc.cancer.gov/files?{urlencode(params)}"
    logger.info(f"GDC APIs: {url}")
    return url

def generate_query_string_study_genes(ensemble_ids, gdc_study_id):
    """
    Generate the filters for the KM plot API which takes ensemble IDs and study ID

    Args:
        ensemble_ids: A list of genes ensemble_ids strings to search for.
        gdc_study_id: GDC study ID

    Returns:
        A string containing GET request URL with all the paramters and filters.
    """
    gdc_study_ids = get_gdc_studies()
    study_found = False
    for s in gdc_study_ids:
        if s['id'] == gdc_study_id:
            study_found = True;
            break
    if not study_found:
        logger.error("Invalid GDC Study ID:" + gdc_study_id)
        return []

    sys_prompt = ''' You are a helpful JSON generator. Given a project ID denoted by <project_id> and a list of ensemble gene IDs denoted by <gene_id>, 
    your job is to generate a JSON formatted like the example below:
        <EXAMPLE>[  
           {  
              "op":"and",
              "content":[  
                 {  
                    "op":"=",
                    "content":{  
                       "field":"cases.project.project_id",
                       "value":<project_id>
                    }
                 },
                 {  
                    "op":"=",
                    "content":{  
                       "field":"gene.gene_id",
                       "value":[<gene_id>]
                    }
                 }
              ]
           },
           {  
              "op":"and",
              "content":[  
                 {  
                    "op":"=",
                    "content":{  
                       "field":"cases.project.project_id",
                       "value":<project_id>
                    }
                 },
                 {  
                    "op":"excludeifany",
                    "content":{  
                       "field":"gene.gene_id",
                       "value":[<gene_id>]
                    }
                 }
              ]
           }
        ] 
        </EXAMPLE>

        Your response MUST be only the raw JSON content, without any markdown code blocks or explanatory text.
    '''
    
    final_query = f'''The project ID is {gdc_study_id} and the gene ids are {ensemble_ids}'''
    message = [ChatMessage(role="system", content=sys_prompt)]
    message.append(ChatMessage(role= "user", content= final_query))
    response = Settings.llm.chat(
                message
        )
    logger.info(f"""GDC generate_query_string_study_genes generated query: {final_query}, 
                    and response is {response.message.blocks[0].text}""")
    # return json.loads(response.message.blocks[0].text)
    parsed_json = extract_and_parse_json(response.message.blocks[0].text)
    if parsed_json:
        try:
            # Attempt to parse the extracted string
            return json.loads(parsed_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON: {e}")
            logger.error(f"Problematic string: {parsed_json}")
            return json.loads(response.message.blocks[0].text)
        except NameError as e:
            # This is a very common error in generated code
            return f"Execution failed due to a NameError: {e}. A variable or library was likely used before it was defined. Please ensure all variables are assigned and libraries are imported."
        except SyntaxError as e:
            # Catches badly formed Python code
            return f"Execution failed due to a SyntaxError: {e}. The generated Python code is invalid. Please correct the syntax."
        except Exception as e:
            # A general catch-all for any other errors
            # Using traceback gives the LLM more context
            error_details = traceback.format_exc()
            return f"An unexpected error occurred during code execution:\n```\n{error_details}\n```"
    else:
        logger.error("An error occured in generate_query_string_study_genes")
        return json.loads(response.message.blocks[0].text)

def generate_query_string_cases(project_id):
    """ 
    Generate the filters for the KM plot API which takes project ID
    Args: 
        project_id
    Returns:
        A string containing GET request URL with all the parameters and filters.
    """
    api_url = get_gdc_cases_by_project(project_id)
    logger.info(f"GDC APIs: {api_url}")
    gdc_cases_list = extract_case_ids_from_gdc_response(api_url)
    size = len(gdc_cases_list)
    list_size = size // 2
    list1 = gdc_cases_list[:list_size]
    list2 = gdc_cases_list[list_size:]
    sys_prompt = '''  You are a helpful JSON generator. Given two lists of case submitter IDs denoted by <list1> and <list2>,
    your job is to generate a JSON formatted like the example below:
        <EXAMPLE>[
           {
                "op":"=",
                "content":{
                    "field":"cases.case_id",
                    "value":[<list1>]
                }
            },
            {
                 "op":"=",
                 "content":{
                     "field":"cases.case_id",
                     "value":[<list2>]
                  }
            }
        ]
        </EXAMPLE>

        Your response MUST be only the raw JSON content, without any markdown code blocks or explanatory text.
    '''
    # final_query = f'''The project ID is {gdc_study_id} and the gene ids are {ensemble_ids}'''
    final_query = f'''The case submitter ID lists are {list1} and {list2}'''
    message = [ChatMessage(role="system", content=sys_prompt)]
    message.append(ChatMessage(role= "user", content= final_query))
    # print(message)
    response = Settings.llm.chat(
                message
        )
    logger.info(f"""GDC API generated a query: {final_query} and got response: {response.message.blocks[0].text}""")
    json.loads(response.message.blocks[0].text)
    return json.loads(response.message.blocks[0].text)


def generate_gdc_api_url(submitter_ids: list[str], fields: list[str] = None) -> str:
    """
    Generates a GDC API URL to query for a list of case submitter IDs.

    Args:
        submitter_ids: A list of case submitter_id strings to search for.
        fields: An optional list of GDC fields to return in the response.
                If None, defaults to a basic set of identifiers.

    Returns:
        A string containing the complete, URL-encoded GET request URL.
    """
    base_url = "https://api.gdc.cancer.gov/cases"

    if not isinstance(submitter_ids, list) or not submitter_ids:
        raise ValueError("submitter_ids must be a non-empty list.")

    # The GDC API uses an 'in' operator to filter by a list of values.
    # We construct this filter as a Python dictionary.
    filters_dict = {
        "op": "in",
        "content": {
            "field": "cases.submitter_id",
            "value": submitter_ids
        }
    }

    # The fields to be returned in the API response.
    if fields is None:
        fields = [
            "case_id",
            "submitter_id",
            "project.project_id",
            "primary_site"
        ]

    # Convert the filters dictionary to a JSON string and URL-encode it.
    filters_json_string = json.dumps(filters_dict, separators=(",", ":"))

    # Assemble the URL parameters.
    # The `filters` parameter must be a JSON string.
    # The `fields` parameter is a comma-separated string.
    params = {
        "filters": filters_json_string,
        "fields": ",".join(fields),
        "format": "JSON",
        "size": len(submitter_ids)  # Request up to the number of IDs provided
    }
    
    # urlencode will handle the necessary character escaping for the full query string.
    query_string = urlencode(params)
    logger.info(f"GDC API constructed a query string: {query_string}")
    return f"{base_url}?{query_string}"


def gdc_km_data_for_gene_mutations(gene_names = [], gdc_study_id="TCGA-BRCA"):
    """
        Generates two JSON lists containing the results of the survival analysis GDC query
        Args:
            gene_names: a list of gene names to be used as filter parameters for the survival analysis query
            gdc_study_id: GDC study id, a default one is used in case none is passed
        Returns:
            Two JSON lists containing survival analysis data needed to build a KM plot
    """
    if len(gene_names) == 0:
        logger.error("At least one gene name and disease type must be specified")
        return
    ensemble_ids = gene_name_to_ensembl_mapping(gene_names)
    if len(ensemble_ids) == 0:
        logger.error("Invalid gene names: "+ ",".join(map(str, gene_names)))
        return
    
    logger.info("Before generating the query string")
    generated_prompt = generate_query_string_study_genes(ensemble_ids, gdc_study_id)
    logger.info("After generating the query string")
    
    if generated_prompt:
        logger.info("Query string was not empty")
        #print (generated_prompt)
        url = "https://api.gdc.cancer.gov/analysis/survival?filters=" + json.dumps(generated_prompt)
        url += "&pretty=true"
        logger.info(f"GDC APIs: {url}")
        response = requests.get(url)
        if(response.ok):
            resp = response.json()
    
            df = pd.read_json(StringIO(json.dumps(resp['results'])))
            df1 = pd.DataFrame(df['donors'][0])
            df2 = pd.DataFrame(df['donors'][1])

            # ctx.state[storage_key] = [df1,df2]
            df1_json = df1.to_json(orient='records')
            df2_json = df2.to_json(orient='records')
    
            # return df1, df2
            # return df1_json, df2_json
            logger.debug("gdc_km_data_for_gene_mutations: keys in resp: %s", list(resp.keys()))
            logger.debug("gdc_km_data_for_gene_mutations: sample results preview: %s", str(resp.get('results', [])[:2])[:1000])
            logger.debug("gdc_km_data_for_gene_mutations: df shape: %s", df.shape)
            logger.debug("gdc_km_data_for_gene_mutations: df columns: %s", df.columns.tolist())
            logger.debug("gdc_km_data_for_gene_mutations: df1 columns: %s, sample row keys: %s", df1.columns.tolist(), list(df1.iloc[0].keys()) if len(df1)>0 else "<empty>")
            logger.debug("gdc_km_data_for_gene_mutations: df2 columns: %s, sample row keys: %s", df2.columns.tolist(), list(df2.iloc[0].keys()) if len(df2)>0 else "<empty>")
            # return json.dumps({"group_1": json.loads(df1_json)}), json.dumps({"group_1": json.loads(df2_json)})
            return json.dumps({"group_1": json.loads(df1_json), "group_2": json.loads(df2_json)})
        else:
            logger.error("Got an error when quering GDC APIs")
            return
    else:
        logger.error(f"Could not generate query for GDC survival analysis APIs for {ensemble_ids} in {gdc_study_id} study")
        # response.raise_for_status()
        return

def get_survival_analysis_by_cases(pdc_case_list1 = [], pdc_case_list2 = []):
    """
        Generates two JSON lists containing the results of the survival analysis GDC query
        Args:
            pdc_case_list1: a list of case IDs to be used as filter parameters for the survival analysis query
            pdc_case_list2: second list of case IDs to be used as filter parameters for the survival analysis query
        Returns:
            Two JSON lists containing survival analysis data needed to build a KM plot
    """
    
    gdc_cases_list1 = get_gdc_case_submitter_ids(pdc_case_list1)
    gdc_cases_list2 = get_gdc_case_submitter_ids(pdc_case_list2)
    filt = [{  
                "op":"=",
                "content":{  
                    "field":"cases.submitter_id",
                    "value":gdc_cases_list1
                }
              },
              {  
                "op":"=",
                "content":{  
                    "field":"cases.submitter_id",
                    "value":gdc_cases_list2
              }
            }]
    api_url = base_api + "/analysis/survival?filters=" + json.dumps(filt)
    logger.info(f"GDC APIs: {api_url}")
    response = requests.get(api_url)
    if(response.ok):
        resp = response.json()
        df = pd.read_json(StringIO(json.dumps(resp['results'])))
        df1 = pd.DataFrame(df['donors'][0])
        df2 = pd.DataFrame(df['donors'][1])
        logger.debug(df1.head())
        # return df1, df2
        df1_json = df1.to_json(orient='records')
        df2_json = df2.to_json(orient='records')
        # return df1_json, df2_json
        return json.dumps({"group_1": json.loads(df1_json)}), json.dumps({"group_1": json.loads(df2_json)})
    else:
        logger.error("Got an error quering GDC APIs")
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()

def gdc_survival_by_project(gdc_project_id):
    """
        Generates a JSON list containing the results of the survival analysis GDC query
        Args:
            gdc_project_id: GDC project ID to be used as filter parameter for the survival analysis query
        Returns:
            A JSON list containing survival analysis data needed to build a KM plot
    """
    
    filt = [{
                "op":"=",
                "content":{
                    "field":"cases.project.project_id",
                    "value":gdc_project_id
                    }
           }]

    url = "https://api.gdc.cancer.gov/analysis/survival?filters=" + json.dumps(filt)
    url += "&pretty=true"
    logger.info(f"GDC APIs: {url}")
    response = requests.get(url)
    if(response.ok):
        resp = response.json()
    
        df = pd.read_json(StringIO(json.dumps(resp['results'])))
        df1 = pd.DataFrame(df['donors'][0])

        df1_json = df1.to_json(orient='records')
    
        # return df1_json
        return json.loads(df1_json)
    else:
        logger.error("Got an error quering GDC APIs")
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()

def build_gdc_filter(filters: dict) -> dict:
    """
    Recursively builds a GDC API compatible filter from a simpler dictionary.

    Example Input:
    {
        "project.project_id": "TCGA-BRCA",
        "demographic.gender": "female",
        "diagnoses.age_at_diagnosis": {">": 60 * 365.25}
    }
    """
    if not filters:
        return None

    content = []
    for field, value in filters.items():
        if isinstance(value, dict):
            # Handle comparison operators like >, <, >=, <=
            op, val = list(value.items())[0]
            content.append({"op": op, "content": {"field": field, "value": val}})
        else:
            # Handle equality
            val = value if isinstance(value, list) else [value]
            content.append({"op": "in", "content": {"field": field, "value": val}})
    
    logger.info(f"Building GDC filters: {content}")
    if len(content) == 1:
        return content[0]
    else:
        return {"op": "and", "content": content}


# Retrieves case data based on a set of filters.
def gdc_cases(filters: dict, fields: list = None, size: int = 10) -> list:

    endpoint = base_api + "cases"
    gdc_filter = build_gdc_filter(filters)
    
    params = {
        "filters": json.dumps(gdc_filter) if gdc_filter else "{}",
        "size": size,
        "pretty": "true"
    }
    if fields:
        params["fields"] = ",".join(fields)

    try:
        logger.info(f"GDC APIs: {endpoint} with params {params}")
        response = requests.get(endpoint, params=params)
        logger.info(f"Successfully retrieved GDC cases data for parameters {params}")
        logger.debug(response[:100])
        response.raise_for_status()
        return response.json()["data"]["hits"]
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error in get_cases: {e}")
        return []


# Retrieves file data based on a set of filters.
def gdc_files(filters: dict, fields: list = None, size: int = 10) -> list:
    endpoint = base_api + "files"
    
    gdc_filter = build_gdc_filter(filters)

    params = {
        "filters": json.dumps(gdc_filter) if gdc_filter else "{}",
        "size": size,
        "pretty": "true"
    }
    if fields:
        params["fields"] = ",".join(fields)

    try:
        logger.info(f"GDC APIs: {endpoint} with params {params}")
        response = requests.get(endpoint, params=params)
        logger.info(f"Successfully retrieved GDC files data for parameters: {params}")
        logger.debug(response[:100])
        response.raise_for_status()
        return response.json()["data"]["hits"]
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error in get_files: {e}")
        return []

# Retrieves aggregations (counts) for a given entity, optionally grouped by a specific field.
# Returns total count or counts grouped by a specific field.
def gdc_aggregations(entity: str, filters: dict, group_by: str = None) -> dict:
    if entity not in ["cases", "files", "projects", "ssm_occurrences", "cnvs"]:
        raise ValueError("Entity must be one of 'cases', 'files', 'projects', 'ssm_occurrences', or 'cnvs'")
        
    endpoint = base_api + entity
    gdc_filter = build_gdc_filter(filters)

    params = {
        "filters": json.dumps(gdc_filter) if gdc_filter else "{}",
        "size": 0  # We only want aggregation data, not the hits
    }
    if group_by:
        params["facets"] = group_by

    try:
        logger.info(f"GDC APIs: {endpoint} with payload {params}")
        # response = requests.get(endpoint, params=params)
        response = requests.post(endpoint, json=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Successfully retrieved GDC aggregated data")
        logger.debug(f"GDC response (truncated): {str(data)[:200]}...")

        if group_by:
            # Return the dictionary of grouped counts
            return data.get("data", {}).get("aggregations", {}).get(group_by, {}).get("buckets", [])
        else:
            # Return the total count
            return {"total": data.get("data", {}).get("pagination", {}).get("total", 0)}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error in get_aggregations: {e}")
        return {}

# Retrieves annotation data from the GDC API based on a set of filters.
# Annotations often contain information about data quality, redaction, or other flags.
def gdc_annotations(filters: dict, fields: list = None, size: int = 100) -> list:
    endpoint = base_api + "annotations"
    
    gdc_filter = build_gdc_filter(filters)
    
    params = {
        "filters": json.dumps(gdc_filter) if gdc_filter else "{}",
        "size": size,
        "pretty": "true"
    }
    # Request a useful set of default fields if none are provided
    if fields:
        params["fields"] = ",".join(fields)
    else:
        params["fields"] = "annotation_id,entity_id,entity_type,category,classification,notes,project.project_id"

    try:
        logger.info(f"GDC APIs: {endpoint} with params: {params}")
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()["data"]["hits"]
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error in get_annotations: {e}")
        return []

def get_gdc_mutation_status(
    gene_symbols: List[str],
    project_id: str
) -> Dict[str, List[str]]:
    """
    Retrieves the somatic mutation status for a list of gene symbols from a specific GDC project.

    Args:
        gene_symbols (List[str]): A list of gene symbols to query, e.g., ["TP53", "PIK3CA"].
        project_id (str): The GDC project ID to search within, e.g., "TCGA-BRCA".

    Returns:
        Dict[str, List[str]]: A dictionary mapping case_ids (patient UUIDs) to a list of
                               the genes from the input list that are mutated in that case.
                               Returns an empty dictionary if no mutations are found.
    """
    ssm_occurrences_endpoint = base_api + "ssm_occurrences"

    filters = {
        "op": "and",
        "content": [
            {
                "op": "in",
                "content": {
                    "field": "case.project.project_id",
                    "value": [project_id]
                }
            },
            {
                "op": "in",
                "content": {
                    "field": "ssm.consequence.transcript.gene.symbol",
                    "value": gene_symbols
                }
            }
        ]
    }

    # Fields to retrieve: Patient ID and the gene symbol for the mutation
    fields = [
        "case.case_id",
        "ssm.consequence.transcript.gene.symbol"
    ]

    # GDC API results are paginated. We need to fetch all results.
    all_hits = []
    from_param = 0
    size = 1000  # Number of records per request

    while True:
        params = {
            "filters": json.dumps(filters),
            "fields": ",".join(fields),
            "format": "JSON",
            "size": size,
            "from": from_param
        }

        try:
            logger.info(f"GDC APIs: {ssm_occurrences_endpoint} with params: {params}")
            response = requests.post(ssm_occurrences_endpoint, json=params, timeout=10)
            response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
            
            data = response.json()
            hits = data.get("data", {}).get("hits", [])
            
            if not hits:
                break # No more results
            
            all_hits.extend(hits)
            from_param += size
            
            # Check if we've fetched all results
            total = data.get("data", {}).get("pagination", {}).get("total", 0)
            if from_param >= total:
                break
                
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return {"error": f"Failed to retrieve data from GDC API: {e}"}

    # Process the results into a clean, case-centric dictionary
    case_mutations = {}
    for hit in all_hits:
        case_id = hit.get("case", {}).get("case_id")
        # The gene symbol is nested; handle potential missing keys gracefully
        try:
            gene_symbol = hit["ssm"]["consequence"][0]["transcript"]["gene"]["symbol"]
            if case_id:
                if case_id not in case_mutations:
                    case_mutations[case_id] = []
                if gene_symbol not in case_mutations[case_id]:
                    case_mutations[case_id].append(gene_symbol)
        except (KeyError, IndexError):
            # Skip records with incomplete data
            continue
            
    return case_mutations

# Constants for Amino Acid Translation
AA_MAP = {
    'A': 'Ala', 'R': 'Arg', 'N': 'Asn', 'D': 'Asp', 'C': 'Cys', 'E': 'Glu',
    'Q': 'Gln', 'G': 'Gly', 'H': 'His', 'I': 'Ile', 'L': 'Leu', 'K': 'Lys',
    'M': 'Met', 'F': 'Phe', 'P': 'Pro', 'S': 'Ser', 'T': 'Thr', 'W': 'Trp',
    'Y': 'Tyr', 'V': 'Val', 'X': 'Ter', '*': 'Ter'
}
INV_MAP = {v: k for k, v in AA_MAP.items()}

def get_variant_variations(aa_change: str) -> List[str]:
    """
    Generates all common GDC notations for an AA change.
    Example: 'R132H' -> ['R132H', 'p.R132H', 'Arg132His', 'p.Arg132His']
    """
    clean = aa_change.replace("p.", "")
    # Regex to extract: (Original AA) (Position) (Mutated AA)
    match = re.match(r"([a-zA-Z*]+)(\d+)([a-zA-Z*]+)", clean)
    
    variations = {clean, f"p.{clean}"} # Use a set to avoid duplicates
    
    if match:
        orig, pos, mut = match.groups()
        
        # 1-letter -> 3-letter
        if len(orig) == 1 and len(mut) == 1:
            long_orig = AA_MAP.get(orig.upper(), orig)
            long_mut = AA_MAP.get(mut.upper(), mut)
            long_form = f"{long_orig}{pos}{long_mut}"
            variations.update([long_form, f"p.{long_form}"])
            
        # 3-letter -> 1-letter
        elif len(orig) == 3 and len(mut) == 3:
            short_orig = INV_MAP.get(orig.capitalize(), orig)
            short_mut = INV_MAP.get(mut.capitalize(), mut)
            short_form = f"{short_orig}{pos}{short_mut}"
            variations.update([short_form, f"p.{short_form}"])
            
    return list(variations)

def get_variant_case_ids(project_id: str, gene_symbol: str, aa_change: str) -> set:
    """
    Helper function using your ssm_occurrences logic to fetch 
    all unique Case IDs for a specific variant.
    """
    ssm_occurrences_endpoint = base_api + "ssm_occurrences"
    
    # Generate all possible string matches for this variant
    search_values = get_variant_variations(aa_change)

    filters = {
        "op": "and",
        "content": [
            {"op": "=", "content": {"field": "case.project.project_id", "value": project_id}},
            {"op": "=", "content": {"field": "ssm.consequence.transcript.gene.symbol", "value": gene_symbol}},
            {"op": "in", "content": {"field": "ssm.consequence.transcript.aa_change", "value": search_values}}
        ]
    }

    all_case_ids = set()
    from_param = 0
    size = 1000

    while True:
        params = {
            "filters": json.dumps(filters), 
            "fields": "case.case_id",
            "format": "JSON",
            "size": size,
            "from": from_param
        }

        try:
            logger.info(f"GDC APIs: {ssm_occurrences_endpoint} with params: {params}")
            response = requests.post(ssm_occurrences_endpoint, json=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            hits = data.get("data", {}).get("hits", [])
            
            if not hits:
                break
            
            for hit in hits:
                case_info = hit.get("case")
                if case_info and "case_id" in case_info:
                    all_case_ids.add(case_info["case_id"])

            # Check pagination
            pagination = data.get("data", {}).get("pagination", {})
            total = pagination.get("total", 0)
            from_param += size
            logger.info(f"Successfully retrieved GDC cases data for genes: {gene_symbol} and ssms: {search_values}")
            logger.debug(all_case_ids)   
            if from_param >= total:
                break 
        except Exception as e:
            logger.error(f"Failed variant lookup for {search_values}: {e}")
            break

    return all_case_ids

def gdc_variant_cooccurrence(
    project_id: str, 
    variant_1: Dict[str, str], 
    variant_2: Dict[str, str]
) -> Dict[str, Any]:
    """
    Computes co-occurrence statistics between two specific amino acid variants.
    Input format: variant_1 = {"gene_symbol": "IDH1", "aa_change": "R132H"}
    """
    # 1. Get sets of cases for both variants
    cases_a = get_variant_case_ids(project_id, variant_1['gene_symbol'], variant_1['aa_change'])
    cases_b = get_variant_case_ids(project_id, variant_2['gene_symbol'], variant_2['aa_change'])
    
    # 2. Calculate intersection (A AND B)
    intersection = cases_a.intersection(cases_b)
    
    # 3. Fetch total mutation-profiled cases for denominator
    # We use your project_id to filter the analysis endpoint
    total_profiled = 0
    try:
        analysis_url = "https://api.gdc.cancer.gov/analysis/mutated_cases_count_by_project"
        response = requests.get(analysis_url, timeout=10)
        response.raise_for_status()
        res = response.json()
    
        # Correct traversal based on your JSON output:
        # aggregations -> projects -> buckets
        buckets = res.get("aggregations", {}).get("projects", {}).get("buckets", [])
    
        for bucket in buckets:
            # In GDC aggregations, 'key' is the project_id (e.g., 'TCGA-LGG')
            if bucket.get("key") == project_id:
                # Path: case_summary -> case_with_ssm -> doc_count
                total_profiled = (
                    bucket.get("case_summary", {})
                    .get("case_with_ssm", {})
                    .get("doc_count", 0)
                )
                break
            
        # Log the finding for debugging
        logger.info(f"Found {total_profiled} profiled cases for project {project_id}")

    except Exception as e:
        logger.warning(f"Could not fetch total profiled cases from Analysis API: {e}")
        # Fallback to the union of cases if the API is unreachable
        total_profiled = len(cases_a.union(cases_b))

    # 4. Compile Results
    count_a = len(cases_a)
    count_b = len(cases_b)
    count_inter = len(intersection)
    count_a_only = len(cases_a) - count_inter
    count_b_only = len(cases_b) - count_inter
    count_neither = total_profiled - (len(cases_a) + len(cases_b) - count_inter)

    # 5. Fisher's Exact Test
    # Table format: [[both, a_only], [b_only, neither]]
    table = [[count_inter, count_a_only], 
             [count_b_only, count_neither]]
    
    odds_ratio, p_value = fisher_exact(table, alternative='two-sided')
    
    # Determine significance and association type
    significance = "Significant" if p_value < 0.05 else "Not Significant"
    association = "Co-occurrence" if odds_ratio > 1 else "Mutual Exclusivity"

    logger.info(f"GDC gdc_variant_cooccurrence analysis results: count_a_only {count_a_only}, count_b_only {count_b_only}, count_inter {count_inter}, total_ssm_cases {total_profiled}")


    return {
        "project_id": project_id,
        "variant_1": f"{variant_1['gene_symbol']} {variant_1['aa_change']}",
        "variant_2": f"{variant_2['gene_symbol']} {variant_2['aa_change']}",
        "counts": {
            "variant_a_only": count_a,
            "variant_b_only": count_b,
            "co_occurrence": count_inter,
            "total_profiled_cases": total_profiled
        },
        "statistics": {
            "percent_of_project": round((count_inter / total_profiled * 100), 2) if total_profiled else 0,
            "percent_overlap_in_variant_a": round((count_inter / count_a * 100), 2) if count_a else 0,
            "percent_overlap_in_variant_b": round((count_inter / count_b * 100), 2) if count_b else 0,
            "p_value": p_value,
            "odds_ratio": odds_ratio,
            "interpretation": f"{significance} {association}"
        }
    }

def get_gdc_cnv_status(
    gene_symbols: List[str],
    project_id: str,
    cnv_type: Optional[str] = None
) -> Dict[str, List[Dict]]:
    """
    Retrieves Copy Number Variation (CNV) events for a list of gene symbols from
    a specific GDC project.

    Args:
        gene_symbols (List[str]): A list of gene symbols to query, e.g., ["ERBB2", "MYC"].
        project_id (str): The GDC project ID to search within, e.g., "TCGA-BRCA".
        cnv_type (Optional[str]): Specific CNV type to filter for, e.g.,
                                  "amplification" or "loss". If None, returns all types.

    Returns:
        Dict[str, List[Dict]]: A dictionary mapping case_ids (patient UUIDs) to a
                               list of CNV events. Each event is a dictionary
                               containing the gene, CNV type, and log2 ratio value.
                               e.g., {"case-uuid-1": [
                                        {"gene": "ERBB2", "cnv_type": "amplification", "value": 2.1}
                                      ]}
    """
    cnv_endpoint = base_api +  "cnvs"

    # --- 1. Build the Filters ---
    filter_content = [
        {
            "op": "in",
            "content": {
                "field": "case.project.project_id",
                "value": [project_id]
            }
        },
        {
            "op": "in",
            "content": {
                "field": "consequence.transcript.gene.symbol",
                "value": gene_symbols
            }
        }
    ]

    # Add optional CNV type filter
    if cnv_type:
        cnv_type_filter = {
            "op": "in",
            "content": {
                "field": "cnv_type",
                "value": [cnv_type]
            }
        }
        filter_content.append(cnv_type_filter)

    filters = {"op": "and", "content": filter_content}

    # --- 2. Define Fields and Pagination ---
    # We need to get the gene symbol from the nested 'consequence' field
    fields = [
        "case.case_id",
        "cnv_type",
        "cnv_value", # This is the log2 ratio
        "consequence.transcript.gene.symbol"
    ]

    all_hits = []
    from_param = 0
    size = 1000

    # --- 3. Handle Pagination (Same as before) ---
    while True:
        params = {
            "filters": json.dumps(filters),
            "fields": ",".join(fields),
            "format": "JSON",
            "size": size,
            "from": from_param
        }

        try:
            logger.info(f"GDC APIs: {cnv_endpoint} with params: {params}")
            # Use POST to handle complex filters
            response = requests.post(cnv_endpoint, json=params, timeout=15)
            response.raise_for_status() # Raise HTTPError for bad responses

            data = response.json()
            hits = data.get("data", {}).get("hits", [])

            if not hits:
                break # No more results

            all_hits.extend(hits)
            from_param += size

            total = data.get("data", {}).get("pagination", {}).get("total", 0)
            if from_param >= total:
                break # All results fetched

        except requests.exceptions.RequestException as e:
            logger.error(f"GDC CNV API request failed: {e}")
            return {"error": f"Failed to retrieve data from GDC API: {e}"}

    # --- 4. Process the Results ---
    # Group the flat list of CNV events by patient
    case_cnvs = {}
    
    # Use a set to avoid adding duplicate gene events for a single patient
    # (e.g., if a CNV hits multiple transcripts of the same gene)
    seen_events = set() 

    for hit in all_hits:
        case_id = hit.get("case", {}).get("case_id")
        if not case_id:
            continue

        if case_id not in case_cnvs:
            case_cnvs[case_id] = []

        cnv_type_val = hit.get("cnv_type")
        cnv_value_val = hit.get("cnv_value")

        # A single CNV segment can hit multiple genes.
        # We must loop through the consequences to find the gene(s) we asked for.
        consequences = hit.get("consequence", [])
        for cons in consequences:
            try:
                gene_symbol = cons["transcript"]["gene"]["symbol"]
                
                # Only add the gene we originally queried for
                if gene_symbol in gene_symbols:
                    event_tuple = (case_id, gene_symbol, cnv_type_val, cnv_value_val)
                    
                    if event_tuple not in seen_events:
                        case_cnvs[case_id].append({
                            "gene": gene_symbol,
                            "cnv_type": cnv_type_val,
                            "value": cnv_value_val
                        })
                        seen_events.add(event_tuple)

            except (KeyError, TypeError):
                # Ignore consequences that don't have the full gene/symbol path
                continue

    return case_cnvs

