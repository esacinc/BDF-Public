from llama_index.core.prompts import RichPromptTemplate
from workflow_config.steps.intent_recognition.intent import AvailableSources
from log_helper.logger import get_logger
logger = get_logger()

# Define data sources
data_sources = [source.value for source in AvailableSources]
sources = ', '.join(data_sources[:-1]) + ', and ' + data_sources[-1]

# Define prompt templates
prompt_templates = [
    RichPromptTemplate("What is the primary purpose of the {{data_source}}?"),
    RichPromptTemplate("What types of data does the {{data_source}} provide?"),
    RichPromptTemplate("What data modalities are included in the {{data_source}}?"),
    RichPromptTemplate("What diseases or conditions are represented in the {{data_source}}?"),
    # RichPromptTemplate("What are the major studies or datasets available in the {{data_source}}?"),
    RichPromptTemplate("What makes the {{data_source}} unique compared to other biomedical data repositories?")
]

# Build dictionary of ChatMessages
query_dict = {}

for source in data_sources:
    messages = []
    for template in prompt_templates:
        messages.extend(template.format_messages(data_source=source))
    query_dict[source] = messages

# Add cross-source queries
cross_source_templates = [
    RichPromptTemplate("What do the following data sources have in common: {{sources}}?"),
    RichPromptTemplate("What is unique about each of the following data sources: {{sources}}?")
    # RichPromptTemplate("Which diseases or conditions are commonly represented across {{sources}}?")
]

cross_messages = []
for template in cross_source_templates:
    cross_messages.extend(template.format_messages(sources=sources))

query_dict["Cross-Source"] = cross_messages

# Serializable 
# import json
# sdict = {k:[i.content for i in query_dict[k]] for k in query_dict}
# json.dumps(sdict, indent=4)
# 