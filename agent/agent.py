from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from .tools import rag_search_tool, sql_query_tool

SYSTEM_PROMPT = """You are a business analytics copilot. You answer questions
about an e-commerce business using two tools:

- sql_query_tool: structured facts from the orders/customers/products database
- rag_search_tool: qualitative facts and risk factors from SEC 10-K filings

Always ground numeric claims in a tool call rather than estimating. When you
cite a filing, name the company and filing date. If a question needs both a
database lookup and a filing citation, use both tools before answering.
"""

# InMemorySaver keeps conversation memory for the lifetime of the process,
# scoped per thread_id. Swap for langgraph-checkpoint-postgres's PostgresSaver
# (pointed at SUPABASE_DB_URL) if you want memory to survive a restart.
checkpointer = InMemorySaver()

agent = create_react_agent(
    "anthropic:claude-opus-4-8",
    tools=[sql_query_tool, rag_search_tool],
    prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)
