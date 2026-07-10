import os
import re

from langchain_core.tools import tool
from openai import OpenAI

from .db import get_connection

EMBEDDING_MODEL = "text-embedding-3-small"  # must match ingestion/embed_filings.py

_openai_client = OpenAI()

# Only single, read-only SELECT statements are allowed through this tool.
# The agent generates this SQL from natural language, so treat it as
# untrusted input even though it never reaches an HTTP layer directly.
_SELECT_ONLY_RE = re.compile(r"^\s*select\b", re.IGNORECASE)


def _is_safe_select(sql: str) -> bool:
    if not _SELECT_ONLY_RE.match(sql):
        return False
    # reject anything after a semicolon (stacked statements), allowing at
    # most one trailing semicolon with nothing but whitespace after it
    body = sql.strip()
    if body.endswith(";"):
        body = body[:-1]
    if ";" in body:
        return False
    forbidden = re.compile(
        r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke)\b",
        re.IGNORECASE,
    )
    return not forbidden.search(body)


@tool
def sql_query_tool(sql: str) -> str:
    """Run a read-only SQL SELECT query against the e-commerce database
    (tables: customers, orders, order_items, order_payments, products,
    sellers, product_category_translation) and return the results.

    Only single SELECT statements are permitted. Always add a LIMIT to
    exploratory queries.
    """
    if not _is_safe_select(sql):
        return "Rejected: only a single read-only SELECT statement is allowed."

    conn = get_connection()
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchmany(200)
        if not rows:
            return "Query returned no rows."
        header = " | ".join(columns)
        lines = [header, "-" * len(header)]
        lines += [" | ".join(str(v) for v in row) for row in rows]
        return "\n".join(lines)
    except Exception as exc:
        return f"Query failed: {exc}"
    finally:
        conn.close()


@tool
def rag_search_tool(query: str, company: str | None = None) -> str:
    """Search SEC 10-K filing text for facts relevant to the query.
    Optionally scope the search to one company's ticker (e.g. "AAPL").
    Returns the most relevant filing excerpts with their source company
    and filing date, for citation.
    """
    embedding = (
        _openai_client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
        .data[0]
        .embedding
    )

    conn = get_connection()
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(
                "select company, filing_type, filing_date, source_url, content, similarity "
                "from match_document_chunks(%s::vector, %s, %s)",
                (embedding, 5, company),
            )
            rows = cur.fetchall()
        if not rows:
            return "No relevant filing excerpts found."
        out = []
        for company_, filing_type, filing_date, source_url, content, similarity in rows:
            out.append(
                f"[{company_} {filing_type}, filed {filing_date}, "
                f"similarity={similarity:.2f}]\n{content}\nSource: {source_url}"
            )
        return "\n\n".join(out)
    except Exception as exc:
        return f"Search failed: {exc}"
    finally:
        conn.close()
