import { test, expect, Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { apiLogin, beat, caption, clickGraphNode, ORG, openTab, setCaptionPosition, signIn } from './helpers'

// One continuous highlight run of the key use cases, for sharing (e.g. LinkedIn).
// Uses the graph from a previous ingest. Every wait on the LLM is recorded as a cut so
// make-reel.mjs can remove it and export a short MP4: `npm run reel`.
test.use({ launchOptions: { slowMo: 120 } })
setCaptionPosition('top')

const REPO = 'github.com/arunks2804/company-knowledge-graph'

test('@reel LinkedIn highlight reel — key use cases in one take', async ({ page, request }, testInfo) => {
  const t0 = Date.now()
  const cuts: { start: number; end: number; label: string }[] = []
  const at = () => (Date.now() - t0) / 1000
  /** Run a slow step (LLM call) and mark its duration to be cut from the final video. */
  async function waitCut<T>(label: string, fn: () => Promise<T>): Promise<T> {
    const start = at()
    const result = await fn()
    cuts.push({ start, end: at(), label })
    return result
  }

  // ── title card ───────────────────────────────────────────────────────────────
  // The recorder's first frames come from a not-yet-resized viewport (grey band at the bottom), so
  // the opening card is captured as a screenshot and make-reel.mjs uses that still for the intro.
  await card(page, 'Company Knowledge Graph',
    'One map of your data across Postgres, DynamoDB and documents — for people and AI agents.',
    'Neo4j · LangGraph · FastAPI · React · local LLM (Ollama)')
  await page.screenshot({ path: testInfo.outputPath('reel-title.png') })
  const introEnd = at()

  // ── sources ──────────────────────────────────────────────────────────────────
  await signIn(page)
  await openTab(page, /Ingest/)
  // show the sources selected (the graph is already built, so the pipeline is not re-run here)
  for (const name of ['postgres', 'dynamodb', 'report_001.txt', 'report_002.txt', 'report_003.txt']) {
    await page.getByRole('checkbox', { name, exact: true }).check()
  }
  await caption(page, '1 · Connect your sources',
    'Two databases (Postgres, DynamoDB) and three maintenance reports — the kind of data no single tool sees together.')
  await beat(page, 3000)

  // ── ontology ─────────────────────────────────────────────────────────────────
  await openTab(page, /Ontology/)
  await caption(page, '2 · The AI builds a shared data model (ontology)',
    'It reads every schema and names the business concepts — Customer, Order, Product, Warehouse, Supplier, Incident — and how they relate.')
  await page.waitForFunction(() => (window as any).__kgOntologyCy?.nodes().length > 0)
  await beat(page, 3500)
  await clickGraphNode(page, '__kgOntologyCy', l => l === 'Product')
  await caption(page, 'One concept, many names',
    '“Product” is product_id in Postgres and product_sku in DynamoDB — different names, one concept.')
  await beat(page, 4000)

  // ── explore ──────────────────────────────────────────────────────────────────
  await openTab(page, /Explore Relationships/)
  const input = page.getByPlaceholder('Search for an entity to explore its relationships…')
  await input.pressSequentially('LP-4471', { delay: 40 })
  await page.getByRole('button', { name: 'Explore', exact: true }).click()
  const pick = page.getByRole('button', { name: /Laptop Pro/ })
  if (await pick.first().isVisible().catch(() => false)) await pick.first().click()
  await page.waitForFunction(() => (window as any).__kgExploreCy?.nodes().length > 1, null, { timeout: 30_000 })
  await caption(page, '3 · One product, every connection',
    'Laptop Pro 14 (LP-4471): where it is stocked, who supplies it, which orders contain it — and the incident that hit it.')
  await beat(page, 3500)
  await clickGraphNode(page, '__kgExploreCy', (l, id) => id.toLowerCase().includes('mnt-2024-001') || l.includes('MNT-2024-001'))
  await caption(page, 'Incident MNT-2024-001',
    'This came from a maintenance report, not a database — now linked to the product and the warehouse.')
  await beat(page, 3000)

  // ── ask + follow-up ──────────────────────────────────────────────────────────
  await openTab(page, /Ask/)
  const ask = page.getByPlaceholder('Ask a question about your data...')
  await caption(page, '4 · Ask in plain English', 'The answer needs both the databases and the maintenance reports.')
  await ask.pressSequentially('Which products had defects at WH-EAST, and who supplies them?', { delay: 18 })
  await ask.press('Enter')
  await caption(page, 'Thinking…', 'Find WH-EAST → follow incidents, products and suppliers → read the reports that mention them.')
  await waitCut('answer 1', () => expect(page.getByText('Answer', { exact: true })).toBeVisible({ timeout: 10 * 60_000 }))
  // a local 8B model is not always right — a wrong answer fails this take and Playwright re-records
  await expectFacts(page.locator('p').last(), [/Laptop Pro 14|LP-4471/, /SUP-001/])
  await caption(page, 'A straight answer', 'Plain English. The documents and records it used are listed underneath.')
  await beat(page, 6500)

  await caption(page, 'Ask a follow-up', 'No need to repeat yourself — “those products” is understood from the conversation.')
  await ask.pressSequentially('Where else are those products stocked, and are they affected?', { delay: 22 })
  await ask.press('Enter')
  // once the follow-up is answered, the first exchange moves into the conversation history ("You: …")
  await waitCut('answer 2', () => expect(page.getByText('You:', { exact: true })).toBeVisible({ timeout: 10 * 60_000 }))
  await expectFacts(page.locator('p').last(), [/WH-WEST|West warehouse/, /not affected|unaffected/i], [/WH-NORTH|WH-SOUTH/])
  await caption(page, 'Follow-up answered', 'Stock records say where else it is held; the quality review says that batch is fine.')
  await beat(page, 6500)

  // ── human in the loop ────────────────────────────────────────────────────────
  await openTab(page, /Review Queue/)
  // feature the queued match found in the most places — the clearest example of why review exists
  const queue = await (await page.request.get('/api/entities?status=needs_review', { headers: { 'X-Org-Id': ORG } })).json()
  const featured = [...queue].sort((a, b) => places(b).length - places(a).length)[0]
  const featuredCard = page.locator('div')
    .filter({ hasText: `ID: ${featured.canonical_id} ` })
    .filter({ has: page.getByRole('button', { name: '✓ Approve' }) })
    .last()
  await featuredCard.scrollIntoViewIfNeeded()
  await caption(page, '5 · A person confirms uncertain matches', reviewCaption(featured))
  await beat(page, 5500)
  await featuredCard.getByRole('button', { name: '✓ Approve' }).click()
  await caption(page, 'Approved', `${featured.canonical_label}'s records are now one trusted ${kind(featured)} in the graph.`)
  await beat(page, 2500)

  // ── agent API ────────────────────────────────────────────────────────────────
  await apiLogin(request)
  const key = (await (await request.post('/api/auth/api-keys', { data: { name: 'reel-agent', role: 'read_only' } })).json()).key
  const question = 'what tables and columns contain product sales data and how do I join them?'
  await card(page, '6 · Context for AI agents', 'An AI agent asks through the API (with a read-only key) before it writes a query.', '')
  const body = await waitCut('agent answer', async () => (await page.request.post('/api/retrieve/investigate', {
    headers: { Authorization: `Bearer ${key}`, 'X-Org-Id': ORG }, data: { question }, timeout: 10 * 60_000,
  })).json())
  expect(body.answer).toMatch(/order_items/)
  expect(body.answer).toMatch(/order_id/)
  await card(page, '6 · Context for AI agents',
    `<span style="color:#8892a4">POST /retrieve/investigate</span><br>“${question}”`,
    `<div style="text-align:left;font-size:17px;line-height:1.55;color:#e2e8f0;background:#1e2130;border:1px solid #2e3450;border-radius:12px;padding:18px 22px;margin-top:8px">${esc(body.answer)}</div>`)
  await beat(page, 7000)

  // ── closing card ─────────────────────────────────────────────────────────────
  await card(page, 'Company Knowledge Graph',
    'Cross-source entity resolution · knowledge graph · Graph RAG · agent API',
    REPO)
  await beat(page, 4000)

  // written only by a passing take, next to its video — make-reel.mjs looks for it there
  writeFileSync(testInfo.outputPath('reel-cuts.json'), JSON.stringify({ cuts, introEnd, total: at() }, null, 2))
})

type Queued = { canonical_id: string; canonical_label: string; confidence: number; sources: string; class?: string }

const kind = (e: Queued) => (e.class ?? 'record').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase()

/** Human-readable places a queued entity was found: "customers table", "orders table", "2 reports". */
function places(entity: Queued): string[] {
  const sources: { source_type: string; table_or_datasource: string }[] = JSON.parse(entity.sources || '[]')
  const tables = [...new Set(sources.filter(s => s.source_type !== 'document').map(s => `the ${s.table_or_datasource} table`))]
  const reports = new Set(sources.filter(s => s.source_type === 'document').map(s => s.table_or_datasource)).size
  return [...tables, ...(reports ? [`${reports} report${reports > 1 ? 's' : ''}`] : [])]
}

/** "Bob Okafor appears in the customers table, the orders table and 2 reports. The AI is 75% sure …" */
function reviewCaption(entity: Queued) {
  const p = places(entity)
  const where = p.length > 1 ? `${p.slice(0, -1).join(', ')} and ${p[p.length - 1]}` : p[0]
  return `${entity.canonical_label} appears in ${where}. The AI is ${Math.round(entity.confidence * 100)}% ` +
    `sure these are the same ${kind(entity)} — so it asks a human before trusting it.`
}

/** Fail the take unless the answer states the expected facts (and none of the wrong ones). */
async function expectFacts(answer: import('@playwright/test').Locator, must: RegExp[], mustNot: RegExp[] = []) {
  const text = await answer.innerText()
  for (const re of must) expect(text, `answer should match ${re}`).toMatch(re)
  for (const re of mustNot) expect(text, `answer should not match ${re}`).not.toMatch(re)
}

function esc(s: string) {
  return String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]!))
}

/** Full-screen title card in the app's palette. */
async function card(page: Page, title: string, subtitle: string, footer: string) {
  await page.setContent(`
    <html style="height:100%;background:#0f1117"><body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
                 background:radial-gradient(circle at 30% 20%,#1e2a4a,#0f1117 60%);color:#e2e8f0;
                 font-family:Inter,system-ui,sans-serif">
      <div style="max-width:980px;padding:0 48px;text-align:center">
        <div style="font-size:52px;font-weight:800;letter-spacing:-1px;margin-bottom:18px">
          ${title.replace('Knowledge Graph', '<span style="color:#4f9cf9">Knowledge Graph</span>')}
        </div>
        <div style="font-size:24px;line-height:1.45;color:#cbd5e1;margin-bottom:22px">${subtitle}</div>
        <div style="font-size:17px;color:#8892a4">${footer}</div>
      </div>
    </body></html>`)
}
