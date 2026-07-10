"""
Minimal HTTP layer around the LangGraph agent.

Run: uvicorn agent.server:app --reload --port 8000
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .agent import agent, extract_text
from .db import get_connection

app = FastAPI(title="Business Analytics Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def handle_uncaught_exception(request: Request, exc: Exception):
    # An unhandled exception otherwise bypasses CORSMiddleware entirely, so
    # the browser reports a misleading "CORS blocked" error instead of the
    # real failure (e.g. a Gemini rate limit) - return a normal response
    # instead so the actual error reaches the frontend.
    return JSONResponse(status_code=500, content={"detail": str(exc)})


class ChatRequest(BaseModel):
    thread_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": req.message}]},
        config={"configurable": {"thread_id": req.thread_id}},
    )
    return ChatResponse(response=extract_text(result["messages"][-1].content))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats/top-categories")
def top_categories():
    """Top 10 product categories by revenue - powers the dashboard chart
    directly from SQL rather than parsing the agent's free-text output."""
    sql = """
        select
            coalesce(t.product_category_name_english, p.product_category_name, 'unknown') as category,
            round(sum(oi.price)::numeric, 2) as revenue
        from order_items oi
        join products p on p.product_id = oi.product_id
        left join product_category_translation t
            on t.product_category_name = p.product_category_name
        group by category
        order by revenue desc
        limit 10
    """
    conn = get_connection()
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return [{"category": category, "revenue": float(revenue)} for category, revenue in rows]
    finally:
        conn.close()
