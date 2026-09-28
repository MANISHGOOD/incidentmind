import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import type { DemoState, Incident, MemoryStats, Metrics, Stats } from '../types'

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="panel p-4">
      <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
      <div className="text-3xl font-semibold text-cyan-200 mt-1 glow-text">{value}</div>
      {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
    </div>
  )
}

const sevColor: Record<string, string> = {
  critical: 'text-rose-300 border-rose-400/40 bg-rose-500/10',
  high: 'text-amber-300 border-amber-400/40 bg-amber-500/10',
  medium: 'text-sky-300 border-sky-400/40 bg-sky-500/10',
  low: 'text-slate-300 border-slate-400/30 bg-white/5',
}
const statusColor: Record<string, string> = {
  investigating: 'text-fuchsia-300 border-fuchsia-400/40 bg-fuchsia-500/10',
  resolved: 'text-emerald-300 border-emerald-400/40 bg-emerald-500/10',
}

export default function Dashboard() {
  const [overview, setOverview] = useState({ active_incidents: 0, resolved_incidents: 0 })
  const [stats, setStats] = useState<Stats | null>(null)
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [demo, setDemo] = useState<DemoState | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])

  const refresh = useCallback(() => {
    api.overview().then(setOverview).catch(() => {})
    api.stats().then(setStats).catch(() => {})
    api.memoryStats().then(setMemory).catch(() => setMemory(null))
    api.metrics().then(setMetrics).catch(() => {})
    api.demoState().then(setDemo).catch(() => {})
    api.listIncidents().then(r => setIncidents(r)).catch(() => setIncidents([]))
  }, [])

  useEffect(() => {
    refresh()
    const t = window.setInterval(refresh, 10000)
    return () => window.clearInterval(t)
  }, [refresh])

  const wm = metrics?.with_memory.avg_steps
  const wom = metrics?.without_memory.avg_steps
  const improvement = wm != null && wom != null && wom > 0 ? Math.round((1 - wm / wom) * 100) : null

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Active incidents" value={overview.active_incidents} />
        <Stat label="Resolved incidents" value={overview.resolved_incidents} hint="application database" />
        <Stat
          label="Memory entries"
          value={stats?.memory_entries ?? memory?.entries ?? '—'}
          hint={memory?.available ? `Hindsight bank: ${memory.bank_id}` : 'Hindsight offline'}
        />
        <Stat
          label="Known patterns"
          value={stats?.known_patterns ?? '—'}
          hint={stats ? `${stats.services} services · ${stats.runbooks} runbooks` : undefined}
        />
      </div>

      {stats && (
        <div className="panel p-4 text-xs text-slate-400 flex flex-wrap gap-x-6 gap-y-1">
          <span><span className="text-cyan-300">{stats.total_incidents}</span> total incidents</span>
          <span><span className="text-cyan-300">{stats.resolved_incidents}</span> resolved</span>
          <span><span className="text-cyan-300">{stats.runbooks}</span> runbooks</span>
          <span>synthetic demo dataset — not real company data</span>
        </div>
      )}

      {metrics && (
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium text-cyan-100">Measured investigation effort</h2>
            <span className="text-xs text-slate-500">{metrics.retention.note}</span>
          </div>
          <div className="grid md:grid-cols-3 gap-4 text-sm">
            <div className="rounded-lg border border-rose-400/20 bg-rose-500/5 p-4">
              <div className="text-rose-300 font-medium mb-1">Without memory</div>
              <div className="text-2xl font-semibold">{metrics.without_memory.avg_steps ?? '—'} <span className="text-sm text-slate-400">steps</span></div>
              <div className="text-xs text-slate-500 mt-1">{metrics.without_memory.runs} run(s)</div>
            </div>
            <div className="rounded-lg border border-emerald-400/20 bg-emerald-500/5 p-4">
              <div className="text-emerald-300 font-medium mb-1">With organizational memory</div>
              <div className="text-2xl font-semibold">{metrics.with_memory.avg_steps ?? '—'} <span className="text-sm text-slate-400">steps</span></div>
              <div className="text-xs text-slate-500 mt-1">{metrics.with_memory.runs} run(s)</div>
            </div>
            <div className="rounded-lg border border-cyan-400/20 bg-cyan-500/5 p-4">
              <div className="text-cyan-300 font-medium mb-1">Effect</div>
              <div className="text-2xl font-semibold">
                {improvement != null ? `${improvement}%` : '—'} <span className="text-sm text-slate-400">fewer steps</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">paired A/B runs on the same alert</div>
            </div>
          </div>
        </div>
      )}

      <div className="panel p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium text-cyan-100">Incidents</h2>
          {demo && (
            <span className="text-xs text-slate-500">
              {demo.historical_incidents} historical · {demo.live_incidents} live (demo)
            </span>
          )}
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-white/10">
              <th className="py-2 pr-3">Ref</th>
              <th className="py-2 pr-3">Title</th>
              <th className="py-2 pr-3">Service</th>
              <th className="py-2 pr-3">Severity</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 pr-3">Memory</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map(inc => (
              <tr key={inc.ref} className="border-b border-white/5 hover:bg-white/5">
                <td className="py-2 pr-3 font-mono text-xs text-cyan-300">
                  <Link to={`/incidents/${inc.ref}`}>{inc.ref}</Link>
                </td>
                <td className="py-2 pr-3 max-w-md truncate">
                  <Link to={`/incidents/${inc.ref}`} className="hover:text-cyan-200">{inc.title}</Link>
                </td>
                <td className="py-2 pr-3 text-slate-300">{inc.service_name}</td>
                <td className="py-2 pr-3">
                  <span className={`text-xs px-2 py-0.5 rounded border ${sevColor[inc.severity] ?? sevColor.low}`}>
                    {inc.severity}
                  </span>
                </td>
                <td className="py-2 pr-3">
                  <span className={`text-xs px-2 py-0.5 rounded border ${statusColor[inc.status] ?? ''}`}>
                    {inc.status}
                  </span>
                </td>
                <td className="py-2 pr-3 text-xs text-slate-400">
                  {inc.memory_used ? 'used' : inc.status === 'resolved' ? '—' : ''}
                </td>
              </tr>
            ))}
            {incidents.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-slate-500">No incidents yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
