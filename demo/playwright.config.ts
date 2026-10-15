import { defineConfig } from '@playwright/test'

// Walkthroughs run against the real stack (see README.md in this folder): local Ollama, Neo4j,
// Postgres and LocalStack. LLM calls on an 8B local model take minutes, hence the long timeouts.
export default defineConfig({
  testDir: './tests',
  globalTeardown: './collect-recordings.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 30 * 60_000,
  expect: { timeout: 10 * 60_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.DEMO_BASE_URL ?? 'http://localhost:5173',
    channel: process.env.DEMO_BROWSER_CHANNEL ?? 'chrome',
    viewport: { width: 1440, height: 900 },
    video: { mode: 'on', size: { width: 1440, height: 900 } },
    screenshot: 'on',
    trace: 'retain-on-failure',
    launchOptions: { slowMo: Number(process.env.DEMO_SLOWMO ?? 250) },
  },
})
