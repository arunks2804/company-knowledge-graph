import { copyFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

/** Global teardown: copy each spec's video to recordings/<spec>.webm (test-results/ is wiped every run). */
export default function collectRecordings() {
  const results = join(__dirname, 'test-results')
  const out = join(__dirname, 'recordings')
  if (!existsSync(results)) return
  mkdirSync(out, { recursive: true })
  for (const dir of readdirSync(results)) {
    const video = join(results, dir, 'video.webm')
    const spec = dir.match(/^(\d+-[a-z-]+?)-[A-Z]/)?.[1]
    if (spec && existsSync(video)) copyFileSync(video, join(out, `${spec}.webm`))
  }
}
