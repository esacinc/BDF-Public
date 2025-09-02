import os
import json, requests
from llama_index.core.tools import FunctionTool
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import Context
from io import StringIO
import pandas as pd
import numpy as np
from urllib.parse import urlencode, quote
from ..ensembl_api import gene_name_to_ensembl_mapping
from config import GDC_BASE_API

base_api = GDC_BASE_API

def setup_llm():
    aws_access_key_id = os.environ["AWS_ACCESS_KEY"]
    aws_secret_access_key = os.environ["AWS_SECRET_KEY"]
    region_name = os.environ["AWS_REGION"]
    llm_model = os.environ["DEFAULT_MODEL"]

    llm_model = BedrockConverse(
              model = llm_model,
              aws_access_key_id=aws_access_key_id,
              aws_secret_access_key=aws_secret_access_key,
              region_name=region_name
    )
    return llm_model

# Returns the list of GDC Studies and their descriptions
def get_gdc_studies():
    url = base_api + "projects?size=100&pretty=true"
    response = requests.get(url)
    resp = response.json()
    resp = resp['data']['hits']
    gdc_list = [ {'id': obj['id'], 'primary_site':obj['primary_site']} for obj in resp]
    return gdc_list

# Returns project ID that a specific study has
def get_gdc_study_by_id(study_id):
    url = base_api + "projects/" + study_id + "?expand=summary,summary.experimental_strategies,summary.data_categories&pretty=true"
    response = requests.get(url)
    resp = response.json()
    project_id = resp['data']['project_id']
    return project_id

# Returns the list of GDC cases and their descriptions
def get_gdc_cases():
    cases_api_url = base_api + "cases?pretty=true"
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
        print("Input list of PDC submitter IDs is empty. Returning an empty list.")
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
    # size = 1000 
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
        print(f"Attempting to query GDC API: {api_url}")
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
            print(f"Successfully retrieved {len(gdc_submitter_ids)} matching GDC submitter IDs.")
        else:
            print("Warning: 'data' or 'hits' not found in the GDC API response, or unexpected JSON structure.")
            print(f"Full response received: {response_json}")

    except requests.exceptions.HTTPError as e:
        print(f"HTTP error occurred while querying GDC API: {e}")
        print(f"Response content: {e.response.text}")
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error occurred while querying GDC API: {e}")
    except requests.exceptions.Timeout as e:
        print(f"Timeout occurred while querying GDC API: {e}")
    except requests.exceptions.RequestException as e:
        print(f"An unknown requests error occurred: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from GDC API: {e}")
        print(f"Raw response text: {response.text}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

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
        print(f"Error during API request: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
        return []
    except KeyError as e:
        print(f"Error accessing key in JSON response: {e}")
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
    print(url)
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
        print("Invalid GDC Study ID:" + gdc_study_id)
        return []

    llm = setup_llm()

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
    '''
    
    final_query = f'''The project ID is {gdc_study_id} and the gene ids are {ensemble_ids}'''
    message = [ChatMessage(role="system", content=sys_prompt)]
    message.append(ChatMessage(role= "user", content= final_query))
    response = llm.chat(
                message
        )
    return json.loads(response.message.blocks[0].text)

def generate_query_string_cases(project_id):
    """ 
    Generate the filters for the KM plot API which takes prohect ID
    Args: 
        project_id
    Returns:
        A string containing GET request URL with all the paramters and filters.
    """
    api_url = get_gdc_cases_by_project(project_id)
    print(api_url)
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
    '''
    # final_query = f'''The project ID is {gdc_study_id} and the gene ids are {ensemble_ids}'''
    final_query = f'''The case submitter ID lists are {list1} and {list2}'''
    message = [ChatMessage(role="system", content=sys_prompt)]
    message.append(ChatMessage(role= "user", content= final_query))
    # print(message)
    response = llm.chat(
                message
        )
    print(response.message.blocks[0].text)
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

    # Convert the Python dictionary to a compact JSON string.
    # `separators` removes whitespace for a cleaner URL.
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

    return f"{base_url}?{query_string}"


def get_km_data_for_gene_mutations(gene_names = [], gdc_study_id="TCGA-BRCA"):
    """
        Generates two JSON lists containing the results of the survival analysis GDC query
        Args:
            gene_names: a list of gene names to be used as filter parameters for the survival analysis query
            gdc_study_id: GDC study id, a default one is used in case none is passed
        Returns:
            Two JSON lists containing survival analysis data needed to build a KM plot
    """
    if len(gene_names) == 0:
        print("At least one gene name and disease type must be specifie")
        return;
    ensemble_ids = gene_name_to_ensembl_mapping(gene_names)
    if len(ensemble_ids) == 0:
        print("Invalide gene names: "+ ",".join(map(str, gene_names)))
        return
    
    generated_prompt = generate_query_string_study_genes(ensemble_ids, gdc_study_id)
    
    #print (generated_prompt)
    url = "https://api.gdc.cancer.gov/analysis/survival?filters=" + json.dumps(generated_prompt)
    url += "&pretty=true"
    print(url)
    response = requests.get(url)
    resp = response.json()
    
    df = pd.read_json(StringIO(json.dumps(resp['results'])))
    df1 = pd.DataFrame(df['donors'][0])
    df2 = pd.DataFrame(df['donors'][1])

    # ctx.state[storage_key] = [df1,df2]
    df1_json = df1.to_json(orient='records')
    df2_json = df2.to_json(orient='records')
    
    # return df1, df2
    return df1_json, df2_json

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
    print(api_url)
    response = requests.get(api_url)
    if(response.ok):
        resp = response.json()
        df = pd.read_json(StringIO(json.dumps(resp['results'])))
        df1 = pd.DataFrame(df['donors'][0])
        df2 = pd.DataFrame(df['donors'][1])
        print(df1.head())
        # return df1, df2
        df1_json = df1.to_json(orient='records')
        df2_json = df2.to_json(orient='records')
        return df1_json, df2_json
    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()

def get_survival_analysis_with_project_id(gdc_project_id):
    """
        Generates two JSON lists containing the results of the survival analysis GDC query
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
    print(url)
    response = requests.get(url)
    resp = response.json()
    
    df = pd.read_json(StringIO(json.dumps(resp['results'])))
    df1 = pd.DataFrame(df['donors'][0])

    df1_json = df1.to_json(orient='records')
    
    return df1_json

gdc_survival_analysis_project_genes = FunctionTool.from_defaults(
    name = "get_km_data_for_gene_mutations",
    fn = get_km_data_for_gene_mutations,
    description = (f"""Useful for data needed for survival analysis plot given gene names list and GDC study ID
                        returns 2 datasets which contain survivalEstimate and related content
                        that is later used to draw survival analysis graph. Requires 'gene_names', 'gdc_study_id'""")
)

gdc_survival_analysis_by_project = FunctionTool.from_defaults(
    name = "get_survival_analysis_with_project_id",
    fn = get_survival_analysis_with_project_id,
    description = (f"""Useful for data needed for survival analysis plot given GDC project ID
                        returns one dataset which contain survivalEstimate and related content
                        that is later used to draw survival analysis graph. Requires only 'gdc_study_id'""")
)

gdc_map_pdc_cases = FunctionTool.from_defaults(
    name = "get_gdc_case_submitter_ids",
    fn = get_gdc_case_submitter_ids,
    description = (f"""Useful function that maps PDC case submitter ids to GDC case submitter ids 
                        Gets as parameter a list of PDC case submitter ids, returns a list of GDC case submitter ids
                        The returned list can be used later to generate survival analysis data for specific cases""")
)

gdc_survival_analysis_by_cases = FunctionTool.from_defaults(   
    name = "get_survival_analysis_by_cases",
    fn = get_survival_analysis_by_cases,
    description = (f"""Useful for data needed for survival analysis plot given PDC case submitter ids
                    Input paramters are two PDC case submitter ids lists pdc_case_list1 and pdc_case_list2
                    Returns 2 datasets which contain survivalEstimate and related content
                    that is later used to draw survival analysis graph. Requires 'pdc_case_list1' and 'pdc_case_list2'""")
)

gdc_tools = [gdc_survival_analysis_project_genes,
             gdc_survival_analysis_by_project
             ]