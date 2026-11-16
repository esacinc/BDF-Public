from llama_index.core.prompts import RichPromptTemplate

template = """
{% chat role="user" %}
Original user query: "{{ USER_QUERY }}"
Task: {{ TASK_DESCRIPTION }}
Your Role: You are an agent in a multi-agent system designed to assist with biomedical research inquiries. Your task is part of a broader effort to answer a user query.
{% endchat %}
"""

AGENT_PROMPT = RichPromptTemplate(template_str=template)