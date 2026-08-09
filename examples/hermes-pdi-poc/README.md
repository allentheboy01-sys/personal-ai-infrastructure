# Hermes PDI PoC Example

This directory contains the sanitized minimum configuration used to reproduce
the Jarvis Runtime Integration V0.1 validation with Hermes as a Reference
Runtime. Hermes is replaceable; PDI does not depend on it.

## Files

- `config.example.yaml` limits Hermes to the three read-only PDI MCP tools.
- `SOUL.example.md` supplies the minimal retrieval and time-semantics guidance.

## Prerequisites

- A working PDI checkout and its existing virtual environment.
- A PostgreSQL database already managed by PDI.
- A separate Hermes Agent 0.10.0 environment.
- A tool-calling model. The example shows the provider used by the validated
  PoC, but the model and provider are not frozen.

Do not install Hermes in the PDI virtual environment and do not change PDI's MCP
version to match Hermes.

## Configure

1. Create an isolated Hermes profile.
2. Copy `config.example.yaml` to that profile as `config.yaml`.
3. Copy `SOUL.example.md` to that profile as `SOUL.md`.
4. Replace `<PDI_PYTHON>` with the absolute path to PDI's virtual-environment
   Python executable, for example `<PDI_REPO>/.venv/bin/python`.
5. Export `DATABASE__URL` and the model provider's API-key environment variable
   in the launching process. Do not add their values to this template or commit
   them to the repository.

The PDI MCP process must be launched from `<PDI_REPO>` because the validated
Hermes stdio configuration inherits its working directory from the Hermes
process:

```bash
cd <PDI_REPO>
hermes -p <PROFILE> chat
```

The resulting stdio command is:

```text
<PDI_PYTHON> -m pdi_mcp
```

## Verify the Tool surface

Before chatting, verify the configured server:

```bash
hermes -p <PROFILE> mcp list
hermes -p <PROFILE> mcp test pdi
```

The only selected PDI tools must be:

```text
pdi_list_recent_resources
pdi_search_resources
pdi_get_resource
```

MCP Resources and Prompts wrappers remain disabled. Do not connect additional
MCP servers or enable filesystem, browser, memory, scheduler, or write tools for
this minimal reproduction.
