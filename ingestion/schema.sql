-- Run this in the Supabase SQL editor (Database -> SQL Editor -> New query) once
-- pgvector has been enabled under Database -> Extensions.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- Structured data: Olist Brazilian E-Commerce dataset
-- https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
-- ---------------------------------------------------------------------------

create table if not exists customers (
    customer_id text primary key,
    customer_unique_id text not null,
    customer_zip_code_prefix text,
    customer_city text,
    customer_state text
);

create table if not exists sellers (
    seller_id text primary key,
    seller_zip_code_prefix text,
    seller_city text,
    seller_state text
);

create table if not exists product_category_translation (
    product_category_name text primary key,
    product_category_name_english text
);

create table if not exists products (
    product_id text primary key,
    product_category_name text references product_category_translation(product_category_name),
    product_weight_g numeric,
    product_length_cm numeric,
    product_height_cm numeric,
    product_width_cm numeric
);

create table if not exists orders (
    order_id text primary key,
    customer_id text references customers(customer_id),
    order_status text,
    order_purchase_timestamp timestamptz,
    order_approved_at timestamptz,
    order_delivered_carrier_date timestamptz,
    order_delivered_customer_date timestamptz,
    order_estimated_delivery_date timestamptz
);

create table if not exists order_items (
    order_id text references orders(order_id),
    order_item_id int,
    product_id text references products(product_id),
    seller_id text references sellers(seller_id),
    price numeric,
    freight_value numeric,
    primary key (order_id, order_item_id)
);

create table if not exists order_payments (
    order_id text references orders(order_id),
    payment_sequential int,
    payment_type text,
    payment_installments int,
    payment_value numeric,
    primary key (order_id, payment_sequential)
);

create index if not exists idx_orders_purchase_ts on orders(order_purchase_timestamp);
create index if not exists idx_orders_customer on orders(customer_id);
create index if not exists idx_order_items_order on order_items(order_id);
create index if not exists idx_customers_state on customers(customer_state);

-- ---------------------------------------------------------------------------
-- Unstructured data: SEC 10-K filing chunks (RAG side)
-- Embedding dimension uses Gemini's gemini-embedding-001, truncated to
-- 1536 dims via output_dimensionality (see ingestion/embed_filings.py and
-- agent/tools.py - both must stay in sync with this column size).
-- Change the vector(1536) size below if you use a different embedding model.
-- ---------------------------------------------------------------------------

create table if not exists document_chunks (
    id bigint generated always as identity primary key,
    company text not null,
    filing_type text not null,
    filing_date date,
    source_url text,
    chunk_index int not null,
    content text not null,
    embedding vector(1536) not null
);

create index if not exists idx_document_chunks_company on document_chunks(company);

-- ivfflat index for approximate nearest-neighbor cosine search.
-- Requires at least a few hundred rows to be useful; fine to create up front.
create index if not exists idx_document_chunks_embedding
    on document_chunks using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- RPC used by the agent's rag_search_tool via supabase-py's .rpc() call.
create or replace function match_document_chunks(
    query_embedding vector(1536),
    match_count int default 5,
    filter_company text default null
)
returns table (
    id bigint,
    company text,
    filing_type text,
    filing_date date,
    source_url text,
    content text,
    similarity float
)
language sql stable
as $$
    select
        document_chunks.id,
        document_chunks.company,
        document_chunks.filing_type,
        document_chunks.filing_date,
        document_chunks.source_url,
        document_chunks.content,
        1 - (document_chunks.embedding <=> query_embedding) as similarity
    from document_chunks
    where filter_company is null or document_chunks.company = filter_company
    order by document_chunks.embedding <=> query_embedding
    limit match_count;
$$;

-- ---------------------------------------------------------------------------
-- Row-level security demo: lock structured tables to read-only for the
-- anon/frontend role, writes only via service_role (used by ingestion scripts).
-- ---------------------------------------------------------------------------

alter table customers enable row level security;
alter table orders enable row level security;
alter table order_items enable row level security;
alter table order_payments enable row level security;
alter table products enable row level security;
alter table sellers enable row level security;
alter table document_chunks enable row level security;

create policy "public read access" on customers for select using (true);
create policy "public read access" on orders for select using (true);
create policy "public read access" on order_items for select using (true);
create policy "public read access" on order_payments for select using (true);
create policy "public read access" on products for select using (true);
create policy "public read access" on sellers for select using (true);
create policy "public read access" on document_chunks for select using (true);
