"""Seeds LocalStack DynamoDB with product inventory data for demo purposes."""
import boto3
import json

ENDPOINT = "http://localhost:4566"
REGION = "us-east-1"

client = boto3.client(
    "dynamodb",
    endpoint_url=ENDPOINT,
    region_name=REGION,
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

TABLE = "product_inventory"

try:
    client.create_table(
        TableName=TABLE,
        KeySchema=[{"AttributeName": "product_sku", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "product_sku", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"Created table {TABLE}")
except client.exceptions.ResourceInUseException:
    print(f"Table {TABLE} already exists")

ITEMS = [
    {"product_sku": "LP-4471", "product_name": "Laptop Pro", "category": "Electronics", "reorder_level": 10, "lead_time_days": 7, "preferred_supplier": "SUP-001"},
    {"product_sku": "PH-8832", "product_name": "Phone Max",  "category": "Electronics", "reorder_level": 20, "lead_time_days": 5, "preferred_supplier": "SUP-002"},
    {"product_sku": "TB-2291", "product_name": "Tablet Plus", "category": "Electronics", "reorder_level": 15, "lead_time_days": 6, "preferred_supplier": "SUP-003"},
    {"product_sku": "MN-5543", "product_name": "Monitor HD",  "category": "Electronics", "reorder_level": 8,  "lead_time_days": 10, "preferred_supplier": "SUP-001"},
    {"product_sku": "KB-1190", "product_name": "Keyboard Elite", "category": "Accessories", "reorder_level": 30, "lead_time_days": 3, "preferred_supplier": "SUP-004"},
]

def to_dynamo(item: dict) -> dict:
    out = {}
    for k, v in item.items():
        if isinstance(v, str):
            out[k] = {"S": v}
        elif isinstance(v, int):
            out[k] = {"N": str(v)}
    return out

for item in ITEMS:
    client.put_item(TableName=TABLE, Item=to_dynamo(item))
    print(f"  inserted {item['product_sku']}")

print("Done.")
