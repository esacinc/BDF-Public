import json, requests
import ppx
import posixpath as pp
import pyteomics.mztab as mztab
import gzip as gz
import shutil
from llama_index.core.tools import FunctionTool


# This is a set of helper function for retrieving and processing data from proteome exchange

def get_data_from_proteome_exchange(px_id: str):
    """
    Returns the data for a give proteome exchange ID
    Parameters:
        px_id: A valid proteome exchange ID
    Returns:
        JSON of the returned values
    """
    px_url = 'https://www.ebi.ac.uk/pride/ws/archive/v3/projects/'+px_id
    response = requests.get(px_url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        return jData
    else:
        response.raise_for_status()
        return "No data found for proteome exchange ID:" + px_id

def get_peptide_information_from_px(px_id: str, peptide: str):
    """
    Returns information about a given peptide from proteome exchange for a given study
    """
    proj = ppx.find_project(px_id)
    mzTabFiles = proj.remote_files("*.mzTab")
    if len(mzTabFiles) > 0:
        download = proj.download(mzTabFiles[0])
        path_to_file = str(pp.abspath(download[0]))
        tables = mztab.MzTab(path_to_file)
        psms = tables.spectrum_match_table
        if len(psms[psms['sequence']==peptide]) > 0:
            df = psms[psms['sequence']==peptide]
            json_str = df.to_json(orient='records')
            return json_str
        else:
            return f"Peptide {peptide} not found in mzTab files for this study"    
    mzTabGzFiles = proj.remote_files("*.mzTab.gz")
    if len(mzTabGzFiles) > 0:
        download = proj.download(mzTabGzFiles[0])
        path_to_file = str(pp.abspath(download[0]))
        with gz.open(path_to_file, 'rb') as f_in:
            out_file = path_to_file.replace(".gz", "")
            with open(out_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
                tables = mztab.MzTab(out_file)
                psms = tables.spectrum_match_table
                if len(psms[psms['sequence']==peptide]) > 0:
                    df = psms[psms['sequence']==peptide]
                    json_str = df.to_json(orient='records')
                    return json_str
                else:
                    return f"Peptide {peptide} not found in mzTab files for this study"

def get_disease_based_data_from_px(disease_name: str):
    """
    Returns the proteome exchange data for a given disease
    Parameters:
        disease_name: A disease name like breast cancer, colon cancer, etc.
    Returns:
        JSON of the returned values
    """
    px_url = 'https://www.ebi.ac.uk/pride/ws/archive/v3/search/projects?keyword=' + disease_name + '&pageSize=10&page=0&sortDirection=DESC&sortFields=submissionDate'     
    response = requests.get(px_url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        return jData
    else:
        response.raise_for_status()
        return "No data found for " + disease_name + " in proteome exchange." 

proteome_exchange_project_tool = FunctionTool.from_defaults(
    name = "get_data_from_proteome_exchange", 
    fn = get_data_from_proteome_exchange,
  
    description = (f"""Useful for getting project information for a given study from Proteome Exchange.
                Study IDs are specified in PX[Y]* format where Y is a string of alpha numeric characters.
                Use this function if the user wants to know about a specific project or sample given 
                   a proteome exchange ID """)
)
proteome_exchange_peptide_tool = FunctionTool.from_defaults(
    name = "get_peptide_from_proteome_exchange", 
    fn = get_peptide_information_from_px,
  
    description = (f"""Useful for getting information about a given peptide from a given study in Proteome exchange.
                Proteome Exchange Study IDs are specified in PX[Y]* format where Y is a string of alpha numeric characters.
                Use this function if the user wants to know about a specific peptide and a specific project given 
                by proteome exchange ID """)
)
proteome_exchange_disease_tool = FunctionTool.from_defaults(
    name = "get_disease_based_data_from_px", 
    fn = get_disease_based_data_from_px,
  
    description = (f"""Useful for getting list of studies from proteome exchange for a given disease.
                   Returns the last 10 studies submitted by PX. The list is sorted by descending submission dates. """)
)

tools = [
    proteome_exchange_project_tool,
    proteome_exchange_peptide_tool,
    proteome_exchange_disease_tool
    ]