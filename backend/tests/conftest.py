"""Stub heavy connector SDKs so the app imports without live databases or cloud credentials."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

for name in ["psycopg2", "psycopg2.extras", "boto3", "boto3.dynamodb", "boto3.dynamodb.types",
             "pyiceberg", "pyiceberg.catalog", "pdfplumber"]:
    root = name.split(".")[0]
    if root not in sys.modules and importlib.util.find_spec(root) is None:
        sys.modules[root] = MagicMock()
    if name not in sys.modules and isinstance(sys.modules.get(root), MagicMock):
        sys.modules[name] = MagicMock()
