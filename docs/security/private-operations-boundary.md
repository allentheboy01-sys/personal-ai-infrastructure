# Private operations boundary

The public PDI repository defines product architecture, reusable contracts,
parameterized deployment examples, and synthetic validation. It is not the
operations repository for a particular person's server.

## Keep private

The following material belongs in a private operations repository or untracked
local documentation:

- real host inventories, usernames, home directories, and checkout paths;
- tailnet, VPN, proxy, DNS, firewall, and private-port topology;
- production account names and Provider account details;
- credentials, environment files, OAuth state, cookies, and rotation records;
- incident logs or commands containing private infrastructure or user data;
- exact production data counts and deployment-specific commit chronology;
- personal launcher, editor, agent, or authentication setup; and
- Provider-derived content, filenames, checksums, screenshots, or samples from
  a real person's digital life.

Private operational material must never be copied into public issues, prompts,
test fixtures, screenshots, or release reports merely to make a bug easier to
describe.

## Keep public

The following material belongs in this repository:

- PDI architecture and security invariants;
- Provider-independent interfaces and extension guidance;
- parameterized deployment examples with documented variables;
- generic troubleshooting that contains no real infrastructure identifiers;
- synthetic fixtures and reproducible tests;
- public application-service, MCP, and Resource Access contracts; and
- release notes describing product behavior without private operational state.

Deployment examples may choose technologies such as systemd, containers, or a
private network, but those choices must be labelled as examples rather than PDI
Core requirements.
