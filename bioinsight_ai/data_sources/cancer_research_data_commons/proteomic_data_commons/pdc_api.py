import json
import requests
import re
from io import StringIO
from typing import List
import pandas as pd
from ..ensembl_api import gene_name_to_ensembl_mapping

from log_helper.logger import get_logger
logger = get_logger()

# This is a set of helper function for retrieving and processing data from PDC

pdc_url = 'https://proteomic.datacommons.cancer.gov/graphql?query='
post_pdc_url = "https://pdc.cancer.gov/graphql"

# Helper function to cache all diseases and primary sites from PDC
# TO DO: Use a proper metadata source for these values e.g. PDC Dictionary or caDSR
def getAllDiseasesAndPrimarySites():
    all_studies = []
    all_studies_map = {}
    submitter_to_pdc_map = {}
    logger.info('Caching studies')
    # Cache all studies
    url = pdc_url
    url += '''{allPrograms 
                   { 
                    projects  
                      {  
                        studies  
                          { pdc_study_id study_id study_submitter_id submitter_id_name 
                            analytical_fraction study_name disease_types 
                            primary_sites  experiment_type acquisition_type
                          } 
                        }
                    }
                }'''
    response = requests.get(url)
    logger.info(f"PDC API getAllDiseasesAndPrimarySites: {url}")
    if(response.ok):
        study_list = json.loads(response.content)
        study_list = study_list['data']['allPrograms']
        if (study_list is not None):
            for programs in study_list:
                for projects in study_list:
                    for project in projects['projects']:
                        for study in project['studies']:
                            all_studies.append(study)
                            all_studies_map[study['pdc_study_id']] = study

                            submitter_id = study.get('study_submitter_id')
                            pdc_id = study.get('pdc_study_id')
                        
                            if submitter_id and pdc_id:
                                # Map the CPTAC/Submitter ID to the PDC ID
                                submitter_to_pdc_map[submitter_id] = pdc_id
                            
                            # Handle the friendly name as well, as it's often used
                            submitter_name = study.get('submitter_id_name')
                            if submitter_name and pdc_id:
                                submitter_to_pdc_map[submitter_name] = pdc_id

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
    logger.info(f"PDC API getAllDiseasesAndPrimarySites: {url}")
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        jData = jData['data']['allPrograms']
        return all_studies, jData, submitter_to_pdc_map
    else:
      # If response code is not ok (200), print the resulting http error code with description
      response.raise_for_status()
        

# This is a helper function
def getDiseaseInformation(mdata:object)->str:
    '''
    Given a disease or a primary site, returns all the matching studies including disease name, primary site and study id.
    '''   
    if None in mdata['disease_type'] and None in mdata['primary_site']:
        return {'mdata':{}, 'original_message':'', 'data':{}}
        
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
    logger.info(f"PDC API: getDiseaseInformation: {url}")
    if(response.ok):
        all_studies = []
        x = json.loads(response.content)
        x = x['data']['allPrograms']
        study_list = x
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
    else:
      # If response code is not ok (200), print the resulting http error code with description
      response.raise_for_status()    

def pdc_list_studies(mdata: object)->object:
    """ Useful for getting a list of studies matching the input. It expects an object with two keys: disease_type and primary_site.
    Returns all the matching studies including disease name, primary site and study id.
    """
    if None in mdata['disease_type'] and None in mdata['primary_site']:
        return {'mdata':{}, 'original_message':'', 'data':{}}
    
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
    logger.info(f"PDC API list_studies: {url}")
    if(response.ok):
        all_studies = []
        x = json.loads(response.content)
        x = x['data']['allPrograms']
        study_list = x
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
        logger.info(f"PDC API get_external_gdc_references: {url}")
        if(response.ok):
         #If the response was OK then print the returned JSON
            jData = json.loads(response.content)
            jData = jData['data']['biospecimenPerStudy']
            for e in jData:
                for extRef in e['externalReferences']:
                    if extRef['reference_resource_shortname'] == 'GDC':
                        ref_id = extRef['reference_entity_location'].split('/')[-1]
                        ref_map[e['aliquot_submitter_id']] = ref_id
            return ref_map
        else:
            return {}

            
post_url = "https://proteomic.datacommons.cancer.gov/graphql"
def pdc_get_expression(gene_list, study_id=None) -> str:
    '''Useful for getting gene expression data given a list of genes for a specific study.
    If no genes are specified it returns the whole dataset.'''
    if study_id is None:
        return ''
    
    if study_id is not None:
        data_type = 'log2_ratio'  # Retrieves CDAP iTRAQ or TMT data
        
        quant_data_query = '{ quantDataMatrix(pdc_study_id: "' + study_id +'" data_type: "log2_ratio" acceptDUA: true )}'
        
        pdc_response = requests.post(post_pdc_url, json={'query': quant_data_query})
        logger.info(f"PDC API: pdc_get_expression: {post_pdc_url} with arguments: {quant_data_query}")
        # Check the results
        if pdc_response.ok:
            # Decode the response
            response = pdc_response.json()
            matrix = response['data']['quantDataMatrix']
            if matrix is None:
                logger.error("Invalid study ID")
                return {}
            ga = pd.DataFrame(matrix[1:], columns=matrix[0]).set_index('Gene/Aliquot')
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
                        logger.error("Gene ", gene, " does not exists or not expressed")
            df.reset_index(inplace=True)
            df = df.rename(columns={'index': 'sample_id'})
            df[['case_id', 'aliquot_submitter_id']] = df['sample_id'].str.split(':', expand=True)
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

            # Send the POST graphql query
            logger.info(f"PDC API get_gene_expression_data: {post_pdc_url} with arguments {metadata_query}")
            pdc_response = requests.post(post_pdc_url, json={'query': metadata_query})
            logger.info(pdc_response)
            # Check the results
            if pdc_response.ok:
                # Decode the response
                decoded = pdc_response.json()
                clin_matrix = decoded['data']['clinicalMetadata']
                metadata = pd.DataFrame(clin_matrix)
                # Custom join: df.aliquot_submitter_id is substring of metadata.aliquot_submitter_id
                def match_row(row):
                    quant_id = re.sub(r'\.\d+$', '', row['aliquot_submitter_id'])
                    matches = metadata[metadata['aliquot_submitter_id'].str.contains(quant_id, na=False)]
                    return matches.iloc[0] if not matches.empty else pd.Series()

                matched_metadata = df.apply(match_row, axis=1)

                # Drop df's original aliquot_submitter_id and use the one from metadata
                # df = df.drop(columns=['aliquot_submitter_id'], errors='ignore')
                df.rename(columns={'aliquot_submitter_id': 'quant_aliquot_submitter_id'}, inplace=True)
                df = pd.concat([df, matched_metadata.reset_index(drop=True)], axis=1)
                
                # Use ID from clinicalMetadata if match found, otherwise use ID from quantDataMatrix
                # should only be from quantDataMatrix if match not found
                df['aliquot_submitter_id'] = df['aliquot_submitter_id'].fillna(df['quant_aliquot_submitter_id'])
                df.drop(columns=['quant_aliquot_submitter_id'], inplace=True)

                # Additional API call to get case_submitter_id
                biospecimen_query = '''
                    {
                        biospecimenPerStudy(pdc_study_id: "''' + study_id + '''") {
                            aliquot_submitter_id
                            case_submitter_id
                        }
                    }
                '''
                biospecimen_response = requests.post(post_pdc_url, json={'query': biospecimen_query})
                if biospecimen_response.ok:
                    biospecimen_data = biospecimen_response.json()['data']['biospecimenPerStudy']
                    biospecimen_df = pd.DataFrame(biospecimen_data)
                    df = pd.merge(df, biospecimen_df, on='aliquot_submitter_id', how='left')
                else:
                    return biospecimen_response.raise_for_status()

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
                logger.info (f"Len of output data: {len(str_value)}")
                if len(str_value) > 799000:
                    logger.error("Results too large for LLM to handle")
                    return ''
                else:
                    return json.loads(str_value)
            else:
                return pdc_response.raise_for_status()
        else:
            # Response not OK, see error
            return pdc_response.raise_for_status()

def has_external_genomic_data(study_id)->object:
    '''This function is used to determine if a given study has corresponding data in an external
    database like GDC'''
    url = pdc_url + '{ biospecimenPerStudy (pdc_study_id: "' + study_id + '"){ '
    url += ' externalReferences { external_reference_id reference_resource_shortname '
    url += ' reference_resource_name reference_entity_location }} }'
    logger.info(f"PDC API has_external_genomic_data: {url}")
    response = requests.get(url)
    if(response.ok):
         #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        # Make sure its a valid study:
        if len(jData['data']['biospecimenPerStudy']) == 0:
            return "Not a valid study"
        ext_ref_list = jData['data']['biospecimenPerStudy'][0]
        logger.info(ext_ref_list)
        if len(ext_ref_list['externalReferences'])>0 and ext_ref_list['externalReferences'][0]['reference_resource_shortname'] == 'GDC':
            return json.loads('{"genomic_data": "Yes, genomic data is available in GDC"}')
        else:
            return json.loads('{"genomic_data": "No, genomic data is not available in GDC"}')

def get_external_resources_data(study_id)->object:
    '''This function is used to provide if exist external resources like GDC, IDC, TCIA for a given study'''
    url = pdc_url + '{ biospecimenPerStudy (pdc_study_id: "' + study_id + '"){ '
    url += ' aliquot_id sample_id case_id aliquot_submitter_id sample_submitter_id case_submitter_id aliquot_status'
    url += ' case_status sample_status project_name sample_type disease_type primary_site pool taxon'
    url += ' externalReferences { external_reference_id reference_resource_shortname '
    url += ' reference_resource_name reference_entity_location }} }'
    logger.info(f"PDC API get_external_resources_data: {url}")
    response = requests.get(url)
    if(response.ok):
         #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        # Make sure its a valid study:
        if len(jData['data']['biospecimenPerStudy']) == 0:
            return "Not a valid study"
        biospecimens = jData['data']['biospecimenPerStudy']
        logger.info(f"The first record retrieved for external references using biospecimenPerStudy PDC API: {biospecimens[0]}")
        # Check if there are any external references retrieved if so, pass the data
        for specimen in biospecimens:
            if len(specimen.get('externalReferences', [])) > 0:
                return jData

        return json.loads('{"external_resources": "No external references were found"}')
    else:
        return json.loads('{"external_resources": "An error occured while quering biospecimenPerStudy PDC API"}')

# Return the matching gdc gene expression data
def get_matches_from_gdc(study_id, ensembl_ids)->pd.DataFrame:
    '''This function is used to return the gene expression for the given ensembl ids '''
    url = pdc_url + '{ biospecimenPerStudy (pdc_study_id: "' + study_id + '"){ '
    url += ' case_id aliquot_id aliquot_submitter_id externalReferences { external_reference_id reference_resource_shortname '
    url += ' reference_resource_name reference_entity_location }} }'
    logger.info(f"PDC API get_matches_from_gdc: {url}")
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
        logger.info(f"PDC API using external GDC APIs to get expression data with {url}")
        response = requests.post(url, headers=headers, json=payload)
        TESTDATA = StringIO(response.text)

        df = pd.read_csv(TESTDATA, sep="\t")
        return df
    else:
        logger.error(f"Error occured in get_matches_from_gdc")
        response.raise_for_status()

# Return the study name based on Study ID.
def get_study_name(study_id):
    """Return the name of the study based on the study ID"""
    url = pdc_url + '{getPaginatedUIStudy(pdc_study_id: "' + study_id + '" limit: 10 offset: 0) {'
    url += 'uiStudies { pdc_study_id submitter_id_name project_name program_name disease_type primary_site analytical_fraction '
    url += 'experiment_type cases_count study_description } } }'
    logger.info(f"PDC API get_study_name: {url}")
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

def pdc_get_biospecimens(study_id):
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
    logger.info(f"PDC API get_biospecimen_data: {url}")
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
        logger.info(f"PDC API get_clinical_and_demographic_data: {url}")
        response = requests.get(url)
        if(response.ok):
            #If the response was OK then print the returned JSON
            jData = json.loads(response.content)
            jData = jData['data']['getPaginatedUIClinical']['uiClinical']
            # convert to dataframe and sort on case id
            df = pd.json_normalize(jData)
            df.sort_values('case_id', inplace=True)
            return df.to_json(orient='records', index=False)
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()
    elif study_id is None:
        url = pdc_url + '{getPaginatedUIClinical( '
        url += 'study_name: "' + study_name +'" limit: 1000000, offset: 0) {'
        url += 'uiClinical { program_name case_id case_submitter_id gender race ethnicity morphology primary_diagnosis site_of_resection_or_biopsy'
        url += ' tissue_or_organ_of_origin tumor_grade tumor_stage age_at_diagnosis classification_of_tumor days_to_recurrence'
        url += '}}}'
        logger.info(f"PDC API get_clinical_and_demographic_data: {url}")
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
    logger.info(f"Ensembl IDs: {ensmbl_ids}")
    e_ids = []
    replace_dict = {}
    for e in ensmbl_ids:
        e_ids.append(e['ensembl_id'])
        replace_dict[e['ensembl_id']] = e['gene_name']
    df = get_matches_from_gdc(study_id, e_ids)
    if len(df) < 1:
        logger.info("No external genomic data found")
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
            logger.info(f"Gene {gene} does not exists or not expressed")
    df2 = df2[1:]
    df2.reset_index(inplace=True)
    df2 = df2.rename(columns={'index': 'sample_id'})
    str_value = df2.to_json()
    logger.info (f"Len of output data: {len(str_value)}")
    if len(str_value) > 799000:
        logger.error("Results too large for LLM to handle")
        return ''
    else:
        return json.loads(str_value)
    
def pdc_get_study_details(study_id: str=None, study_name: str=None):
    """Useful for getting details about a study and its participants 
    including age, gender, demographics given a study_id or a study name or a program name"""
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
        url += 'experiment_type cases_count study_description has_genomic_data has_imaging_data has_lipidome_data has_metabolome_data } } }'
        logger.info(f"PDC API pdc_get_study_details: {url}")
    response = requests.get(url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        jData = jData['data']['getPaginatedUIStudy']['uiStudies']
        logger.info(f"# of records: {len(jData['data']['getPaginatedUIStudy']['uiStudies'])}")
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
    """Useful for getting gene details for a study_id or a study name or a program name"""
    if study_name is not None:
        return get_gene_data(study_name, study_id=None)
    if program_name is None and study_id is not None:
        # Convert to study name
        study_name = get_study_name(study_id)
        return get_gene_data(study_name, study_id=None)
    else:
        url = pdc_url + '{getPaginatedUIGene(program_name: "' + program_name + '" limit: 1000000 offset: 0) {'
        url += 'uiGenes {gene_name chromosome locus num_study ncbi_gene_id proteins } } }'
        logger.info(f"PDC API get_gene_details: {url}")
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
        logger.info(f"PDC API get_gene_data: {url}")
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
        logger.info(f"PDC API get_gene_data: {url}")
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

def get_references(reference_type:str, study_id: str=None, case_id: str=None, ):
    """Find Entity References for a Study or a Case"""
    url = pdc_url + '{pdcEntityReference( '
    if study_id is None and case_id is not None:
        url += 'entity_type: "case", entity_id: "' + case_id + '", '
    elif case_id is None and study_id is not None:
        url += 'entity_type: "study", entity_id: "' + study_id + '", '
    else:
        # either study id or case id must be defined, otherwise return empty response
        return {}
    url += 'reference_type: "' + reference_type + '" ) {'
    url += 'reference_id entity_type entity_id reference_type reference_entity_type reference_entity_alias reference_resource_name reference_resource_shortname reference_entity_location } }'
    logger.info(f"PDC API get_references: {url}")
    response = requests.get(url)
    if(response.ok):
        #If the response was OK then print the returned JSON
        jData = json.loads(response.content)
        jData = jData['data']['pdcEntityReference']
        return jData
    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()

# def get_all_cases(study_submitter_id_value):
#    """ Get all cases using allCases PDC API """
#    url = pdc_url
#    url += '''{allCases {
#                        case_id 
#                        case_submitter_id 
#                        project_id 
#                        project_submitter_id 
#                        disease_type 
#                        primary_site 
#                        externalReferences { 
#                            external_reference_id 
#                            reference_resource_shortname 
#                            reference_resource_name 
#                            reference_entity_location 
#                            }
#                        }
#            }'''
#    logger.info(f"PDC API allCases: {url}")
#    response = requests.get(url)
#    if(response.ok):
#        #If the response was OK then print the returned JSON
#        jData = json.loads(response.content)
#        jData = jData['data']['allCases']
#        return jData
#    else:
#        logger.error("An error has occured while calling for PDC API allCases")
#        # If response code is not ok (200), print the resulting http error code with description
#        response.raise_for_status()

def get_all_cases(study_submitter_id_value: str):
    """
    Get all cases for a specific study by first resolving the submitter ID 
    to a UUID, then fetching paginated demographics.
    """
    try:
        # Step 1: Get the internal UUID (study_id) using the submitter_id
        # Note: We use the UIStudy query which you've had success with.
        id_query = f"""
        {{
            getPaginatedUIStudy(study_submitter_id: "{study_submitter_id_value}") {{
                uiStudies {{
                    study_id
                }}
            }}
        }}
        """
        id_response = requests.post(post_pdc_url, json={'query': id_query})
        id_response.raise_for_status()
        id_data = id_response.json()
        
        ui_studies = id_data.get('data', {}).get('getPaginatedUIStudy', {}).get('uiStudies', [])
        if not ui_studies:
            logger.error(f"Could not find study UUID for: {study_submitter_id_value}")
            return []
            
        study_uuid = ui_studies[0]['study_id']
        logger.info(f"Resolved {study_submitter_id_value} to UUID: {study_uuid}")

        # Step 2: Fetch the cases using the UUID
        # We use the paginatedCaseDemographicsPerStudy endpoint per documentation
        case_query = f"""
        {{
            paginatedCaseDemographicsPerStudy(study_id: "{study_uuid}", limit: 500, offset: 0) {{
                caseDemographicsPerStudy {{
                    case_id
                    case_submitter_id
                    disease_type
                    primary_site
                    demographics {{
                        demographic_id
                        gender
                        race
                        ethnicity
                        age_at_index
                        vital_status
                    }}
                }}
            }}
        }}
        """
        
        logger.info(f"Fetching case details for study UUID: {study_uuid}")
        case_response = requests.post(post_pdc_url, json={'query': case_query})
        case_response.raise_for_status()
        case_data = case_response.json()

        if 'errors' in case_data:
            logger.error(f"GraphQL errors: {case_data['errors']}")
            return []

        cases = case_data.get('data', {}).get('paginatedCaseDemographicsPerStudy', {}).get('caseDemographicsPerStudy', [])
        return cases

    except Exception as e:
        logger.error(f"An exception occurred while calling PDC API: {e}")
        return []

def get_cases_by_study(study_submitter_id: str, 
                       disease_type: str = None, 
                       primary_site: str = None, 
                       sex: str = None, 
                       min_age_years: int = None, 
                       max_age_years: int = None):
    """
    Retrieves cases for a study and applies optional filters.
    """
    
    all_cases_for_study = get_all_cases(study_submitter_id)

    if not all_cases_for_study:
        return json.dumps([])

    filtered_cases = []
    for case in all_cases_for_study:
        # Filter by disease_type
        if disease_type and case.get('disease_type') != disease_type:
            continue

        # Filter by primary_site
        if primary_site and case.get('primary_site') != primary_site:
            continue

        # Get demographic info (handle list structure)
        demographics_list = case.get('demographics', [])
        demographic_info = demographics_list[0] if demographics_list else {}

        # Filter by sex (Note: API uses 'gender' field)
        if sex:
            if demographic_info.get('gender') != sex:
                continue

        # Filter by age (Note: API uses 'age_at_index')
        # Check if age filters are present
        age_val = demographic_info.get('age_at_index')
        
        if min_age_years is not None or max_age_years is not None:
            if age_val is None:
                continue 
            
            try:
                # Assuming age_at_index is in years; if in days, divide by 365.25
                age_in_years = float(age_val)
            except (ValueError, TypeError):
                continue

            if min_age_years is not None and age_in_years < min_age_years:
                continue
            if max_age_years is not None and age_in_years > max_age_years:
                continue

        filtered_cases.append(case)

    logger.info(f"Filtered {len(all_cases_for_study)} total cases down to {len(filtered_cases)} matches.")
    return json.dumps(filtered_cases, indent=2)


def pdc_map_case_ids():
    """
    Retrieves all necessary data and creates a bidirectional map between 
    PDC Case IDs and CPTAC/Submitter IDs.
    
    Returns:
        tuple: (pdc_to_cptac_map, cptac_to_pdc_map)
    """
    # 1. Define the GraphQL query to get the case submitter IDs and external references
    # This query structure may need slight adjustment based on the latest PDC API version.
    query = """
    {
      allCases {
        case_id           # PDC ID (UUID)
        case_submitter_id # Often the CPTAC/TCGA ID, e.g., S057
        externalReferences {
          reference_resource_shortname
          external_reference_id
        }
      }
    }
    """
    
    # 2. Execute the API call
    try:
        logger.info(f"PDC API pdc_map_case_ids: {post_pdc_url} with query {query}")
        response = requests.post(post_pdc_url, json={'query': query})    
        if not response.ok:
            logger.error(f"API call failed: {response.status_code}")
            return {}, {}
            
        data = response.json().get('data', {}).get('allCases', [])
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception: {e}")
        return {}, {}
    
    # 3. Build the bidirectional maps
    pdc_to_cptac_map = {}
    cptac_to_pdc_map = {}
    
    for case in data:
        pdc_id = case.get('case_id')
        case_submitter_id = case.get('case_submitter_id')
        
        if pdc_id and case_submitter_id:
            # Direct mapping from PDC UUID to Case Submitter ID
            pdc_to_cptac_map[pdc_id] = case_submitter_id
            cptac_to_pdc_map[case_submitter_id] = pdc_id
            
            # Additional mapping using external references (for GDC, etc.)
            for ref in case.get('externalReferences', []):
                ref_id = ref.get('external_reference_id')
                ref_name = ref.get('reference_resource_shortname')
                
                # You can extend this logic to include GDC IDs if needed
                if ref_id and ref_name in ['CPTAC', 'TCGA', 'GDC']:
                    # Map the external ID to the PDC ID (UUID)
                    cptac_to_pdc_map[ref_id] = pdc_id
                    
    logger.info(f"Generated bidirectional map with {len(pdc_to_cptac_map)} entries.")
    return pdc_to_cptac_map, cptac_to_pdc_map


def pdc_get_study_files(study_submitter_id: str,
                        offset: int = 0, 
                        limit: int = 50,
                        file_type: str = None) -> str:
    """
    Retrieves file metadata (name, size, location, etc.) for a study. 
    Supports filtering by file type (e.g., 'PSM').
    """
    # 2. Build GraphQL Query (filesPerStudy)
    # The fileType filter can be applied directly within the query arguments.
    file_filter = f' file_type: "{file_type}" ' if file_type else ''
    
    file_query = f"""
    {{
        filesPerStudy(pdc_study_id: "{study_submitter_id}" {file_filter} offset: {offset} limit: {limit} ) {{
            file_id
            file_name
            file_type
            file_size
            md5sum
            file_location
            data_category
            file_format
            signedUrl {url}
        }}
    }}
    """
    
    url = pdc_url + file_query

    # 3. Execute API Call
    try:
        # logger.info(f"PDC API pdc_get_study_files: {post_pdc_url} with query {file_query}")
        # response = requests.post(post_pdc_url, json={'query': file_query})
        logger.info(f"PDC API pdc_get_study_files: {url}")
        response = requests.get(url)
        if response.ok:
            # file_data = response.json().get('data', {}).get('filesPerStudy', [])
            # return json.dumps({"files": file_data}, indent=2)
            json_file_data = json.loads(response.content)
            json_file_data = json_file_data['data']['filesPerStudy']
            return json_file_data
        else:
            logger.error(f"File query failed for {study_submitter_id}: {response.status_code}")
            # return json.dumps({"error": f"PDC API call failed: {response.status_code} {response.reason}"})
            # Response not OK, see error
            return response.raise_for_status()
            
    except Exception as e:
        logger.error(f"File query exception: {e}")
        # return json.dumps({"error": f"API request exception: {e}"})
        # Response not OK, see error
        return response.raise_for_status()


def pdc_get_quantitative_data(study_submitter_id: str, 
                              gene_list: list[str], 
                              data_type: str = "log2_ratio") -> str:
    """
    Retrieves quantitative data matrices (gene expression/abundance) for a study.
    Fetches the full matrix via 'quantDataMatrix' and locally filters by the provided gene_list.
    
    Args:
        study_submitter_id (str): The study ID (e.g., 'S015-1').
        gene_list (list[str]): Optional. List of gene symbols to filter the output.
        data_type (str): The type of data to retrieve (default: 'log2_ratio').
    """
    # 2. Build GraphQL Query (quantDataMatrix)
    # Note: acceptDUA: true is often required for this endpoint
    quant_query = f"""
    {{
        quantDataMatrix(pdc_study_id: "{study_submitter_id}", data_type: "{data_type}", acceptDUA: true)
    }}
    """

    url = pdc_url + quant_query
    
    # 3. Execute API Call
    try:
        logger.info(f"PDC API pdc_get_quantitative_data: {url}")
        response = requests.get(url)
        if not response.ok:
            logger.error(f"Quant matrix query failed for {study_submitter_id}: {response.status_code}")
            return {}
            
        # 4. Process the Response (List of Strings)
        # The API returns a distinct structure: a list of strings where each string is a row.
        # Row 0: "Gene/Aliquot:AliquotID1:AliquotID2:..."
        # Row N: "GeneSymbol:Value1:Value2:..."
        raw_matrix = response.json().get('data', {}).get('quantDataMatrix', [])
        
        if not raw_matrix:
            return json.dumps({"data_matrix": []})

        # Parse the Header (Aliquot IDs)
        # Row 0 contains the headers: ["Gene/Aliquot", "AliquotID1", "AliquotID2", ...]
        header_row = raw_matrix[0]
        
        # We skip the first element ("Gene/Aliquot") to get just the IDs
        aliquot_ids = header_row[1:] 

        final_matrix = []

        # Prepare gene filter set for O(1) lookup
        target_genes = set(gene_list) if gene_list else None

        # Iterate through Data Rows (Row 1 to End)
        for row in raw_matrix[1:]:
            # The row is ALREADY a list: ["GeneSymbol", "Val1", "Val2", ...]
            gene_symbol = row[0]
            
            # --- Filtering Logic ---
            if target_genes and gene_symbol not in target_genes:
                continue
            # -----------------------

            values = row[1:]
            
            # Map values to aliquot IDs
            for i, value in enumerate(values):
                # Handle missing data or NaNs
                # The API returns "NaN" (string) or None for missing values.
                if value is None or value == "NaN" or value == "": 
                    continue
                
                entry = {
                    "gene_name": gene_symbol,
                    "sample_id": aliquot_ids[i], 
                    "value": value,
                    "units": data_type
                }
                final_matrix.append(entry)
        
        return json.dumps({"data_matrix": final_matrix}, indent=2)

    except Exception as e:
        logger.error(f"Matrix processing exception: {e}")
        return {}
        

all_studies, study_list, submitter_to_pdc_map = getAllDiseasesAndPrimarySites()
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

def pdc_list_diseases(question:str) -> list[str]:
    """ Useful for getting all available disease or cancer types studied in PDC."""
    return disease_types_list
def pdc_list_primary_sites(question:str) -> list[str]:
    """ Useful for getting all available primary sites or organs where tissues are collected from in PDC """
    return primary_sites_list
