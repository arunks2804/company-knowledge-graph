import { test, expect } from '@playwright/test'
import { beat, caption, clickGraphNode, openTab, signIn } from './helpers'

// PRODUCT.md — Feature 6: ontology diagram (workflow 1, step 9).
test('Ontology — the class-level data model generated for this org', async ({ page }) => {
  await signIn(page)
  await openTab(page, /Ontology/)
  await caption(page, 'Ontology', 'Classes and relationships only — not individual products or customers.')
  await page.waitForFunction(() => (window as any).__kgOntologyCy?.nodes().length > 0)
  await beat(page, 2500)  // let the force layout settle

  const picked = await clickGraphNode(page, '__kgOntologyCy', l => l === 'Product')
  await caption(page, `Click a class: ${picked}`, 'Description and source hints: which tables and columns map to it.')
  await beat(page, 2500)

  await clickGraphNode(page, '__kgOntologyCy', l => l === 'MaintenanceIncident')
  await caption(page, 'MaintenanceIncident', 'A class that exists only in documents — resolved from maintenance reports.')
  await beat(page, 2500)
  await expect(page.locator('body')).toContainText('MaintenanceIncident')
})
