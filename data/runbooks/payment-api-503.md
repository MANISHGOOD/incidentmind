# Runbook: Payment API HTTP 503

**Service:** payment-api · **Trigger:** HTTP 503 on `/v1/charges` or similar

## Immediate checks (5 minutes)
1. Check error trend: sudden spike vs gradual climb.
   - Sudden spike → check recent deploys and node drains first.
   - Gradual climb with traffic → suspect resource exhaustion (Redis pool, DB pool, connections).
2. Grep logs for `pool timed out` or `waiting_for_connection`.
3. Check Redis pool metrics: `pool_in_use` vs `pool_size`.

## Known patterns
- **Redis connection pool exhaustion** (past: INC-0101): leaked connections keep `busy=pool_size`;
  fix is leak hotfix + pool size increase + worker restart.
- **Node drain / rescheduling** (past: INC-0112): short burst only, correlates with k8s maintenance;
  fix is PodDisruptionBudget + zone anti-affinity.

## If Redis pool exhaustion confirmed
- Hotfix connection leak (return connection in `finally`).
- Raise pool size (`REDIS_POOL_SIZE`, default was 10 → 50 under load).
- Restart affected workers; verify `pool_in_use` drops.

## Escalation
- If pool metrics look normal, check upstream dependencies and gateway logs.
- Page payments-oncall if customer impact > 15 minutes.
