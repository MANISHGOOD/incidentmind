# Runbook: API Gateway 504 / 429

**Service:** api-gateway · **Trigger:** Elevated 504 or 429 at the edge

## Immediate checks
1. Is the 504 gateway-wide or route-specific? Route-specific → that upstream is slow.
2. Compare upstream p99 vs gateway deadline (30s). Past incident: INC-0104.
3. For 429s: which customers? One customer + normal traffic = limiter misconfig, not attack (past: INC-0110).

## Known patterns
- **Slow upstream → 504**: search-service near the 30s deadline. Fix at the upstream, raise timeout only as interim.
- **Per-IP limiter vs NAT'd customer → 429**: shared_ips count high. Fix: switch to per-API-key for paid tiers.

## If slow upstream confirmed
- Identify the slowest upstream from gateway metrics.
- Raise route timeout as interim headroom (max 45s) while the upstream team mitigates.

## Escalation
- Edge-wide impact: page platform-oncall and open a status-page incident.
