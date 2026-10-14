import React, { useEffect, useState } from 'react'
import { api, OrgSources } from '../api'

const s = {
  wrap: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, padding: 20, marginBottom: 20,
  },
  sectionLabel: {
    fontSize: 11, fontWeight: 700, color: 'var(--accent)',
    textTransform: 'uppercase' as const, letterSpacing: 1, marginBottom: 8,
  },
  section: { marginBottom: 16 },
  grid: { display: 'flex', flexWrap: 'wrap' as const, gap: 8 },
  chip: (active: boolean, disabled: boolean): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '6px 12px', borderRadius: 6, fontSize: 13,
    background: disabled ? 'var(--bg)' : active ? 'var(--surface2)' : 'var(--surface2)',
    border: `1px solid ${disabled ? 'var(--border)' : active ? 'var(--accent)' : 'var(--border)'}`,
    color: disabled ? 'var(--border)' : 'var(--text)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    userSelect: 'none' as const,
    opacity: disabled ? 0.45 : 1,
  }),
  checkbox: { accentColor: 'var(--accent)', width: 14, height: 14 },
  footer: { display: 'flex', alignItems: 'center', gap: 12, paddingTop: 4 },
  runBtn: (disabled: boolean): React.CSSProperties => ({
    padding: '9px 22px', borderRadius: 7,
    background: disabled ? 'var(--surface2)' : 'var(--accent)',
    color: disabled ? 'var(--muted)' : '#fff',
    fontWeight: 700, fontSize: 14, cursor: disabled ? 'not-allowed' : 'pointer',
  }),
  status: { fontSize: 13, color: 'var(--muted)' },
  badge: { fontSize: 11, color: 'var(--muted)', marginLeft: 6 },
} satisfies Record<string, React.CSSProperties | ((...args: never[]) => React.CSSProperties)>

type Props = {
  orgId: string
  onStatusChange: (s: Record<string, unknown>) => void
}

export default function SourceSelector({ orgId, onStatusChange }: Props) {
  const [sources, setSources] = useState<OrgSources | null>(null)
  const [selectedConnectors, setSelectedConnectors] = useState<Set<string>>(new Set())
  const [selectedSchemas, setSelectedSchemas] = useState<Set<string>>(new Set())
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set())
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState<Record<string, unknown>>({ state: 'idle' })

  useEffect(() => {
    if (!orgId) return
    setSources(null)
    setSelectedConnectors(new Set())
    setSelectedSchemas(new Set())
    setSelectedDocs(new Set())
    api.orgSources(orgId).then(setSources).catch(() => null)
  }, [orgId])

  function toggle<T>(set: Set<T>, val: T): Set<T> {
    const n = new Set(set); n.has(val) ? n.delete(val) : n.add(val); return n
  }

  async function run() {
    const total = selectedConnectors.size + selectedSchemas.size + selectedDocs.size
    if (total === 0) return
    setRunning(true)
    try {
      await api.ingest(Array.from(selectedConnectors), Array.from(selectedSchemas), Array.from(selectedDocs))
      const iv = setInterval(async () => {
        const st = await api.ingestStatus()
        setStatus(st); onStatusChange(st)
        if (st['state'] === 'done' || st['state'] === 'error') { clearInterval(iv); setRunning(false) }
      }, 2000)
    } catch (e: unknown) {
      const st = { state: 'error', detail: e instanceof Error ? e.message : String(e) }
      setStatus(st); onStatusChange(st); setRunning(false)
    }
  }

  const totalSelected = selectedConnectors.size + selectedSchemas.size + selectedDocs.size

  if (!sources) return <div style={{ color: 'var(--muted)', fontSize: 13, padding: 16 }}>Loading sources for organisation…</div>

  return (
    <div style={s.wrap}>
      {/* Live connectors */}
      <div style={s.section}>
        <div style={s.sectionLabel}>Live DB connectors</div>
        <div style={s.grid}>
          {sources.connectors.map(c => {
            const disabled = !c.enabled
            const checked = selectedConnectors.has(c.name)
            return (
              <label key={c.name} style={s.chip(checked, disabled)} title={disabled ? 'Not enabled for this org — edit orgs/config.yaml to enable' : ''}>
                <input
                  type="checkbox"
                  style={s.checkbox}
                  checked={checked}
                  disabled={disabled}
                  onChange={() => !disabled && setSelectedConnectors(toggle(selectedConnectors, c.name))}
                />
                {c.name}
                {disabled && <span style={{ fontSize: 10, color: 'var(--border)' }}>off</span>}
              </label>
            )
          })}
        </div>
      </div>

      {/* Schema files */}
      <div style={s.section}>
        <div style={s.sectionLabel}>
          Schema files
          <span style={s.badge}>{sources.schema_files.length} file{sources.schema_files.length !== 1 ? 's' : ''}</span>
        </div>
        {sources.schema_files.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>No schema files found in configured folders.</div>
        ) : (
          <div style={s.grid}>
            {sources.schema_files.map(f => (
              <label key={f.path} style={s.chip(selectedSchemas.has(f.path), false)}>
                <input
                  type="checkbox"
                  style={s.checkbox}
                  checked={selectedSchemas.has(f.path)}
                  onChange={() => setSelectedSchemas(toggle(selectedSchemas, f.path))}
                />
                {f.name}
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Documents */}
      <div style={s.section}>
        <div style={s.sectionLabel}>
          Documents
          <span style={s.badge}>{sources.documents.length} file{sources.documents.length !== 1 ? 's' : ''}</span>
        </div>
        {sources.documents.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>No documents found in configured folders.</div>
        ) : (
          <div style={s.grid}>
            {sources.documents.map(f => (
              <label key={f.path} style={s.chip(selectedDocs.has(f.path), false)}>
                <input
                  type="checkbox"
                  style={s.checkbox}
                  checked={selectedDocs.has(f.path)}
                  onChange={() => setSelectedDocs(toggle(selectedDocs, f.path))}
                />
                {f.name}
              </label>
            ))}
          </div>
        )}
      </div>

      <div style={s.footer}>
        <button style={s.runBtn(running || totalSelected === 0)} onClick={run} disabled={running || totalSelected === 0}>
          {running ? 'Ingesting…' : `▶ Run Ingestion (${totalSelected} selected)`}
        </button>
        <span style={s.status}>
          {status['state'] === 'idle' && 'Select sources above and run ingestion.'}
          {status['state'] === 'running' && `Running: ${status['detail']}`}
          {status['state'] === 'done' && `Done — ${status['entities'] ?? 0} entities, ${status['documents'] ?? 0} docs`}
          {status['state'] === 'error' && `Error: ${status['detail']}`}
        </span>
      </div>
    </div>
  )
}
