# Business Analytics Copilot

A tool-calling agent that answers business questions by combining structured
e-commerce data with qualitative facts from SEC filings — built to demonstrate
the three patterns 2026 AI-engineering hiring managers screen for: grounded
retrieval (RAG), autonomous tool use, and evaluated, cited output, rather than
a plain LLM wrapper.

**Business question it answers:** *"Given our order history and how our
competitors describe their own risk factors and strategy in public filings,
what should we watch out for?"* — the kind of question a business analyst
gets asked and has to pull from two different kinds of sources to answer.

## Architecture

```
                 ┌─────────────┐
   React ──HTTP──▶  FastAPI    │
  dashboard      │  (agent.py) │
                 └──────┬──────┘
                        │ LangGraph create_react_agent
             ┌──────────┴──────────┐
             ▼                     ▼
      sql_query_tool         rag_search_tool
             │                     │
             ▼                     ▼
     ┌──────────────────────────────────┐
     │      Supabase (Postgres)         │
     │  orders/customers/products  +    │
     │  document_chunks (pgvector)      │
     └──────────────────────────────────┘
```

One Postgres instance (Supabase) serves both the structured tables and the
embedded filing chunks via `pgvector` — no separate vector database.

- **Structured data:** [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
  (~100K real orders)
- **Unstructured data:** latest 10-K filing per company for ~10 large public
  companies, pulled live from [SEC EDGAR](https://www.sec.gov/edgar)
- **Agent:** LangGraph `create_react_agent` with two tools and a
  checkpointer for per-session memory
- **Frontend:** React + Vite dashboard — a revenue-by-category chart (direct
  SQL, not LLM-generated) plus a chat panel for open-ended questions

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Enable the `pgvector` extension: **Database → Extensions → vector**
3. Run `ingestion/schema.sql` in the SQL editor
4. Copy your project URL, anon key, service role key, and DB connection
   string into `.env` (see `.env.example`)

### 2. Load the data

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# download https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
# and unzip into ingestion/data/olist/
python ingestion/load_olist.py

# requires OPENAI_API_KEY and SEC_EDGAR_CONTACT in .env
python ingestion/embed_filings.py
```

### 3. Run the agent

```bash
# quick interactive test in the terminal
python -m agent.cli

# or serve it over HTTP
uvicorn agent.server:app --reload --port 8000
```

### 4. Run the dashboard

```bash
cd frontend
npm install
cp .env.example .env   # defaults to http://localhost:8000
npm run dev
```

## Evaluation

A handful of test questions and what "correct" looks like, used to sanity-check
the agent after any prompt or schema change:

| Question | Tool(s) expected | Pass criteria |
|---|---|---|
| "What were total sales in São Paulo in 2017?" | `sql_query_tool` | Number matches a manual SQL query against `orders`/`order_items`/`customers` |
| "What risk factors did Tesla disclose in their latest 10-K?" | `rag_search_tool` | Cites TSLA, correct filing date, claims traceable to returned excerpts |
| "How does our top category's revenue compare to what Amazon's 10-K says about their retail risk factors?" | both | Uses both tools before answering; doesn't hallucinate a number it didn't query |

Run these manually via `python -m agent.cli` after setup and record the
transcripts here (or in `docs/`) once the data is loaded — a documented eval
section is one of the differentiators the 2026 hiring research flagged as rare
among AI-engineering candidates.

## Repo layout

```
agent/        LangGraph agent, tools, FastAPI server, CLI
ingestion/    schema.sql + scripts to load Olist data and embed SEC filings
frontend/     React + Vite dashboard
docs/         architecture notes, eval transcripts
```

## Security notes

`sql_query_tool` only accepts a single read-only `SELECT` statement (rejects
writes and stacked statements) since the SQL it runs is LLM-generated from
untrusted natural-language input. Both tools open the DB connection in a
read-only transaction as defense in depth. Row-level security is enabled on
every table with public read policies; only the `service_role` key (used
solely by the ingestion scripts, never the frontend) can write.
