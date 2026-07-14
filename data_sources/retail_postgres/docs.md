# Retail Postgres — Business Context

This database is the system of record for the retail order management system.

## Tables

### customers
Registered buyers. `tier` indicates account level: standard (default), premium (loyalty members), enterprise (B2B accounts). `region` is a geographic sales region (North, South, East, West) shared with the logistics and inventory systems.

### products
The product catalogue. `product_id` is the company's canonical product identifier — a short alphanumeric code (e.g. LP-4471 for the Laptop Pro 14). This is the same identifier used across all company systems, although some systems call it `sku_code` or `unit_id` instead. `category` is a broad product grouping. `active = FALSE` means the product is discontinued but kept for historical order records.

### orders
A customer purchase transaction. `status` lifecycle: pending → shipped → delivered (or cancelled). `shipping_region` is where the order was shipped, which may differ from the customer's home region for enterprise customers shipping to multiple sites.

### order_items
Line items within an order. Each row is one product in one order. `discount_pct` is the percentage discount applied to that line.

### inventory
Physical stock levels per product per warehouse. `qty_reserved` is stock already allocated to pending orders but not yet shipped. Available stock = `qty_on_hand - qty_reserved`. Warehouses are identified by `warehouse_id` (WH-WEST, WH-EAST, WH-NORTH, WH-SOUTH).

## Key relationships
- A customer places many orders
- An order contains one or more products via order_items
- A product appears in inventory across one or more warehouses
- product_id in this system is the same real-world concept as sku_code in the streaming events system and "unit" identifiers in maintenance documents
