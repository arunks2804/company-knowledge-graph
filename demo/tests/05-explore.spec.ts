import { test, expect } from '@playwright/test'
import { beat, caption, clickGraphNode, openTab, signIn } from './helpers'

// PRODUCT.md — Workflow 3: exploring relationships visually.
test('Workflow 3 — explore LP-4471 and hop to WH-EAST', async ({ page }) => {
  await signIn(page)
  await openTab(page, /Explore Relationships/)
  await caption(page, 'Workflow 3 · Explore', 'Search an entity and see everything it connects to across sources.')

  const input = page.getByPlaceholder('Search for an entity to explore its relationships…')
  await input.pressSequentially('LP-4471', { delay: 60 })
  await page.getByRole('button', { name: 'Explore', exact: true }).click()

  // several matches → pick the product itself
  const pick = page.getByRole('button', { name: /Laptop Pro/ })
  if (await pick.first().isVisible().catch(() => false)) await pick.first().click()

  await page.waitForFunction(() => (window as any).__kgExploreCy?.nodes().length > 1, null, { timeout: 30_000 })
  await caption(page, 'LP-4471 at the centre',
    'Orders that contain it, the warehouse it is stocked at, its supplier, and the incident that affects it.')
  await beat(page, 4000)

  const wh = await clickGraphNode(page, '__kgExploreCy', (l, id) => id.toLowerCase().includes('wh-east') || l.includes('WH-EAST'))
  await caption(page, `Selected ${wh}`, 'Click any node or edge to inspect and correct it in place.')
  await beat(page, 3500)
  await expect(page.getByText('Edit Entity')).toBeVisible()
})
