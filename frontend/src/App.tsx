import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from './services/api'
import type { MemoryStats } from './types'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded-lg text-sm transition ${
    isActive
      ? 'bg-cyan-500/20 text-cyan-200 border border-cyan-400/40'
      : 'text-slate-300 hover:text-cyan-200 hover:bg-white/5 border border-transparent'
  }`

export default function App() {
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const navigate = useNavigate()

  const refresh = useCallback(() => {
    api.memoryStats().then(setMemory).catch(() => setMemory(null))
  }, [])

  useEffect(refresh, [refresh])

  const flash = (msg: string) => {
    setNote(msg)
    window.setTimeout(() => setNote(null), 4000)
  }

  const toggleMemory = async () => {
    if (!memory) return
    const next = !memory.enabled
    setBusy(true)
    try {
      await api.toggleMemory(next)
      refresh()
      flash(`Organizational memory ${next ? 'ENABLED' : 'DISABLED'} for this run`)
    } finally {
      setBusy(false)
    }
  }

  const createDemoIncident = async () => {
    setBusy(true)
    try {
      const inc = await api.createIncident({
        service_name: 'payment-api',
        alert_text: 'Payment API is returning HTTP 503 on /v1/charges. Error rate climbing.',
        severity: 'high',
      })
      flash(`Created ${inc.ref}`)
      navigate(`/incidents/${inc.ref}`)
    } finally {
      setBusy(false)
    }
  }

  const demoReset = async () => {
    setBusy(true)
    try {
      await api.demoReset()
      refresh()
      flash('Demo reset — historical incidents only')
    } finally {
      setBusy(false)
    }
  }

  const seedMemory = async () => {
    setBusy(true)
    try {
      const r = await api.demoSeedMemory()
      refresh()
      flash(`Seeded organizational memory: ${r.retained}/${r.total} incidents retained`)
    } catch (e) {
      flash(e instanceof Error ? e.message : 'Seed failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-full flex flex-col">
      <header className="px-6 py-4 flex items-center gap-6 border-b border-cyan-400/10">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-400/40 grid place-items-center text-cyan-300 text-lg">
            🧠
          </div>
          <div>
            <div className="font-semibold tracking-wide glow-text">IncidentMind</div>
            <div className="text-xs text-slate-400">AI incident response with organizational memory</div>
          </div>
        </div>
        <nav className="flex gap-1 ml-4">
          <NavLink to="/" className={navClass} end>Dashboard</NavLink>
          <NavLink to="/memory" className={navClass}>Memory</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          {note && <span className="text-cyan-300 mr-2">{note}</span>}
          <button
            onClick={createDemoIncident}
            disabled={busy}
            className="px-3 py-1.5 rounded-lg bg-cyan-500/25 border border-cyan-400/50 text-cyan-100 hover:bg-cyan-500/35 disabled:opacity-50"
          >
            + Simulate payment 503
          </button>
          <button onClick={demoReset} disabled={busy}
            className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/15 hover:bg-white/10 disabled:opacity-50">
            Reset demo
          </button>
          <button onClick={seedMemory} disabled={busy || memory?.enabled === false}
            className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/15 hover:bg-white/10 disabled:opacity-50">
            Seed memory
          </button>
          <button
            onClick={toggleMemory}
            disabled={busy}
            className={`px-3 py-1.5 rounded-lg border disabled:opacity-50 ${
              memory?.enabled
                ? 'bg-emerald-500/15 border-emerald-400/40 text-emerald-200'
                : 'bg-rose-500/15 border-rose-400/40 text-rose-200'
            }`}
            title="Toggle the memory layer for the A/B demo"
          >
            Memory: {memory?.enabled ? 'ON' : 'OFF'}
          </button>
          <span
            className={`ml-1 text-xs px-2 py-1 rounded-md border ${
              memory?.available
                ? 'text-emerald-300 border-emerald-400/30'
                : 'text-amber-300 border-amber-400/30'
            }`}
            title={memory ? `${memory.bank_id} @ hindsight` : ''}
          >
            {memory?.available ? 'Hindsight live' : 'Hindsight offline'}
          </span>
        </div>
      </header>
      <main className="flex-1 px-6 py-5">
        <Outlet />
      </main>
      <footer className="px-6 py-3 text-xs text-slate-500 border-t border-white/5">
        HackWithHyderabad 3.0 · IncidentMind · PostgreSQL = application data · Hindsight = agent memory
      </footer>
    </div>
  )
}
