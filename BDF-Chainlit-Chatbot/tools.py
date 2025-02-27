from typing import Any, List
#from llama_index.llms.openai import OpenAI
import asyncio, json, requests
from pydantic.fields import Field
import sys
from io import StringIO

from typing import Any, Awaitable, Optional, Callable, Type, List, Tuple, Union, cast
import boto3
from pydantic import BaseModel
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import FunctionCallingAgent
import pandas as pd;
import ppx
import pyteomics.mztab as mztab
import posixpath as pp
import gzip as gz
import shutil
pdc_url = 'https://proteomic.datacommons.cancer.gov/graphql?query='

# Helper function to cache all diseases and primary sites from PDC
# TO DO: Use a proper metadata source for these values e.g. PDC Dictionary or caDSR
def getAllDiseasesAndPrimarySites():
    all_studies = []
    all_studies_map = {}
    print('Caching studies')
    # Cache all studies
    url = pdc_url
    url += '''{allPrograms 
                   { 
                    projects  
                      {  
                        studies  
                          { pdc_study_id study_submitter_id submitter_id_name 
                            analytical_fraction study_name disease_types 
                            primary_sites  experiment_type acquisition_type
                          } 
                        }
                    }
                }'''
    response = requests.get(url)
    if(response.ok):
        study_list = json.loads(response.content)
        study_list = study_list['data']['allPrograms']
        #print(study_list)
        for programs in study_list:
            for projects in study_list:
                for project in projects['projects']:
                    for study in project['studies']:
                        #print(study, project['project_id'])
                        all_studies.append(study)
                        all_studies_map[study['pdc_study_id']] = study
    url = pdc_url + '''{allPrograms {program_id  
                program_submitter_id  name 
                projects  {
                    project_id  project_submitter_id  name  
                    studies  {
                        pdc_study_id study_id study_submitter_id submitter_id_name 
                        analytical_fraction study_name disease_types 
                        primary_sites  
                        experiment_type acquisition_type} }}}'''
    response = requests.get(url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        jData = jData['data']['allPrograms']
        return all_studies, jData
    else:
      # If response code is not ok (200), print the resulting http error code with description
      response.raise_for_status()
        

# This is a helper function
def getDiseaseInformation(mdata:object)->str:
    '''
    Given a disease or a primary site, returns all the matching studies including disease name, primary site and study id.
    '''   
    # This function is very inefficient - it should be replaced by a direct PDC API call
    if None in mdata['disease_type'] and None in mdata['primary_site']:
        return {'mdata':{}, 'original_message':inp['original_message'], 'data':{}}
        
    url = pdc_url
    url += '''{allPrograms 
                   { 
                    projects  
                      {  
                        studies  
                          { pdc_study_id study_submitter_id submitter_id_name 
                            analytical_fraction study_name disease_types 
                            primary_sites  experiment_type acquisition_type
                          } 
                        }
                    }
                }'''
    response = requests.get(url)
    if(response.ok):
        all_studies = []
        x = json.loads(response.content)
        x = x['data']['allPrograms']
        study_list = x
        #print(study_list)
        matching_data = {}
        # Match the disease_type field with metadata_filter['disease_type']
        for disease_type in mdata['disease_type']:
            for projects in study_list:
                for project in projects['projects']:
                    for study in project['studies']:
                        if disease_type in study['disease_types']:
                            matching_data[study['pdc_study_id']] = study  
        for primary_site in mdata['primary_site']:
            for projects in study_list:
                for project in projects['projects']:
                    for study in project['studies']:
                        if primary_site in study["primary_sites"]:
                            matching_data[study['pdc_study_id']] = study
                        
        X = list(matching_data.values())
        
        return {'mdata': mdata, 'data': X}
        #return json.dumps(matching_data, sort_keys=True)
    else:
      # If response code is not ok (200), print the resulting http error code with description
      response.raise_for_status()    

pdc_url = 'https://proteomic.datacommons.cancer.gov/graphql?query='
def list_studies(mdata: object)->object:
    """ Useful for getting a list of studies matching the input. It expects an object with two keys: disease_type and primary_site.
    Returns all the matching studies including disease name, primary site and study id.
    """
    # This function is very inefficient - it should be replaced by a direct PDC API call
    if None in mdata['disease_type'] and None in mdata['primary_site']:
        return {'mdata':{}, 'original_message':inp['original_message'], 'data':{}}
    
    url = pdc_url
    url += '''{allPrograms 
                   { 
                    projects  
                      {  
                        studies  
                          { pdc_study_id study_submitter_id submitter_id_name 
                            analytical_fraction study_name disease_types 
                            primary_sites  experiment_type acquisition_type
                          } 
                        }
                    }
                }'''
    response = requests.get(url)
    if(response.ok):
        all_studies = []
        x = json.loads(response.content)
        x = x['data']['allPrograms']
        study_list = x
        #print(study_list)
        matching_data = {}
        # Match the disease_type field with metadata_filter['disease_type']
        if 'disease_type' in mdata:
            for disease_type in mdata['disease_type']:
                for projects in study_list:
                    for project in projects['projects']:
                        for study in project['studies']:
                            if disease_type in study['disease_types']:
                                matching_data[study['pdc_study_id']] = study  
        if 'primary_site' in mdata:
            for primary_site in mdata['primary_site']:
                for projects in study_list:
                    for project in projects['projects']:
                        for study in project['studies']:
                            if primary_site in study["primary_sites"]:
                                matching_data[study['pdc_study_id']] = study
                        
        X = list(matching_data.values())
        
        return {'mdata': mdata, 'data': X}
        #return json.dumps(matching_data, sort_keys=True)
    else:
      # If response code is not ok (200), print the resulting http error code with description
      response.raise_for_status()     

# Internal function - Returns a map of the external data to internal PDC IDs
def get_external_gdc_references(study_id=None):
    if study_id is None:
        return {}
    else:
        url = pdc_url + '{ biospecimenPerStudy (pdc_study_id: "' + study_id + '"){ '
        url += ' case_id aliquot_id aliquot_submitter_id externalReferences { external_reference_id reference_resource_shortname '
        url += ' reference_resource_name reference_entity_location }} }'
        response = requests.get(url)
        ref_map = {}
        if(response.ok):
         #If the response was OK then print the returned JSON
            jData = json.loads(response.content)
            jData = jData['data']['biospecimenPerStudy']
            for e in jData:
                for extRef in e['externalReferences']:
                    #print(extRef)
                    if extRef['reference_resource_shortname'] == 'GDC':
                        ref_id = extRef['reference_entity_location'].split('/')[-1]
                        ref_map[e['aliquot_submitter_id']] = ref_id
            return ref_map
        else:
            return {}

            
post_url = "https://proteomic.datacommons.cancer.gov/graphql"
def get_gene_expression_data(gene_list, study_id=None)->str:
    '''Useful for getting gene expression data given a list of genes for a specific study.
    If no genes are specified it returns the whole dataset.'''
    if study_id is None:
        return ''
    
    if study_id is not None:
        data_type = 'log2_ratio'  # Retrieves CDAP iTRAQ or TMT data
        
        quant_data_query = '{ quantDataMatrix(pdc_study_id: "' + study_id +'" data_type: "log2_ratio" acceptDUA: true )}'
        
        pdc_response = requests.post(post_url, json={'query': quant_data_query})
        # Check the results
        if pdc_response.ok:
            # Decode the response
            response = pdc_response.json()
            matrix = response['data']['quantDataMatrix']
            if matrix is None:
                print("Invalid study ID")
                return {}
            ga = pd.DataFrame(matrix[1:], columns=matrix[0]).set_index('Gene/Aliquot')

            #oldnames = list(ga.columns)
            #newnames = [ x.split(':')[0] for x in oldnames ]
            #ga.rename(columns=dict(zip(oldnames, newnames)), inplace=True)

            ga = ga.sort_index(axis=1)
            for col in ga.keys():
                ga[col] = pd.to_numeric(ga[col], errors='coerce')
            
            mask_na = 0.000666
            ga = ga.fillna(mask_na)
            
            # Filter only the genes of interest
            
            df = pd.DataFrame()
            if len(gene_list) < 1:
                df = ga
            else:
                for gene in gene_list:
                    if gene in ga.index:
                        idx = ga.index.get_loc(gene)
                        x = ga.iloc(0)[int(idx)]
                        df1 = pd.DataFrame(x)
                        df = pd.concat([df, df1], axis=1)
                    else:
                        print("Gene ", gene, " does not exists or not expressed")
            df.reset_index(inplace=True)
            df = df.rename(columns={'index': 'sample_id'})
            df[['case_id', 'aliquot_submitter_id']] = df['sample_id'].str.split(':', expand=True)
            #lables = df['sample_id'].values
            # Get metadata
            metadata_query = '''
                    {
                        clinicalMetadata(pdc_study_id: "''' + study_id + '''" acceptDUA: true) {
                            aliquot_submitter_id
                            morphology
                            primary_diagnosis
                            tumor_grade
                            tumor_stage
                        }
                    }
                    '''
            url = 'https://pdc.cancer.gov/graphql'

            # Send the POST graphql query
            print('Sending query.')
            pdc_response = requests.post(url, json={'query': metadata_query})
            print(pdc_response)
            # Check the results
            if pdc_response.ok:
                # Decode the response
                decoded = pdc_response.json()
                clin_matrix = decoded['data']['clinicalMetadata']
                metadata = pd.DataFrame(clin_matrix, columns=clin_matrix[0]).set_index('aliquot_submitter_id')
                metadata = metadata.sort_index(axis=0)
                df2 = metadata.reset_index()
                df = pd.merge(df, df2, left_on='aliquot_submitter_id', right_on='aliquot_submitter_id', how='inner')
                # Map the IDs to match the external GDC IDs so we can make comparisons
                # across samples
                replace_dict = get_external_gdc_references(study_id)
                df.replace({'aliquot_submitter_id':replace_dict}, inplace=True)
                df.drop(columns=['sample_id', 'case_id'], inplace=True)
                
                # We do this replacement so the LLM can match column names deterministically
                # instead of guessing as GDC column names are sample_ids
                df.rename(columns={'aliquot_submitter_id':'sample_id'}, inplace=True)

                # Check if too much data is being returned - max input token size is 200000000 tokens approx.
                
                str_value = df.to_json()
                print ("Len of output data:", len(str_value))
                if len(str_value) > 799000:
                    print("Results too large for LLM to handle")
                    return ''
                else:
                    return json.loads(str_value)
            else:
                return pdc_response.raise_for_status()
        else:
            # Response not OK, see error
            return pdc_response.raise_for_status()

def has_external_genomic_data(study_id)->object:
    '''This function is used to determin if a given study has corresponding data in an external
    database like GDC'''
    url = pdc_url + '{ biospecimenPerStudy (pdc_study_id: "' + study_id + '"){ '
    url += ' externalReferences { external_reference_id reference_resource_shortname '
    url += ' reference_resource_name reference_entity_location }} }'
    response = requests.get(url)
    if(response.ok):
         #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        # Make sure its a valid study:
        if len(jData['data']['biospecimenPerStudy']) == 0:
            return "Not a valid study"
        ext_ref_list = jData['data']['biospecimenPerStudy'][0]
        print(ext_ref_list)
        if len(ext_ref_list['externalReferences'])>0 and ext_ref_list['externalReferences'][0]['reference_resource_shortname'] == 'GDC':
            return json.loads('{"genomic_data": "Yes, genomic data is available in GDC"}')
        else:
            return json.loads('{"genomic_data": "No, genomic data is not available in GDC"}')

# Return the matching gdc gene expression data
def get_matches_from_gdc(study_id, ensembl_ids)->pd.DataFrame:
    '''This function is used to return the gene expression for the given ensembl ids '''
    url = pdc_url + '{ biospecimenPerStudy (pdc_study_id: "' + study_id + '"){ '
    url += ' case_id aliquot_id aliquot_submitter_id externalReferences { external_reference_id reference_resource_shortname '
    url += ' reference_resource_name reference_entity_location }} }'
    response = requests.get(url)
    ret_val = []
    if(response.ok):
         #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        jData = jData['data']['biospecimenPerStudy']
        if len(jData[0]['externalReferences']) > 0:
            for case in jData:
                for er in case['externalReferences']:
                    if er['reference_resource_shortname']=='GDC':
                        ret_val.append({'pdc_case_id':case['case_id'], 'pdc_aliquot_id':case['aliquot_submitter_id'],
                                        'gdc_case_id':er['reference_entity_location'].split('/')[-1]})
        else:
            return []            
        df_gdc = pd.json_normalize(ret_val)
        # Define the URL
        url = 'https://api.gdc.cancer.gov/gene_expression/values'

        # Define the headers
        headers = {
            'accept': 'text/tab-separated-values',
            'Content-Type': 'application/json'   
        }

        # Define the payload
        payload = {
            "case_ids": df_gdc['gdc_case_id'].astype(str).tolist(),
            "gene_ids": ensembl_ids,
            "tsv_units": "median_centered_log2_uqfpkm",
            "format": "tsv"
        }

        # Make the POST request
        response = requests.post(url, headers=headers, json=payload)
        TESTDATA = StringIO(response.text)

        df = pd.read_csv(TESTDATA, sep="\t")
        return df


# Return the study name based on Study ID.
def get_study_name(study_id):
    """Return the name of the study based on the study ID"""
    url = pdc_url + '{getPaginatedUIStudy(pdc_study_id: "' + study_id + '" limit: 10 offset: 0) {'
    url += 'uiStudies { pdc_study_id submitter_id_name project_name program_name disease_type primary_site analytical_fraction '
    url += 'experiment_type cases_count study_description } } }'
    response = requests.get(url)
    if(response.ok):
         #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        if len(jData['data']['getPaginatedUIStudy']['uiStudies'])> 0:
            jData = jData['data']['getPaginatedUIStudy']['uiStudies'][0]['submitter_id_name']
            return jData
        else:
            return ''
    else:
        return ''

def get_biospecimen_data(study_id):
    """ Useful for getting biospecimen information like aliquots, morphology, primary diagnosis, tumor grade, tumor stage, etc.
    Use this function only if the user is asking about aliquots, samples or cases."""    
    url = pdc_url + '''
    {
        clinicalMetadata(pdc_study_id: "''' + study_id + '''" acceptDUA: true) {
            aliquot_submitter_id
            morphology
            primary_diagnosis
            tumor_grade
            tumor_stage
        }
    }
    '''
    #url = pdc_url + '{ biospecimenPerStudy (pdc_study_id: "' + study_id + '"'
    #url += '){ aliquot_id sample_id case_id sample_type } }'
    response = requests.get(url)
    if (response.ok):
        jData = json.loads(response.content)
        jData = jData['data']['clinicalMetadata']
        df = pd.json_normalize(jData)
        if len(df)>0:
            df.sort_values('aliquot_submitter_id', inplace=True)
            return df.to_json(orient='records', index=False)
        else:
            return {}
        
    else:
        response.raise_for_status()


def get_clinical_and_demographic_data(study_name=None, study_id=None):
    """Useful for getting clinical diagnosis like tissue_or_organ_of_origin tumor_grade tumor_stage age_at_diagnosis classification_of_tumor days_to_recurrence  and demographic information like gender, race, ethnicity, etc. 
    for a give study id or a Study Name. Can be also used to get all clinical data if study id or name is not available"""
    if study_id is None and study_name is None:
        url = pdc_url + '{getPaginatedUIClinical( '
        url += ' limit: 1000000, offset: 0) {'
        url += 'uiClinical { program_name case_id case_submitter_id gender race ethnicity morphology primary_diagnosis site_of_resection_or_biopsy'
        url += ' tissue_or_organ_of_origin tumor_grade tumor_stage age_at_diagnosis classification_of_tumor days_to_recurrence'
        url += '}}}'
        response = requests.get(url)
        if(response.ok):
            #If the response was OK then print the returned JSON
            jData = json.loads(response.content)
            jData = jData['data']['getPaginatedUIClinical']['uiClinical']
            # convert to dataframe and sort on case id
            df = pd.json_normalize(jData)
            df.sort_values('case_id', inplace=True)
            return df.to_json(orient='records', index=False)
        
            #return jData
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()
    elif study_id is None:
        url = pdc_url + '{getPaginatedUIClinical( '
        url += 'study_name: "' + study_name +'" limit: 1000000, offset: 0) {'
        url += 'uiClinical { program_name case_id case_submitter_id gender race ethnicity morphology primary_diagnosis site_of_resection_or_biopsy'
        url += ' tissue_or_organ_of_origin tumor_grade tumor_stage age_at_diagnosis classification_of_tumor days_to_recurrence'
        url += '}}}'
        response = requests.get(url)
        if(response.ok):
            #If the response was OK then print the returned JSON
            jData = json.loads(response.content)
            jData = jData['data']['getPaginatedUIClinical']['uiClinical']
            df = pd.json_normalize(jData)
            df.sort_values('case_id', inplace=True)
            return df.to_json(orient='records', index=False)
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()
    elif study_name is None:
        jData = get_study_name(study_id=study_id)
        if len(jData)>0:
            return get_clinical_and_demographic_data(jData)
        else: 
            return {}

def get_external_genomic_data(study_id: str, gene_names: List):
    """ Get data from GDC based on study name"""
    ensmbl_ids = gene_name_to_ensembl_mapping(gene_names)
    print("Ensembl IDs: ", ensmbl_ids)
    e_ids = []
    replace_dict = {}
    for e in ensmbl_ids:
        e_ids.append(e['ensembl_id'])
        replace_dict[e['ensembl_id']] = e['gene_name']
    df = get_matches_from_gdc(study_id, e_ids)
    if len(df) < 1:
        print("No external genomic data found")
        return 'No external genomic data found for this study'
    df.replace({'gene_id':replace_dict}, inplace=True)
    df2 = pd.DataFrame()
    col_idx = 0
    for gene in gene_names:
        if gene in list(df['gene_id']):
            idx = df[df['gene_id']==gene].index[0]
            x = df.iloc(0)[int(idx)]
            df1 = pd.DataFrame(x)
            df1 = df1.rename(columns={idx:gene})
            col_idx += 1
            df2 = pd.concat([df2, df1], axis=1)
        else:
            print("Gene ", gene, " does not exists or not expressed")
    df2 = df2[1:]
    df2.reset_index(inplace=True)
    df2 = df2.rename(columns={'index': 'sample_id'})
    str_value = df2.to_json()
    print ("Len of output data:", len(str_value))
    if len(str_value) > 799000:
        print("Results too large for LLM to handle")
        return ''
    else:
        return json.loads(str_value)
    
def get_study_details(study_id: str=None, study_name: str=None):
    """Useful for getting details about a study and its participands 
    including age, gender, demographics given a study_id or a study name or a progam name"""
    if study_name is not None:
        return get_clinical_and_demographic_data( study_name=study_name, study_id=None)
    if study_id is not None:
        # Convert to study name
        study_name = get_study_name(study_id)
        if len(study_name)>0:
            return get_clinical_and_demographic_data(study_name=study_name, study_id=None)
        else:
            return {}
    else:
        url = pdc_url + '{getPaginatedUIStudy(program_name: "' + program_name + '" limit: 1000000 offset: 0) {'
        url += 'uiStudies { pdc_study_id submitter_id_name project_name program_name disease_type primary_site analytical_fraction '
        url += 'experiment_type cases_count study_description } } }'
    response = requests.get(url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        jData = jData['data']['getPaginatedUIStudy']['uiStudies']
        print("# of records: ", len(jData['data']['getPaginatedUIStudy']['uiStudies']))
        if len(jData['data']['getPaginatedUIStudy']['uiStudies']) > 0:
            df = pd.json_normalize(jData)
            df.sort_values('case_id', inplace=True)
            return df.to_json(orient='records', index=False)
        else:
            return {}
    else:
      # If response code is not ok (200), print the resulting http error code with description
      response.raise_for_status()        

def get_gene_details(study_id: str=None, study_name: str=None, program_name: str=None):
    """Useful for getting gene details for a study_id or a study name or a progam name"""
    if study_name is not None:
        return get_gene_data(study_name, study_id=None)
    if program_name is None and study_id is not None:
        # Convert to study name
        study_name = get_study_name(study_id)
        return get_gene_data(study_name, study_id=None)
    else:
        url = pdc_url + '{getPaginatedUIGene(program_name: "' + program_name + '" limit: 1000000 offset: 0) {'
        url += 'uiGenes {gene_name chromosome locus num_study ncbi_gene_id proteins } } }'
    response = requests.get(url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        jData = jData['data']['getPaginatedUIGene']['uiGenes']
        return jData
    else:
      # If response code is not ok (200), print the resulting http error code with description
      response.raise_for_status()        

def get_gene_data(study_name=None, study_id=None):
    """Retrieves gene-level data. Genes are a functional unit of heredity which occupies a specific position on a particular chromosome and serves as the
    template for a product that contributes to a phenotype or a biological function."""
    if study_id is None and study_name is None:
        url = pdc_url + '{getPaginatedUIGene('
        url += ' limit: 1000000, offset: 0) {'
        url += 'uiGenes {gene_name chromosome locus num_study ncbi_gene_id proteins } } }'
        response = requests.get(url)
        if(response.ok):
            #If the response was OK then print the returned JSON
            jData = json.loads(response.content)
            jData = jData['data']['getPaginatedUIGene']['uiGenes']
            return jData
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()
    elif study_id is None:
        url = pdc_url + '{getPaginatedUIGene( '
        url += 'study_name: "' + study_name +'" limit: 1000000, offset: 0) {'
        url += 'uiGenes {gene_name chromosome locus num_study ncbi_gene_id proteins } } }'
        response = requests.get(url)
        if(response.ok):
            #If the response was OK then print the returned JSON
            jData = json.loads(response.content)
            jData = jData['data']['getPaginatedUIGene']['uiGenes']
            return jData
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()
    elif study_name is None:
        jData = get_gene_details(study_id=study_id)
        if len(jData)>0:
            study = jData[0]

def gene_name_to_ensembl_mapping(gene_name: List):
    """
    Convert a list of gene names to Ensembl ID using the Ensembl REST API.
    Parameters:
        gene_name (str): The gene name to convert.
        species (str): The species (default: "human").
        
    Returns:
        list: A list of matching gene_name ensemble_id pairs as a list or an empty list if none are found.
    """
    ret_val = []
    
    for g in gene_name:
        url = f"https://rest.ensembl.org/xrefs/symbol/human/{g}?"
        headers = {"Content-Type": "application/json"}

        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            #print(data)
            
            ensembl_ids = [entry["id"] for entry in data if entry["type"] == "gene"]
            #print(ensembl_ids)
            for e in ensembl_ids:
                if "ENS" in e:
                    ret_val.append({'gene_name':g, 'ensembl_id':e})
                    break
    return ret_val

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
    #print(f"Found {len(mzTabFiles) } mzTab files in study {px_id}")
    if len(mzTabFiles) > 0:
        download = proj.download(mzTabFiles[0])
        #print("MzTab download: ", pp.abspath(download[0]))
        path_to_file = str(pp.abspath(download[0]))
        #print(path_to_file)
        tables = mztab.MzTab(path_to_file)
        psms = tables.spectrum_match_table
        if len(psms[psms['sequence']==peptide]) > 0:
            df = psms[psms['sequence']==peptide]
            json_str = df.to_json(orient='records')
            return json_str
        else:
            return f"Peptide {peptide} not found in mzTab files for this study"
        #print(psms[psms['sequence']==peptide])
        #print(psms.columns)
        
    mzTabGzFiles = proj.remote_files("*.mzTab.gz")
    #print(f"Found {len(mzTabGzFiles) } mzTab gzipped files in study {px_id}")
    if len(mzTabGzFiles) > 0:
        download = proj.download(mzTabGzFiles[0])
        path_to_file = str(pp.abspath(download[0]))
        #print("Path to file: ", path_to_file)
        with gz.open(path_to_file, 'rb') as f_in:
            out_file = path_to_file.replace(".gz", "")
            #print(out_file)
            with open(out_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
                tables = mztab.MzTab(out_file)
                psms = tables.spectrum_match_table
                #print(psms.columns)
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
    
def get_study_metstat_from_mw(analysis_type=None, polarity=None, chromatography=None, species=None, sample_source=None, disease=None, kegg_id=None, refmet_name=None):
    """
    Returns Metabolite report for studies on the Metabolomics Workbench
    Parameters:
        analysis_type: different types of metabolomics analysis including ALL MS, LCMS, GCMS, NMR. Do not add - in analysis_type
        polarity: POSITIVE or NEGATIVE
        chromatography: a technique that uses chromatography to analyze metabolites including Reversed phase, Normal phase, HILIC, GC, Phenyl, etc.
        species: species (default: "human").
        sample_source: example of sample_source including Blood, Urine, Saliva, Breast, etc.
        disease: disease (default: "cancer").
    Returns:
        JSON of the returned values
    """
    mw_url = "https://www.metabolomicsworkbench.org/rest/metstat/"
    if analysis_type is not None:
        mw_url = mw_url+analysis_type
    mw_url = mw_url+';'
    if polarity is not None:
        mw_url = mw_url+polarity
    mw_url = mw_url+';'  
    if chromatography is not None:
        mw_url = mw_url+chromatography
    mw_url = mw_url+';'  
    if species is not None:
        mw_url = mw_url+species
    else:
         mw_url = mw_url+'Human'
    mw_url = mw_url+';'  
    if sample_source is not None:
        mw_url = mw_url+sample_source
    mw_url = mw_url+';'  
    if disease is not None:
        mw_url = mw_url+disease
    else:
        mw_url = mw_url+'Cancer'
    mw_url = mw_url+';'  
    if kegg_id is not None:
        mw_url = mw_url+kegg_id
    mw_url = mw_url+';'  
    if refmet_name is not None:
        mw_url = mw_url+refmet_name
    mw_url = mw_url+';'      
    print(f'Metabolomics Workbench url: {mw_url}')
    response = requests.get(mw_url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        return jData
    else:
        response.raise_for_status()
        return "No data found in metabolomics workbench." 

def get_study_details_from_mw(study_id: str):
    """
    Returns summary, samples, experimental variables, analysis information for a given study in Metabolomics Workbench
    Parameters:
        study_id: study id starting with ST.
    Returns:
        JSON of the returned values
    """
    have_data = False
    final_data = {}
    mw_url = "https://www.metabolomicsworkbench.org/rest/study/study_id/"+study_id
    
    response = requests.get(mw_url+"/summary")
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        final_data["study_summary"] = jData
        have_data = True

    response = requests.get(mw_url+"/factors")
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        final_data["study_samples_experimental_variables"] = jData
        have_data = True

    response = requests.get(mw_url+"/analysis")
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        final_data["study_analysis_information"] = jData
        have_data = True

    if have_data:
        return final_data
    else:
        response.raise_for_status()
        return "No data found in metabolomics workbench."     

all_studies, study_list = getAllDiseasesAndPrimarySites()
primary_sites_list = []
disease_types_list = []
for study in study_list:
    for project in study["projects"]:
        for study in project["studies"]:
            for primary_site in study["primary_sites"]:
                primary_sites_list.append(primary_site)
            for disease in study["disease_types"]:
                disease_types_list.append(disease)
primary_sites_list = list(set(primary_sites_list))
disease_types_list = list(set(disease_types_list))

def list_all_diseases(question:str) -> list[str]:
    """ Useful for getting all available disease or cancer types studied in PDC."""
    return disease_types_list
def list_all_primary_sites(question:str) -> list[str]:
    """ Useful for getting all available primary sites or organs where tissues are collected from in PDC """
    return primary_sites_list

disease_tools = FunctionTool.from_defaults(
    name=f"list_all_diseases",
    fn=list_all_diseases,
        
    description=(
        f"Useful for finding all the matching diseases in the question"
    ),
)
sites_or_organ_tools = FunctionTool.from_defaults(
     name=f"list_all_primary_sites",
    fn=list_all_primary_sites,
    description=(
        f"Useful for finding all the disease sites or organs studied in PDC"
    ),
)
list_study_tools = FunctionTool.from_defaults(
     name=f"list_studies",
    fn=list_studies,
    description=(f"""Useful for finding a study matching a disease and/or site. The disease names 
        and primary sites must be mapped to PDC terms using the list all disease tools and sites_or_organ tools first
        respectively before calling this function. 
        Use the values returned by these tools as the input to the list studies tool
        for the disease_type and primary site parameters.
        It expects an input object with two attribute lists: disease_type and primary_site"""
    ),
)

study_detail_tools = FunctionTool.from_defaults(
    name="get_study_details",
    fn = get_study_details,
    description = (f"""Useful for getting details of a given study including all demographic data 
                   age, gender, disease type, and other demographics for a given study ID 
                   or study name"""),
)

study_name_tool = FunctionTool.from_defaults(
    name="get_study_name",
    fn = get_study_name,

    description = (f"Useful for getting the name of the study based on the study ID")
)

gene_detail_tools = FunctionTool.from_defaults(
    name="get_gene_details",
    fn = get_gene_details,
  
    description = (f"Useful for finding all the data about genes and chromosomes given study ID or study name"),
)    
gene_expression_tools = FunctionTool.from_defaults(
    name = "get_gene_expression_data", 
    fn = get_gene_expression_data,
    description = (f"""Useful for getting individual gene level expression for a given study and a list of gene names from PDC. 
                    Use this function only for getting gene expression values from PDC. 
                   Gene names can be arbitrarily long list of gene names separated by commas or spaces.
                   Gene names should be converted to upper case before calling this tool and passed in as a list object.
                   If no genes are specified then just let the user know that you can only work with up to 20 genes at
                   a time due to memory restrictions and that you will do a search in the publications database for the answer.""")
)
external_genomic_data_tools = FunctionTool.from_defaults(
    name = "has_external_genomic_data", 
    fn = has_external_genomic_data,
  
    description = (f"""Useful for checking if a given study has external genomic data in GDC. Do not call this
                   tool if user only wants study details.
                   Return false if a valid ID is not provided""")
)

get_ensembl_ids = FunctionTool.from_defaults(
    name = "get_ensembl_ids", 
    fn = gene_name_to_ensembl_mapping,
    description = (f"""
        Useful for converting a list of gene names to Ensembl ID using the Ensembl REST API.
        Parameters:
            gene_name (list): A list of gene names to convert. This must be an array of strings.
        Returns:
            list: A list of matching gene_name ensemble_id pairs as a list.
    """)
)

external_data_tool = FunctionTool.from_defaults(
    name = "get_extenal_genomic_data", 
    fn = get_external_genomic_data,
    description = (f"""
        Useful for getting gene expression data from GDC
        Parameters:
            gene_name (list): A list of gene names to convert. This must be an array of strings.
            PDC_study_ID: A valid PDC study ID that has corrosponding patients in GDC.
            Maximum number of genes is five.
            DO NOT USE THIS UNLESS THE USER EXPLICITLY ASKS FOR EXTERNAL or data from GDC
        Returns: Gene expression data directly from GDC.
    """)
)
biospecimen_data_tools = FunctionTool.from_defaults(
    name = "get_biospecimen_data", 
    fn = get_biospecimen_data,
  
    description = (f"""Useful for getting sample or biospecimen or aliquot information for a given study. Study IDs are
                   specified by PDC000XXX where XXX is are numbers only. Use this function if the user
                   wants to know about samples, specimen IDs, cases, sample types. """)
)
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
metabolomics_workbench_metstat_tool = FunctionTool.from_defaults(
    name = "get_study_metstat_from_mw", 
    fn = get_study_metstat_from_mw,

    description = (f"""Useful for getting list of studies from metabolomics workbench. 
                   Split the disease term in a question into two parts, a sample source name and a disease. The following are some examples:
                        1. Breast Cancer - should result in sample_source: breast, disease: cancer
                        2. Brain Cancer - should result in sample_source: brain, disease: cancer
                        3. Glioblastoma - should result in sample_source: brain, disease: cancer
                        4. LUAD - should result in sample_source: lung, disease: cancer""")
)
metabolomics_workbench_study_tool = FunctionTool.from_defaults(
    name = "get_study_details_from_mw", 
    fn = get_study_details_from_mw,

    description = (f"""Useful for getting information about a given study in metabolomics workbench.
                       Study IDs are specified in ST[Y]* format where Y is a string of alpha numeric characters.
                       Use this function if the user wants to know about a study in metabolomics workbench given
                       a study ID """)
)
tools = [disease_tools, sites_or_organ_tools,
         list_study_tools, 
         study_detail_tools, 
         gene_expression_tools,
         proteome_exchange_project_tool,
         proteome_exchange_peptide_tool,
         proteome_exchange_disease_tool,
        biospecimen_data_tools,
        get_ensembl_ids,
        external_data_tool,
        metabolomics_workbench_metstat_tool,
        metabolomics_workbench_study_tool,
        ]

class Metadata(BaseModel):
    """Metadata like disease names and organ sites detected from a question"""

    disease_type: str = Field(default=None, description="All the disease types mentioned in the message as a comma separated list. Here are some possible disease types : 'breast cancer', 'colon cancer', 'melanoma', 'GBM', 'sarcoma' or 'glioblastoma'")
    primary_site: str = Field(default=None, description="All the primary site or organ mentioned in the message as a comma separated list. Here are some possible organs: 'kidney', 'colon', 'breast', 'lung'")

class PDCMetadata(BaseModel):
    """Metadata like disease names and organ sites detected from a question"""
    disease_type: List[str] = Field(default=None, description="All the disease types matched as a list. ")
    primary_site: List[str] = Field(default=None, description="All the primary site or organ matched as a list.")
