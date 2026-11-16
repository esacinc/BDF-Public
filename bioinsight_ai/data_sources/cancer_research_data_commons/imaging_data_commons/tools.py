from llama_index.core.tools import FunctionTool
import pandas as pd
from idc_index import index
from pathlib import Path
import re
import os
import io
import pydicom
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import matplotlib.figure
import base64
import json
import gzip
import uuid
from llama_index.core.llms import ChatMessage
from workflow_config.default_settings import Settings
from .viz_slider_tool import VizSliderAgent, Task, TaskResult, ConversationState
from log_helper.logger import get_logger
logger = get_logger()

def parse(chat_response):
      code_blocks = re.findall(r"```(.+?)```", chat_response, re.DOTALL)
      if len(code_blocks)>0:
        code_blocks[0] = code_blocks[0].replace('python','')
        code_blocks[0] = code_blocks[0].replace(';','')
        code_blocks[0] = code_blocks[0]
      return code_blocks

def generate_python_MIDRC(prompt):
    pretext= 'Please be as specific as possible and only return the final python code enclosed in ```. \
                Do not provide explanations. I have created two dataframes \
                the first dataframe contains all the data for the platform IDC and is created using the package idc-index. \
                This data frame was created using the following command: IDC_Client = index.IDCClient(); df_IDC = IDC_Client.index. Assume df_IDC is already present. \
                Using the pandas dataframe, df_IDC which has data fields such as: \
                collection_id: id of different collections or datasets on IDC,\
                Modality: modality of the images or imaging datasets (e.g., CT, MR, PT (for PET), etc.). Make sure to use MR when the user asks for MRI, \
                BodyPartExamined: body part examined (for example, brain or lung, etc.), \
                SeriesDescription: Different series or sequences contained within a dataset (e.g., MR contains DWI, T1WI, etc.), \
                PatientID: ID of different patients, PatientSex: Sex of different patients (e.g., M for male), \
                PatientAge: Age of different patients (Hint: Use SAFE_CAST), \
                Manufacturer: Scanner manufacturer, \
                ManufacturerModelName: Name of the scanner model, \
                instanceCount: Number of images in the series \
                StudyDescription: Description of the studies, \
                SeriesInstanceUID: Series IDs, \
                These were the commonly queried data fields. There are other data fields as well. \
                Use your best guess if the user asks for information present outside the provided data fields. \
                Make sure the queries are case insensitive and use Regex wherever necessary. \
                **Crucially, you must not alter any provided names, identifiers, or variables in any way.**\
                This includes, but is not limited to, replacing underscores (`_`) with dashes (`-`). \
                The names provided in the input must be preserved exactly as they are in the generated code.\
                For example, if the input mentions `upenn_gbm`, the output code must use `upenn_gbm` and **not** `upenn-gbm`.\
                If the user wants to download data, use the following commands: from idc_index import index; IDC_Client = index.IDCClient(); IDC_Client.download_from_selection(seriesInstanceUID=selected_series, downloadDir=".") \
                The second dataframe df_MIDRC contains the multi-source indexed dataframe\
                This index contains study level data from multiple source or public platforms including IDC, MIDRC, TCIA, among others\
                You have to identify whether the user wants to query this BDF dataframe or the IDC dataframe and answer their query\
                The MIDC dataframe has the following fields\
                subject_id: patient id \
                commons_name: name of the data source like IDC, MIDRC, AIMI\
                metadata_source_version: version of the metadata \
                race: race of the patient\
                disease_type: disease type of the patient \
                data_url_doi: url to access the data, sometimes this points to a journal\
                StudyDescription: Description of what the study contains\
                StudyInstanceUID: instance UID to look at this particular study\
                study_viewer_url: link to OHIF viewer that hosts the dataset\
                collection_id: id of different collections or datasets\
                license: licens whether data is public or not etc.\
                primary_site: primary body site for which data is collected \
                metadata_source_date: date metadata was sourced\
                commons_long_name: long name of the data source\
                PatientAge: Age of the patient - numeric value\
                EthnicGroup: Ethnic group\
                PatientSex: Sex of the patient\
                collection_id: id of the collection\
                You also have access to the following tools if you are working with local data where the user provides path to the data: \
                1) DICOM to NIfTI conversion using the dicom2nifti Python package. \
                2) Image visualization using ipywidgets and matplotlib for viewing DICOM and NIfTI images. \
                3) Segmentation using TotalSegmentator, which supports organ and lesion segmentation from CT/MRI NIfTI files. \
                Example Command line usage: TotalSegmentator -i ct.nii.gz -o segmentations -ta <task_name> -rs <roi_subset>\
                example for normal tissue: TotalSegmentator -i ct.nii.gz -o seg -ta total -rs liver\
                For tumor, the task is different: here is an example: TotalSegmentator -i ct.nii.gz -o seg -ta liver_vessels\
                Here seg is the folder name\
                4) Radiomics extraction using PyRadiomics, which computes shape, first-order, and texture features from segmented regions. \
                Usage Command line: pyradiomics <path/to/image> <path/to/segmentation> -o results.csv -f csv\
                When a user asks a clinical imaging question (e.g., "What is the liver volume in this scan?"), you should: \
                Run TotalSegmentator on the input NIfTI file to segment the requested region (e.g., liver).\
                Use PyRadiomics to extract relevant metrics from the segmentation. \
                Return the answer (e.g., volume in cc).\
                Use your best guess if the user asks for information present outside the provided data fields. \
                Make sure the queries are case insensitive and use Regex wherever necessary. Write a python script\
                to do the following and store the final output to a variable called res_query.\
                Make sure to store the final result in a variable called `res_query`.\
                Make sure to import all the necessary libraries such as pandas.\
                Do not include any display or rendering commands such as plt.show(), fig.show(), or any image encoding (e.g. base64 or HTML representations).\
                When creating pandas DataFrames from dictionaries, always ensure all values are list-like (lists, tuples, arrays, or pandas Series), \
	            and all columns have the same number of elements.\
                When you create the final pandas DataFrame that holds the requested data, store it in a variable called res_query.\
                After creating res_query, convert it into a JSON string using:\
	            res_query_json = res_query.to_json(orient="records")\
                If you generate any Plotly figure object, store it in a variable called fig.\
                Convert Plotly figures into JSON strings using:\
	            fig_json = fig.to_json()\
                Do not use json.dumps(), PlotlyJSONEncoder(), or json_normalize() for figure serialization.\
                Do not output anything else except the code itself.\
                Always serialize your dataframe using df.to_json(orient="records"). Always serialize plotly figures using fig.to_json().\
                '

    llm_model = Settings.llm

    chat_history = [] # Initialize an empty list to maintain chat history

    user_input = pretext + prompt

    logger.info("User input: %s", user_input)
      
    message = [ChatMessage(role="user", content=pretext)]
    message.append(ChatMessage(role= "user", content=prompt))

    # Get the LLM's response using the BedrockConverse model
    chat_response = llm_model.chat(message)

    response = chat_response.message.blocks[0].text
    logger.info(response)

    # Append the assistant's response to the history
    chat_history.append({"role": "assistant", "content": response})

    return response

def MIDRC_text2cohort(prompt):
      IDC_Client = index.IDCClient()
      df_IDC = IDC_Client.index
      index_file_path = os.path.abspath(os.getcwd())
      try:
        df_MIDRC = pd.read_csv(index_file_path + "/data_sources/cancer_research_data_commons/imaging_data_commons/midrc_distributed_subjects.csv")
      except Exception as e:
          return f"Error reading index file: {e}"  
      try:
          python_code = generate_python_MIDRC(prompt)
          logger.info("Resulting python code:")
          logger.info(python_code)
          query = parse(python_code)
          if not query:
                logger.warning("No executable code found in the response.")
          q = query[0]
          local_vars = {
                    "os": os,
                    "pydicom": pydicom,
                    "plt": plt,
                    "io": io,
                    "df_IDC": df_IDC,
                    "df_MIDRC": df_MIDRC
                    }
          exec(q, globals(), local_vars)
          # print(res_query)
          result = local_vars.get("res_query_json", None)
          if result is None:
               result = local_vars.get("res_query", "No explicit result returned.")
          logger.info(result)
          logger.debug(f"RETURNING OBJECT OF TYPE: {type(result)} !")
          return result
      except Exception as e:
          return f"Error executing code: {e}"

def idc_query(prompt):
    logger.info("Starting idc_query")
    index_file_path = os.path.abspath(os.getcwd())
    IDC_Client = index.IDCClient()
    logger.info("loaded IDC_Client")
    df_IDC = IDC_Client.index
    df_BIH = pd.DataFrame()
    df_MIDRC = pd.DataFrame()
    logger.info("Initialized dataframes")
    try:
        df_MIDRC = pd.read_csv(index_file_path + "/data_sources/cancer_research_data_commons/imaging_data_commons/midrc_distributed_subjects.csv", low_memory=False)
        logger.info("Read df_MIDRC")
    except Exception as e:
        logger.error(f"Exception {e} after reading df_MIDRC fired")
        return f"Error reading index file: {e}"  
    try:
        system_prompt = Path(index_file_path + "/data_sources/cancer_research_data_commons/imaging_data_commons/prompts/agent_systems/data_query.txt").read_text()
        llm_model = Settings.llm
        logger.info("Loaded all neccessary data and system prompt")
        # logger.info(system_prompt)
        chat_history = [] # Initialize an empty list to maintain chat history

        user_input = system_prompt + prompt

        logger.info("User input: %s", user_input)
      
        message = [ChatMessage(role="user", content=system_prompt)]
        message.append(ChatMessage(role= "user", content=prompt))

        # Get the LLM's response using the BedrockConverse model
        chat_response = llm_model.chat(message)

        python_code = chat_response.message.blocks[0].text

        # Append the assistant's response to the history
        chat_history.append({"role": "assistant", "content": python_code})
        logger.info("Resulting python code:")
        logger.info(python_code)
        query = parse(python_code)
        if not query:
            logger.warning("No executable code found in the response.")
        q = query[0]
        local_vars = {
                    "os": os,
                    "pydicom": pydicom,
                    "plt": plt,
                    "io": io,
                    "pd": pd,
                    "df_IDC": df_IDC,
                    "df_BIH": df_BIH
                    }
        exec(q, globals(), local_vars)
        # print(res_query)
        result = local_vars.get("res_query_json", None)
        if result is None:
            result = local_vars.get("res_query", "No explicit result returned.")
        logger.info(result)
        logger.debug(f"RETURNING OBJECT OF TYPE: {type(result)} !")

        # Now, wrap the result in our standardized dictionary format
        if isinstance(result, go.Figure):
            logger.info("Formatting Plotly figure into standard response.")
            return result.to_json()

        elif isinstance(result, matplotlib.figure.Figure):
            logger.info("Formatting Matplotlib figure into standard response.")
            buf = io.BytesIO()
            result.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            # Encode the binary image data to a Base64 string
            image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            return image_base64

        elif isinstance(result, pd.DataFrame) or isinstance(result, pd.Series):
            logger.info("Formatting DataFrame into standard response.")
            return result.to_json(orient='split')

        else:
            # Fallback for unknown types
            logger.warning(f"Result is of an unhandled type: {type(result)}. Returning as is.")
            return  json.dumps(result)
        return result
    except Exception as e:
        logger.error(f"Exception {e} fired")
        return f"Error executing code: {e}"

idc_query_tool = FunctionTool.from_defaults(
    name = "idc_query", 
    fn = idc_query,
    description = """
    <Summary>
        Query imaging collection metadata (IDC, MIDRC, TCIA, etc.) and optionally prepare results for analysis. Executes generated Python
        code against indexed dataframes (df_IDC, df_MIDRC) and returns serialized JSON or Plotly JSON for downstream agents.
    </Summary>

    <Input>
        query_text (string, required): The user's question verbatim describing the imaging query (e.g., 'List CT lung collections with >10,000 instances').
        source (enum['IDC','MIDRC','multi'], optional; default inferred): Which imaging resource(s) to query.
        return (enum['records','plotly_json'], optional): Output format preference (records JSON or Plotly JSON).
        Note: This tool expects indexed dataframes available in the environment (df_IDC and df_MIDRC) and will execute generated code against them.
    </Input>

    <Output>
        records_json (string, JSON orient='records') and/or plotly_json (string): Query results in the requested format. The function
        serializes pandas DataFrames (df.to_json) or Plotly figures (fig.to_json) before returning.
    </Output>

    <Notes>
        Constraint: If local data paths are provided, validate file existence before processing.
    </Notes>

    <Examples>
        {'query_text': 'List CT lung collections with >10,000 instances', 'source': 'IDC'}
    </Examples>
    """
)
idc_query_tool.subnode = "IDC"

async def IDC_viz_slider_tool(url: str, args):

    viz_task = Task(
        user_msg = args.get("prompt") or "",
        files = [],
        kwargs = {"image_path":url})
    viz_tool = VizSliderAgent()
    try:
        result_fig = await viz_tool.run(viz_task, ConversationState())
        logger.info(f"""Resulting figure of type {type(result_fig.output)} with artifacts {result_fig.artifacts}""")
        fig = result_fig.output
        # If caller provided a presigned_s3_client in args, upload the figure to S3 and return a small metadata dict
        presigned = args.get("presigned_s3_client") or args.get("presigned_s3")
        if presigned and hasattr(presigned, "upload_file"):
            try:
                # Upload Plotly figures as JSON
                if isinstance(fig, go.Figure):
                    fig_json = fig.to_json().encode('utf-8')
                    object_key = f"plots/{uuid.uuid4()}.json"
                    upload = await presigned.upload_file(object_key=object_key, mime="application/json", data=fig_json)
                    url = upload.get("url")
                    return {"format": "plotly_json", "objectKey": object_key, "url": url, "artifacts": result_fig.artifacts}

                # Upload Matplotlib figures as PNG
                if isinstance(fig, matplotlib.figure.Figure):
                    buf = io.BytesIO()
                    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
                    buf.seek(0)
                    object_key = f"plots/{uuid.uuid4()}.png"
                    upload = await presigned.upload_file(object_key=object_key, mime="image/png", data=buf.getvalue())
                    url = upload.get("url")
                    return {"format": "image_png", "objectKey": object_key, "url": url, "artifacts": result_fig.artifacts}
            except Exception as e:
                logger.exception(f"S3 upload failed: {e}")
                # Fall back to returning the figure directly if upload fails
        # Fallback: return the raw figure object
        return fig
    except Exception as e:
        logger.error(f"Exception {e} fired")
        return f"Error running vizualiation slider"

idc_slider_visualization_tool = FunctionTool.from_defaults(
    name = "idc_slider_visualization", 
    fn = IDC_viz_slider_tool,
    description = """
    <Summary>
        Create an interactive slice slider for a 3D CT/MR with optional mask overlays. When a `presigned_s3_client` is provided in
        the `args` passed to the tool, the produced figure is uploaded to S3 and the tool returns a small metadata dictionary
        instead of the full figure payload. This avoids sending large Plotly JSON blobs between agents.
    </Summary>

    <Input>
        image_path (string) OR image_array (ndarray, required): Path to image or in-memory image array.
        mask_paths (array<string>) OR mask_arrays (array<ndarray>, optional): Mask file paths or arrays for overlays.
        alpha (float, optional, 0-1; default 0.4): Transparency for mask overlays.
        cmaps (array<string>, optional): Color maps for overlays.
        window_center (float, optional): Window center for image display.
        window_width (float, optional): Window width for image display.
        per_slice_minmax (bool, optional; default true if no WL/WW): Compute per-slice min/max if no WL/WW provided.
        interactive (bool, optional; default true): Whether the visualization is interactive.
        max_dim (int, optional; default 512): Max display dimension to scale images.
        presigned_s3_client (optional): Instance with an `upload_file` coroutine (e.g., `PreSignedS3Client`). If provided, the tool
            will upload the generated figure to S3 and return metadata pointing to the uploaded object.
    </Input>

    <Output>
        If `presigned_s3_client` is provided and upload succeeds, returns a dict with the following keys:
            - `format`: string, one of `plotly_json` or `image_png` indicating the serialized payload type stored in S3.
            - `objectKey`: S3 object key where the payload was stored (e.g., `plots/<uuid>.json`).
            - `url`: presigned GET URL for the uploaded object.
            - `artifacts`: optional list of additional artifacts from the visualization agent.

        Fallback behavior: if no presigned client is provided or upload fails, the tool will return the raw figure object
        produced by the visualization agent (a `plotly.graph_objects.Figure` or `matplotlib.figure.Figure`).
    </Output>

    <Examples>
        {'image_path': 's3://bucket/sample.nii.gz', 'mask_paths': ['s3://bucket/lung_mask.nii.gz']}
    </Examples>
    """,
)
idc_slider_visualization_tool.subnode = "IDC"
# Now MIDRC query performs the same functionality as IDC and in addition MIDRC, so idc_python_query is not needed
tools = [idc_query_tool, idc_slider_visualization_tool]