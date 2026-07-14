import React, { useEffect, useRef, useState, useCallback } from 'react'
import cytoscape from 'cytoscape'
import { api } from '../api'

const CLASS_COLORS: Record<string, string> = {
  Product: '#4f9cf9', Customer: '#34d399', Order: '#fbbf24',
  Warehouse: '#f87171', Supplier: '#a78bfa', Shipment: '#fb923c',
  MaintenanceIncident: '#e879f9', Entity: '#64748b',
}
const CLASSES = Object.keys(CLASS_COLORS)

function nodeColor(classes: string[]): string {
  for (const c of classes) if (CLASS_COLORS[c]) return CLASS_COLORS[c]
  return '#4f9cf9'
}

type SelectedNode = { type: 'node'; id: string; label: string; classes: string[]; status: string }
type SelectedEdge = { type: 'edge'; source: string; target: string; relType: string }
type Selected = SelectedNode | SelectedEdge | null

const p: Record<string, React.CSSProperties> = {
  wrap: { display: 'flex', flexDirection: 'column', height: '100%', gap: 12 },
  searchRow: { display: 'flex', gap: 8 },
  input: { flex: 1, padding: '10px 14px', borderRadius: 8, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 14, outline: 'none' },
  btn: { padding: '10px 20px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 14 },
  body: { flex: 1, display: 'flex', gap: 12, minHeight: 0 },
  canvas: { flex: 1, background: 'var(--surface2)', borderRadius: 10, border: '1px solid var(--border)', position: 'relative' as const },
  empty: { position: 'absolute' as const, inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 13, pointerEvents: 'none' as const },
  panel: { width: 260, background: 'var(--surface)', borderRadius: 10, padding: 16, border: '1px solid var(--border)', flexShrink: 0, overflowY: 'auto' as const, display: 'flex', flexDirection: 'column', gap: 12 },
  panelTitle: { fontWeight: 700, fontSize: 13, color: 'var(--accent)', marginBottom: 4 },
  label: { fontSize: 11, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.8, marginBottom: 4 },
  fieldInput: { width: '100%', padding: '7px 10px', borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13, outline: 'none', boxSizing: 'border-box' as const },
  select: { width: '100%', padding: '7px 10px', borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13, outline: 'none' },
  saveBtn: { padding: '8px 0', borderRadius: 6, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13, width: '100%', textAlign: 'center' as const },
  removeBtn: { padding: '8px 0', borderRadius: 6, background: 'var(--surface2)', color: 'var(--danger)', fontWeight: 600, fontSize: 13, width: '100%', border: '1px solid var(--danger)', textAlign: 'center' as const },
  divider: { height: 1, background: 'var(--border)', margin: '4px 0' },
}

export default function NeighbourhoodGraph() {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [entityResults, setEntityResults] = useState<Record<string, unknown>[]>([])
  const [selected, setSelected] = useState<Selected>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editClass, setEditClass] = useState('')
  const [editStatus, setEditStatus] = useState('')
  const [editRelType, setEditRelType] = useState('')
  const [saving, setSaving] = useState(false)
  const [centreId, setCentreId] = useState('')

  const initCy = useCallback(() => {
    if (!containerRef.current) return
    cyRef.current?.destroy()
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (el: cytoscape.NodeSingular) =>
              el.data('isCentre') ? '#fff' : nodeColor(el.data('nodeClasses') || []),
            'border-width': (el: cytoscape.NodeSingular) => el.data('isCentre') ? 3 : 0,
            'border-color': (el: cytoscape.NodeSingular) => nodeColor(el.data('nodeClasses') || []),
            'color': (el: cytoscape.NodeSingular) => el.data('isCentre') ? '#0f1117' : '#fff',
            'label': 'data(label)',
            'font-size': '12px', 'font-weight': 'bold',
            'text-valign': 'center', 'text-halign': 'center',
            'width': 110, 'height': 36, 'shape': 'round-rectangle',
          } as cytoscape.Css.Node,
        },
        {
          selector: 'node:selected',
          style: { 'border-width': 3, 'border-color': '#fff', 'border-opacity': 1 } as cytoscape.Css.Node,
        },
        {
          selector: 'edge',
          style: {
            'width': 2, 'line-color': '#2e3450',
            'target-arrow-color': '#2e3450', 'target-arrow-shape': 'triangle',
            'curve-style': 'bezier', 'label': 'data(label)',
            'font-size': '10px', 'color': '#8892a4',
            'text-background-color': '#0f1117', 'text-background-opacity': 1, 'text-background-padding': '2px',
          } as cytoscape.Css.Edge,
        },
        {
          selector: 'edge:selected',
          style: { 'line-color': 'var(--accent)', 'target-arrow-color': 'var(--accent)' } as cytoscape.Css.Edge,
        },
      ],
      layout: { name: 'preset' },
      userZoomingEnabled: true, userPanningEnabled: true,
    })

    cy.on('tap', 'node', evt => {
      const n = evt.target
      const sel: SelectedNode = { type: 'node', id: n.data('id'), label: n.data('label'), classes: n.data('nodeClasses') || [], status: n.data('status') || '' }
      setSelected(sel)
      setEditLabel(sel.label)
      setEditClass(sel.classes.find((c: string) => c !== 'Entity') || '')
      setEditStatus(sel.status)
    })

    cy.on('tap', 'edge', evt => {
      const e = evt.target
      const sel: SelectedEdge = { type: 'edge', source: e.data('source'), target: e.data('target'), relType: e.data('label') }
      setSelected(sel)
      setEditRelType(sel.relType)
    })

    cy.on('tap', evt => { if (evt.target === cy) setSelected(null) })
    cyRef.current = cy
  }, [])

  useEffect(() => { initCy(); return () => { cyRef.current?.destroy() } }, [initCy])

  async function searchEntities() {
    if (!query.trim()) return
    setLoading(true); setError(''); setEntityResults([])
    try {
      const results = await api.searchEntities(query)
      setEntityResults(results)
      if (results.length === 1) await loadNeighbourhood(String(results[0].id))
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setLoading(false) }
  }

  async function loadNeighbourhood(canonicalId: string) {
    setLoading(true); setError(''); setEntityResults([]); setCentreId(canonicalId)
    try {
      const data = await api.neighbourhood(canonicalId)
      const cy = cyRef.current; if (!cy) return
      cy.elements().remove()
      cy.add([
        ...data.nodes.map((n, i) => {
          const angle = i === 0 ? 0 : ((i - 1) / Math.max(data.nodes.length - 1, 1)) * 2 * Math.PI
          return { data: { id: n.data.id, label: n.data.label, nodeClasses: n.data.classes || [], isCentre: n.data.id === data.centre, status: n.data.status }, position: { x: i === 0 ? 300 : 300 + 200 * Math.cos(angle), y: i === 0 ? 250 : 250 + 200 * Math.sin(angle) } }
        }),
        ...data.edges.map(e => ({ data: { id: `${e.data.source}-${e.data.label}-${e.data.target}`, source: e.data.source, target: e.data.target, label: e.data.label } })),
      ])
      cy.layout({ name: 'cose', padding: 60, animate: true, animationDuration: 400 } as cytoscape.CoseLayoutOptions).run()
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setLoading(false) }
  }

  async function saveNodeEdit() {
    if (!selected || selected.type !== 'node') return
    setSaving(true)
    try {
      await api.updateEntity(selected.id, { canonical_label: editLabel, class_name: editClass, status: editStatus })
      const cy = cyRef.current
      if (cy) {
        const node = cy.$(`#${selected.id}`)
        node.data('label', editLabel)
        node.data('nodeClasses', editClass ? [editClass] : [])
      }
      setSelected(prev => prev && prev.type === 'node' ? { ...prev, label: editLabel, classes: editClass ? [editClass] : [] } : prev)
    } finally { setSaving(false) }
  }

  async function saveEdgeEdit() {
    if (!selected || selected.type !== 'edge') return
    setSaving(true)
    try {
      await api.updateGraphRelationship(selected.source, selected.target, selected.relType, editRelType)
      const cy = cyRef.current
      if (cy) {
        const edgeId = `${selected.source}-${selected.relType}-${selected.target}`
        cy.$(`#${edgeId}`).data('label', editRelType)
      }
      setSelected(prev => prev && prev.type === 'edge' ? { ...prev, relType: editRelType } : prev)
    } finally { setSaving(false) }
  }

  async function removeNode() {
    if (!selected || selected.type !== 'node') return
    await api.removeEntity(selected.id)
    cyRef.current?.$(`#${selected.id}`).remove()
    setSelected(null)
  }

  async function removeEdge() {
    if (!selected || selected.type !== 'edge') return
    await api.removeGraphRelationship(selected.source, selected.target, selected.relType)
    const edgeId = `${selected.source}-${selected.relType}-${selected.target}`
    cyRef.current?.$(`#${edgeId}`).remove()
    setSelected(null)
  }

  const hasGraph = (cyRef.current?.elements().length || 0) > 0

  return (
    <div style={p.wrap}>
      <div style={p.searchRow}>
        <input style={p.input} placeholder="Search for an entity to explore its relationships…" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchEntities()} />
        <button style={p.btn} onClick={searchEntities} disabled={loading}>{loading ? '…' : 'Explore'}</button>
      </div>

      {error && <div style={{ color: 'var(--danger)', fontSize: 13 }}>{error}</div>}

      {entityResults.length > 1 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>Multiple matches:</span>
          {entityResults.map((e, i) => (
            <button key={i} onClick={() => loadNeighbourhood(String(e.id))} style={{ padding: '4px 12px', borderRadius: 6, fontSize: 12, background: 'var(--surface2)', color: 'var(--text)', border: '1px solid var(--border)' }}>
              {String(e.label || e.id)}
            </button>
          ))}
        </div>
      )}

      <div style={p.body}>
        <div style={p.canvas}>
          {!hasGraph && !loading && <div style={p.empty}>Search for an entity above to see its relationships</div>}
          <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        </div>

        {selected && (
          <div style={p.panel}>
            {selected.type === 'node' ? (
              <>
                <div style={p.panelTitle}>Edit Entity</div>

                <div>
                  <div style={p.label}>Label</div>
                  <input style={p.fieldInput} value={editLabel} onChange={e => setEditLabel(e.target.value)} />
                </div>

                <div>
                  <div style={p.label}>Class</div>
                  <select style={p.select} value={editClass} onChange={e => setEditClass(e.target.value)}>
                    {CLASSES.filter(c => c !== 'Entity').map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>

                <div>
                  <div style={p.label}>Status</div>
                  <select style={p.select} value={editStatus} onChange={e => setEditStatus(e.target.value)}>
                    <option value="auto_commit">auto_commit</option>
                    <option value="needs_review">needs_review</option>
                    <option value="unresolved">unresolved</option>
                  </select>
                </div>

                <button style={p.saveBtn} onClick={saveNodeEdit} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
                <div style={p.divider} />
                <button style={p.removeBtn} onClick={removeNode}>Remove entity</button>
              </>
            ) : (
              <>
                <div style={p.panelTitle}>Edit Relationship</div>
                <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                  {selected.source} → {selected.target}
                </div>

                <div>
                  <div style={p.label}>Relationship name</div>
                  <input style={p.fieldInput} value={editRelType} onChange={e => setEditRelType(e.target.value)} />
                </div>

                <button style={p.saveBtn} onClick={saveEdgeEdit} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
                <div style={p.divider} />
                <button style={p.removeBtn} onClick={removeEdge}>Remove relationship</button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
