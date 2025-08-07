from llama_index.core.agent.workflow import FunctionAgent
from workflow_config.default_settings import Settings

#
# Router Agent that takes user query and hands off to an appropriate
# agent specializing in a context area of the MWB REST API to get data
# or the RAG Agent for general questions
#

router_agent = FunctionAgent(
    name="Router Agent",
    description=(
        "This agent does not answer user queries directly. Instead, it analyzes the query and determines which agent "
        "or agents are best suited to handle it. It uses the `handoff` tool to pass the query along with a detailed reason. "
        "The reason should help the next agent(s) understand the context and decide whether to respond or hand off again."
    ),
    system_prompt=(
        "You are a routing agent. Your only job is to carefully analyze the user's query and determine which agent "
        "or agents should handle it. You must use the `handoff` tool to pass the query to the selected agent.\n\n"
        "The `reason` argument must be detailed. It should explain:\n"
        "- Why the selected agent is appropriate.\n"
        "- What the agent should focus on.\n"
        "- Whether the agent should consider handing off again, and if so, to which agent(s) and why.\n\n"
        "You must not attempt to answer the query yourself or use any tools other than `handoff`."
    ),
    tools=[],  # No tools needed since handoff is built-in
    can_hand_off_to=[
        "Compound Agent",
        "Gene Agent",
        "Moverz Agent",
        "Protein Agent",
        "Refmet Agent",
        "Study Agent",
        "Metabolomics RAG Agent"
    ]
)
