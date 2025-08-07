from llama_index.core.tools import FunctionTool
import pandas as pd
from idc_index import index
import re
import os
import io
import pydicom
import matplotlib.pyplot as plt
from llama_index.core.llms import ChatMessage
from workflow_config.default_settings import Settings
from log_helper.logger import get_logger
logger = get_logger()

def parse(chat_response):
      code_blocks = re.findall(r"```(.+?)```", chat_response, re.DOTALL)
      if len(code_blocks)>0:
        code_blocks[0] = code_blocks[0].replace('python','')
        code_blocks[0] = code_blocks[0].replace(';','')
        code_blocks[0] = code_blocks[0]
      return code_blocks

def generate_python_IDC(prompt):
      pretext= 'Please be as specific as possible and only return the final python code enclosed in ```. \
      Do not provide explanations. I have created a dataframe using the package idc-index. \
      This data frame was created using the following command: client = index.IDCClient(); df = client.index. Assume df is already present. \
      Using the pandas dataframe, df which has data fields such as: \
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
      Make sure the queries are case insensitive and use Regex wherever necessary. Write a python script to do the following and store the final output to a variable called res_query.\
      If the user wants to download data, use the following 2 commands: client = index.IDCClient(); client.download_from_selection(seriesInstanceUID=selected_series, downloadDir=".") \
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
      Make sure the queries are case insensitive and use Regex wherever necessary.\
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
      Always serialize your dataframe using df.to_json(orient="records"). Always serialize plotly figures using fig.to_json().'

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

def text2cohort(prompt):
      client = index.IDCClient()
      df = client.index
      try:
          python_code = generate_python_IDC(prompt)
          logger.info("Resulting python code:")
          logger.info(python_code)
          query = parse(python_code)
          if not query:
                logger.warning("No executable code found in the response.")
          q = query[0]
          local_vars = {'df': df}
          exec(q, globals(), local_vars)
          # print(res_query)
          result = local_vars.get("res_query_json", None)
          if result is None:
               result = local_vars.get("res_query", "No explicit result returned.")
          logger.info(result)
          return str(result)
      except Exception as e:
          return f"Error executing code: {e}"

idc_python_query = FunctionTool.from_defaults(
    name = "text2cohort", 
    fn = text2cohort,
    description = (f"""Useful for responding on any questions asked about Imaging Data Commons (IDC) \
                        Expects to receive user query as was entered by the user, generates python code, \
                        executes the generated code and returns back the result of the executed code.\
                        Can respond to questions related to different collections or datasets on IDC,\
                        for example: Modality: modality of the images or imaging datasets (e.g., CT, MR, PT (for PET), etc.),\
                        BodyPartExamined: body part examined (for example, brain or lung, etc.), \
                        SeriesDescription: Different series or sequences contained within a dataset (e.g., MR contains DWI, T1WI, etc.), \
                        PatientID: ID of different patients, PatientSex: Sex of different patients (e.g., M for male), \
                        PatientAge: Age of different patients, \
                        Manufacturer: Scanner manufacturer, \
                        ManufacturerModelName: Name of the scanner model, \
                        instanceCount: Number of images in the series \
                        StudyDescription: Description of the studies, \
                        SeriesInstanceUID: Series IDs, \
                        These were the commonly queried data fields. There are other data fields as well. \
                        User can also ask to download data and visualize and analyze image data, this tool has access to the following:\
                        1) DICOM to NIfTI conversion. 2) Image visualization tools for viewing DICOM and NIfTI images. \
                        3) Segmentation which supports organ and lesion segmentation from CT/MRI NIfTI files. \
                        4) Radiomics extraction tool, which computes shape, first-order, and texture features from segmented regions. \
                        The user might provide path to local data for further analysis.\
                        Output:\
	                    This tool returns a serialized JSON string representing the processed data.\
	                    The data is prepared and formatted into a pandas.DataFrame within the function,\
	                    but is serialized into JSON using df.to_json(orient="records") before returning.\
	                    The JSON string allows easy transmission to downstream agents that handle plotting or additional analysis.\
	                    The tool may also return serialized Plotly figure objects (using fig.to_json()) if requested.\
	                    Important: This tool's sole responsibility is data preparation and (optionally) pre-serialization.\
	                    It does not directly generate images, but returns structured data suitable for visualization by separate agents.                   
                        """)
)


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
                instanceCount: Numbre of images in the series \
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
          return str(result)
      except Exception as e:
          return f"Error executing code: {e}"

midrc_python_query = FunctionTool.from_defaults(
    name = "MIDRC_text2cohort", 
    fn = MIDRC_text2cohort,
    description = (f"""Useful for responding on any questions asked about imaging data resource platforms like \
                        Medical Imaging and Data Resource Center (MIDRC), Imaging Data Commons (IDC), Stanford AIMI, NIHCC, TCIA, ACR DART\
                        Expects existance of two dataframes. First dataframe df_IDC contains all the data for the platform IDC \
                        Second data frame df_MIDRC contains the multi-source indexed dataframe\
                        This index contains study level data from multiple source or public platforms including IDC, MIDRC, TCIA, among others\
                        Expects to receive user query as was entered by the user, generates python code, \
                        executes the generated code and returns back the result of the executed code.\
                        Can respond to questions related to different collections or datasets on IDC,\
                        for example: Modality: modality of the images or imaging datasets (e.g., CT, MR, PT (for PET), etc.),\
                        BodyPartExamined: body part examined (for example, brain or lung, etc.), \
                        SeriesDescription: Different series or sequences contained within a dataset (e.g., MR contains DWI, T1WI, etc.), \
                        PatientID: ID of different patients, PatientSex: Sex of different patients (e.g., M for male), \
                        PatientAge: Age of different patients, \
                        Manufacturer: Scanner manufacturer, \
                        ManufacturerModelName: Name of the scanner model, \
                        instanceCount: Number of images in the series \
                        StudyDescription: Description of the studies, \
                        SeriesInstanceUID: Series IDs, \
                        These were the commonly queried data fields. There are other data fields as well. \
                        User can also ask to download data and visualize and analyze image data, this tool has access to the following:\
                        1) DICOM to NIfTI conversion. 2) Image visualization tools for viewing DICOM and NIfTI images. \
                        3) Segmentation which supports organ and lesion segmentation from CT/MRI NIfTI files. \
                        4) Radiomics extraction tool, which computes shape, first-order, and texture features from segmented regions. \
                        The user might provide path to local data for further analysis.\
                        Output:\
	                    This tool returns a serialized JSON string representing the processed data.\
	                    The data is prepared and formatted into a pandas.DataFrame within the function,\
	                    but is serialized into JSON using df_IDC.to_json(orient="records") or df_MIDRC.to_json(orient="records") before returning.\
	                    The JSON string allows easy transmission to downstream agents that handle plotting or additional analysis.\
	                    The tool may also return serialized Plotly figure objects (using fig.to_json()) if requested.\
	                    Important: This tool's sole responsibility is data preparation and (optionally) pre-serialization.\
	                    It does not directly generate images, but returns structured data suitable for visualization by separate agents.                   
                        """)
)
# Now MIDRC query performs the same functionality as IDC and in addition MIDRC, so idc_python_query is not needed
tools = [midrc_python_query]