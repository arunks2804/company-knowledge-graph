# Company Knowledge Graph

A source-agnostic tool that reads structured schemas (Postgres, Druid, DynamoDB) and unstructured documents, uses an LLM to build a shared ontology, resolves entities across all sources to single graph nodes, syncs to Neo4j, and exposes a retrieval interface.

---

## What it does

1. **Extracts** schemas and sample rows from Postgres, Apache Druid, DynamoDB, TimescaleDB, and Apache Iceberg
2. **Processes** documents (txt, md, pdf) into 800-char overlapping chunks with embeddings
3. **Generates** a shared ontology by asking the LLM to map all source concepts to a class hierarchy
4. **Resolves** entities across sources — `products.product_id = LP-4471` in Postgres, `sku_code = LP-4471` in Druid, `product_sku = LP-4471` in DynamoDB, and "SKU LP-4471" in maintenance reports all become one `Product` node
5. **Syncs** everything to Neo4j with confidence-based status (`auto_commit`, `needs_review`, `unresolved`)
6. **Authenticates** humans via session cookie (username/password) and AI agents via Bearer API keys, with read-only and read-write roles
7. **Exposes** a React UI for investigation, graph browsing, ontology exploration, document search, and a review queue

---

## Architecture

```
data_sources/           ← schemas, seed data, documents
ontology/               ← core_ontology.yaml (seed + LLM-extended)
skills/                 ← LLM skill files (entity_resolution.md, etc.)
backend/
  app/
    auth/               ← session + API key auth, RBAC dependencies
    llm/                ← provider abstraction (Ollama / Anthropic / OpenAI)
    connectors/         ← postgres_live, druid_live, dynamo_sample, iceberg, timescale
    documents/          ← chunker, doc_extractor, embedder
    ontology/           ← generator, resolver, taxonomy, editor
    graph/              ← neo4j_sync, nl_describe, editor
    retrieval/          ← search, investigate, cypher_access, api
    main.py             ← FastAPI app (port 8007)
  config/
    auth.json           ← users and API key hashes (auto-created, do not commit)
    llm_config.yaml     ← LLM provider and model selection
frontend/               ← Vite + React + TypeScript
  src/
    components/         ← SearchBox, GraphBrowser, OntologyExplainer,
                           DocumentViewer, ReviewQueue
docker-compose.yml      ← Neo4j, Postgres, LocalStack, backend
```

---

## Quick start

```bash
# 1. Copy env
cp .env.example .env
# Set ADMIN_USERNAME and ADMIN_PASSWORD — these create the first admin account on startup
# Set ALLOWED_ORIGINS to match your frontend URL (default: http://localhost:5173)
# Fill in LANGCHAIN_API_KEY if you want LangSmith tracing

# 2. Start infrastructure
docker-compose up -d

# 3. Seed DynamoDB (LocalStack)
pip install boto3
python data_sources/dynamodb_seed.py

# 4. Install backend deps
cd backend
pip install -r requirements.txt

# 5. Run backend
uvicorn app.main:app --reload --port 8007

# 6. Install and run frontend
cd ../frontend
npm install
npm run dev        # http://localhost:5173
```

Then open the UI, click **Run Ingestion**, and watch the graph build.

---

## LLM configuration

Edit `backend/config/llm_config.yaml`:

```yaml
provider: ollama      # ollama | anthropic | openai
model: llama3.1
embedding_model: nomic-embed-text
```

For Ollama (local, default):
```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

---

## Authentication

Two auth paths — humans get a session cookie, agents get an API key.

**Human login:**
```bash
curl -c cookies.txt -X POST http://localhost:8007/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "yourpassword"}'
# subsequent requests: curl -b cookies.txt -H "X-Org-Id: example" http://localhost:8007/entities
```

**Create an API key for an agent (requires read_write session):**
```bash
curl -b cookies.txt -X POST http://localhost:8007/auth/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "trend-agent", "role": "read_only"}'
# returns: {"key": "sk_...", ...} — copy this, it is shown once only
```

**Agent request with API key:**
```bash
curl -H "Authorization: Bearer sk_..." -H "X-Org-Id: example" http://localhost:8007/retrieve/investigate \
  -H "Content-Type: application/json" \
  -d '{"question": "Which products had defects at WH-EAST?"}'

# follow-up questions: pass the earlier turns as history
curl -H "Authorization: Bearer sk_..." -H "X-Org-Id: example" http://localhost:8007/retrieve/investigate \
  -H "Content-Type: application/json" \
  -d '{"question": "Who supplies those products?", "history": [
        {"role": "user", "content": "Which products had defects at WH-EAST?"},
        {"role": "assistant", "content": "Laptop Pro 14 (product:LP-4471) ..."}]}'
```

**Organisation scope:** every graph, ontology, ingest and retrieval endpoint requires an
`X-Org-Id` header naming an org under `orgs/`. Entities, documents and chunks are stored per
org, each org's generated ontology is written to `orgs/<org_id>/ontology.yaml`, and ingestion
only accepts connectors and files enabled in that org's `config.yaml`.

---

## API endpoints

**Public (no auth):**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Neo4j + LangSmith status |
| POST | `/auth/login` | Login — returns session cookie |

**Read-only (session cookie or Bearer key with `read_only` role):**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/me` | Current user/key info and role |
| GET | `/sources` | List all available sources |
| GET | `/ontology` | Current ontology |
| GET | `/ontology/graph` | Ontology as Cytoscape nodes/edges |
| GET | `/entities` | List graph entities |
| GET | `/ingest/status` | Poll ingestion progress |
| GET | `/graph/summary` | LLM executive summary |
| POST | `/retrieve/investigate` | RAG-style Q&A |
| POST | `/retrieve/search/entities` | Entity name search |
| POST | `/retrieve/search/chunks` | Vector doc search |
| POST | `/retrieve/cypher` | NL → Cypher → results |
| GET | `/retrieve/neighbourhood/{id}` | Entity relationship graph |

**Read-write (session cookie or Bearer key with `read_write` role):**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest` | Trigger ingestion pipeline |
| PATCH | `/entities/{id}` | Update entity label, class, or status |
| DELETE | `/entities/{id}` | Remove entity |
| POST | `/entities/{id}/approve` | Approve a needs_review entity |
| POST | `/entities/{id}/reject` | Reject a needs_review entity |
| POST | `/entities/{id}/split` | Split one entity into two |
| POST | `/auth/api-keys` | Generate a new API key |
| GET | `/auth/api-keys` | List all API keys |
| DELETE | `/auth/api-keys/{key_id}` | Revoke an API key |

---

## Entity resolution confidence

| Confidence | Status | Behaviour |
|-----------|--------|-----------|
| ≥ 0.85 | `auto_commit` | Written to graph immediately |
| 0.50–0.85 | `needs_review` | Written but flagged in Review Queue |
| < 0.50 | `unresolved` | Not committed, surfaced for manual review |

---

## LangSmith tracing

Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env`. Every LLM call (ontology generation, entity resolution, investigation, Cypher translation, entity descriptions) is traced automatically.
