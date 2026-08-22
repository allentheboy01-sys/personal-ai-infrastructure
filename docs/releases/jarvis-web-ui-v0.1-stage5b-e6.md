# Jarvis Web UI V0.1 — Stage 5B Gate E.6 Exec Sandbox Freeze

Gate E.6 freezes Jarvis Exec Sandbox V0.1 after the bounded real-host Gate
E.5.1 validation passed. This commit is an application/deployment candidate;
it does not build or install a production release.

The frozen path is:

```text
Hermes jarvis-web profile
  -> sanitized fixed stdio proxy
  -> /run/jarvis-exec.sock (AF_UNIX)
  -> systemd Accept=yes
  -> one DynamicUser jarvis-exec@ instance per connection
  -> one private 16 MiB tmpfs with a 0700 product workspace
```

The Web profile exposes exactly seven read-only PDI MCP tools and exactly five
Jarvis Exec tools: bounded Python plus write/read/list/delete operations for
workspace-relative text files. Hermes terminal, file, built-in
`code_execution`, web/browser, delegation, memory, Provider write tools, shell,
arbitrary executables, host paths, package installation, network, arbitrary
socket targets, and persistent workspaces are excluded.

The instance uses `DynamicUser=yes`, `PrivateNetwork=yes`, AF_UNIX-only address
families, strict system/home/device protections, empty capabilities, protected
process visibility, control-group cleanup, and bounded memory, swap, CPU,
tasks, runtime, file descriptors, file size, execution time, and output. The
tmpfs is the only useful writable surface and enforces a kernel-level aggregate
16 MiB ceiling underneath protocol accounting. The private child workspace is
mode 0700; `/tmp` and `/var/tmp` are inaccessible.

Real-host validation proved: dynamic identity; kernel quota under direct Python
and child-process writes; no model/PDI/Jarvis secret, private-home, Docker, or
network authority; rejected traversal/symlink escape; no descendant escape;
all resource limits; exact five-tool MCP initialization; a secret-free proxy;
per-connection fresh state; and a real Hermes -> Exec MCP Turn with the exact
registered tool-name set. Cleanup left no temporary unit, socket, process,
workspace, listener, production row, PDI write, or Provider write.

Exec state is non-authoritative and disposable. It creates no Jarvis database
table, PDI Resource, persistent Artifact, or cross-Turn state. Jarvis DB remains
conversation authority and PDI remains personal-world authority. Exec has no
network in V0.1; Internet/Web access is a separate future capability.

The compatibility observations are frozen only for Hermes 0.10.0: local
terminal and `code_execution` are unsafe host execution; Web-specific profiles
are supported; MCP tools are registered as
`mcp_<server>_<canonical_tool>`; a read-only profile needs `cron/`, `memories/`,
and `SOUL.md`; `sessions/` and `logs/` require transient writable state; and
`persist_session=False` does not prevent initial runtime-directory creation.
Hermes runtime state is never authoritative.

A new immutable application release is required. Production Exec and Jarvis
Web services remain uninstalled until the next separately reviewed release and
installation gate.
