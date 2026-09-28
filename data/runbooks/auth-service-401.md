# Runbook: Auth Service 401 Spike

**Service:** auth-service · **Trigger:** Auth failure rate far above ~2% baseline

## Immediate checks
1. Log cause: `certificate verify failed` → expired certificate (past: INC-0105).
2. Cert dashboard: `not_after` timestamps for the signing cert and trust bundle.
3. Recent auth-service deploys or key rotations.

## Known patterns
- **Expired signing certificate**: 100% 401s starting exactly on an hour boundary.
  Fix: rotate certificate, roll renewed trust bundle, confirm failure rate recovers.

## If certificate expired
- Rotate immediately (automated rotation should exist — check why it didn't run).
- Roll trust bundle to all instances; monitor auth_failure_rate to baseline.

## Escalation
- All-login outage: page security-oncall together with auth-oncall.
