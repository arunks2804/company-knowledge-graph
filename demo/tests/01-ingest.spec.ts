import { test, expect } from '@playwright/test'
import { beat, caption, openTab, signIn } from './helpers'

// PRODUCT.md — Workflow 1: first-time setup for a data engineer.
// Runs a real ingestion (local LLM), so this recording is long. Set DEMO_SKIP_INGEST=1 to only
// show the source selection without re-running the pipeline.
test('Workflow 1 — data engineer ingests sources for an organisation', async ({ page }) => {
  await signIn(page)
  await openTab(page, /Ingest/)
  await caption(page, 'Workflow 1 · Ingest',
    'Sources come from orgs/example/config.yaml. Connectors not enabled for this org are greyed out.')

  await expect(page.getByText('Live DB connectors')).toBeVisible()
  await expect(page.getByRole('checkbox', { name: /^druid/ })).toBeDisabled()
  await caption(page, 'Pick what to ingest',
    'Postgres (orders, customers, products) + DynamoDB (inventory) + three maintenance reports.')
  await page.getByRole('checkbox', { name: 'postgres', exact: true }).check()
  await page.getByRole('checkbox', { name: 'dynamodb', exact: true }).check()
  for (const doc of ['report_001.txt', 'report_002.txt', 'report_003.txt']) {
    await page.getByRole('checkbox', { name: doc, exact: true }).check()
  }
  await beat(page)

  if (process.env.DEMO_SKIP_INGEST) {
    await caption(page, 'Ready to run', 'Skipping the live run (DEMO_SKIP_INGEST is set).')
    return
  }

  await page.getByRole('button', { name: /Run Ingestion/ }).click()
  await caption(page, 'LangGraph pipeline running',
    'extract → ontology → cross-source entity resolution (docs included) → relationships → Neo4j → embeddings')
  await expect(page.getByText(/^Running:/)).toBeVisible()
  await expect(page.getByText(/^Done —/)).toBeVisible({ timeout: 25 * 60_000 })
  await caption(page, 'Ingestion complete', await page.getByText(/^Done —/).innerText())
  await beat(page, 3000)
})
