# Runbook: Kafka Consumer Lag (notification-service)

**Service:** notification-service · **Trigger:** Consumer lag growing, delayed notifications

## Immediate checks
1. Retry topic depth: is the retry queue growing faster than the main topic? (past: INC-0106)
2. Upstream provider status: 429/503 from email/SMS providers. (past: INC-0114)
3. Consumer throughput vs message arrival rate.

## Known patterns
- **Provider outage + requeue-without-backoff → retry storm**: lag grows linearly.
  Fix: exponential backoff + DLQ; never restart consumers mid-storm.
- **Campaign volume > provider rate limit**: 429s from provider, queue growth.
  Fix: adaptive throttling, separate transactional vs marketing accounts.

## If retry storm confirmed
- Deploy backoff config first, then let the backlog drain naturally.
- Do NOT scale consumers: it multiplies provider load.

## Escalation
- Customer-visible OTP/login email delay > 10 min: page notification-oncall.
