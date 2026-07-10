"""
Loads the Olist Brazilian E-Commerce dataset into Supabase Postgres.

Setup:
    1. Download the dataset from
       https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
       and unzip it into ingestion/data/olist/ (this folder is gitignored).
       You should end up with files like:
         olist_customers_dataset.csv
         olist_orders_dataset.csv
         olist_order_items_dataset.csv
         olist_order_payments_dataset.csv
         olist_products_dataset.csv
         olist_sellers_dataset.csv
         product_category_name_translation.csv
    2. Run schema.sql in the Supabase SQL editor first.
    3. Set SUPABASE_DB_URL in .env (Project Settings -> Database -> Connection string).
    4. python ingestion/load_olist.py

Idempotent: uses upsert on primary key, safe to re-run.
"""

import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent / "data" / "olist"
DB_URL = os.environ["SUPABASE_DB_URL"]

# (csv filename, table name, columns to keep in table order, primary key cols)
TABLES = [
    (
        "product_category_name_translation.csv",
        "product_category_translation",
        ["product_category_name", "product_category_name_english"],
        ["product_category_name"],
    ),
    (
        "olist_customers_dataset.csv",
        "customers",
        [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ],
        ["customer_id"],
    ),
    (
        "olist_sellers_dataset.csv",
        "sellers",
        ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
        ["seller_id"],
    ),
    (
        "olist_products_dataset.csv",
        "products",
        [
            "product_id",
            "product_category_name",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
        ["product_id"],
    ),
    (
        "olist_orders_dataset.csv",
        "orders",
        [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        ["order_id"],
    ),
    (
        "olist_order_items_dataset.csv",
        "order_items",
        [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "price",
            "freight_value",
        ],
        ["order_id", "order_item_id"],
    ),
    (
        "olist_order_payments_dataset.csv",
        "order_payments",
        [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ],
        ["order_id", "payment_sequential"],
    ),
]


def load_table(conn, csv_name, table, columns, pk_cols):
    csv_path = DATA_DIR / csv_name
    if not csv_path.exists():
        print(f"skip {table}: {csv_path} not found")
        return

    df = pd.read_csv(csv_path, usecols=columns)
    # cast to object first - on a numeric-dtype column, .where(..., None) silently
    # keeps NaN instead of None, since a float64 array can't hold Python None
    df = df.astype(object).where(pd.notnull(df), None)
    rows = list(df[columns].itertuples(index=False, name=None))
    if not rows:
        print(f"skip {table}: no rows")
        return

    update_cols = [c for c in columns if c not in pk_cols]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conflict_clause = (
        f"on conflict ({', '.join(pk_cols)}) do update set {set_clause}"
        if update_cols
        else f"on conflict ({', '.join(pk_cols)}) do nothing"
    )

    sql = (
        f"insert into {table} ({', '.join(columns)}) values %s {conflict_clause}"
    )

    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)
    conn.commit()
    print(f"loaded {len(rows)} rows into {table}")


def main():
    conn = psycopg2.connect(DB_URL)
    try:
        for csv_name, table, columns, pk_cols in TABLES:
            load_table(conn, csv_name, table, columns, pk_cols)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
