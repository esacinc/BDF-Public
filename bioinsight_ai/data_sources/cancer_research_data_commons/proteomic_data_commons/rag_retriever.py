from config import AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, PUBLICATIONS_KB_ID
from workflow_config.default_settings import Settings
from llama_index.retrievers.bedrock import AmazonKnowledgeBasesRetriever
from llama_index.core import get_response_synthesizer
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor

#
# RAG retriever to gather PDC website info and/or journal article information
#

retriever = AmazonKnowledgeBasesRetriever(
    knowledge_base_id=PUBLICATIONS_KB_ID,
    aws_access_key_id=AWS_ACCESS_KEY, 
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
    retrieval_config={
        "vectorSearchConfiguration": {
            "numberOfResults": 10,
            "overrideSearchType": "HYBRID",
        }
    },
)

response_synthesizer = get_response_synthesizer(
    response_mode="compact"
)

website_journal_engine = RetrieverQueryEngine(
    retriever=retriever,
    response_synthesizer=response_synthesizer,
    node_postprocessors=[SimilarityPostprocessor(similarity_cutoff=0.45)]
)