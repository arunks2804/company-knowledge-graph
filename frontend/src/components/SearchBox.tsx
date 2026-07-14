import React, { useState } from 'react'
import { api } from '../api'

const styles: Record<string, React.CSSProperties> = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 16 },
  row: { display: 'flex', gap: 8 },
  input: {
    flex: 1, padding: '10px 14px', borderRadius: 8,
    background: 'var(--surface2)', border: '1px solid var(--border)',
    color: 'var(--text)', fontSize: 14, outline: 'none',
  },
  btn: {
    padding: '10px 20px', borderRadius: 8, background: 'var(--accent)',
    color: '#fff', fontWeight: 600, fontSize: 14,
  },
  tabs: { display: 'flex', gap: 8 },
  tab: (active: boolean): React.CSSProperties => ({
    padding: '6px 14px', borderRadius: 6, fontSize: 13, fontWeight: 500,
    background: active ? 'var(--accent)' : 'var(--surface2)',
    color: active ? '#fff' : 'var(--muted)',
    border: '1px solid var(--border)',
  }),
  result: {
    background: 'var(--surface2)', borderRadius: 8, padding: 16,
    border: '1px solid var(--border)', fontSize: 14, lineHeight: 1.6,
  },
  label: { fontSize: 12, color: 'var(--muted)', marginBottom: 6 },
  tag: {
    display: 'inline-block', padding: '2px 8px', borderRadius: 4,
    background: 'var(--accent2)', color: '#fff', fontSize: 11, marginRight: 4,
  },
  code: {
    display: 'block', background: 'var(--bg)', padding: 12, borderRadius: 6,
    fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap', marginTop: 8,
    color: '#93c5fd',
  },
}

type Mode = 'investigate' | 'entities' | 'chunks' | 'cypher'

export default function SearchBox() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<Mode>('investigate')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState('')

  async function run() {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      let res: unknown
      if (mode === 'investigate') res = await api.investigate(query)
      else if (mode === 'entities') res = await api.searchEntities(query)
      else if (mode === 'chunks') res = await api.searchChunks(query)
      else res = await api.cypher(query)
      setResult(res)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.wrap}>
      <div style={styles.tabs}>
        {(['investigate', 'entities', 'chunks', 'cypher'] as Mode[]).map(m => (
          <button key={m} style={styles.tab(mode === m)} onClick={() => setMode(m)}>
            {m === 'investigate' ? '🔍 Investigate' :
             m === 'entities' ? '🏷 Entities' :
             m === 'chunks' ? '📄 Docs' : '⚡ Cypher'}
          </button>
        ))}
      </div>

      <div style={styles.row}>
        <input
          style={styles.input}
          placeholder={
            mode === 'investigate' ? 'Ask a question about your data...' :
            mode === 'entities' ? 'Search for an entity...' :
            mode === 'chunks' ? 'Search document text...' :
            'Describe a query in natural language...'
          }
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
        />
        <button style={styles.btn} onClick={run} disabled={loading}>
          {loading ? '...' : 'Run'}
        </button>
      </div>

      {error && <div style={{ color: 'var(--danger)', fontSize: 13 }}>{error}</div>}

      {result !== null && <ResultView mode={mode} result={result} />}
    </div>
  )
}

function ResultView({ mode, result }: { mode: Mode; result: unknown }) {
  if (mode === 'investigate') {
    const r = result as { answer: string; sources: {document?: string; score?: number}[]; entities_used: string[] }
    return (
      <div style={styles.result}>
        <div style={styles.label}>Answer</div>
        <p style={{ marginBottom: 12 }}>{r.answer}</p>
        {r.entities_used?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={styles.label}>Entities used</div>
            {r.entities_used.map(e => <span key={e} style={styles.tag}>{e}</span>)}
          </div>
        )}
        {r.sources?.length > 0 && (
          <div>
            <div style={styles.label}>Sources</div>
            {r.sources.slice(0, 3).map((s, i) => (
              <div key={i} style={{ fontSize: 12, color: 'var(--muted)' }}>
                {s.document} {s.score !== undefined ? `(score: ${s.score.toFixed(3)})` : ''}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (mode === 'cypher') {
    const r = result as { cypher: string; explanation: string; rows: unknown[]; error?: string }
    return (
      <div style={styles.result}>
        <div style={styles.label}>Generated Cypher</div>
        <code style={styles.code}>{r.cypher}</code>
        {r.explanation && <p style={{ marginTop: 8, fontSize: 13, color: 'var(--muted)' }}>{r.explanation}</p>}
        {r.error && <p style={{ color: 'var(--danger)', marginTop: 8 }}>{r.error}</p>}
        {r.rows?.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={styles.label}>Results ({r.rows.length} rows)</div>
            <code style={styles.code}>{JSON.stringify(r.rows, null, 2)}</code>
          </div>
        )}
      </div>
    )
  }

  const rows = result as Record<string, unknown>[]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rows.map((row, i) => (
        <div key={i} style={styles.result}>
          {Object.entries(row).map(([k, v]) => (
            <div key={k} style={{ marginBottom: 4 }}>
              <span style={{ color: 'var(--muted)', fontSize: 12 }}>{k}: </span>
              <span style={{ fontSize: 13 }}>{String(v)}</span>
            </div>
          ))}
        </div>
      ))}
      {rows.length === 0 && <div style={{ color: 'var(--muted)', fontSize: 13 }}>No results found.</div>}
    </div>
  )
}
