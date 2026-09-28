import { useCallback, useRef, useState } from 'react'
import { investigate, type StreamEvent } from '../services/api'
import type { Recommendation } from '../types'

export interface TimelineEntry {
  kind: StreamEvent['kind']
  message: string
  data?: Record<string, unknown>
  at: string
}

export function useInvestigation(ref: string) {
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [timeline, setTimeline] = useState<TimelineEntry[]>([])
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const startRef = useRef<number>(0)

  const run = useCallback(async () => {
    setRunning(true)
    setError(null)
    setTimeline([])
    setRecommendation(null)
    startRef.current = Date.now()
    try {
      await investigate(ref, ev => {
        setTimeline(prev => [...prev, {
          kind: ev.kind, message: ev.message, data: ev.data,
          at: new Date().toLocaleTimeString(),
        }])
        if (ev.kind === 'recommendation' && ev.data) {
          setRecommendation(ev.data as unknown as Recommendation)
        }
        if (ev.kind === 'error') {
          setError(ev.message)
        }
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }, [ref])

  return { run, running, error, timeline, recommendation }
}
