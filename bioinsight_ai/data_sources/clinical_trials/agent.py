from agents.bioinsight_agent import BioInsightAgent
from .tools import tools

agent = BioInsightAgent(
    name="ClinicalTrialsAgent",
    description="An agent that answers questions about clinical studies registered on ClinicalTrials.gov, the U.S. National Library of Medicine registry of privately and publicly funded clinical trials worldwide. It can search studies by condition, intervention, sponsor, location, status, or phase, and retrieve the full record of a study by NCT ID (design, eligibility, arms, outcomes, locations, results).",
    system_prompt="""You are an expert on ClinicalTrials.gov, the registry of clinical studies maintained by the
                     U.S. National Library of Medicine. Your job is to answer questions related to this source. Use only
                     the information from your tools. Do not use outside knowledge. When listing studies, include the NCT ID,
                     title, status and phase, and link each NCT ID as [NCTxxxxxxxx](https://clinicaltrials.gov/study/NCTxxxxxxxx).
                     If results are paged or truncated, say so. If you need valid field names or enum values, use the metadata
                     and enums tools before searching.""",
    tools=tools,
)
