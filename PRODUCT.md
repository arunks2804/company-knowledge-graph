# Company Knowledge Graph — Product Specification

> **One-line pitch:** Connect your databases, schema files, and documents once. Ask questions in plain English, explore relationships visually, and give any AI agent a grounded map of your organisation's data before it acts.

> **Status:** Working prototype. Supports live connections to Postgres, DynamoDB, Apache Druid, TimescaleDB, and Apache Iceberg. Schema files (SQL DDL, JSON, YAML) and documents (txt, md, pdf) can be dropped into folders without any live DB connection. Entity resolution, ontology generation, and retrieval run on Ollama locally or any major LLM provider. Neo4j is the graph store. LangSmith traces every LLM call.

---

## The Problem

Every organisation's data is split across many places — transactional databases, analytical warehouses, data lakes, and documents like reports, runbooks, and specifications. Each source uses different names for the same thing. A product called LP-4471 in Postgres is sku_code LP-4471 in Druid, product_sku LP-4471 in DynamoDB, and "Laptop Pro unit" in a maintenance report. Nobody has a single view.

The consequences are real:

- A data engineer wants to understand how tables relate across systems — she reads schema files from three different teams and pieces it together manually.
- An analyst asks "which products had supply issues last quarter?" — the answer lives partly in a warehouse event log, partly in a PDF maintenance report. Neither system knows the other exists.
- An AI agent is asked to analyse product trends — it hallucinates table names because it has no grounded knowledge of what actually exists in the organisation's data.
- A new engineer joins and spends weeks learning the data model — there is no single place to look.
- A PM agent tries to write a product brief — it doesn't know which database to query, which columns are relevant, or how the concepts connect.

**The cost:** disconnected data that can't be reasoned over — by humans or by AI agents.

---

## Who This Is For

### Persona 1 — The Data Engineer
*"I know where all the data lives. I just can't show anyone the whole picture."*

**Profile:** Owns the data infrastructure. Writes SQL daily. Manages Postgres, Druid, or DynamoDB instances. Knows that the same concept has different column names in different systems but has never had a tool to resolve that automatically. Gets asked constantly what a table means or where a piece of data lives.

**Challenges:**
- Explaining the data model to stakeholders requires manual documentation that goes stale immediately.
- Entity resolution across systems is done ad hoc — someone writes a one-off JOIN and it lives in a notebook nobody else can find.
- New team members take weeks to understand how systems relate to each other.
- Documents like maintenance reports, runbooks, and specs are completely disconnected from the structured data they describe.
- No single source of truth for "what does our data look like and how does it connect."

**What this app gives them:**
- Point at live databases or drop schema files — the graph builds itself.
- Entity resolution across all sources with confidence scores — review the ones the LLM wasn't sure about.
- An ontology that explains the data model in class-level terms — shareable with anyone.
- One place that answers "where does this concept live and what is it connected to."

---

### Persona 2 — The Knowledge Explorer
*"I know what question I want to ask. I don't know which system has the answer."*

**Profile:** Data analyst, product manager, or operations lead. Understands the business well. Comfortable reading a table but not comfortable writing complex SQL across multiple systems. Often gets blocked because the answer to a question spans a database and a document — and no tool connects the two.

**Challenges:**
- "Which customers were affected by the WH-EAST defect issue?" requires joining a database with a PDF report — currently impossible without the data engineer's help.
- Doesn't know which database or table to look at for a given question.
- Cannot explore data relationships freely — each question requires asking someone more technical.
- Has no way to see how concepts connect across systems — everything looks siloed.

**What this app gives them:**
- Ask questions in plain English — get answers grounded in both structured schemas and unstructured documents.
- Search for any entity and see its relationships across all sources in a visual graph.
- Understand what is connected to what without writing a single line of SQL.
- The app points to the right database and table — they or their tooling can then go fetch the actual numbers.

---

### Persona 3 — The Executive or Decision Maker
*"I need to know if our supply chain data connects to our customer complaints data. Someone figure it out."*

**Profile:** VP, Director, or C-suite. Doesn't interact with databases directly. Makes decisions that depend on understanding how different parts of the business connect. Currently relies on someone else to manually stitch together answers from multiple systems.

**Challenges:**
- No self-serve way to understand cross-system relationships without involving engineering.
- Questions that span databases and documents have no home — they fall between teams.
- The data model is documented nowhere accessible to non-technical stakeholders.
- Cannot quickly verify "do we even have data about X" without asking someone.

**What this app gives them:**
- Ask a plain English question — get a sourced, grounded answer.
- See the ontology — understand what types of data the organisation has and how they relate, without SQL.
- Confirm in seconds whether a data asset exists and what it connects to.

---

### Persona 4 — The Retrieval Agent
*This is not a human. It is an AI agent that calls this application's API as one step in a larger workflow.*

**Task:** Get grounded context about an organisation's data before reasoning, querying, or writing.

**Authentication:** An admin generates an API key for the agent (`POST /auth/api-keys`). The agent passes it as `Authorization: Bearer <key>` on every request. The key is assigned `read_only` role — the agent can ask questions and explore the graph but cannot ingest data or modify entities.

**Inputs it provides:**
- A natural language question: "What tables contain product and order data and how do they relate?"
- An entity name: "LP-4471"
- A concept: "customer churn"

**What it gets back:**
- The schema — which tables exist, which columns, which database to go to.
- The relationships — how Product connects to Order, which connects to Customer.
- Document context — what the maintenance reports say about this product.
- A plain English answer synthesised from all sources.

**Why it needs this app:**
Without grounded context, an agent guesses table names, hallucinates column names, and queries the wrong database. With this app, it knows exactly where to look before it acts. It does not query the live database through this app — it gets the map, then queries the database directly.

**Example agent workflow:**
```
Trend Agent wants to analyse sales trends for LP-4471

Step 1 — calls POST /retrieve/investigate
         "what tables and columns contain sales data for products?"
         → gets: orders table, order_items table, product_id column, Postgres

Step 2 — connects directly to Postgres
         runs: SELECT SUM(total_amount), YEAR(order_date)
               FROM orders JOIN order_items ON orders.order_id = order_items.order_id
               WHERE product_id = 'LP-4471'
               GROUP BY YEAR(order_date)
         → gets actual numbers

Step 3 — combines map from this app + data from Postgres
         → writes trend analysis grounded in real data
```

---

### Persona 5 — The Orchestrator Agent
*This is not a human. It is a higher-level AI agent that coordinates multiple specialised agents and decides when to call this application.*

**Task:** Coordinate a multi-agent workflow — product intelligence, market research, competitive analysis, PRD generation — using the right tool for each step.

**How it uses this app:**
The Orchestrator Agent treats this application as the **grounded context tool**. Before spinning up any specialised agent, it calls this app to establish what the organisation actually has in its data. Then it sends that context to the appropriate agent.

**Example orchestration:**
```
User asks: "Analyse the market opportunity for our Laptop Pro product line"

Orchestrator Agent:

  ├── calls this app → /retrieve/investigate
  │   "what do we know about LP-4471 and related products?"
  │   → gets: schema context, maintenance incidents, supplier info
  │
  ├── sends context to → Trend Agent
  │   "here is the schema — go query Postgres for sales 2020–2025"
  │
  ├── sends context to → Competitor Agent
  │   "here is what we know about our product — search the web for alternatives"
  │
  ├── sends context to → Market Agent
  │   "here are the customer segments from our data — estimate TAM"
  │
  └── sends all findings to → PM Agent
      "write a PRD and roadmap proposal"
```

**Why the separation matters:** The Orchestrator decides what to do with the context. This app's job is only to provide it — accurately, quickly, from real organisational data. Internet search, live query execution, and document generation are the responsibility of the agents that consume this app's output.

---

## The Proposition

### What this application is

Company Knowledge Graph is a **data discovery and context layer**. It sits between your databases, schema files, and documents on one side — and your humans and AI agents on the other.

It does not replace your database. It does not run analytical queries. It does not tell you your Q3 revenue. Those answers live in your warehouse.

What it does is answer a different question: **"What data do we have, where does it live, and how does it connect?"** — across every source, in one place, in plain English, as a visual graph, and as a structured API.

Built with:
- **Neo4j** — the graph store. All entities, relationships, and document embeddings live here.
- **LangGraph** — orchestrates the ingestion pipeline: extract → generate ontology → resolve entities → sync to graph.
- **LangSmith** — traces every LLM call in the pipeline. Every ontology generation, every entity resolution decision, every retrieval answer is observable.
- **LLM provider abstraction** — Ollama (local, default), Anthropic Claude, OpenAI GPT-4o. Switch in config, not in code.
- **FastAPI** — the retrieval API consumed by agents and the React UI.
- **React + TypeScript + Cytoscape.js** — the frontend. Two modes: Ask (text answers) and Explore (visual relationship graph).

---

### For the Data Engineer
Configure once. Point at your live databases or drop schema files into a folder. Run ingestion. The LLM builds a shared ontology, resolves entities across all sources, and syncs everything to Neo4j. Review the low-confidence resolutions in the queue. The graph is live and queryable in minutes — not weeks.

### For the Knowledge Explorer
Two ways to get answers. Ask a question in plain English — the app searches the graph and your documents and writes a grounded answer with sources cited. Or search for any entity and see its neighbourhood: every system it appears in, every document that mentions it, every relationship it has. No SQL required.

### For the Executive
One question. One answer. Sourced from your organisation's actual data — not a guess, not a web search. If the data exists in any connected system or document, the answer is grounded in it.

### For the Retrieval Agent
A REST API that returns structured context. Call `/retrieve/investigate` with a natural language question. Get back an answer, the entities used, and the source documents cited. Use that context to query the right database with confidence. No hallucinated table names. No guessing.

### For the Orchestrator Agent
A reliable first step in any multi-agent workflow. Before any specialised agent runs, call this app to establish what the organisation's data actually contains. Every downstream agent — Trend, Market, Competitor, Monetization, PM — gets grounded context rather than starting from zero.

---

## Features

### 1. Multi-source Ingestion — Live Connectors and File Drop

Two ways to get data in:

**Live connectors** — direct database connections at ingest time:

| Database | Type | How schema is read |
|----------|------|--------------------|
| Postgres | OLTP | `information_schema.columns` |
| TimescaleDB | Time-series | `information_schema` + hypertable metadata |
| Apache Druid | OLAP | Druid SQL API `INFORMATION_SCHEMA.COLUMNS` |
| DynamoDB | NoSQL | boto3 scan + type inference |
| Apache Iceberg | Data lake | PyIceberg REST/Hive/Glue catalog |

**File drop** — no live connection needed:
- Drop `.sql` DDL exports, `.json`, or `.yaml` schema files into the `schemas/` folder.
- The pipeline parses `CREATE TABLE` statements and extracts column definitions automatically.
- Works with exports from Snowflake, BigQuery, MySQL, Redshift, ClickHouse — anything that produces standard DDL.

**Documents** — drop `.txt`, `.md`, or `.pdf` files into configured document folders. The pipeline chunks them (800 characters, 150 overlap), embeds each chunk, and stores them in Neo4j with a vector index for semantic search.

---

### 2. Organisation and App Scoping

Every ingestion run is scoped to an **organisation**. Each organisation has a config file (`orgs/{id}/config.yaml`) that defines:
- Which live connectors are enabled
- Which schema folders to scan
- Which document folders to scan
- Which apps (sub-systems) belong to the org

The UI shows all supported databases — enabled ones are selectable, disabled ones are greyed out. Drop a new file into a configured folder and it appears in the source selector on next load.

---

### 3. LLM-Generated Ontology

After extracting schemas from all sources, the pipeline asks the LLM to build a shared ontology — a class hierarchy that maps all source concepts to a common vocabulary.

- **Classes** — Product, Customer, Order, Warehouse, Supplier, Shipment, MaintenanceIncident
- **Relationships** — PLACED_BY, SHIPS_TO, SUPPLIED_BY, MENTIONED_IN, HAS_INCIDENT
- **Source hints** — each class records which table names and column names from each source map to it

The ontology is seeded with a baseline (`ontology/core_ontology.yaml`) and extended by the LLM based on what it actually finds in your schemas. It is stored as YAML and versioned.

---

### 4. Cross-Source Entity Resolution

The core capability. The LLM identifies which records across all sources refer to the same real-world entity and resolves them to a single graph node.

Example — LP-4471 appears as:
- `products.product_id = 'LP-4471'` in Postgres
- `inventory_events.sku_code = 'LP-4471'` in Druid
- `product_inventory.product_sku = 'LP-4471'` in DynamoDB
- `"SKU LP-4471"` in a maintenance report PDF

All four become one `Product` node in Neo4j with edges to every source and every document that mentions it.

**Confidence-based status:**

| Confidence | Status | What happens |
|-----------|--------|-------------|
| ≥ 0.85 | `auto_commit` | Written to graph immediately |
| 0.50–0.85 | `needs_review` | Written but flagged in Review Queue |
| < 0.50 | `unresolved` | Not committed — surfaced for manual review |

---

### 5. Two Output Modes for Humans

**Ask mode** — type a question in plain English:
- The question is embedded and matched against document chunks via vector search
- Matching entities are found via graph traversal
- The LLM synthesises an answer with sources cited
- Output: text answer + list of source documents + entities used

**Explore mode** — search for an entity and see its neighbourhood:
- Force-directed graph rendered with Cytoscape.js
- Centre node is the entity searched for
- Surrounding nodes are everything it connects to across all sources
- Click any node for an LLM-generated plain English description
- Multiple search results presented as a picker before rendering

---

### 6. Ontology Diagram

A class-level diagram of the data model — always readable regardless of data volume. Shows types and relationships only — not specific products or customers.

- Rendered with Cytoscape.js, force-directed layout
- Each class colour-coded by type
- Click any class to see its description and source hints
- This is the sharable view for stakeholders who need to understand the data model without touching a database

---

### 7. Authentication and Access Control

Two authentication paths — one for humans, one for agents — with role-based access control.

**Human login — session cookie**

Humans log in at `POST /auth/login` with username and password. On success the server sets a `HttpOnly` session cookie valid for 7 days. The browser sends it automatically on every subsequent request. No tokens to manage, no headers to set.

**Agent authentication — API key**

An admin generates a key per agent at `POST /auth/api-keys`. The agent passes it as `Authorization: Bearer <key>` on every API call. Keys can be revoked independently — revoking one agent's key does not affect any other. The raw key is shown once on creation and never stored — only its SHA-256 hash is kept.

**Roles**

| Role | What it allows |
|------|---------------|
| `read_only` | Ask, Explore, search entities, view ontology, view graph, view ingest status |
| `read_write` | Everything above + Ingest, approve/reject/split entities, edit ontology, manage API keys |

A retrieval agent doing only Q&A should have `read_only`. An ingestion agent or a human operating the Review Queue needs `read_write`.

**Bootstrap**

On first startup, if `ADMIN_USERNAME` and `ADMIN_PASSWORD` are set in `.env`, the admin account is created automatically. After that, the admin creates additional users and API keys through the API.

**Public endpoints** (no authentication required):
- `GET /health`
- `POST /auth/login`

All other endpoints require a valid session cookie or Bearer token.

---

### 8. REST API for Agents (read_only role required)

Every retrieval capability is available as a structured API endpoint:

| Endpoint | What it does |
|----------|-------------|
| `POST /retrieve/investigate` | RAG-style Q&A — question in, grounded answer out |
| `POST /retrieve/search/entities` | Find entities by name or keyword |
| `POST /retrieve/search/chunks` | Semantic search over document chunks |
| `POST /retrieve/cypher` | Natural language → read-only Cypher → live graph results |
| `GET /retrieve/neighbourhood/{id}` | Nodes and edges for one entity's connections |
| `POST /retrieve/describe/entity` | LLM-written description of one entity |
| `GET /ontology/graph` | Full ontology as Cytoscape-compatible nodes and edges |

All endpoints return structured JSON. Designed to be called by LLM agents without human involvement.

---

### 8. Review Queue

Entity resolutions with confidence between 0.50 and 0.85 are flagged for human review. The Review Queue tab shows:
- The proposed canonical entity
- The confidence score
- Every source record that was mapped to it
- The raw source mappings for verification

The Data Engineer reviews and confirms or rejects. This is the human-in-the-loop checkpoint for data quality.

---

### 9. Full Pipeline Observability via LangSmith

Every LLM call in the pipeline is traced in LangSmith:
- Ontology generation — what schemas went in, what classes came out
- Entity resolution — which records were matched, what confidence was assigned
- Investigation answers — which chunks were retrieved, what the LLM synthesised
- Cypher generation — the NL question, the generated query, the result

Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env`. Every subsequent ingestion and retrieval appears automatically in your LangSmith project.

---

### 10. Multi-LLM, No Lock-in

The provider abstraction means any LLM can power the pipeline. Switch in `backend/config/llm_config.yaml` — no code changes:

| Provider | Best for |
|----------|---------|
| **Ollama** (local) | Privacy-sensitive environments, offline use, development |
| **Anthropic Claude** | Highest quality ontology generation and entity resolution |
| **OpenAI GPT-4o** | General use, strong structured output |

Embeddings default to Ollama's `nomic-embed-text` (768 dimensions). Anthropic falls back to Ollama for embeddings since Anthropic has no public embeddings endpoint.

---

## User Workflows

### Workflow 1 — First-time setup for a data engineer
1. Copy `orgs/example/config.yaml` → `orgs/your-org/config.yaml`
2. Set which live connectors are enabled, which schema folders to point at, which document folders to scan
3. Add credentials to `.env`
4. Open the app, select the organisation in the top bar
5. Go to **Ingest** tab — see all configured sources, enabled connectors selectable, others greyed out
6. Select sources and click **Run Ingestion**
7. Watch status bar: extracting → generating ontology → resolving entities → processing documents
8. Go to **Review Queue** — review any low-confidence entity resolutions
9. Go to **Ontology** — verify the class diagram matches your understanding of the data model

---

### Workflow 2 — An analyst asks a cross-source question
1. Open the app, select organisation
2. Go to **Ask** tab
3. Type: *"Which products had defects at WH-EAST and which customers placed orders for them?"*
4. Get a plain English answer sourced from both the database schema and maintenance report documents
5. See which entities were used in the answer and which documents were cited
6. Follow up: *"What supplier provides those products?"* — next answer builds on graph relationships

---

### Workflow 3 — Exploring relationships visually
1. Go to **Explore Relationships** tab
2. Type "LP-4471" in the search box
3. See the force-directed graph: LP-4471 at the centre, connected to SUP-001, WH-EAST, ORD-20240115, report_001.txt
4. Click WH-EAST — see its description and what else connects to it
5. Realise the warehouse connects to other products with incidents — without writing a single query

---

### Workflow 4 — An AI agent uses the retrieval API
```
POST /retrieve/investigate
{
  "question": "what tables and columns contain product sales data and how do I join them?"
}

Response:
{
  "answer": "Sales data lives in the orders and order_items tables in Postgres.
              Join on order_id. Use product_id to filter by product.
              The products table contains product_name, category, and unit_price.",
  "sources": [...],
  "entities_used": ["Product", "Order", "OrderItem"]
}
```
The agent now queries Postgres directly with correct table and column names.

---

### Workflow 5 — Orchestrator agent coordinates a product analysis
1. Orchestrator calls `/retrieve/investigate` — "what do we know about our laptop product line?"
2. Gets back schema context, supplier info, maintenance incidents from documents
3. Sends schema context to Trend Agent → Trend Agent queries Postgres for sales data
4. Sends product context to Competitor Agent → searches the web for competing products
5. Sends customer segment data to Market Agent → estimates TAM
6. All findings go to PM Agent → produces PRD and roadmap proposal
7. Every step in this app is traced in LangSmith

---

## What Is Not in v1

| Feature | Status |
|---------|--------|
| Visual graph showing full relationship diagram beyond neighbourhood | Roadmap |
| Incremental sync — detect schema changes and update graph without full re-ingest | Roadmap |
| Additional live connectors — Snowflake, BigQuery, ClickHouse, MongoDB, Redshift | Roadmap |
| Folder watching — auto-rescan when new files are dropped without manual trigger | Roadmap |
| Multi-hop neighbourhood expansion — click to expand one more hop in the graph | Roadmap |
| Graph diff — show what changed between two ingestion runs | Roadmap |
| Scheduled re-ingestion — run on a cron, flag new entities for review | Roadmap |
| Export — ontology and entity map as PDF or shareable link | Roadmap |
| Embedded retrieval SDK — pip install and call from any Python agent directly | Roadmap |
| SSO / OAuth2 — replace username/password login with Google, Okta, or GitHub | Roadmap |
| Per-key usage tracking — log API call counts and latency per agent key | Roadmap |
| User management UI — create/revoke users and keys from the browser | Roadmap |
