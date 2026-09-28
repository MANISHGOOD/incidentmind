# Runbook: Inventory Deadlocks / Lock Timeouts

**Service:** inventory-service · **Trigger:** 500s on reservation endpoints, lock wait timeouts

## Immediate checks
1. Correlate error start with sales events or flash sales. (past: INC-0111)
2. Postgres logs: `deadlock detected`, circular waits between SKU rows.
3. Lock ordering consistency in the reservation code path.

## Known patterns
- **Inconsistent row-lock ordering under flash-sale concurrency**: circular waits.
  Fix: enforce consistent SKU lock order + deadlock retry logic.

## If deadlock confirmed
- Do not restart the service mid-sale; retry logic sheds the impact.
- Deploy lock-order fix; load-test the sale flow before the next event.

## Escalation
- Sale-blocking impact > 10 min: page inventory-oncall and commerce lead.
