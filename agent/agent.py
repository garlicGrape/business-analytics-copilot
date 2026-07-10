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
# gemini-flash-latest is Google's maintained alias for the current recommended
# Flash model. The free tier grants zero quota for Pro-tier models (confirmed
# via a live 429 with limit: 0), so Flash is what's actually usable here -
# swap to gemini-pro-latest if this project moves to a paid tier.
model = ChatGoogleGenerativeAI(model="gemini-flash-latest")

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
