export interface Incident {
  ref: string
  title: string
  service_name: string
  environment: string
  severity: string
  status: string
  alert_text: string
  symptoms: string
  root_cause: string | null
  memory_used: boolean
  started_at: string
  resolved_at: string | null
  source_ref: string | null
  events?: IncidentEvent[]
  resolutions?: Resolution[]
}

export interface IncidentEvent {
  seq: number
  kind: string
  tool_name: string | null
  summary: string
  detail: string | null
  created_at: string
}

export interface Resolution {
  root_cause: string
  action_taken: string
  outcome: string
  lessons: string | null
  created_at: string
}

export interface Recommendation {
  summary: string
  likely_root_causes: { cause: string; confidence: string; evidence: string }[]
  historical_match: {
    ref: string
    why_similar: string
    root_cause: string
    resolution: string
    outcome: string
  } | null
  applies_to_current_evidence: string | null
  investigation_steps: string[]
  proposed_actions: string[]
  confidence: string
}

export interface MemoryStats {
  enabled: boolean
  bank_id: string
  available: boolean
  entries: number | null
  breakdown?: Record<string, number>
}

export interface Metrics {
  with_memory: { runs: number; avg_steps: number | null; min_steps?: number; max_steps?: number }
  without_memory: { runs: number; avg_steps: number | null; min_steps?: number; max_steps?: number }
  retention: { resolved_incidents_in_db: number; paired_comparisons: number; note: string }
}

export interface Stats {
  total_incidents: number
  active_incidents: number
  resolved_incidents: number
  memory_entries: number | null
  memory_available: boolean
  known_patterns: number
  services: number
  runbooks: number
}

export interface LogLine {
  ts: string | null
  level: string | null
  service: string | null
  line: string
}

export interface DemoState {
  live_incidents: number
  historical_incidents: number
}

export interface Runbook {
  slug: string
  title: string
  service_name: string | null
  content: string
}
