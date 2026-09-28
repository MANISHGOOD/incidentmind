import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { MemoryStats, Runbook } from '../types'

export default function MemoryView() {
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [runbooks, setRunbooks] = useState<Runbook[]>([])

  useEffect(() => {
    api.memoryStats().then(setMemory).catch(() => setMemory(null))
    api.runbooks().then(setRunbooks).catch(() => {})
  }, [])

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="space-y-6">
        <div className="panel p-5">
          <h2 className="font-medium text-cyan-100 mb-3">Organizational memory (Hindsight)</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-xs uppercase tracking-wider text-slate-500">Status</div>
              <div className={memory?.available ? 'text-emerald-300' : 'text-amber-300'}>
                {memory?.available ? 'connected' : 'offline'}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-slate-500">Bank</div>
              <div className="font-mono text-xs text-cyan-300">{memory?.bank_id ?? '—'}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-slate-500">Entries</div>
              <div className="text-2xl font-semibold text-cyan-200">{memory?.entries ?? '—'}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-slate-500">Breakdown</div>
              {memory?.breakdown && Object.keys(memory.breakdown).length > 0 ? (
                <ul className="text-xs text-slate-300">
                  {Object.entries(memory.breakdown).map(([t, n]) => (
                    <li key={t}>{t}: {n}</li>
                  ))}
                </ul>
              ) : (
                <div className="text-xs text-slate-500">seed the memory to populate</div>
              )}
            </div>
          </div>
        </div>

        <div className="panel p-5 text-sm text-slate-300">
          <h2 className="font-medium text-cyan-100 mb-2">What lives in memory</h2>
          <ul className="space-y-2">
            <li><span className="text-cyan-300">Incident memory</span> — service, symptoms, root cause, resolution, outcome per incident.</li>
            <li><span className="text-cyan-300">Investigation memory</span> — what was checked, what worked, what didn't.</li>
            <li><span className="text-cyan-300">Organizational memory</span> — recurring problems, dependencies and remediation patterns, consolidated by Hindsight into observations and mental models.</li>
          </ul>
          <p className="text-xs text-slate-500 mt-3">
            Every engineer-approved resolution is retained back into the bank — the demo closes the learning loop.
          </p>
        </div>
      </div>

      <div className="panel p-5">
        <h2 className="font-medium text-cyan-100 mb-3">Runbooks</h2>
        <div className="space-y-2">
          {runbooks.map(rb => (
            <details key={rb.slug} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
              <summary className="cursor-pointer text-sm text-slate-200">
                {rb.title}
                {rb.service_name && <span className="ml-2 text-xs text-cyan-400/70">{rb.service_name}</span>}
              </summary>
              <pre className="mt-2 text-xs text-slate-400 whitespace-pre-wrap font-sans">{rb.content}</pre>
            </details>
          ))}
          {runbooks.length === 0 && <div className="text-sm text-slate-500">No runbooks loaded.</div>}
        </div>
      </div>
    </div>
  )
}
