const BASE = '/api'

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export type OrgSummary = { id: string; name: string; apps: { id: string; name: string }[] }
export type OrgSources = {
  connectors: { name: string; enabled: boolean; supported: boolean }[]
  schema_files: { name: string; path: string; folder: string }[]
  documents: { name: string; path: string; folder: string }[]
}
export type GraphData = {
  nodes: { data: { id: string; label: string; [k: string]: unknown } }[]
  edges: { data: { source: string; target: string; label: string; [k: string]: unknown } }[]
}

export const api = {
  // orgs
  orgs: () => req<OrgSummary[]>('GET', '/orgs'),
  orgSources: (orgId: string) => req<OrgSources>('GET', `/orgs/${orgId}/sources`),

  // health
  health: () => req<{ neo4j: boolean; langsmith: boolean }>('GET', '/health'),

  // ontology
  ontologyGraph: () => req<GraphData>('GET', '/ontology/graph'),

  // ingest
  ingest: (sources: string[], schema_file_paths: string[], doc_file_paths: string[]) =>
    req<{ status: string }>('POST', '/ingest', { sources, schema_file_paths, doc_file_paths }),
  ingestStatus: () => req<Record<string, unknown>>('GET', '/ingest/status'),

  // entities
  entities: (status?: string) =>
    req<Record<string, unknown>[]>('GET', `/entities${status ? `?status=${status}` : ''}`),

  // graph
  graphSummary: () => req<{ summary: string }>('GET', '/graph/summary'),
  neighbourhood: (canonicalId: string) =>
    req<GraphData & { centre: string }>('GET', `/retrieve/neighbourhood/${encodeURIComponent(canonicalId)}`),

  // entity editing
  updateEntity: (id: string, fields: { canonical_label?: string; class_name?: string; status?: string }) =>
    req<{ ok: boolean }>('PATCH', `/entities/${encodeURIComponent(id)}`, fields),
  removeEntity: (id: string) =>
    req<{ ok: boolean }>('DELETE', `/entities/${encodeURIComponent(id)}`),
  approveEntity: (id: string) =>
    req<{ ok: boolean }>('POST', `/entities/${encodeURIComponent(id)}/approve`),
  rejectEntity: (id: string) =>
    req<{ ok: boolean }>('POST', `/entities/${encodeURIComponent(id)}/reject`),
  splitEntity: (id: string, entity_a: Record<string, unknown>, entity_b: Record<string, unknown>) =>
    req<{ ok: boolean }>('POST', `/entities/${encodeURIComponent(id)}/split`, { entity_a, entity_b }),
  updateGraphRelationship: (source_id: string, target_id: string, rel_type: string, new_type: string) =>
    req<{ ok: boolean }>('PATCH', '/graph/relationship', { source_id, target_id, rel_type, new_type }),
  removeGraphRelationship: (source_id: string, target_id: string, rel_type: string) =>
    req<{ ok: boolean }>('DELETE', '/graph/relationship', { source_id, target_id, rel_type }),

  // ontology editing
  updateOntologyClass: (name: string, fields: { new_name?: string; description?: string; source_hints?: string[] }) =>
    req<{ ok: boolean }>('PATCH', `/ontology/classes/${encodeURIComponent(name)}`, fields),
  removeOntologyClass: (name: string) =>
    req<{ ok: boolean }>('DELETE', `/ontology/classes/${encodeURIComponent(name)}`),
  addOntologyClass: (name: string, description: string, source_hints: string[]) =>
    req<{ ok: boolean }>('POST', '/ontology/classes', { name, description, source_hints }),
  updateOntologyRelationship: (from_class: string, to_class: string, name: string, new_name: string) =>
    req<{ ok: boolean }>('PATCH', '/ontology/relationships', { from_class, to_class, name, new_name }),
  removeOntologyRelationship: (from_class: string, to_class: string, name: string) =>
    req<{ ok: boolean }>('DELETE', '/ontology/relationships', { from_class, to_class, name }),
  addOntologyRelationship: (from_class: string, to_class: string, name: string, description: string) =>
    req<{ ok: boolean }>('POST', '/ontology/relationships', { from_class, to_class, name, description }),

  // retrieval
  investigate: (question: string) =>
    req<{ answer: string; sources: unknown[]; entities_used: string[] }>('POST', '/retrieve/investigate', { question }),
  searchEntities: (question: string) =>
    req<Record<string, unknown>[]>('POST', '/retrieve/search/entities', { question }),
  cypher: (question: string) =>
    req<{ cypher: string; explanation: string; rows: unknown[]; error?: string }>('POST', '/retrieve/cypher', { question }),
  describeEntity: (canonical_id: string) =>
    req<{ description: string }>('POST', '/retrieve/describe/entity', { canonical_id }),
}
