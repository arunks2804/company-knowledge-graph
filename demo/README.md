# Playwright demo

Recorded walkthroughs of the workflows in [PRODUCT.md](../PRODUCT.md), driven through the real UI
and API against a real local stack — no mocked LLM, database or graph.

| Spec | Product workflow |
|------|------------------|
| `01-ingest.spec.ts` | Workflow 1 — data engineer selects sources for an org and runs the LangGraph ingestion |
| `02-ontology.spec.ts` | Feature 6 — the generated class-level ontology diagram |
| `03-review-queue.spec.ts` | Feature 8 — approve a medium-confidence entity resolution |
| `04-ask.spec.ts` | Workflow 2 — cross-source question about defects at WH-EAST, then a follow-up |
| `05-explore.spec.ts` | Workflow 3 — explore LP-4471's neighbourhood and click through to WH-EAST |
| `06-agent-api.spec.ts` | Workflow 4 — an agent calls `/retrieve/investigate` with a read-only API key |

Each run records a video, screenshots and an HTML report under `test-results/` and `playwright-report/`.
Captions are overlaid on the page so the videos explain themselves.

## Prerequisites

- Docker, Node 18+, Python 3.11+, Google Chrome
- [Ollama](https://ollama.com) with `llama3.1:8b` and `nomic-embed-text` pulled
  (`ollama pull llama3.1:8b && ollama pull nomic-embed-text`)

## Run it

```bash
# 1. databases + graph (from the repo root)
docker compose up -d neo4j postgres localstack
python data_sources/dynamodb_seed.py

# 2. API — uses demo/demo.env (local-only demo admin account, compose credentials)
PYTHON=/path/to/venv/bin/python demo/run-backend.sh

# 3. UI
npm --prefix frontend run dev -- --port 5173

# 4. walkthroughs
cd demo && npm install && npm run demo
```

`01-ingest` re-runs the full pipeline on the local model and takes several minutes; the other
specs need it to have run at least once. Set `DEMO_SKIP_INGEST=1` to record only the source
selection. `npm run demo:headed` shows the browser while it runs; `DEMO_SLOWMO` (ms, default 250)
changes the pace.

LLM answers come from an 8B local model, so wording differs between runs and is less precise than
a hosted model. Switch `provider` in `backend/config/llm_config.yaml` to compare.
