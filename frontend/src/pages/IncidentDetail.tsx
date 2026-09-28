import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../services/api'
import { useInvestigation } from '../hooks/useInvestigation'
import type { Incident, LogLine, Resolution } from '../types'

const kindIcon: Record<string, string> = {
  status: '⏳',
  step: '🔧',
  memory: '🧠',
  recommendation: '✅',
  error: '⚠️',
  done: '🏁',
}

const confColor: Record<string, string> = {
  high: 'text-emerald-300 border-emerald-400/40 bg-emerald-500/10',
  medium: 'text-amber-300 border-amber-400/40 bg-amber-500/10',
  low: 'text-rose-300 border-rose-400/40 bg-rose-500/10',
}

export default function IncidentDetail() {
  const { ref = '' } = useParams()
  const [incident, setIncident] = useState<Incident | null>(null)
  const [logs, setLogs] = useState<LogLine[]>([])
  const { run, running, error, timeline, recommendation } = useInvestigation(ref)

  const [rootCause, setRootCause] = useState('')
  const [actionTaken, setActionTaken] = useState('')
  const [lessons, setLessons] = useState('')
  const [resolveNote, setResolveNote] = useState<string | null>(null)

  const refresh = useCallback(() => {
    api.getIncident(ref).then(inc => {
      setIncident(inc)
      if (inc.root_cause) setRootCause(prev => prev || inc.root_cause!)
    }).catch(() => setIncident(null))
    api.incidentLogs(ref).then(r => setLogs(r.lines)).catch(() => setLogs([]))
  }, [ref])

  useEffect(refresh, [refresh])

  if (!incident) {
    return <div className="panel p-6 text-slate-400">Incident {ref} not found. <Link to="/" className="text-cyan-300">Back to dashboard</Link></div>
  }

  const doResolve = async () => {
    if (!rootCause.trim() || !actionTaken.trim()) return
    const r = await api.resolveIncident(ref, {
      root_cause: rootCause.trim(),
      action_taken: actionTaken.trim(),
      lessons: lessons.split(',').map(s => s.trim()).filter(Boolean),
    })
    setResolveNote(r.memory_retained
      ? 'Resolved ✔ Retained to organizational memory — future incidents will benefit.'
      : 'Resolved ✔ (memory offline — not retained)')
    refresh()
  }

  const res: Resolution | undefined = incident.resolutions?.[incident.resolutions.length - 1]

  let symptoms: string[] = []
  try {
    symptoms = incident.symptoms ? JSON.parse(incident.symptoms) : []
  } catch {
    symptoms = incident.symptoms ? [incident.symptoms] : []
  }

  let lessonList: string[] = []
  if (res?.lessons) {
    try {
      lessonList = JSON.parse(res.lessons)
    } catch {
      lessonList = []
    }
  }

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      {/* Left: incident + live investigation */}
      <div className="space-y-6">
        <div className="panel p-5">
          <div className="flex items-start gap-3">
            <div>
              <div className="font-mono text-xs text-cyan-300">{incident.ref}</div>
              <h1 className="text-lg font-semibold">{incident.title}</h1>
            </div>
            <div className="ml-auto flex gap-2 text-xs">
              <span className="px-2 py-0.5 rounded border border-rose-400/40 bg-rose-500/10 text-rose-300">{incident.severity}</span>
              <span className={`px-2 py-0.5 rounded border ${incident.status === 'resolved' ? 'text-emerald-300 border-emerald-400/40 bg-emerald-500/10' : 'text-fuchsia-300 border-fuchsia-400/40 bg-fuchsia-500/10'}`}>
                {incident.status}
              </span>
              <span className="px-2 py-0.5 rounded border border-white/15 bg-white/5 text-slate-300">{incident.service_name}</span>
            </div>
          </div>
          <p className="text-sm text-slate-300 mt-3">{incident.alert_text}</p>
          {symptoms.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {symptoms.map((s, i) => (
                <span key={i} className="text-xs px-2 py-0.5 rounded-full border border-sky-400/30 bg-sky-500/10 text-sky-200">{s}</span>
              ))}
            </div>
          )}
          <div className="text-xs text-slate-500 mt-2">
            Memory-assisted run: {incident.memory_used ? 'yes' : 'no'} · started {new Date(incident.started_at).toLocaleString()}
          </div>
          <button
            onClick={run}
            disabled={running || incident.status === 'resolved'}
            className="mt-4 px-4 py-2 rounded-lg bg-cyan-500/25 border border-cyan-400/50 text-cyan-100 hover:bg-cyan-500/35 disabled:opacity-40"
          >
            {running ? 'Investigating…' : incident.events?.length ? 'Re-investigate' : 'Investigate with agent'}
          </button>
        </div>

        <div className="panel p-5">
          <h2 className="font-medium text-cyan-100 mb-3">Evidence / logs {logs.length > 0 && <span className="text-xs text-slate-500">({logs.length} lines)</span>}</h2>
          {logs.length > 0 ? (
            <div className="max-h-72 overflow-y-auto rounded-lg bg-black/30 border border-white/10 p-3">
              {logs.map((l, i) => (
                <div key={i} className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
                  <span className={l.level === 'ERROR' ? 'text-rose-400' : l.level === 'WARN' ? 'text-amber-300' : l.level === 'CRITI' ? 'text-rose-300 font-semibold' : 'text-slate-500'}>
                    [{l.level ?? 'LOG'}]
                  </span>{' '}
                  <span className="text-slate-400">{l.line}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-slate-500">No log evidence captured for this incident.</div>
          )}
        </div>

        <div className="panel p-5">
          <h2 className="font-medium text-cyan-100 mb-3">Live investigation timeline</h2>
          {error && <div className="text-sm text-rose-300 mb-2">{error}</div>}
          <ol className="space-y-2 text-sm">
            {timeline.map((t, i) => (
              <li key={i} className={`flex gap-2 ${t.kind === 'memory' ? 'text-cyan-200' : t.kind === 'recommendation' ? 'text-emerald-200' : 'text-slate-300'}`}>
                <span>{kindIcon[t.kind] ?? '•'}</span>
                <span className="font-mono text-[10px] text-slate-500 pt-1">{t.at}</span>
                <span>{t.message}</span>
              </li>
            ))}
            {!running && timeline.length === 0 && (
              <li className="text-slate-500">No live run in this session. Recorded events below are from the database.</li>
            )}
          </ol>
          {incident.events && incident.events.length > 0 && !running && (
            <div className="mt-4 pt-4 border-t border-white/10">
              <div className="text-xs uppercase tracking-wider text-slate-500 mb-2">Recorded events</div>
              <ol className="space-y-1 text-xs text-slate-400">
                {incident.events.map(e => (
                  <li key={e.seq}>
                    <span className="font-mono text-slate-500">#{e.seq}</span>{' '}
                    <span className="text-slate-300">{e.kind}</span>
                    {e.tool_name ? <span className="text-cyan-400/70"> · {e.tool_name}</span> : null}
                    {' — '}{e.summary}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </div>

      {/* Right: recommendation + resolution */}
      <div className="space-y-6">
        {recommendation && (
          <div className="panel p-5 border-emerald-400/30">
            <div className="flex items-center gap-3 mb-3">
              <h2 className="font-medium text-emerald-200">Agent recommendation</h2>
              <span className={`ml-auto text-xs px-2 py-0.5 rounded border ${confColor[recommendation.confidence] ?? ''}`}>
                confidence: {recommendation.confidence}
              </span>
            </div>
            <p className="text-sm text-slate-200">{recommendation.summary}</p>

            {recommendation.likely_root_causes.length > 0 && (
              <div className="mt-4">
                <div className="text-xs uppercase tracking-wider text-slate-500 mb-1">Likely root causes</div>
                <ul className="text-sm space-y-1">
                  {recommendation.likely_root_causes.map((rc, i) => (
                    <li key={i}>
                      <span className={`text-xs px-1.5 py-0.5 mr-2 rounded border ${confColor[rc.confidence] ?? ''}`}>{rc.confidence}</span>
                      {rc.cause}
                      <span className="text-slate-500"> — {rc.evidence}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {recommendation.historical_match && (
              <div className="mt-4 rounded-lg border border-cyan-400/30 bg-cyan-500/5 p-3 text-sm">
                <div className="text-cyan-300 font-medium mb-1">
                  🧠 Historical match: <span className="font-mono">{recommendation.historical_match.ref}</span>
                </div>
                <div className="text-slate-300">{recommendation.historical_match.why_similar}</div>
                <div className="mt-1"><span className="text-slate-500">Past root cause:</span> {recommendation.historical_match.root_cause}</div>
                <div><span className="text-slate-500">Past resolution:</span> {recommendation.historical_match.resolution}</div>
                <div><span className="text-slate-500">Past outcome:</span> {recommendation.historical_match.outcome}</div>
                {recommendation.applies_to_current_evidence && (
                  <div className="mt-2 text-slate-200">
                    <span className="text-cyan-300">Applies to current evidence?</span> {recommendation.applies_to_current_evidence}
                  </div>
                )}
              </div>
            )}

            {recommendation.investigation_steps.length > 0 && (
              <div className="mt-4">
                <div className="text-xs uppercase tracking-wider text-slate-500 mb-1">Suggested investigation path</div>
                <ol className="list-decimal list-inside text-sm text-slate-300 space-y-0.5">
                  {recommendation.investigation_steps.map((s, i) => <li key={i}>{s}</li>)}
                </ol>
              </div>
            )}

            {recommendation.proposed_actions.length > 0 && (
              <div className="mt-4">
                <div className="text-xs uppercase tracking-wider text-slate-500 mb-1">Proposed actions (need engineer approval)</div>
                <ul className="list-disc list-inside text-sm text-slate-300 space-y-0.5">
                  {recommendation.proposed_actions.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="panel p-5">
          <h2 className="font-medium text-cyan-100 mb-3">Engineer resolution</h2>
          {res ? (
            <div className="text-sm space-y-1">
              <div className="text-emerald-300">Resolved ✔</div>
              <div><span className="text-slate-500">Root cause:</span> {res.root_cause}</div>
              <div><span className="text-slate-500">Action taken:</span> {res.action_taken}</div>
              <div><span className="text-slate-500">Outcome:</span> {res.outcome}</div>
              {lessonList.length > 0 && (
                <div className="mt-2">
                  <div className="text-xs uppercase tracking-wider text-slate-500 mb-1">Lessons learned</div>
                  <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                    {lessonList.map((lesson, i) => <li key={i}>{lesson}</li>)}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <textarea value={rootCause} onChange={e => setRootCause(e.target.value)}
                placeholder="Confirmed root cause (pre-filled from the agent's recommendation)"
                className="w-full h-16 rounded-lg bg-white/5 border border-white/15 px-3 py-2 placeholder:text-slate-600" />
              <textarea value={actionTaken} onChange={e => setActionTaken(e.target.value)}
                placeholder="Action taken (e.g. raise pool size, restart workers)"
                className="w-full h-16 rounded-lg bg-white/5 border border-white/15 px-3 py-2 placeholder:text-slate-600" />
              <input value={lessons} onChange={e => setLessons(e.target.value)}
                placeholder="Lessons learned (comma-separated)"
                className="w-full rounded-lg bg-white/5 border border-white/15 px-3 py-2 placeholder:text-slate-600" />
              <button onClick={doResolve}
                className="px-4 py-2 rounded-lg bg-emerald-500/20 border border-emerald-400/50 text-emerald-100 hover:bg-emerald-500/30">
                Resolve &amp; store in memory
              </button>
              {resolveNote && <div className="text-cyan-300 text-xs">{resolveNote}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
