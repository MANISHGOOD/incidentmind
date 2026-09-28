# Runbook: Orders Service Database Errors

**Service:** orders-service · **Trigger:** HTTP 500, DB timeouts, connection errors

## Immediate checks
1. `pg_stat_activity` on orders primary: connection count vs `max_connections`.
2. Recent deploys: ORM/pool config changes are the usual culprit (past: INC-0102).
3. Long-running queries from `analytics` roles on the primary (past: INC-0113).

## Known patterns
- **Postgres connection exhaustion**: `too many clients already` + pool in_use=max.
  Fix: revert pool config, enable pgbouncer transaction pooling.
- **Analytics query storm** (overnight hours): CPU saturation + long aggregate queries.
  Fix: move analytics roles to the read replica with a `statement_timeout`.

## If connection exhaustion confirmed
- Revert offending deploy config.
- Verify pgbouncer pooling is active for the service.
- Add alerting on `max_connections` at 80%.

## Escalation
- DBA oncall if primary needs restart; customer comms if checkout flow impacted.
