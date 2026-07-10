from langchain_google_genai import ChatGoogleGenerativeAI
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

# reads GOOGLE_API_KEY from the environment automatically
#
# Pinned to gemini-3.1-flash-lite after ruling out the alternatives live:
#   - gemini-pro-latest / any Pro-tier model: free tier grants zero quota
#   - gemini-flash-latest (-> gemini-3.5-flash): free tier caps at 20
#     requests/DAY, exhausted almost immediately by normal testing
#   - gemini-2.5-flash: 404s - no longer available to new API keys
# gemini-3.1-flash-lite actually has usable free-tier quota. Revisit this
# once the project is on a paid tier, or if free-tier limits change again.
model = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite")

agent = create_react_agent(
    model,
    tools=[sql_query_tool, rag_search_tool],
    prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)


def extract_text(content) -> str:
    """Gemini returns message content as a list of content blocks (each
    carrying extra metadata like thought signatures), not a plain string
    like Claude does. Normalize either shape down to plain text."""
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )
