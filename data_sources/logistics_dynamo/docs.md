# Logistics DynamoDB — Business Context

This DynamoDB table (`logistics_shipments`) tracks shipments from warehouse to customer. Unlike the Postgres and Druid sources, DynamoDB has no enforced schema — each item may have different attributes depending on the shipment type and carrier. The table is sampled at ingestion time to infer the shape.

## Common attributes observed across items

- **shipment_id** (PK, String): Unique shipment identifier. Format: SHP-{year}-{sequence}.
- **order_ref** (String): Reference to the originating order — corresponds to `order_id` in Postgres orders table.
- **product_sku** (String): The product being shipped — same real-world product as `product_id` (Postgres) and `sku_code` (Druid). Yet another naming variant.
- **status** (String): Current shipment state — in_transit, delivered, failed_delivery, returned.
- **carrier** (String): Shipping carrier name.
- **tracking_number** (String): Carrier tracking reference.
- **destination_region** (String): Geographic region for delivery.
- **estimated_delivery** (String, ISO date): Expected delivery date.
- **actual_delivery** (String, ISO date, optional): Present only when status = delivered.
- **failure_reason** (String, optional): Present only when status = failed_delivery or returned.
- **weight_kg** (Number, optional): Package weight — present for large items (laptops, monitors) but often absent for small items.
- **fragile_flag** (Boolean, optional): Present only when the carrier requires special handling.

## Notes
The per-item variability is intentional — this tests whether the ontology generator can handle a non-relational, structurally inconsistent source. `product_sku` here is a third naming variant for the same product identifier concept already seen as `product_id` (Postgres) and `sku_code` (Druid).
