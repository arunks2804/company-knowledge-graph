-- Retail domain: customers, orders, products, inventory
-- Deliberately uses 'product_id' as the product identifier
-- (Druid uses 'sku_code' for the same concept — exercises cross-system reconciliation)

CREATE TABLE IF NOT EXISTS customers (
    customer_id   VARCHAR(20) PRIMARY KEY,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(150) UNIQUE NOT NULL,
    region        VARCHAR(50),
    tier          VARCHAR(20) DEFAULT 'standard',   -- standard, premium, enterprise
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    product_id    VARCHAR(20) PRIMARY KEY,           -- e.g. LP-4471, PH-8832
    product_name  VARCHAR(150) NOT NULL,
    category      VARCHAR(80),
    unit_price    NUMERIC(10, 2) NOT NULL,
    stock_qty     INTEGER DEFAULT 0,
    supplier_id   VARCHAR(20),
    active        BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      VARCHAR(30) PRIMARY KEY,
    customer_id   VARCHAR(20) REFERENCES customers(customer_id),
    order_date    DATE NOT NULL,
    status        VARCHAR(30) DEFAULT 'pending',     -- pending, shipped, delivered, cancelled
    total_amount  NUMERIC(12, 2),
    shipping_region VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id       SERIAL PRIMARY KEY,
    order_id      VARCHAR(30) REFERENCES orders(order_id),
    product_id    VARCHAR(20) REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    NUMERIC(10, 2) NOT NULL,
    discount_pct  NUMERIC(5, 2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id  SERIAL PRIMARY KEY,
    product_id    VARCHAR(20) REFERENCES products(product_id),
    warehouse_id  VARCHAR(20),
    qty_on_hand   INTEGER DEFAULT 0,
    qty_reserved  INTEGER DEFAULT 0,
    last_restocked DATE
);
