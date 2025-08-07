from llama_index.core.prompts import RichPromptTemplate

template_str = (
    "Here is the original user query: {{ original_query }}\n\n"
    "Here is some additional context that may help in understanding the user query. "
    "If it's not helpful or doesn't enhance the query, feel free to disregard it: {{ modified_query }}"
)

USER_QUERY_TEMPLATE = RichPromptTemplate(template_str)
