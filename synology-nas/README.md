# synology-nas

Full, authenticated control of a Synology DiskStation over the DSM Web API,
from Claude Code. Built and tested against **nas-host**, a **DS1817+**
running **DSM 7.x**.

## What's inside

- **MCP server** (`mcp/synology_server.py`) — authenticates to DSM (session id +
  CSRF token, auto re-login) and exposes:
  - **Generic passthrough** (`synology_call`, `synology_batch`, `synology_list_apis`,
    `synology_describe_api`) reaching **all ~870 SYNO.\* APIs** on the box.
  - **69 curated tools** for system health, logs, storage, snapshots, File Station,
    Download Station, Container Manager (containers/images/Compose projects),
    packages, services, users, groups, shares & permissions, firewall (status + rules)
    & auto-block, certificates, UPS, DSM updates, Hyper Backup / Active Backup, and power.
- **Skill** (`skills/synology-control/`) — teaches Claude how to drive the server,
  with a full categorized **API map** of this NAS, verified **task recipes**, and the
  **auth/conventions** reference.
- **Commands** (`commands/`) — `/syno-health`, `/syno-storage`, `/syno-downloads`,
  `/syno-find-large`, `/syno-containers`.
- **Smoke test** (`mcp/_smoketest.py`) — runs every curated read-only tool against
  the live NAS (`uv run --script mcp/_smoketest.py`); exits cleanly if no
  `config.local.json` is present.

## Setup

1. **Credentials.** Copy `config.example.json` → `config.local.json` and fill in your
   NAS host, port, username, and password. `config.local.json` is git-ignored so your
   password is never committed. Any field can instead be set via environment variables
   (`SYNOLOGY_HOST`, `SYNOLOGY_PORT`, `SYNOLOGY_HTTPS`, `SYNOLOGY_USERNAME`,
   `SYNOLOGY_PASSWORD`, `SYNOLOGY_OTP_CODE`, `SYNOLOGY_VERIFY_SSL`), which override the
   file.
2. **Runtime.** The MCP server launches via [`uv`](https://docs.astral.sh/uv/)
   (`uv run --script`), which auto-provisions its dependencies (`mcp`, `httpx`) in a
   cached environment — no manual `pip install` needed. `uv` must be on PATH.
3. **Load the plugin** in Claude Code (`/plugin marketplace add <this repo>` →
   `/plugin install synology-nas@gh-tools`), then run `/reload-plugins` or restart.
   Ask Claude to "check the NAS" or run `/syno-health`.

## Security notes

- The password lives only in `config.local.json` (git-ignored) or your environment.
- HTTPS to a LAN NAS uses a self-signed cert, so certificate verification is off by
  default (`verify_ssl: false`). Set it true if you've installed a trusted cert.
- Destructive/disruptive tools (`synology_reboot`, `synology_shutdown`,
  `synology_fs_delete`, container/image/project stop & delete, package stop &
  uninstall, DSM update apply, share/user/group writes, firewall toggle, download
  task deletion) all require `confirm=True`. The skill instructs Claude to confirm
  any write/disruptive action with you first.

## Coverage notes (this DSM)

- **Container Manager** `SYNO.Docker.*` is available only while the ContainerManager
  package is running (its APIs register only then). Curated container/image/Compose
  tools are included; if they return 102, start the package with
  `synology_package_control(package_id="ContainerManager", action="start")`.
- **Virtual Machine Manager** APIs are present but require per-user VMM privileges
  (and a Pro license for full API control) before calls succeed.

See `skills/synology-control/references/` for the full API map and details.
