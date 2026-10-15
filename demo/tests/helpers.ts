import { expect, Page, APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/** Demo admin credentials and settings, from demo/demo.env (local-only values). */
export const demoEnv: Record<string, string> = Object.fromEntries(
  readFileSync(join(__dirname, '..', 'demo.env'), 'utf8')
    .split('\n')
    .filter(l => l.trim() && !l.trim().startsWith('#') && l.includes('='))
    .map(l => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]),
)

export const ORG = process.env.DEMO_ORG ?? 'example'

/** Pause so a viewer can read what is on screen. */
export const beat = (page: Page, ms = 1500) => page.waitForTimeout(ms)

let captionAt: 'top' | 'bottom' = 'bottom'
/** 'top' renders captions as a banner above the app (the page is shifted down, so nothing is covered). */
export function setCaptionPosition(where: 'top' | 'bottom') { captionAt = where }

/** Show a caption over the app so the recording narrates itself. */
export async function caption(page: Page, title: string, detail = '') {
  await page.evaluate(([t, d, where]) => {
    const BANNER = 96
    let el = document.getElementById('__demo_caption')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_caption'
      document.body.appendChild(el)
    }
    if (where === 'top') {
      el.style.cssText = [
        'position:fixed', 'left:0', 'right:0', 'top:0', `height:${BANNER}px`, 'z-index:99999',
        'display:flex', 'flex-direction:column', 'justify-content:center', 'padding:0 40px',
        'background:#0b0d13', 'border-bottom:2px solid #4f9cf9', 'color:#e2e8f0',
        'font-family:Inter,system-ui,sans-serif', 'pointer-events:none',
      ].join(';')
      document.body.style.paddingTop = `${BANNER}px`
      el.innerHTML = `<div style="font:800 24px/1.2 Inter,system-ui,sans-serif;color:#4f9cf9">${t}</div>` +
        (d ? `<div style="font:500 18px/1.35 Inter,system-ui,sans-serif;margin-top:6px">${d}</div>` : '')
      return
    }
    el.style.cssText = [
      'position:fixed', 'left:50%', 'bottom:24px', 'transform:translateX(-50%)', 'z-index:99999',
      'max-width:min(900px,90vw)', 'padding:14px 22px', 'border-radius:12px',
      'background:rgba(15,17,23,.92)', 'border:1px solid #4f9cf9', 'color:#e2e8f0',
      'font:500 15px/1.45 Inter,system-ui,sans-serif', 'box-shadow:0 8px 30px rgba(0,0,0,.45)',
      'pointer-events:none',
    ].join(';')
    el.innerHTML = `<div style="font-weight:700;color:#4f9cf9;margin-bottom:${d ? 4 : 0}px">${t}</div>${d ? `<div>${d}</div>` : ''}`
  }, [title, detail, captionAt] as const)
  await beat(page, 1800)
}

/** Sign in through the login screen and pick the organisation. */
export async function signIn(page: Page) {
  await page.goto('/')
  await caption(page, 'Sign in', 'Humans sign in with a session; agents use API keys.')
  await page.getByLabel('Username').fill(demoEnv.ADMIN_USERNAME)
  await page.getByLabel('Password').fill(demoEnv.ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Organisation', { exact: true })).toBeVisible()
  await expect(page.locator('select').first()).toHaveValue(ORG)
}

export async function openTab(page: Page, name: RegExp) {
  await page.getByRole('button', { name }).click()
  await beat(page, 800)
}

/** Click a Cytoscape node with the real mouse, using the dev-only handle the graph components expose. */
export async function clickGraphNode(page: Page, handle: '__kgExploreCy' | '__kgOntologyCy', match: (label: string, id: string) => boolean) {
  const target = await page.evaluate(([h, fn]) => {
    // eslint-disable-next-line no-new-func
    const test = new Function('label', 'id', `return (${fn})(label, id)`) as (l: string, i: string) => boolean
    const cy = (window as any)[h]
    const node = cy?.nodes().filter((n: any) => test(String(n.data('label') ?? ''), String(n.id())))[0]
    if (!node) return null
    const pos = node.renderedPosition()
    const box = cy.container().getBoundingClientRect()
    return { x: box.left + pos.x, y: box.top + pos.y, label: String(node.data('label')) }
  }, [handle, match.toString()] as const)
  expect(target, 'graph node to click').not.toBeNull()
  await page.mouse.move(target!.x, target!.y, { steps: 15 })
  await page.mouse.click(target!.x, target!.y)
  return target!.label
}

/** Session-authenticated API context for setup steps that are not part of the recorded story. */
export async function apiLogin(request: APIRequestContext) {
  const r = await request.post('/api/auth/login', {
    data: { username: demoEnv.ADMIN_USERNAME, password: demoEnv.ADMIN_PASSWORD },
  })
  expect(r.ok()).toBeTruthy()
}
