import React, { useState } from 'react'
import { api } from '../api'

const s: Record<string, React.CSSProperties> = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 12 },
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
  chunk: {
    background: 'var(--surface2)', borderRadius: 8, padding: 14,
    border: '1px solid var(--border)',
  },
  chunkMeta: { fontSize: 11, color: 'var(--muted)', marginBottom: 6 },
  score: { color: 'var(--success)', fontWeight: 600 },
  text: { fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' },
}

type Chunk = { text: string; document?: string; path?: string; chunk_index?: number; score?: number }

export default function DocumentViewer() {
  const [query, setQuery] = useState('')
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function search() {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    try {
      const r = await api.searchChunks(query)
      setChunks(r as Chunk[])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.wrap}>
      <div style={s.row}>
        <input
          style={s.input}
          placeholder="Search document chunks by semantic similarity…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
        />
        <button style={s.btn} onClick={search} disabled={loading}>
          {loading ? '…' : 'Search'}
        </button>
      </div>

      {error && <div style={{ color: 'var(--danger)', fontSize: 13 }}>{error}</div>}

      {chunks.length === 0 && !loading && query && (
        <div style={{ color: 'var(--muted)', fontSize: 13 }}>No chunks found.</div>
      )}

      {chunks.map((c, i) => (
        <div key={i} style={s.chunk}>
          <div style={s.chunkMeta}>
            📄 {c.document || 'unknown'} · chunk #{c.chunk_index ?? i}
            {c.score !== undefined && (
              <span style={{ ...s.score, marginLeft: 8 }}>score: {c.score.toFixed(3)}</span>
            )}
          </div>
          <div style={s.text}>{c.text}</div>
        </div>
      ))}
    </div>
  )
}
