import React, { useEffect, useState } from 'react'
import { api } from './api'
import OrgSelector from './components/OrgSelector'
import SourceSelector from './components/SourceSelector'
import SearchBox from './components/SearchBox'
import NeighbourhoodGraph from './components/NeighbourhoodGraph'
import OntologyGraph from './components/OntologyGraph'
import ReviewQueue from './components/ReviewQueue'

type Mode = 'ask' | 'explore' | 'ontology' | 'ingest' | 'review'

const s: Record<string, React.CSSProperties> = {
  app: { minHeight: '100vh', display: 'flex', flexDirection: 'column' },
  header: {
    padding: '14px 24px', background: 'var(--surface)',
    borderBottom: '1px solid var(--border)',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  },
  logo: { fontWeight: 800, fontSize: 18, letterSpacing: '-0.5px' },
  accent: { color: 'var(--accent)' },
  statusRow: { display: 'flex', gap: 16, fontSize: 12, color: 'var(--muted)', alignItems: 'center' },
  dot: (ok: boolean): React.CSSProperties => ({
    width: 7, height: 7, borderRadius: '50%',
    background: ok ? 'var(--success)' : 'var(--danger)',
    display: 'inline-block', marginRight: 5,
  }),
  nav: {
    padding: '0 24px', background: 'var(--surface)',
    borderBottom: '1px solid var(--border)', display: 'flex', gap: 2,
  },
  navBtn: (active: boolean): React.CSSProperties => ({
    padding: '11px 18px', fontSize: 13, fontWeight: 600, background: 'transparent',
    color: active ? 'var(--accent)' : 'var(--muted)',
    borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
    borderRadius: 0, cursor: 'pointer',
  }),
  main: { flex: 1, display: 'flex', flexDirection: 'column', padding: 24, maxWidth: 1200, width: '100%', margin: '0 auto' },
  fullHeight: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 },
}

export default function App() {
  const [mode, setMode] = useState<Mode>('ask')
  const [health, setHealth] = useState<{ neo4j: boolean; langsmith: boolean } | null>(null)
  const [orgId, setOrgId] = useState('')

  useEffect(() => {
    api.health().then(setHealth).catch(() => null)
  }, [])

  const tabs: { id: Mode; label: string }[] = [
    { id: 'ask',      label: '💬 Ask' },
    { id: 'explore',  label: '🕸 Explore Relationships' },
    { id: 'ontology', label: '📐 Ontology' },
    { id: 'ingest',   label: '⚙️ Ingest' },
    { id: 'review',   label: '⚠️ Review Queue' },
  ]

  return (
    <div style={s.app}>
      {/* Header */}
      <header style={s.header}>
        <div style={s.logo}>
          Company <span style={s.accent}>Knowledge Graph</span>
        </div>
        <div style={s.statusRow}>
          {health && (
            <>
              <span><span style={s.dot(health.neo4j)} />Neo4j</span>
              <span><span style={s.dot(health.langsmith)} />LangSmith</span>
            </>
          )}
        </div>
      </header>

      {/* Org / App selector */}
      <OrgSelector onSelect={(org, _app) => setOrgId(org)} />

      {/* Nav */}
      <nav style={s.nav}>
        {tabs.map(t => (
          <button key={t.id} style={s.navBtn(mode === t.id)} onClick={() => setMode(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      {/* Main */}
      <main style={s.main}>
        {mode === 'ask' && (
          <div>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 20 }}>
              Ask any question about your organisation's data. Answers are grounded in ingested schemas and documents.
            </p>
            <SearchBox />
          </div>
        )}

        {mode === 'explore' && (
          <div style={s.fullHeight}>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>
              Search for an entity to see how it connects across all your data sources.
            </p>
            <div style={{ flex: 1, minHeight: 500 }}>
              <NeighbourhoodGraph />
            </div>
          </div>
        )}

        {mode === 'ontology' && (
          <div style={s.fullHeight}>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>
              Class-level view of your data model. Shows types and how they relate — not specific products or customers.
              Click any node for details.
            </p>
            <div style={{ flex: 1, minHeight: 500 }}>
              <OntologyGraph />
            </div>
          </div>
        )}

        {mode === 'ingest' && orgId && (
          <div>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 20 }}>
              Select which sources to ingest for <strong>{orgId}</strong>. Disabled connectors are not configured for this organisation.
              Edit <code>orgs/{orgId}/config.yaml</code> to enable them.
            </p>
            <SourceSelector orgId={orgId} onStatusChange={() => null} />
          </div>
        )}

        {mode === 'review' && <ReviewQueue />}
      </main>
    </div>
  )
}
