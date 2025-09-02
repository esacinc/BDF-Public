import json
import requests
import re
from io import StringIO
from typing import List
import pandas as pd
# from ..ensembl_api import gene_name_to_ensembl_mapping

# This is a set of helper function for retrieving and processing data from PDC

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
        if (study_list is not None):
            for programs in study_list:
                for projects in study_list:
                    for project in projects['projects']:
                        for study in project['studies']:
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

def list_studies(mdata: object)->object:
    """ Useful for getting a list of studies matching the input. It expects an object with two keys: disease_type and primary_site.
    Returns all the matching studies including disease name, primary site and study id.
    """
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
def get_gene_expression_data(gene_list, study_id=None) -> str:
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
                biospecimen_response = requests.post(url, json={'query': biospecimen_query})
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
    '''This function is used to determine if a given study has corresponding data in an external
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
