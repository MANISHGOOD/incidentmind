# Runbook: Checkout Service OOM / Restart Loops

**Service:** checkout-service · **Trigger:** Pod restarts, OOMKilled, memory near limit

## Immediate checks
1. Memory trend per pod: climbing over hours (leak) vs step change at deploy (bad config).
2. `kubectl describe pod` → last state: `OOMKilled`?
3. Cart cache backend: in-process (risk) vs Redis (safe). Past incidents: INC-0103, INC-0115.

## Known patterns
- **In-process cache leak** (past: INC-0103): heap grows with unique sessions until OOM.
  Fix: move cache to Redis with TTL, rolling restart.
- **Redis failover resets** (past: INC-0115): transient errors ~5 min during promotion.
  Fix: client retry-with-jittered-backoff; do not restart pods.

## If memory leak confirmed
- Roll back to the last known-good build to stop bleeding.
- Profile heap on a canary; look for unbounded maps/caches.
- Ship fix behind a flag; canary before full rollout.

## Escalation
- If checkout is fully down: page checkout-oncall, enable queue-based checkout fallback.
