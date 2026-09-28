# Runbook: Disk / Storage Capacity Exhaustion

**Trigger:** Disk usage alerts on database or service hosts, "No space left on device"

## Immediate checks
1. Which filesystem? Data volume vs log directory (past: INC-0116).
2. Growth rate: user data grows slowly; debug logs grow 10s of GB/day after a release.
3. Recent releases with verbose/debug logging flags.

## Known patterns
- **Log growth from a recent release** (past: INC-0116): fix the logging flag first,
  then truncate/archive logs — resizing alone wastes money and will fill again.

## If log growth confirmed
- Disable the verbose logging flag (deploy).
- Archive + truncate the log directory (do NOT delete open files without truncating).
- Add disk alerts at 70/85/95% if missing.

## If genuine data growth
- Expand the volume, then plan archival/partitioning.

## Escalation
- Database host over 99%: page DBA-oncall immediately; writes may already be failing.
