# Unraid deployment layer — design

Date: 2026-08-11
Plugin: `unraid-control`
Status: approved (build all four layers; live validation on throwaways permitted)

## Context

`unraid-control` today gives full *control* of an existing Unraid box over its
GraphQL API (array, disks, parity, docker/VM lifecycle, shares, settings,
notifications, users) plus a thin SSH layer for container env-var editing. What
it cannot do is *create* things: Unraid's GraphQL API exposes no mutation to
run a new container, define a VM, or install an app. The user wants the plugin
to deploy apps, containers, and VMs and fully configure the box — so this adds
a **deployment layer** built on the same SSH foundation the env-var editor uses.

Verified live on Unraid-Host (Unraid 7.x, docker 29.5.3, key-only SSH as root):

- Docker templates: `/boot/config/plugins/dockerMan/templates-user/my-<Name>.xml`
  (Container XML v2). Unraid marks a container "managed" via container labels
  `net.unraid.docker.managed=dockerman`, `net.unraid.docker.icon=<url>`,
  `net.unraid.docker.webui=<url>`. A container run with these labels + a matching
  template appears and is editable in the Docker tab.
- Compose Manager plugin is **not installed** (installable via `unraid_plugin_install`);
  its convention is `/boot/config/plugins/compose.manager/projects/<name>/`.
- VMs: `virsh` + `qemu-img` present; ISOs in `/mnt/user/isos/`; vdisks in
  `/mnt/user/domains/<name>/`; libvirt XML in `/etc/libvirt/qemu/`. `virsh define`
  surfaces a VM in the VM Manager.
- Community Applications is installed; its app templates are Container XMLs
  referenced from a searchable app feed (GitHub-backed).

## Architecture

One shared **template engine** that everything reuses, plus four capability
groups of MCP tools. All new code lives in `unraid-control/mcp/unraid_server.py`
alongside the existing SSH helpers (`_ssh_exec`, `_ssh_read_file`,
`_ssh_write_file`, `_ssh_connect`). No new files; no new dependencies (paramiko
already declared).

### Template engine (internal helpers)

- `_template_xml(spec: dict) -> str` — build a Container v2 XML from structured
  input (name, repository, network, ports, volumes, env, webui, icon, extra
  params, privileged).
- `_run_cmd_from_spec(spec) -> str` — build the `docker run -d` command with the
  three `net.unraid.docker.*` managed labels, `--name`, restart policy, and every
  `-p`/`-v`/`-e` from the spec. Every interpolated value passes through
  `shlex.quote`.
- `_write_template(cfg, name, xml)` — SFTP the XML to templates-user.
- Deploy = write template → `docker run` → verify via existing GraphQL docker list.

### Layer 1 — custom containers

- `unraid_docker_deploy(name, image, ports=[], volumes=[], env={}, network="bridge",
  webui="", icon="", extra_params="", privileged=False, autostart=False, confirm=False)`
- `unraid_docker_redeploy(name, confirm=False)` — recreate from stored template
  (pulls latest image).
- `unraid_template_get(name)` — read back the stored template XML (read-only).

Reuses the existing `unraid_docker_remove` for teardown.

### Layer 2 — Community Applications

- `unraid_ca_search(query, limit=20)` — search the CA app feed; returns name,
  repository, template URL, category, overview.
- `unraid_ca_deploy(app, name="", overrides={}, confirm=False)` — fetch the app's
  template XML, apply path/port overrides, deploy through the engine.

Feed + template fetched over HTTP with the existing `httpx` client and timeout.

### Layer 3 — compose stacks

- `unraid_compose_deploy(name, compose_yaml, env_file="", confirm=False)` —
  ensure Compose Manager is installed (install if missing), write
  `projects/<name>/docker-compose.yml` (+ optional `.env`), `docker compose up -d`.
- `unraid_compose_down(name, confirm=False)` — `docker compose down`.
- `unraid_compose_list()` — list projects and their state (read-only).

### Layer 4 — VM create

- `unraid_vm_isos()` — list `/mnt/user/isos/` (read-only).
- `unraid_vm_create(name, cpu=2, mem_gb=4, vdisk_gb=30, iso="", os_type="linux",
  vdisk_bus="virtio", confirm=False)` — `qemu-img create` the vdisk, generate
  domain XML from an Unraid template (Linux or Windows/virtio), `virsh define`,
  optionally autostart. Appears in VM Manager.
- `unraid_vm_delete(name, delete_vdisk=False, confirm=False, acknowledge="")` —
  `virsh undefine`; deleting the vdisk is double-gated (`confirm` + typed
  `acknowledge=name`).

## Safety

- Every deploy/create/redeploy/down/delete is `confirm=True`-gated (mirrors the
  existing tools). Data-destroying deletes (vdisk removal) are double-gated with a
  typed acknowledge token, matching the sabnzbd/tdarr precedent.
- All shell-interpolated user values pass through `shlex.quote`; template values
  are XML-escaped.
- **Hard guard:** any VM tool refuses to target `GH-Dev` (this session's own VM)
  regardless of confirm, to prevent self-destruction. Implemented as a
  `_PROTECTED_VMS` set checked before any state change.
- GraphQL/SSH errors surface through the existing `err()`/`refuse()` wrappers.

## Validation plan (live, on throwaways)

1. `busybox` container via `unraid_docker_deploy` → confirm it appears managed in
   the Docker tab (label check + GraphQL list) → `unraid_docker_remove` →
   confirm template + container gone.
2. `unraid_ca_search "syncthing"` returns hits; deploy dry-parse of the fetched
   template (no real second container needed if layer 1 proved the engine).
3. Compose: deploy a 1-service busybox stack → verify `docker compose ps` →
   `unraid_compose_down` → cleanup.
4. VM: create a tiny diskless (or 1 GB vdisk) test VM named `gh-tools-test` with
   no ISO → confirm it appears in `virsh list --all` → `unraid_vm_delete` with
   vdisk removal → confirm gone. `GH-Dev` guard tested (must refuse).
5. Re-run `mcp/_smoketest.py` and the MCP handshake test; add the new read-only
   tools (`unraid_vm_isos`, `unraid_compose_list`, `unraid_template_get`) to the
   smoke test.

## Out of scope

- Editing arbitrary libvirt XML by hand (`unraid_vm_create` generates it).
- GPU/PCI passthrough config on VM create (future; base create only).
- CA "install" via the plugin's own PHP path (we fetch+deploy the template
  directly, which is equivalent and API-free).
