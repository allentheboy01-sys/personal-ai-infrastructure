# Jarvis Web UI V0.1 Stage 5B Gate E.1

Gate E.1 corrects a bounded production sandbox incompatibility without
changing the frozen Jarvis application artifact.

Hermes Agent 0.10.0 always creates `HERMES_HOME/sessions` during `AIAgent`
initialization and configures writes under `HERMES_HOME/logs`, including when
the Jarvis bridge disables session persistence, session DB, trajectories,
memory, and checkpoints. The production unit now retains
`ProtectHome=read-only` while bind-mounting two 0700 systemd
`RuntimeDirectory` paths over only those formal-profile subdirectories.

The runtime state is ephemeral and non-authoritative. It is removed with the
service lifecycle and is never used for Jarvis conversation continuity. The
formal profile configuration, Hermes venv, all other Hermes state, user SSH and
Codex data, project checkouts, Docker socket, and immutable release remain
non-writable or inaccessible.

An actual transient systemd sandbox verified AIAgent initialization, a harmless
general-tool Turn using PrivateTmp, exact denial boundaries, child cleanup,
runtime-state removal, and a subsequent Turn supplied only normalized canonical
history. No production Jarvis service was installed, no port was opened, and no
PDI or Provider writes occurred.

Artifact identity remains split intentionally:

- application release: `6afab42096469699c918f9130739e8324db6ee47`;
- deployment configuration: the commit containing this document.

A separately authorized Gate E retry is required to install and start the
corrected persistent service.
