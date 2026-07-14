import React, { useEffect, useRef, useState, useCallback } from 'react'
import cytoscape from 'cytoscape'
import { api } from '../api'

const CLASS_COLORS: Record<string, string> = {
  Product: '#4f9cf9', Customer: '#34d399', Order: '#fbbf24',
  Warehouse: '#f87171', Supplier: '#a78bfa', Shipment: '#fb923c',
  MaintenanceIncident: '#e879f9', Entity: '#64748b',
}

type SelectedClass = { type: 'class'; name: string; description: string; source_hints: string[] }
type SelectedRel = { type: 'rel'; from_class: string; to_class: string; name: string; edgeId: string }
type Selected = SelectedClass | SelectedRel | null

const p: Record<string, React.CSSProperties> = {
  wrap: { display: 'flex', height: '100%', gap: 16 },
  canvas: { flex: 1, background: 'var(--surface2)', borderRadius: 10, border: '1px solid var(--border)', position: 'relative' as const },
  toolbar: { position: 'absolute' as const, top: 12, right: 12, display: 'flex', gap: 6 },
  toolBtn: { padding: '6px 12px', borderRadius: 6, background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 12, cursor: 'pointer' },
  panel: { width: 280, background: 'var(--surface)', borderRadius: 10, padding: 16, border: '1px solid var(--border)', flexShrink: 0, overflowY: 'auto' as const, display: 'flex', flexDirection: 'column', gap: 12 },
  panelTitle: { fontWeight: 700, fontSize: 13, color: 'var(--accent)' },
  label: { fontSize: 11, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.8, marginBottom: 4 },
  fieldInput: { width: '100%', padding: '7px 10px', borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13, outline: 'none', boxSizing: 'border-box' as const },
  textarea: { width: '100%', padding: '7px 10px', borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13, outline: 'none', resize: 'vertical' as const, minHeight: 60, boxSizing: 'border-box' as const },
  select: { width: '100%', padding: '7px 10px', borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 13, outline: 'none' },
  saveBtn: { padding: '8px 0', borderRadius: 6, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13, width: '100%' },
  removeBtn: { padding: '8px 0', borderRadius: 6, background: 'var(--surface2)', color: 'var(--danger)', fontWeight: 600, fontSize: 13, width: '100%', border: '1px solid var(--danger)' },
  divider: { height: 1, background: 'var(--border)', margin: '4px 0' },
  hint: { fontSize: 11, color: 'var(--muted)', marginTop: 4 },
}

type GraphData = { nodes: { data: Record<string, unknown> }[]; edges: { data: Record<string, unknown> }[] }

export default function OntologyGraph() {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] })
  const [selected, setSelected] = useState<Selected>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // edit state for class
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editHints, setEditHints] = useState('')

  // edit state for relationship
  const [editRelName, setEditRelName] = useState('')

  // add relationship form
  const [showAddRel, setShowAddRel] = useState(false)
  const [addRelFrom, setAddRelFrom] = useState('')
  const [addRelTo, setAddRelTo] = useState('')
  const [addRelName, setAddRelName] = useState('')

  // add class form
  const [showAddClass, setShowAddClass] = useState(false)
  const [addClassName, setAddClassName] = useState('')
  const [addClassDesc, setAddClassDesc] = useState('')

  const classNames = graphData.nodes.map(n => String(n.data.id))

  const buildCy = useCallback((data: GraphData) => {
    if (!containerRef.current) return
    cyRef.current?.destroy()
    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...data.nodes.map(n => ({ data: n.data, classes: 'class-node' })),
        ...data.edges.map(e => ({ data: e.data, classes: 'rel-edge' })),
      ],
      style: [
        {
          selector: 'node.class-node',
          style: {
            'background-color': (el: cytoscape.NodeSingular) => CLASS_COLORS[el.data('label')] || '#4f9cf9',
            'label': 'data(label)', 'color': '#fff', 'font-size': '13px', 'font-weight': 'bold',
            'text-valign': 'center', 'text-halign': 'center', 'width': 130, 'height': 42, 'shape': 'round-rectangle',
          } as cytoscape.Css.Node,
        },
        { selector: 'node.class-node:selected', style: { 'border-width': 3, 'border-color': '#fff' } as cytoscape.Css.Node },
        {
          selector: 'edge.rel-edge',
          style: {
            'width': 2, 'line-color': '#2e3450', 'target-arrow-color': '#2e3450',
            'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
            'label': 'data(label)', 'font-size': '10px', 'color': '#8892a4',
            'text-background-color': '#0f1117', 'text-background-opacity': 1, 'text-background-padding': '2px',
          } as cytoscape.Css.Edge,
        },
        { selector: 'edge.rel-edge:selected', style: { 'line-color': 'var(--accent)', 'target-arrow-color': 'var(--accent)' } as cytoscape.Css.Edge },
      ],
      layout: { name: 'cose', padding: 40, nodeRepulsion: () => 8000, idealEdgeLength: () => 140, animate: false } as cytoscape.CoseLayoutOptions,
      userZoomingEnabled: true, userPanningEnabled: true,
    })

    cy.on('tap', 'node', evt => {
      const n = evt.target
      const sel: SelectedClass = { type: 'class', name: n.data('label'), description: n.data('description') || '', source_hints: n.data('source_hints') || [] }
      setSelected(sel); setEditName(sel.name); setEditDesc(sel.description); setEditHints((sel.source_hints || []).join(', '))
      setShowAddRel(false); setShowAddClass(false)
    })

    cy.on('tap', 'edge', evt => {
      const e = evt.target
      const sel: SelectedRel = { type: 'rel', from_class: e.data('source'), to_class: e.data('target'), name: e.data('label'), edgeId: e.data('id') }
      setSelected(sel); setEditRelName(sel.name)
      setShowAddRel(false); setShowAddClass(false)
    })

    cy.on('tap', evt => { if (evt.target === cy) setSelected(null) })
    cyRef.current = cy
  }, [])

  async function loadGraph() {
    setLoading(true)
    try {
      const data = await api.ontologyGraph()
      setGraphData(data)
      buildCy(data)
    } finally { setLoading(false) }
  }

  useEffect(() => { loadGraph(); return () => { cyRef.current?.destroy() } }, [])

  async function saveClassEdit() {
    if (!selected || selected.type !== 'class') return
    setSaving(true)
    try {
      await api.updateOntologyClass(selected.name, { new_name: editName, description: editDesc, source_hints: editHints.split(',').map(s => s.trim()).filter(Boolean) })
      await loadGraph()
      setSelected(null)
    } finally { setSaving(false) }
  }

  async function removeClass() {
    if (!selected || selected.type !== 'class') return
    await api.removeOntologyClass(selected.name)
    await loadGraph(); setSelected(null)
  }

  async function saveRelEdit() {
    if (!selected || selected.type !== 'rel') return
    setSaving(true)
    try {
      await api.updateOntologyRelationship(selected.from_class, selected.to_class, selected.name, editRelName)
      await loadGraph(); setSelected(null)
    } finally { setSaving(false) }
  }

  async function removeRel() {
    if (!selected || selected.type !== 'rel') return
    await api.removeOntologyRelationship(selected.from_class, selected.to_class, selected.name)
    await loadGraph(); setSelected(null)
  }

  async function addRelationship() {
    if (!addRelFrom || !addRelTo || !addRelName) return
    await api.addOntologyRelationship(addRelFrom, addRelTo, addRelName, '')
    setShowAddRel(false); setAddRelFrom(''); setAddRelTo(''); setAddRelName('')
    await loadGraph()
  }

  async function addClass() {
    if (!addClassName) return
    await api.addOntologyClass(addClassName, addClassDesc, [])
    setShowAddClass(false); setAddClassName(''); setAddClassDesc('')
    await loadGraph()
  }

  return (
    <div style={p.wrap}>
      <div style={p.canvas}>
        {loading && <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 13 }}>Loading ontology…</div>}
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        <div style={p.toolbar}>
          <button style={p.toolBtn} onClick={() => { setShowAddClass(true); setShowAddRel(false); setSelected(null) }}>+ Class</button>
          <button style={p.toolBtn} onClick={() => { setShowAddRel(true); setShowAddClass(false); setSelected(null) }}>+ Relationship</button>
        </div>
      </div>

      <div style={p.panel}>
        {/* Add class form */}
        {showAddClass && (
          <>
            <div style={p.panelTitle}>Add Class</div>
            <div><div style={p.label}>Name</div><input style={p.fieldInput} value={addClassName} onChange={e => setAddClassName(e.target.value)} placeholder="e.g. Invoice" /></div>
            <div><div style={p.label}>Description</div><textarea style={p.textarea} value={addClassDesc} onChange={e => setAddClassDesc(e.target.value)} /></div>
            <button style={p.saveBtn} onClick={addClass}>Add Class</button>
            <button style={{ ...p.removeBtn, color: 'var(--muted)', border: '1px solid var(--border)' }} onClick={() => setShowAddClass(false)}>Cancel</button>
          </>
        )}

        {/* Add relationship form */}
        {showAddRel && (
          <>
            <div style={p.panelTitle}>Add Relationship</div>
            <div><div style={p.label}>From class</div>
              <select style={p.select} value={addRelFrom} onChange={e => setAddRelFrom(e.target.value)}>
                <option value="">Select…</option>
                {classNames.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div><div style={p.label}>Relationship name</div><input style={p.fieldInput} value={addRelName} onChange={e => setAddRelName(e.target.value)} placeholder="e.g. INVOICED_BY" /></div>
            <div><div style={p.label}>To class</div>
              <select style={p.select} value={addRelTo} onChange={e => setAddRelTo(e.target.value)}>
                <option value="">Select…</option>
                {classNames.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <button style={p.saveBtn} onClick={addRelationship}>Add Relationship</button>
            <button style={{ ...p.removeBtn, color: 'var(--muted)', border: '1px solid var(--border)' }} onClick={() => setShowAddRel(false)}>Cancel</button>
          </>
        )}

        {/* Class edit */}
        {selected?.type === 'class' && !showAddClass && !showAddRel && (
          <>
            <div style={p.panelTitle}>Edit Class</div>
            <div><div style={p.label}>Name</div><input style={p.fieldInput} value={editName} onChange={e => setEditName(e.target.value)} /></div>
            <div><div style={p.label}>Description</div><textarea style={p.textarea} value={editDesc} onChange={e => setEditDesc(e.target.value)} /></div>
            <div>
              <div style={p.label}>Source hints</div>
              <input style={p.fieldInput} value={editHints} onChange={e => setEditHints(e.target.value)} placeholder="product_id, sku_code, product_sku" />
              <div style={p.hint}>Comma-separated column or table names that map to this class</div>
            </div>
            <button style={p.saveBtn} onClick={saveClassEdit} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
            <div style={p.divider} />
            <button style={p.removeBtn} onClick={removeClass}>Remove class</button>
          </>
        )}

        {/* Relationship edit */}
        {selected?.type === 'rel' && !showAddClass && !showAddRel && (
          <>
            <div style={p.panelTitle}>Edit Relationship</div>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{selected.from_class} → {selected.to_class}</div>
            <div><div style={p.label}>Relationship name</div><input style={p.fieldInput} value={editRelName} onChange={e => setEditRelName(e.target.value)} /></div>
            <button style={p.saveBtn} onClick={saveRelEdit} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
            <div style={p.divider} />
            <button style={p.removeBtn} onClick={removeRel}>Remove relationship</button>
          </>
        )}

        {/* Default hint */}
        {!selected && !showAddClass && !showAddRel && (
          <div style={{ color: 'var(--muted)', fontSize: 13, lineHeight: 1.6 }}>
            Click any class or relationship to edit it.<br /><br />
            Use the buttons above to add a new class or relationship.
          </div>
        )}
      </div>
    </div>
  )
}
