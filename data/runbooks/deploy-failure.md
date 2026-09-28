# Runbook: Failed Deployment / Crash Loop On Startup

**Trigger:** Deploy fails health checks, pods crash-loop right after rollout

## Immediate checks
1. Startup logs: validation errors mean missing environment config, not bad code. (past: INC-0109)
2. Compare env var diff between the last healthy and the failing deploy.
3. Rollback status: is the previous revision serving?

## Known patterns
- **Missing required env var → startup abort → crash loop**: fix is config, not code.
  Fix: add the variable, re-run deploy; harden validation to fail fast with explicit messages.

## If misconfiguration confirmed
- Rollback is automatic — confirm the previous revision is healthy first.
- Correct the deploy config; add the variable to the deploy template checklist.

## Escalation
- Production deploy blocked > 30 min: page platform-oncall.
