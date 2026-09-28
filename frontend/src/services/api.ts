import type {
  DemoState, Incident, LogLine, MemoryStats, Metrics, Recommendation, Runbook, Stats,
} from '../types'

// Backend base URL. On Netlify (or any static host) set VITE_API_URL to the
// deployed FastAPI origin, e.g. https://incidentmind-api.fly.dev (no trailing
// slash, no secrets — this value is baked into the public JS bundle).
// Unset → same-origin /api, which works locally through the Vite dev proxy.
const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

function url(path: string): string {
  return `${API_BASE}${path}`
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch { /* keep statusText */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  overview: () =>
    fetch(url('/api/overview')).then(r => handle<{ active_incidents: number; resolved_incidents: number }>(r)),

  listIncidents: (status?: string) =>
    fetch(url(`/api/incidents${status ? `?status=${encodeURIComponent(status)}` : ''}`))
      .then(r => handle<Incident[]>(r)),

  getIncident: (ref: string) =>
    fetch(url(`/api/incidents/${ref}`)).then(r => handle<Incident>(r)),

  createIncident: (body: { service_name: string; alert_text: string; severity?: string }) =>
    fetch(url('/api/incidents'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => handle<Incident>(r)),

  resolveIncident: (ref: string, body: {
    root_cause: string; action_taken: string; outcome?: string; lessons?: string[]
  }) =>
    fetch(url(`/api/incidents/${ref}/resolve`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => handle<{ resolved: boolean; memory_retained: boolean }>(r)),

  runbooks: () => fetch(url('/api/runbooks')).then(r => handle<Runbook[]>(r)),

  memoryStats: () => fetch(url('/api/memory/stats')).then(r => handle<MemoryStats>(r)),

  toggleMemory: (enabled: boolean) =>
    fetch(url('/api/memory/toggle'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }).then(r => handle<{ memory_enabled: boolean }>(r)),

  demoReset: () =>
    fetch(url('/api/demo/reset'), { method: 'POST' }).then(r => handle<unknown>(r)),

  demoSeedMemory: () =>
    fetch(url('/api/demo/seed-memory'), { method: 'POST' }).then(r => handle<{ retained: number; failed: number; total: number }>(r)),

  demoState: () => fetch(url('/api/demo/state')).then(r => handle<DemoState>(r)),

  metrics: () => fetch(url('/api/metrics')).then(r => handle<Metrics>(r)),

  stats: () => fetch(url('/api/stats')).then(r => handle<Stats>(r)),

  incidentLogs: (ref: string) =>
    fetch(url(`/api/incidents/${ref}/logs`)).then(r => handle<{ ref: string; count: number; lines: LogLine[] }>(r)),

  seedDemo: () =>
    fetch(url('/api/seed-demo'), { method: 'POST' })
      .then(r => handle<{ database: { incidents: number; logs: number; runbooks: number }; memory: { retained?: number; failed?: number; total: number; skipped?: boolean } }>(r)),
}

export interface StreamEvent {
  kind: 'status' | 'step' | 'memory' | 'recommendation' | 'error' | 'done'
  message: string
  data?: Record<string, unknown>
}

/** Run an investigation, invoking onEvent for each streamed agent step. */
export async function investigate(ref: string, onEvent: (ev: StreamEvent) => void): Promise<void> {
  const res = await fetch(url(`/api/incidents/${ref}/investigate`), { method: 'POST' })
  if (!res.ok || !res.body) {
    throw new Error(`Investigation failed: ${res.statusText}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of raw.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            onEvent(JSON.parse(line.slice(6)) as StreamEvent)
          } catch { /* skip malformed frame */ }
        }
      }
    }
  }
}

export type { Recommendation }
