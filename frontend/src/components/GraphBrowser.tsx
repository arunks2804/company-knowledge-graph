import React, { useEffect, useState } from 'react'
import { api } from '../api'

const s: Record<string, React.CSSProperties> = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 16 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  btn: {
    padding: '6px 14px', borderRadius: 6, background: 'var(--accent)',
    color: '#fff', fontSize: 13, fontWeight: 500,
  },
  filterRow: { display: 'flex', gap: 8 },
  filterBtn: (active: boolean): React.CSSProperties => ({
    padding: '4px 12px', borderRadius: 6, fontSize: 12,
    background: active ? 'var(--accent2)' : 'var(--surface2)',
    color: active ? '#fff' : 'var(--muted)',
    border: '1px solid var(--border)',
  }),
  card: {
    background: 'var(--surface2)', borderRadius: 8, padding: 14,
    border: '1px solid var(--border)', cursor: 'pointer',
  },
  cardTitle: { fontWeight: 600, fontSize: 14, marginBottom: 4 },
  badge: (s: string): React.CSSProperties => ({
    display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 11, marginLeft: 8,
    background: s === 'auto_commit' ? 'var(--success)' : s === 'needs_review' ? 'var(--warning)' : 'var(--danger)',
    color: '#000',
  }),
  meta: { fontSize: 12, color: 'var(--muted)', marginTop: 4 },
  modal: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
  },
  modalBox: {
    background: 'var(--surface)', borderRadius: 12, padding: 24, maxWidth: 560,
    width: '90%', border: '1px solid var(--border)', maxHeight: '80vh', overflowY: 'auto',
  },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 },
}

type Entity = Record<string, unknown>

export default function GraphBrowser() {
  const [entities, setEntities] = useState<Entity[]>([])
  const [filter, setFilter] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Entity | null>(null)
  const [description, setDescription] = useState('')
  const [descLoading, setDescLoading] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const data = await api.entities(filter || undefined)
      setEntities(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filter])

  async function selectEntity(e: Entity) {
    setSelected(e)
    setDescription('')
    setDescLoading(true)
    try {
      const r = await api.describeEntity(String(e.canonical_id))
      setDescription(r.description)
    } catch {
      setDescription('Could not generate description.')
    } finally {
      setDescLoading(false)
    }
  }

  return (
    <div style={s.wrap}>
      <div style={s.header}>
        <div style={s.filterRow}>
          {[null, 'auto_commit', 'needs_review', 'unresolved'].map(f => (
            <button key={String(f)} style={s.filterBtn(filter === f)} onClick={() => setFilter(f)}>
              {f ?? 'All'}
            </button>
          ))}
        </div>
        <button style={s.btn} onClick={load} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div style={s.grid}>
        {entities.map((e, i) => (
          <div key={i} style={s.card} onClick={() => selectEntity(e)}>
            <div style={s.cardTitle}>
              {String(e.canonical_label || e.canonical_id)}
              <span style={s.badge(String(e.status))}>{String(e.status)}</span>
            </div>
            <div style={s.meta}>
              ID: {String(e.canonical_id)} · Confidence: {Number(e.confidence ?? 0).toFixed(2)}
            </div>
          </div>
        ))}
        {!loading && entities.length === 0 && (
          <div style={{ color: 'var(--muted)', fontSize: 13 }}>
            No entities found. Run ingestion first.
          </div>
        )}
      </div>

      {selected && (
        <div style={s.modal} onClick={() => setSelected(null)}>
          <div style={s.modalBox} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>
              {String(selected.canonical_label)}
            </div>
            <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>
              {String(selected.canonical_id)}
              <span style={s.badge(String(selected.status))}>{String(selected.status)}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
              Confidence: {Number(selected.confidence ?? 0).toFixed(3)}
            </div>
            <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>AI Description</div>
            <div style={{ fontSize: 13, lineHeight: 1.7, color: descLoading ? 'var(--muted)' : 'var(--text)' }}>
              {descLoading ? 'Generating…' : description}
            </div>
            <button
              style={{ marginTop: 16, padding: '8px 16px', borderRadius: 6, background: 'var(--surface2)', color: 'var(--text)', border: '1px solid var(--border)', fontSize: 13 }}
              onClick={() => setSelected(null)}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
