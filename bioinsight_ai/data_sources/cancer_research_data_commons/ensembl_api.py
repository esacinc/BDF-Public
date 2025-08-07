import requests
from typing import List

# Helper function to get ensembl gene IDs

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
            ensembl_ids = [entry["id"] for entry in data if entry["type"] == "gene"]
            for e in ensembl_ids:
                if "ENS" in e:
                    ret_val.append({'gene_name':g, 'ensembl_id':e})
                    break
    return ret_val

