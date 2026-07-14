import React, { useEffect, useState } from 'react'
import { api, OrgSummary } from '../api'

const s: Record<string, React.CSSProperties> = {
  bar: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '10px 24px', background: 'var(--surface)',
    borderBottom: '1px solid var(--border)',
  },
  label: { fontSize: 12, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.8 },
  select: {
    padding: '6px 12px', borderRadius: 6, background: 'var(--surface2)',
    border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13,
    outline: 'none', cursor: 'pointer',
  },
  divider: { width: 1, height: 20, background: 'var(--border)' },
}

type Props = {
  onSelect: (orgId: string, appId: string | null) => void
}

export default function OrgSelector({ onSelect }: Props) {
  const [orgs, setOrgs] = useState<OrgSummary[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [selectedApp, setSelectedApp] = useState('')

  useEffect(() => {
    api.orgs().then(data => {
      setOrgs(data)
      if (data.length > 0) {
        setSelectedOrg(data[0].id)
        onSelect(data[0].id, null)
      }
    }).catch(() => null)
  }, [])

  function handleOrgChange(orgId: string) {
    setSelectedOrg(orgId)
    setSelectedApp('')
    onSelect(orgId, null)
  }

  function handleAppChange(appId: string) {
    setSelectedApp(appId)
    onSelect(selectedOrg, appId || null)
  }

  const currentOrg = orgs.find(o => o.id === selectedOrg)

  return (
    <div style={s.bar}>
      <span style={s.label}>Organisation</span>
      <select style={s.select} value={selectedOrg} onChange={e => handleOrgChange(e.target.value)}>
        {orgs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
        {orgs.length === 0 && <option value="">No organisations configured</option>}
      </select>

      {currentOrg && currentOrg.apps.length > 0 && (
        <>
          <div style={s.divider} />
          <span style={s.label}>App</span>
          <select style={s.select} value={selectedApp} onChange={e => handleAppChange(e.target.value)}>
            <option value="">All apps</option>
            {currentOrg.apps.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </>
      )}
    </div>
  )
}
