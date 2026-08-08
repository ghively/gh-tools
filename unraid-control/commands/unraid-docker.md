---
description: Inspect and manage Docker containers on the Unraid server
argument-hint: (optional) a container name or action, e.g. "sonarr" or "list"
---

# Unraid Docker management

Help the user inspect or control Docker containers via the `unraid` MCP
tools. If `$ARGUMENTS` names a specific container, focus there; otherwise
give an overview.

## Overview (no argument, or a general request)

1. `unraid_docker_containers` — list all containers with state, image, ports,
   and whether an update is available.
2. Group by state (RUNNING / EXITED / PAUSED) in the summary. Call out any
   `EXITED` container that looks like it should be running (was likely
   running before), and any with `isUpdateAvailable: true`.

## Inspecting one container

1. `unraid_docker_container(id)` for full config (image, ports, mounts,
   network, WebUI URL, autostart).
2. `unraid_docker_logs(id, tail=100)` for recent activity — useful for
   diagnosing a crash-looping or unhealthy container.
3. `unraid_docker_stats(id)` for live CPU/memory/network/block IO (this opens
   a brief WebSocket subscription — allow a few seconds).

## Controlling a container

- Starting (`unraid_docker_start`) and unpausing (`unraid_docker_unpause`)
  need no confirmation — they're not disruptive.
- Stopping, restarting, pausing, removing, or updating a container
  interrupts whatever it serves — **state clearly what you're about to do and
  why, get the user's go-ahead, then call the tool with `confirm=True`.**
  Don't pass `confirm=True` preemptively "to save a round trip."
- After any control action, re-fetch `unraid_docker_containers` (or the one
  container) and report the resulting state — don't just assume the mutation
  succeeded from its return value alone.

## Updating containers

`unraid_docker_containers` shows `isUpdateAvailable`. To update:
`unraid_docker_update(id, confirm=True)` for one, or
`unraid_docker_update_all(confirm=True)` for every container with an update
pending — both restart the container(s) they touch, so confirm with the user
first, especially for `_update_all`.
