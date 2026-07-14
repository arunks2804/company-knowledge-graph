import React, { useEffect, useState } from 'react'
import { api } from '../api'

const s: Record<string, React.CSSProperties> = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 20 },
  section: {
    background: 'var(--surface2)', borderRadius: 8, padding: 16,
    border: '1px solid var(--border)',
  },
  h2: { fontSize: 14, fontWeight: 700, marginBottom: 10, color: 'var(--accent)' },
  classCard: {
    padding: '10px 12px', borderRadius: 6, background: 'var(--bg)',
    border: '1px solid var(--border)', marginBottom: 8,
  },
  className: { fontWeight: 600, fontSize: 14, marginBottom: 4 },
  desc: { fontSize: 13, color: 'var(--muted)', marginBottom: 6 },
  tag: {
    display: 'inline-block', padding: '2px 8px', borderRadius: 4,
    background: 'var(--surface)', color: 'var(--text)', fontSize: 11,
    border: '1px solid var(--border)', marginRight: 4, marginTop: 2,
  },
  relRow: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0',
    borderBottom: '1px solid var(--border)', fontSize: 13,
  },
  node: {
    padding: '3px 10px', borderRadius: 4, background: 'var(--accent2)',
    color: '#fff', fontWeight: 500, fontSize: 12,
  },
  arrow: { color: 'var(--muted)', fontSize: 12 },
  relName: { color: 'var(--accent)', fontSize: 12, fontFamily: 'monospace' },
}

type OntologyData = {
  classes?: { name: string; description?: string; properties?: string[]; source_hints?: string[] }[]
  relationships?: { name: string; from?: string; to?: string; description?: string }[]
}

export default function OntologyExplainer() {
  const [data, setData] = useState<OntologyData>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.ontology().then(d => {
      setData(d as OntologyData)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ color: 'var(--muted)' }}>Loading ontology…</div>

  return (
    <div style={s.wrap}>
      <div style={s.section}>
        <div style={s.h2}>Classes ({data.classes?.length ?? 0})</div>
        {data.classes?.map(c => (
          <div key={c.name} style={s.classCard}>
            <div style={s.className}>{c.name}</div>
            {c.description && <div style={s.desc}>{c.description}</div>}
            {c.source_hints && c.source_hints.length > 0 && (
              <div>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>Source hints: </span>
                {c.source_hints.map(h => <span key={h} style={s.tag}>{h}</span>)}
              </div>
            )}
            {c.properties && c.properties.length > 0 && (
              <div style={{ marginTop: 4 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>Properties: </span>
                {c.properties.map(p => <span key={p} style={s.tag}>{p}</span>)}
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={s.section}>
        <div style={s.h2}>Relationships ({data.relationships?.length ?? 0})</div>
        {data.relationships?.map((r, i) => (
          <div key={i} style={s.relRow}>
            <span style={s.node}>{r.from ?? '?'}</span>
            <span style={s.arrow}>──</span>
            <span style={s.relName}>[{r.name}]</span>
            <span style={s.arrow}>──▶</span>
            <span style={s.node}>{r.to ?? '?'}</span>
            {r.description && <span style={{ color: 'var(--muted)', fontSize: 12 }}>· {r.description}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
