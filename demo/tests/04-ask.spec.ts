import { test, expect } from '@playwright/test'
import { beat, caption, openTab, signIn } from './helpers'

// PRODUCT.md — Workflow 2: an analyst asks a cross-source question, then a follow-up.
test('Workflow 2 — ask a cross-source question and a follow-up', async ({ page }) => {
  await signIn(page)
  await openTab(page, /Ask/)
  const input = page.getByPlaceholder('Ask a question about your data...')

  const q1 = 'Which products had defects at WH-EAST and which customers placed orders for them?'
  await caption(page, 'Workflow 2 · Ask', 'The answer needs Postgres orders AND a maintenance report.')
  await input.pressSequentially(q1, { delay: 25 })
  await input.press('Enter')
  await caption(page, 'Retrieving',
    'Find WH-EAST in the graph → traverse incidents, products, orders, customers → pull the reports that mention them → answer.')
  await expect(page.getByText('Answer', { exact: true })).toBeVisible()
  await caption(page, 'Grounded answer', 'Entities used and the cited documents are listed under the answer.')
  await page.mouse.wheel(0, 400)
  await beat(page, 6000)

  const q2 = 'Who supplies those products?'
  await caption(page, 'Follow-up', '"those products" is resolved from the conversation, then answered from SUPPLIED_BY edges.')
  await input.pressSequentially(q2, { delay: 35 })
  await input.press('Enter')
  await expect(page.getByText(/Interpreted as:/)).toBeVisible()
  await caption(page, 'Follow-up answered', 'See "Interpreted as" — the standalone question the follow-up was rewritten to.')
  await beat(page, 6000)
})
