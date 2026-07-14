# Retail Druid — Business Context

This Druid datasource (`inventory_events`) is the real-time event stream for inventory movements. It receives events from warehouse management systems, the order fulfilment pipeline, and the maintenance reporting system.

## Key columns

- **sku_code**: The product identifier. This is the same real-world product as `product_id` in the Postgres system — the naming differs because this stream was built by a different team. Values are identical (LP-4471, PH-8832, etc.).
- **event_type**: What happened — restock (positive qty_delta), sale (negative qty_delta), flag_low_stock (threshold alert, zero delta), failure_report (unit failed, zero delta).
- **warehouse_code**: The warehouse where the event occurred. Same real-world locations as `warehouse_id` in Postgres inventory (WH-WEST, WH-EAST, etc.) — again, column named differently.
- **region**: Geographic region — same values as the `region` column in Postgres customers and inventory.
- **qty_delta**: Change in stock level. Positive = added, negative = removed, zero = status event.
- **stock_level**: Running total of units at this warehouse after the event.
- **triggered_by**: What caused this event — auto_replenish (automated reorder), an order ID, threshold_alert (low-stock rule), manual (warehouse staff action), or maintenance_system.

## Purpose
Downstream consumers use this stream to monitor stock levels in real time, trigger replenishment, and track which orders caused which inventory movements. The `failure_report` event type bridges to the maintenance reporting system — when maintenance logs a failed unit, it emits an event here too.
