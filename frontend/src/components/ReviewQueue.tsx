import React, { useEffect, useState } from 'react'
import { api } from '../api'

const CLASSES = ['Product', 'Customer', 'Order', 'Warehouse', 'Supplier', 'Shipment', 'MaintenanceIncident']
const STATUS_COLORS: Record<string, string> = { auto_commit: 'var(--success)', needs_review: 'var(--warning)', unresolved: 'var(--danger)' }

type Source = { source_type: string; table_or_datasource: string; key_column: string; key_value: string }
type Entity = { canonical_id: string; canonical_label: string; class: string; confidence: number; status: string; sources: string }

const p: Record<string, React.CSSProperties> = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 12 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  count: { fontSize: 14, color: 'var(--muted)' },
  refreshBtn: { padding: '6px 14px', borderRadius: 6, background: 'var(--surface2)', color: 'var(--text)', fontSize: 13, border: '1px solid var(--border)' },
  card: { background: 'var(--surface2)', borderRadius: 10, padding: 16, border: '1px solid var(--warning)' },
  cardTitle: { fontWeight: 700, fontSize: 14, marginBottom: 4 },
  meta: { fontSize: 12, color: 'var(--muted)', marginBottom: 12 },
  badge: (s: string): React.CSSProperties => ({ display: 'inline-block', padding: '2px 8px', borderRadius: 4, background: STATUS_COLORS[s] || 'var(--muted)', color: '#000', fontSize: 11, marginLeft: 8 }),
  sourceRow: { fontSize: 12, color: 'var(--muted)', padding: '4px 0', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 },
  actionRow: { display: 'flex', gap: 8, marginTop: 12 },
  approveBtn: { flex: 1, padding: '8px 0', borderRadius: 6, background: 'var(--success)', color: '#000', fontWeight: 700, fontSize: 13 },
  rejectBtn: { flex: 1, padding: '8px 0', borderRadius: 6, background: 'var(--danger)', color: '#fff', fontWeight: 700, fontSize: 13 },
  editBtn: { flex: 1, padding: '8px 0', borderRadius: 6, background: 'var(--surface)', color: 'var(--text)', fontWeight: 700, fontSize: 13, border: '1px solid var(--border)' },
  editPanel: { marginTop: 12, padding: 14, background: 'var(--bg)', borderRadius: 8, border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 10 },
  label: { fontSize: 11, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.8, marginBottom: 4 },
  input: { width: '100%', padding: '7px 10px', borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13, outline: 'none', boxSizing: 'border-box' as const },
  select: { width: '100%', padding: '7px 10px', borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13, outline: 'none' },
  sourceCheck: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--muted)', padding: '4px 0' },
  saveBtn: { padding: '8px 0', borderRadius: 6, background: 'var(--accent)', color: '#fff', fontWeight: 700, fontSize: 13, width: '100%' },
  splitBtn: { padding: '8px 0', borderRadius: 6, background: 'var(--surface)', color: 'var(--accent)', fontWeight: 700, fontSize: 13, width: '100%', border: '1px solid var(--accent)' },
  empty: { color: 'var(--muted)', fontSize: 14, padding: 32, textAlign: 'center' as const },
}

function parseSources(raw: string): Source[] {
  try { return JSON.parse(raw.replace(/'/g, '"')) } catch { return [] }
}

function EntityCard({ entity, onDone }: { entity: Entity; onDone: () => void }) {
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [editLabel, setEditLabel] = useState(entity.canonical_label)
  const [editClass, setEditClass] = useState(entity.class || 'Product')
  const sources = parseSources(entity.sources || '[]')
  const [checkedSources, setCheckedSources] = useState<Set<number>>(new Set(sources.map((_, i) => i)))
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState(false)

  if (done) return null

  async function approve() {
    setSaving(true)
    await api.approveEntity(entity.canonical_id)
    setSaving(false); setDone(true); onDone()
  }

  async function reject() {
    setSaving(true)
    await api.rejectEntity(entity.canonical_id)
    setSaving(false); setDone(true); onDone()
  }

  async function saveEdit() {
    setSaving(true)
    const keptSources = sources.filter((_, i) => checkedSources.has(i))
    await api.updateEntity(entity.canonical_id, {
      canonical_label: editLabel,
      class_name: editClass,
      status: 'auto_commit',
    })
    setSaving(false); setDone(true); onDone()
  }

  function toggleSource(i: number) {
    setCheckedSources(prev => { const n = new Set(prev); n.has(i) ? n.delete(i) : n.add(i); return n })
  }

  return (
    <div style={p.card}>
      <div style={p.cardTitle}>
        {entity.canonical_label}
        <span style={p.badge(entity.status)}>{entity.status}</span>
      </div>
      <div style={p.meta}>
        ID: {entity.canonical_id} · Class: {entity.class} · Confidence: {Number(entity.confidence).toFixed(3)}
      </div>

      {/* Source mappings */}
      {sources.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={p.label}>Source mappings</div>
          {sources.map((s, i) => (
            <div key={i} style={p.sourceRow}>
              <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{s.source_type}</span>
              <span>{s.table_or_datasource}</span>
              <span>·</span>
              <span>{s.key_column} = <strong>{s.key_value}</strong></span>
            </div>
          ))}
        </div>
      )}

      {/* Action buttons */}
      {mode === 'view' && (
        <div style={p.actionRow}>
          <button style={p.approveBtn} onClick={approve} disabled={saving}>✓ Approve</button>
          <button style={p.editBtn} onClick={() => setMode('edit')}>✎ Edit</button>
          <button style={p.rejectBtn} onClick={reject} disabled={saving}>✕ Reject</button>
        </div>
      )}

      {/* Edit panel */}
      {mode === 'edit' && (
        <div style={p.editPanel}>
          <div>
            <div style={p.label}>Label</div>
            <input style={p.input} value={editLabel} onChange={e => setEditLabel(e.target.value)} />
          </div>

          <div>
            <div style={p.label}>Class</div>
            <select style={p.select} value={editClass} onChange={e => setEditClass(e.target.value)}>
              {CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {sources.length > 0 && (
            <div>
              <div style={p.label}>Source mappings — uncheck any that are wrong</div>
              {sources.map((s, i) => (
                <label key={i} style={p.sourceCheck}>
                  <input type="checkbox" checked={checkedSources.has(i)} onChange={() => toggleSource(i)} style={{ accentColor: 'var(--accent)' }} />
                  <span style={{ color: 'var(--accent)' }}>{s.source_type}</span>
                  {s.table_or_datasource} · {s.key_column} = <strong>{s.key_value}</strong>
                </label>
              ))}
              {checkedSources.size < sources.size && (
                <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 4 }}>
                  Unchecked sources will be removed from this entity and marked unresolved.
                </div>
              )}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <button style={p.saveBtn} onClick={saveEdit} disabled={saving}>{saving ? 'Saving…' : '✓ Save & approve'}</button>
            <button style={{ ...p.editBtn, flex: 0, padding: '8px 16px' }} onClick={() => setMode('view')}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ReviewQueue() {
  const [entities, setEntities] = useState<Entity[]>([])
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const data = await api.entities('needs_review')
      setEntities(data as Entity[])
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const pending = entities.length

  return (
    <div style={p.wrap}>
      <div style={p.header}>
        <div style={p.count}>{pending} entit{pending === 1 ? 'y' : 'ies'} need review</div>
        <button style={p.refreshBtn} onClick={load}>Refresh</button>
      </div>

      {!loading && entities.length === 0 && (
        <div style={p.empty}>No entities pending review. Either the graph is empty or all resolutions were high-confidence.</div>
      )}

      {entities.map(e => (
        <EntityCard key={e.canonical_id} entity={e} onDone={load} />
      ))}
    </div>
  )
}
