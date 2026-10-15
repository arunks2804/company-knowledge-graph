// Turns the recorded highlight run into a short MP4: removes the LLM waits logged by
// tests/07-linkedin-reel.spec.ts (test-results/reel-cuts.json) and encodes H.264 for LinkedIn.
// Usage: node make-reel.mjs   (requires ffmpeg on PATH)
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const here = new URL('.', import.meta.url).pathname
const results = join(here, 'test-results')
// with retries there is one folder per take; only the passing take writes reel-cuts.json
const dir = readdirSync(results).find(d => d.startsWith('07-linkedin-reel') && existsSync(join(results, d, 'reel-cuts.json')))
if (!dir) throw new Error('No passing reel take found — run `npx playwright test --grep @reel` first')
const video = join(results, dir, 'video.webm')
const { cuts, introEnd } = JSON.parse(readFileSync(join(results, dir, 'reel-cuts.json'), 'utf8'))
const title = join(results, dir, 'reel-title.png')

const duration = Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration',
  '-of', 'csv=p=0', video]).toString().trim())

const KEEP_BEFORE = 1.2   // seconds of "Thinking…" kept before each cut
const KEEP_AFTER = 0.4    // seconds kept before the answer appears
const INTRO_SECONDS = 3.5 // the title card, from a full-viewport screenshot

// keep = everything except [start+KEEP_BEFORE, end-KEEP_AFTER] of each wait
const keep = []
let cursor = introEnd + 0.3   // recorded frames start after the title card
for (const c of [...cuts].sort((a, b) => a.start - b.start)) {
  const from = c.start + KEEP_BEFORE, to = c.end - KEEP_AFTER
  if (to - from < 1) continue          // too short to bother cutting
  keep.push([cursor, from]); cursor = to
}
keep.push([cursor, duration])

// input 0 = title still, input 1 = recording
const parts = keep.map(([a, b], i) =>
  `[1:v]trim=start=${a.toFixed(2)}:end=${b.toFixed(2)},setpts=PTS-STARTPTS,fps=30,format=yuv420p,setsar=1[v${i}]`)
const intro = `[0:v]scale=1440:900,fps=30,format=yuv420p,setsar=1[t]`
const filter = `${intro};${parts.join(';')};[t]${keep.map((_, i) => `[v${i}]`).join('')}concat=n=${keep.length + 1}:v=1:a=0[out]`

const out = join(here, 'recordings')
mkdirSync(out, { recursive: true })
const target = join(out, 'linkedin-reel.mp4')
execFileSync('ffmpeg', ['-y', '-v', 'error', '-loop', '1', '-t', String(INTRO_SECONDS), '-i', title, '-i', video, '-filter_complex', filter, '-map', '[out]',
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-movflags', '+faststart', target], { stdio: 'inherit' })

const final = INTRO_SECONDS + keep.reduce((s, [a, b]) => s + (b - a), 0)
console.log(`linkedin-reel.mp4: ${final.toFixed(1)}s (raw ${duration.toFixed(1)}s, ${cuts.length} waits cut) → ${target}`)
