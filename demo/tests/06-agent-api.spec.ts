import { test, expect } from '@playwright/test'
import { apiLogin, beat, ORG } from './helpers'

// PRODUCT.md — Persona 4 / Workflow 4: an AI agent uses the retrieval API with a read-only key.
test('Workflow 4 — an agent queries the API with a read-only key', async ({ page, request }) => {
  await apiLogin(request)
  const created = await request.post('/api/auth/api-keys', { data: { name: 'demo-retrieval-agent', role: 'read_only' } })
  expect(created.ok()).toBeTruthy()
  const { key } = await created.json()

  const question = 'what tables and columns contain product sales data and how do I join them?'
  const started = Date.now()
  const res = await page.request.post('/api/retrieve/investigate', {
    headers: { Authorization: `Bearer ${key}`, 'X-Org-Id': ORG },
    data: { question },
    timeout: 15 * 60_000,
  })
  expect(res.ok()).toBeTruthy()
  const body = await res.json()

  // the same key must not be able to write
  const denied = await page.request.post('/api/ingest', {
    headers: { Authorization: `Bearer ${key}`, 'X-Org-Id': ORG }, data: { sources: [] },
  })
  expect(denied.status()).toBe(403)

  const esc = (s: string) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]!))
  await page.setContent(`
    <body style="margin:0;background:#0f1117;color:#e2e8f0;font:15px/1.5 Inter,system-ui,sans-serif">
      <div style="max-width:1100px;margin:40px auto;padding:0 24px">
        <div style="color:#4f9cf9;font-weight:700;font-size:20px">Workflow 4 · Agent → Retrieval API</div>
        <p style="color:#8892a4">A read-only API key, scoped to org <b>${ORG}</b>. Took ${Math.round((Date.now() - started) / 1000)}s on a local 8B model.</p>
        <pre style="background:#1e2130;border:1px solid #2e3450;border-radius:10px;padding:16px;white-space:pre-wrap">POST /retrieve/investigate
Authorization: Bearer sk_••••••••
X-Org-Id: ${ORG}

{"question": "${esc(question)}"}</pre>
        <pre style="background:#1e2130;border:1px solid #2e3450;border-radius:10px;padding:16px;white-space:pre-wrap">${esc(JSON.stringify({
          answer: body.answer, entities_used: body.entities_used,
          sources: (body.sources ?? []).map((s: any) => s.document), relationships_used: body.relationships_used,
        }, null, 2))}</pre>
        <pre style="background:#1e2130;border:1px solid #f87171;border-radius:10px;padding:16px">POST /ingest with the same key → ${denied.status()} Forbidden (read_only role)</pre>
      </div>
    </body>`)
  await beat(page, 9000)
})
