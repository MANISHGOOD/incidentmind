# Runbook: Search Service Latency Degradation

**Service:** search-service · **Trigger:** Query latency 5–10x baseline, error rate normal

## Immediate checks
1. Elasticsearch cluster health: yellow/red, relocating shards. (past: INC-0108)
2. Recent cluster maintenance: node replacement triggers automatic rebalancing.
3. Gateway timeouts on this route (slow upstream pattern — see gateway runbook).

## Known patterns
- **Shard rebalancing after node replacement**: recovery IO starves query threads.
  Fix: throttle recovery concurrency, finish rebalancing in low-traffic window.

## If rebalancing confirmed
- Throttle recovery, don't cancel it: cancelling restarts the whole process.
- Communicate degraded latency ETA based on remaining relocation %.

## Escalation
- Search down entirely: page search-oncall; gateway timeout change as interim.
