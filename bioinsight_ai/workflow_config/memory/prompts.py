from llama_index.core.prompts import RichPromptTemplate

FACT_EXTRACTION_PROMPT = RichPromptTemplate("""You are a biomedical research context extraction system. Your job is to capture key information from a conversation about biomedical data exploration.

INSTRUCTIONS:
1. Review the conversation segment provided prior to this message
2. Extract concrete, specific information that would be important to recall later in the conversation
3. Focus on:
   - Datasets, studies, and study IDs mentioned or queried (e.g., PDC000173, TCGA-BRCA)
   - Genes, proteins, metabolites, or biomarkers discussed (e.g., BRCA1, TP53, CDKN2A)
   - Data sources accessed (e.g., Proteomics Data Commons, Metabolomics Workbench, Imaging Data Commons)
   - Key results, findings, or data values returned by queries
   - Analytical conclusions or observations made
   - Visualizations generated and what they showed
   - Disease areas, cancer types, or biological processes under investigation
   - The user's research questions and analytical goals
4. Format each piece of information as a separate <fact> XML tag
5. Be specific — include IDs, names, and values rather than vague summaries
6. Do not duplicate information already in the existing facts list

<existing_facts>
{{ existing_facts }}
</existing_facts>

Return ONLY the extracted information in this exact format:
<facts>
  <fact>Specific information 1</fact>
  <fact>Specific information 2</fact>
</facts>

If no new information is present, return: <facts></facts>""")

FACT_CONDENSE_PROMPT = RichPromptTemplate("""You are a biomedical research context condensation system.

INSTRUCTIONS:
1. Review the current list of extracted research context
2. Condense into fewer than {{ max_facts }} items by merging related information
3. Prioritize retaining: study IDs, gene/protein names, key results, data source details, and the user's research goals
4. Drop redundant or superseded information (e.g., if a later fact updates an earlier one)
5. Format each item as a separate <fact> XML tag

<existing_facts>
{{ existing_facts }}
</existing_facts>

Return ONLY the condensed facts:
<facts>
  <fact>Specific information 1</fact>
  <fact>Specific information 2</fact>
</facts>

If no facts remain: <facts></facts>""")
