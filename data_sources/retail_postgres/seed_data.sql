-- Customers
INSERT INTO customers VALUES
  ('CUST-001', 'Alice Nakamura',    'alice@example.com',   'West',  'premium',    NOW()),
  ('CUST-002', 'Bob Okafor',        'bob@example.com',     'East',  'standard',   NOW()),
  ('CUST-003', 'Carol Vance',       'carol@example.com',   'North', 'enterprise', NOW()),
  ('CUST-004', 'David Ramos',       'david@example.com',   'South', 'standard',   NOW()),
  ('CUST-005', 'Elena Petrova',     'elena@example.com',   'West',  'premium',    NOW());

-- Products — note product_id values match sku_code values in Druid seed
INSERT INTO products VALUES
  ('LP-4471', 'Laptop Pro 14',   'Laptops',   1299.99,  42, 'SUP-001', TRUE),
  ('PH-8832', 'Phone Max',       'Phones',     899.00,  78, 'SUP-002', TRUE),
  ('TB-2291', 'Tablet Plus',     'Tablets',    599.50,  31, 'SUP-001', TRUE),
  ('MN-5543', 'Monitor HD 27',   'Monitors',   449.00,  15, 'SUP-003', TRUE),
  ('KB-1190', 'Keyboard Elite',  'Peripherals', 149.00,  60, 'SUP-003', TRUE);

-- Orders
INSERT INTO orders VALUES
  ('ORD-20240101', 'CUST-001', '2024-01-01', 'delivered', 1299.99, 'West'),
  ('ORD-20240115', 'CUST-002', '2024-01-15', 'shipped',    899.00, 'East'),
  ('ORD-20240120', 'CUST-003', '2024-01-20', 'delivered', 2048.49, 'North'),
  ('ORD-20240201', 'CUST-001', '2024-02-01', 'pending',    599.50, 'West'),
  ('ORD-20240210', 'CUST-005', '2024-02-10', 'cancelled',  449.00, 'West');

-- Order items
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
  ('ORD-20240101', 'LP-4471', 1, 1299.99),
  ('ORD-20240115', 'PH-8832', 1,  899.00),
  ('ORD-20240120', 'TB-2291', 2,  599.50),
  ('ORD-20240120', 'KB-1190', 1,  149.00),  -- correction: 2*599.50 + 149 + discount -> approximate
  ('ORD-20240201', 'TB-2291', 1,  599.50),
  ('ORD-20240210', 'MN-5543', 1,  449.00);

-- Inventory
INSERT INTO inventory (product_id, warehouse_id, qty_on_hand, qty_reserved, last_restocked) VALUES
  ('LP-4471', 'WH-WEST', 30, 5, '2024-01-10'),
  ('LP-4471', 'WH-EAST', 12, 2, '2024-01-05'),
  ('PH-8832', 'WH-WEST', 50, 8, '2024-01-12'),
  ('TB-2291', 'WH-NORTH', 31, 3, '2024-01-08'),
  ('MN-5543', 'WH-SOUTH', 15, 1, '2023-12-20'),
  ('KB-1190', 'WH-WEST', 60, 0, '2024-01-15');
