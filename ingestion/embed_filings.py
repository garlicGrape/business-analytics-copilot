"""
Fetches each company's latest 10-K from SEC EDGAR, chunks the text, embeds
the chunks, and upserts them into Supabase's document_chunks pgvector table.

Setup:
    1. Run schema.sql in the Supabase SQL editor first (creates document_chunks
       + the match_document_chunks RPC).
    2. Set in .env:
         SUPABASE_DB_URL       - Supabase Postgres connection string
         GOOGLE_API_KEY        - used for gemini-embedding-001, truncated to
                                  1536 dims to match the vector(1536) column
                                  in schema.sql (also used by agent/tools.py -
                                  keep EMBEDDING_MODEL/EMBEDDING_DIM in sync
                                  between the two files, or search stops matching)
         SEC_EDGAR_CONTACT     - required by SEC's fair-access policy, e.g.
                                  "Your Name your.email@example.com"
    3. python ingestion/embed_filings.py

SEC EDGAR requires a descriptive User-Agent identifying the requester
(https://www.sec.gov/os/webmaster-faq#developers) - do not remove it or
requests will be blocked.
"""

import os
import re
import time

import psycopg2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

DB_URL = os.environ["SUPABASE_DB_URL"]
SEC_CONTACT = os.environ.get(
    "SEC_EDGAR_CONTACT", "Portfolio Project portfolio-project@example.com"
)
EMBEDDING_MODEL = "models/gemini-embedding-001"  # must match agent/tools.py
EMBEDDING_DIM = 1536  # must match schema.sql's vector(1536) and agent/tools.py

# Ticker -> 10-digit zero-padded CIK. Extend this list as you like; keep it
# to ~10-15 companies for a portfolio-scale corpus (see plan for storage math).
COMPANIES = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "AMZN": "0001018724",
    "TSLA": "0001318605",
    "NFLX": "0001065280",
    "NVDA": "0001045810",
    "JPM": "0000019617",
    "WMT": "0000104169",
    "KO": "0000021344",
    "DIS": "0001744489",
}

HEADERS = {"User-Agent": SEC_CONTACT}
# Larger chunks than a typical RAG setup: the Gemini free tier caps embedding
# calls at 100 requests/minute, and langchain_google_genai issues roughly one
# request per chunk for this model, so fewer/bigger chunks means fewer calls.
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 400

embedder = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)


def get_latest_10k(cik: str):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    recent = data["filings"]["recent"]
    for form, accession, primary_doc, filing_date in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        recent["filingDate"],
    ):
        if form == "10-K":
            accession_nodashes = accession.replace("-", "")
            cik_nolead = cik.lstrip("0")
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_nolead}/{accession_nodashes}/{primary_doc}"
            )
            return doc_url, filing_date
    return None, None


def fetch_filing_text(doc_url: str) -> str:
    resp = requests.get(doc_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def _embed_one_with_retry(text: str, max_retries: int = 6) -> list[float]:
    for attempt in range(max_retries):
        try:
            return embedder.embed_documents(
                [text],
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBEDDING_DIM,
            )[0]
        except Exception as exc:
            if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                wait = 20
                print(f"  rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("embedding failed after repeated rate-limit retries")


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    # One request per chunk, paced to stay under the free tier's
    # 100 requests/minute cap on embed_content (~0.7s/req = ~85/min).
    embeddings = []
    for i, chunk in enumerate(chunks):
        embeddings.append(_embed_one_with_retry(chunk))
        if i < len(chunks) - 1:
            time.sleep(0.7)
    return embeddings


def upsert_chunks(conn, company, filing_date, source_url, chunks, embeddings):
    with conn.cursor() as cur:
        cur.execute("delete from document_chunks where company = %s", (company,))
        rows = [
            (company, "10-K", filing_date, source_url, idx, chunk, embedding)
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        cur.executemany(
            """
            insert into document_chunks
                (company, filing_type, filing_date, source_url, chunk_index, content, embedding)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()


def main():
    conn = psycopg2.connect(DB_URL)
    try:
        for ticker, cik in COMPANIES.items():
            print(f"{ticker}: looking up latest 10-K...")
            doc_url, filing_date = get_latest_10k(cik)
            if not doc_url:
                print(f"{ticker}: no 10-K found, skipping")
                continue

            print(f"{ticker}: fetching {doc_url}")
            text = fetch_filing_text(doc_url)
            chunks = chunk_text(text)
            print(f"{ticker}: {len(chunks)} chunks, embedding...")
            embeddings = embed_chunks(chunks)
            upsert_chunks(conn, ticker, filing_date, doc_url, chunks, embeddings)
            print(f"{ticker}: stored {len(chunks)} chunks (filed {filing_date})")

            time.sleep(0.5)  # stay well within SEC's fair-access rate limits
    finally:
        conn.close()


if __name__ == "__main__":
    main()
