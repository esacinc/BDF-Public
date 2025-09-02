#
# MWB REST API example inputs and outputs. Used to formulate API call.
# API broken up into seven context areas, not all have an example table. 
# See https://metabolomicsworkbench.org/tools/MWRestAPIv1.1.pdf for more detail
#

study  = """
--------------------------------------------------------------------------------------------------------------------------
Input item: study_id
Input value: Metabolomics Workbench (MW) study ID
Input value type: ST<6 digit integer>
Input example: ST000001
Output item: summary | factors | analysis | metabolites | mwtab | source | species | disease | number_of_metabolites | data
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
A substring may be specified for the study_id input value. For example, using "ST" will retrieve the summary information for all studies

Input item: study_id
Input value: Metabolomics Workbench (MW) study ID wildcard
Input value type: ST
Input example: ST
Output item: summary | factors | analysis | metabolites | mwtab | source | species | disease | number_of_metabolites | data
Output format: json | txt
Example: https://www.metabolomicsworkbench.org/rest/study/study_id/ST/summary 

--------------------------------------------------------------------------------------------------------------------------
A substring may be specified for the study_id input value. For example, using "ST0004" will retrieve summary information for studies ST000400 to ST000499. 

Input item: study_id
Input value: Metabolomics Workbench (MW) study ID range
Input value type: ST000<1-5 digit integer>
Input example: ST0004
Output item: summary | factors | analysis | metabolites | mwtab | source | species | disease | number_of_metabolites | data
Output format: json | txt
Example: https://www.metabolomicsworkbench.org/rest/study/study_id/ST0004/summary 

--------------------------------------------------------------------------------------------------------------------------
Input item: study_title
Input value: Title of a study
Input value type: string
Input example: Diabetes
Output item: summary | factors | analysis | number_of_metabolites | source | species | disease
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: institute
Input value: Name of an institute for a study
Input value type: string
Input example: Michigan
Output item: summary | factors | analysis | number_of_metabolites | source | species | disease
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: last_name
Input value: Last name of an investigator for a study
Input value type: string
Input example: Kind
Output item: summary | factors | analysis | number_of_metabolites | source | species | disease
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: analysis_id
Input value: Metabolomics Workbench analysis ID for a study
Input value type: AN<6-digit integer>
Input example: AN000001
Output item: mwtab | metabolites | datatable | untarg_factors | untarg_data
Output format: txt file for datatable and untarg_data; json for untargeted_factors; json | txt for others

--------------------------------------------------------------------------------------------------------------------------
Input item: metabolite_id
Input value: Metabolomics Workbench metabolite ID for a study
Input value type: ME<6-digit integer>
Input example: ME000096
Output item: summary (ignored but needed as a placeholder)
Output format: json | txt
--------------------------------------------------------------------------------------------------------------------------
"""

compound = """
--------------------------------------------------------------------------------------------------------------------------
Input item: regno
Input value: Metabolomics Workbench Metabolite database ID
Input value type: integer
Input example: 11
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: formula
Input value: Molecular Formula
Input value type: string
Input example: C20H34O11
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: inchi_key
Input value: valid InChIKey
Input value type: 27-character string
Input example: JTWQQJDENGGSBJ-UHFFFAOYSA-N
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: lm_id
Input value: LIPID MAPS ID
Input value type: LM<2-character LIPID MAPS category><8-10 character string>
Input example: LMFA03010001
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: pubchem_cid
Input value: PubChem Compound ID
Input value type: integer
Input example: 52921723
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: hmdb_id
Input value: Human Metabolome Database ID
Input value type: HMDB<integer>
Input example: HMDB0002886
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: kegg_id
Input value: KEGG compound ID
Input value type: CO<integer>
Input example: C05961
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: chebi_id
Input value: ChEBI compound id
Input value type: integer
Input example: 30805
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: metacyc_id
Input value: METACYC compound ID
Input value type: string
Input example: CPD-7836
Output item: all | any, some or all of: regno, formula, exactmass, inchi_key, name, sys_name, smiles, lm_id, pubchem_cid, hmdb_id, kegg_id, chebi_id, metacyc_id, classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: abbrev
Input value: Lipid bulk abbreviation
Input value type: string
Input example: LPC(18:0)
Output item: classification
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: regno
Input value: Metabolomics Workbench Metabolite database ID (integer)
Input value type: integer
Input example: 11
Output item: png
Output format: png image (By default; No specification allowed.)

--------------------------------------------------------------------------------------------------------------------------
Input item: regno
Input value: Metabolomics Workbench Metabolite database ID (integer)
Input value type: integer
Input example: 11
Output item: molfile
Output format: downloadable text file (By default; No specification allowed.)

--------------------------------------------------------------------------------------------------------------------------
Input item: regno
Input value: Metabolomics Workbench Metabolite database ID (integer)
Input value type: integer
Input example: 11
Output item: sdf
Output format: downloadable text file (By default; No specification allowed.)
As well as the molfile, the sd file also contains (if present): name, systematic name, exact mass, formula, PubChem compound ID, LIPID MAPS ID, HMDB ID, ChEBI ID, KEGG ID InChI key and SMILES for the molecule specified by the regno.

--------------------------------------------------------------------------------------------------------------------------
"""

refmet = """
--------------------------------------------------------------------------------------------------------------------------
Input item: all
Input value: none
Input example: none
Output item: none; automatically retrieves all (name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms)
Output format: json

--------------------------------------------------------------------------------------------------------------------------
Input item: match
Input value: Character string for a synonym match
Input value type: string
Input example: Lyso PC (16:0)
Output item: none; automatically retrieves refmet_name, formula, exactmass, main_class, sub_class
Output format: json

--------------------------------------------------------------------------------------------------------------------------
Input item: name
Input value: Compound name
Input value type: string
Input example: Cholesterol
Output item: all | any, some or all of: name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: inchi_key
Input value: valid InChIKey
Input value type: 27-character string
Input example: HVYWMOMLDIMFJA-DPAQBDIFSA-N
Output item: all | any, some or all of: name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: regno
Input value: Metabolomics Workbench Metabolite database ID (integer)
Input value type: integer
Input example: 11
Output item: all | any, some or all of: name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: pubchem_cid
Input value: PubChem Compound ID
Input value type: integer
Input example: 5997
Output item: all | any, some or all of: name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms
Output format: json | txt
--------------------------------------------------------------------------------------------------------------------------
Input item: formula
Input value: Molecular Formula
Input value type: string
Input example: C27H46O
Output item: all | any, some or all of: name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: main_class
Input value: Refmet main class
Input value type: string
Input example: Sterols
Output item: all | any, some or all of: name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: sub_class
Input value: Refmet sub class
Input value type: string
Input example: Cholesterol and derivatives
Output item: all | any, some or all of: name, regno, pubchem_cid, inchi_key, exactmass, formula, sys_name, main_class, sub_class, synonyms
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
"""

gene = """
--------------------------------------------------------------------------------------------------------------------------
Input item: mgp_id
Input value: Human Metabolome Gene/Protein (MGP) database gene ID
Input value type: MGP<6-digit integer>
Input example: MGP000016
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, gene_synonyms, alt_names, chromosome, map_location, summary, taxid, species, species_long
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: gene_id
Input value: Entrez gene ID
Input value type: integer
Input example: 31
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, gene_synonyms, alt_names, chromosome, map_location, summary, taxid, species, species_long
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: gene_name
Input value: Gene name
Input value type: string
Input example: acetyl-CoA carboxylase alpha
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, gene_synonyms, alt_names, chromosome, map_location, summary, taxid, species, species_long
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: gene_symbol
Input value: Gene symbol
Input value type: string
Input example: ACACA
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, gene_synonyms, alt_names, chromosome, map_location, summary, taxid, species, species_long
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: taxid
Input value: NCBI taxonomy ID
Input value type: integer
Input example: 9606
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, gene_synonyms, alt_names, chromosome, map_location, summary, taxid, species, species_long
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
"""

protein = """
--------------------------------------------------------------------------------------------------------------------------
Input item: mgp_id
Input value: Human Metabolome Gene/Protein (MGP) database protein ID
Input value type: MGP<6-digit integer>
Input example: MGP000016
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: gene_id
Input value: Entrez gene ID
Input value type: integer
Input example: 31
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: gene_name
Input value: Gene name
Input value type: string
Input example: acetyl-CoA carboxylase
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: gene_symbol
Input value: Gene symbol
Input value type: string
Input example: ACACA
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: taxid
Input value: NCBI taxonomy ID
Input value type: integer
Input example: 9606
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: mrna_id
Input value: mRNA ID
Input value type: NM_<integer>
Input example: NM_198834
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: refseq_id
Input value: NCBI reference sequence ID
Input value type: NP_<integer>
Input example: NP_942131
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: protein_gi
Input value: NCBI protein GI
Input value type: integer
Input example: 38679977
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: uniprot_id
Input value: UniProt ID
Input value type: string
Input example: Q13085
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: protein_entry
Input value: Protein entry symbol
Input value type: string
Input example: ACACA_HUMAN
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
Input item: protein_name
Input value: Protein name
Input value type: string
Input example: acetyl-CoA carboxylase
Output item: all | any, some or all of: mgp_id, gene_id, gene_name, gene_symbol, taxid, species, species_long, mrna_id, refseq_id, protein_gi, uniprot_id, protein_entry, protein_name , seqlength, seq, is_identical_to
Output format: json | txt

--------------------------------------------------------------------------------------------------------------------------
"""

moverz = """
--------------------------------------------------------------------------------------------------------------------------
Input item: LIPIDS
Input value1: m/z
Input value1 type: float, range: 50-2000
Input example1: 635.52
Input value2: ion type
Input value2 type: string, member of list of allowed ion adducts
Input example2: M+H
Input value3: m/z tolerance
Input value3 type: float, range: 0.0001-1
Input example3: 0.5
Output format: txt
Output: Input m/z, Matched m/z, Delta, Name, Systematic name, Formula, Ion, Category, Main class, Sub class

--------------------------------------------------------------------------------------------------------------------------
Input item: MB
Input value1: m/z
Input value1 type: float, range: 50-2000
Input example1: 513.45
Input value2: ion type
Input value2 type: string, member of list of allowed ion adducts
Input example2: M-2H
Input value3: m/z tolerance
Input value3 type: float, range: 0.0001-1
Input example3: 0.2
Output format: txt
Output: Input m/z, Matched m/z, Delta, Name, Formula, Ion, Category, Main class, Sub class

--------------------------------------------------------------------------------------------------------------------------
Input item: REFMET
Input value1: m/z
Input value1 type: float, range: 50-2000
Input example1: 255.2
Input value2: ion type
Input value2 type: string, member of list of allowed ion adducts
Input example2: M+H
Input value3: m/z tolerance
Input value3 type: float, range: 0.0001-1
Input example3: 0.2
Output format: txt
Output: Input m/z, Matched m/z, Delta, Name, Systematic name, Formula, Ion, Category, Main class, Sub class

--------------------------------------------------------------------------------------------------------------------------
Input item: exactmass
Input value1: Lipid abbreviation
Input value1 type: text
Input example1: PC(34:1)
Input value2: ion type
Input value2 type: string, member of list of allowed ion adducts
Input example2: M+H
Output format: txt
Output: Refmet name, exact mass(m/z) of ion adduct, formula

--------------------------------------------------------------------------------------------------------------------------
"""