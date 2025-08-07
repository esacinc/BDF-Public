from config import MWB_KB_ID, AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, MWB_SOURCE_ID
from llama_index.retrievers.bedrock import AmazonKnowledgeBasesRetriever
from llama_index.core import get_response_synthesizer
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.tools import QueryEngineTool
from llama_index.core.agent.workflow import FunctionAgent
from workflow_config.default_settings import Settings

#
# RAG Agent that specializes in information scrapped from MWB website. Can answer
# general questions about this data source
#

# AWS KB Web Crawler
retriever = AmazonKnowledgeBasesRetriever(
    knowledge_base_id=MWB_KB_ID,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
    retrieval_config={
        "vectorSearchConfiguration": {
            "overrideSearchType": "HYBRID",
            "filter": {
                "equals": {
                    "key": "x-amz-bedrock-kb-data-source-id",
                    "value": MWB_SOURCE_ID
                }
            }
        }
    },
)

response_synthesizer = get_response_synthesizer(
    response_mode="compact",
    structured_answer_filtering=True
)
engine = RetrieverQueryEngine(retriever=retriever, response_synthesizer=response_synthesizer)

rag_tool = QueryEngineTool.from_defaults(
    query_engine=engine,
    name="MetabolomicsRAGTool",
    description=(
        "Retrieve information from the Metabolomics Workbench website to answer general questions about this data source."
    ) 
)

rag_agent = FunctionAgent(
    name="Metabolomics RAG Agent",
    description=(
        "An expert assistant for answering general questions about the Metabolomics Workbench website. "
        "This agent helps users understand the platform's purpose, available data types (including metabolomics and multiomics), "
        "how to navigate the site, use its tools, access APIs, and upload their own data. It is ideal for users seeking guidance "
        "on how to interact with the platform, but it does not retrieve specific datasets or perform analysis."
    ),
    system_prompt=(
        "You are a knowledgeable assistant specialized in the Metabolomics Workbench website. Your role is to help users understand "
        "what the platform offers and how to use it. You can explain:\n"
        "- What Metabolomics Workbench is and its mission\n"
        "- The types of data available (e.g., metabolomics, multiomics)\n"
        "- How users can upload their own data\n"
        "- How to access data via the API\n"
        "- Available databases, tools, and analysis features\n"
        "- Tutorials, documentation, and general usage guidance\n\n"
        "You do not retrieve or analyze specific data, and you must not use any external knowledge. Only use information available through your tools."
    ),
    tools=[rag_tool],
    can_hand_off_to=[
        "Compound Agent", "Gene Agent", "Moverz Agent", "Protein Agent",
        "Refmet Agent", "Study Agent", "Metabolomics RAG Agent"
    ]
)