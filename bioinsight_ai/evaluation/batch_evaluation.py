import sys
sys.path.append("..")
from llama_index.core.evaluation import (
    AnswerRelevancyEvaluator,
    CorrectnessEvaluator,
    FaithfulnessEvaluator,
    GuidelineEvaluator,
    SemanticSimilarityEvaluator,
    BatchEvalRunner
)
from workflow_config.default_settings import Settings
from bioinsight_workflow import wf
import asyncio

wf._verbose = False
wf._timeout = 300
    
# Answer relevancy checker
answer_relevancy = AnswerRelevancyEvaluator()

# Batch evaluator with only one evaluation type for the time being
batch_evaluator = BatchEvalRunner(evaluators={'answer':answer_relevancy}, show_progress=True)

# From 42569_icfcorp Stage-April worksheet
# questions = [
#     "What is PDC?",
#     "When is PDC launched?",
#     "What are goals for PDC?",
#     "How do I cite to the PDC?",
#     "Do PDC offer GBM datasets for analysis?",
#     "As a researcher, I want to know if there are any available GBM datasets in the PDC, so that I can access relevant data for my research.",
#     "As a researcher, I want to compare and contrast two GBM studies, so that I can identify differences and similarities in their methodologies, patient cohorts, molecular data, and key findings.",
#     "Can you generate pie charts to display the demographic distribution (e.g. gender, age, ethnicity) of the cohort used in Study PDC000552?",
#     "Can you help me create a stacked bar chart that shows the distribution of cases by tumor stage and tissue origin, along with additional variables from Study PDC000250?",
#     "Could you plot the gene expression data from GDC for the genes MDM4 and TP53 in the context of Study PDC000173?",
#     "Could you generate a violin plot for the gene expression data from GDC for the genes CDKN2A, MDM4, and TP53 in Study PDC000173?",
#     "Could you generate a heat map for the gene expression data from GDC for the genes CDKN2A, MDM2, MDM4, and TP53 in Study PDC000173?",
#     "What are analytical challenges in analyzing the Pan cancer data?",
#     "Give me the colon cancer studies from proteome exchange",
#     "Is peptide AEPLAFTFSHDYK found in study PXD057661?",
#     "What kind of cancer studies are there on PDC?",
#     "Could you list all early onset gastric cancer studies?"
# ]

# Testing chainlit.md test case questions prior to stage deployment
questions = [
    "Can you provide information on any available GBM (glioblastoma multiforme) datasets in the PDC?",
    "Tell me which molecular data types are associated with GBM datasets in the PDC?",
    "Can I compare and contrast two GBM studies in terms of methodologies, patient cohorts, molecular data, and key findings?",
    "I want to generate pie charts to visualize the demographic distribution (e.g., gender, age, ethnicity) of the cohort in Study PDC000552.",
    "I want to create a stacked bar chart that shows the distribution of cases by tumor stage and tissue origin, along with additional variables from Study PDC000250.",
    "Could you generate a graph displaying the gene expression data from GDC for the genes CDKN2A, MDM2, MDM4, and TP53 in Study PDC000173?",
    "I want to follow up on my previous request and generate a violin plot for the gene expression data from GDC for the genes CDKN2A, MDM2, and TP53 in Study PDC000173.",
    "Could you please generate a heat map to visualize the gene expression data from GDC for the genes CDKN2A, MDM2, and TP53 in Study PDC000173?",
    "I want to understand the analytical challenges in analyzing Pan Cancer data.",
    "Give me the colon cancer studies from ProteomeXchange.",
    "Is peptide AEPLAFTFSHDYK found in study PXD057661?",
    "Retrieve studies analyzing metabolite glutamine in brain cancer across all available analytical methods from Metabolomics Workbench."
]


# await answer_relevancy.aevaluate(query="Can you generate pie charts to display the demographic distribution (e.g. gender, age, ethnicity) of the cohort used in Study PDC000552?", response=str(answers['graph'].to_dict()))

async def generate_responses(user_query:str):
    print(f"🧠 Generating Bioinsight AI response for query: {user_query}")
    
    counter = 1
    while True:
        try:
            answer = await wf.run(query=user_query)
            break
        except:
            if counter > 3: 
                print(f"Tried running query {user_query} 3x and failed.")
                raise Exception
            print(f"Failed on query: {user_query}. Trying again...") 
            counter += 1
            
        

    if 'graph' in answer:
        response = '\n\n'.join(['This message has a chart\n\n' + str(answer['graph'].to_dict()), answer['response']])
    else:
        response = str(answer['response'])
    # keep query, responses together since async might run out of order
    return (user_query, response) 



if __name__ == "__main__":
    async def main():
        #! testing with 3 for now
        qa = await asyncio.gather(*map(generate_responses, questions)) # , questions[0:2] + questions[8:10]))

        # transpose so all queries are 0 index list and all answers are in 1 index list
        q0a1 = list(map(list,zip(*qa)))

        evaluation = await batch_evaluator.aevaluate_response_strs(
            queries=q0a1[0], # all queries in the first sublist
            response_strs=q0a1[1] # all corresponding responses in the second sublist
        )
        for (i, eval) in enumerate(evaluation['answer']):
            if eval.score < 1:
                print("-"*50, f"{i+1}) ", eval.query, "-"*50)
                print(eval.feedback)
                print(f"Final score: {eval.score}")
                print("="*125)
        print("::] DONE")
            
    asyncio.run(main())
