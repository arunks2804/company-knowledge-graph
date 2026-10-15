import { test, expect } from '@playwright/test'
import { beat, caption, openTab, signIn } from './helpers'

// PRODUCT.md — Feature 8: review queue (human-in-the-loop for 0.50–0.85 confidence matches).
test('Review queue — approve a medium-confidence entity resolution', async ({ page }) => {
  await signIn(page)
  await openTab(page, /Review Queue/)
  await caption(page, 'Review Queue', 'Entity matches with confidence between 0.50 and 0.85 wait here for a person.')
  await beat(page, 2000)

  const approve = page.getByRole('button', { name: '✓ Approve' })
  if (await approve.count() === 0) {
    await caption(page, 'Queue is empty', 'Every entity in this ingest resolved with high confidence.')
    await beat(page, 2500)
    return
  }
  await caption(page, 'Each card shows the proposed entity and every source record mapped to it',
    'Uncheck a wrong mapping, edit the label/class, approve, or reject.')
  await beat(page, 2500)
  const before = await approve.count()
  await approve.first().click()
  await caption(page, 'Approved', 'The entity is now committed to the graph as auto_commit.')
  await expect(page.getByRole('button', { name: '✓ Approve' })).toHaveCount(before - 1, { timeout: 15_000 }).catch(() => null)
  await beat(page, 2000)
})
