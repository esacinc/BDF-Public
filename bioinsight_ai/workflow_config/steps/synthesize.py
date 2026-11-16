from llama_index.core.prompts import RichPromptTemplate, ChatMessage
import re

# Should cache this since static
SYNTHESIZE_SYSTEM_PROMPT = ChatMessage(
            role="system",
            content="""
            You are a biomedical research content synthesizer. Your role is to organize multiple data source responses into a comprehensive document that clearly attributes information to its originating source while maintaining scientific rigor.
            This synthesis will help researchers understand findings from multiple data sources, with clear attribution to enable further investigation of specific sources when needed.
            """
        )

SYNTHESIZE_TEMPLATE = RichPromptTemplate(
    """
    {% chat role="user" %}
    <synthesis_requirements>
    1. ORGANIZE content by data source with clear section headers
    2. EXPLICITLY attribute all information to its originating data source  
    3. PRESERVE all factual information, findings, and insights
    4. CREATE logical flow within each source section
    5. CROSS-REFERENCE between sources for related or contradictory findings
    6. MAINTAIN all hyperlinks, citations, and references exactly as provided - DO NOT modify existing markdown links [text](url)
    </synthesis_requirements>

    <output_format>
    Use clean markdown formatting where appropriate such as:
    - ## Headers
    - ### Topic subsections
    - **Bold** for key findings
    - Bullet points for lists and findings
    - Tables using markdown syntax when appropriate
    For hyperlinks:
    - Keep all existing markdown links [text](url) completely unchanged
    - Only convert plain URLs (like https://example.com) to markdown format [description](https://example.com)
    - Do NOT modify, enhance, or wrap existing markdown links
    </output_format>

    <agent_responses>
    {{ AGENT_RESPONSES }}
    </agent_responses>
    
    Before generating your synthesis, consider the key themes, relationships between sources, and how to best organize information for the user.

    User query: "{{ USER_QUERY }}"

     CRITICAL: Before finalizing your response, verify that:
    1. No existing markdown links [text](url) have been modified
    2. No nested or double-encoded links exist
    3. Only plain URLs have been converted to markdown format

    Provide your complete synthesis within <answer></answer> tags.
    {% endchat %}
    """)


