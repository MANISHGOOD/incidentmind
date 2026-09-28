import type {
  DemoState, Incident, MemoryStats, Metrics, Recommendation, Runbook,
} from '../types'

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
    fetch('/api/overview').then(r => handle<{ active_incidents: number; resolved_incidents: number }>(r)),

  listIncidents: (status?: string) =>
    fetch(`/api/incidents${status ? `?status=${encodeURIComponent(status)}` : ''}`)
      .then(r => handle<Incident[]>(r)),

  getIncident: (ref: string) =>
    fetch(`/api/incidents/${ref}`).then(r => handle<Incident>(r)),

  createIncident: (body: { service_name: string; alert_text: string; severity?: string }) =>
    fetch('/api/incidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => handle<Incident>(r)),

  resolveIncident: (ref: string, body: {
    root_cause: string; action_taken: string; outcome?: string; lessons?: string[]
  }) =>
    fetch(`/api/incidents/${ref}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => handle<{ resolved: boolean; memory_retained: boolean }>(r)),

  runbooks: () => fetch('/api/runbooks').then(r => handle<Runbook[]>(r)),

  memoryStats: () => fetch('/api/memory/stats').then(r => handle<MemoryStats>(r)),

  toggleMemory: (enabled: boolean) =>
    fetch('/api/memory/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }).then(r => handle<{ memory_enabled: boolean }>(r)),

  demoReset: () =>
    fetch('/api/demo/reset', { method: 'POST' }).then(r => handle<unknown>(r)),

  demoSeedMemory: () =>
    fetch('/api/demo/seed-memory', { method: 'POST' }).then(r => handle<{ retained: number; failed: number; total: number }>(r)),

  demoState: () => fetch('/api/demo/state').then(r => handle<DemoState>(r)),

  metrics: () => fetch('/api/metrics').then(r => handle<Metrics>(r)),
}

export interface StreamEvent {
  kind: 'status' | 'step' | 'memory' | 'recommendation' | 'error' | 'done'
  message: string
  data?: Record<string, unknown>
}

/** Run an investigation, invoking onEvent for each streamed agent step. */
export async function investigate(ref: string, onEvent: (ev: StreamEvent) => void): Promise<void> {
  const res = await fetch(`/api/incidents/${ref}/investigate`, { method: 'POST' })
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
