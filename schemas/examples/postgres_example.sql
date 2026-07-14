-- Example: drop your exported Postgres DDL here
-- Export with: pg_dump --schema-only -t tablename mydb > schema.sql

CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    full_name     VARCHAR(200),
    email         VARCHAR(200) UNIQUE,
    region        VARCHAR(50),
    tier          VARCHAR(20),
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE products (
    product_id    VARCHAR(20) PRIMARY KEY,
    product_name  VARCHAR(200),
    category      VARCHAR(100),
    unit_price    NUMERIC(10,2),
    supplier_id   VARCHAR(20)
);
