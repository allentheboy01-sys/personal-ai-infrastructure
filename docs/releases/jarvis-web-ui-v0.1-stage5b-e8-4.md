# Jarvis Web UI V0.1 — Stage 5B Gate E.8.4 Cancellation Fix Freeze

Gate E.8.4 supersedes source candidate
`e8125009b49fa723b51599327a9d7075a859f0d0` after real localhost production
validation exposed its only remaining blocker: the synchronous cancellation
response could return a still-running Turn before terminal processing completed.

The frozen `POST /turns/{turn_id}/cancel` contract is
`SYNCHRONOUS_TERMINAL`. A successful cancellation response follows this exact
ordering:

```text
Runtime terminal received
  -> Jarvis DB Turn status persisted as cancelled
  -> ActiveTurnRegistry terminal published
  -> HTTP response returns cancelled
```

Cancelled Turns create no canonical Assistant Message, publish exactly one
`turn.cancelled` event, and remain idempotent under repeated cancellation.
Completion or failure that wins a race remains the single authoritative
terminal outcome.

`TurnCoordinator` now records the existing `_consume` task by exact Turn ID and
awaits that task after `RuntimeAdapter.cancel_turn()`. The task is shielded so
HTTP request cancellation cannot cancel canonical event consumption or terminal
persistence. A matching-task identity check removes the mapping at completion,
preventing stale-task deletion and active-task reference accumulation. The
arbitrary 200 ms polling window is removed.

HermesRuntimeAdapter signaling, bounded escalation, process-group cleanup,
Runtime events, registry behavior, Jarvis state/schema, Exec Sandbox, PDI,
frontend, deployment units, and protected configuration are unchanged.

Deterministic regression covers a terminal delayed beyond 200 ms, synchronous
HTTP terminal response, repeated cancellation, completion/failure races, one
terminal event, no partial Assistant Message, request-cancellation shielding,
and exact consumer-task cleanup. Existing Hermes child/process-group cleanup
tests remain authoritative.

This commit is source and deployment configuration identity only. It does not
build or install production artifacts. A new immutable release and matching
SHA-versioned production venv are required before another Final Gate E attempt;
the e812 artifact must not be reused.
