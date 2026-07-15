---
description: View, manage, and deploy Docker containers on the Synology NAS (Container Manager)
argument-hint: (optional) e.g. "deploy nginx", "restart romm", "logs bookorbit-app-1", "status"
---

# Synology containers (Container Manager)

Manage Docker via the `synology` MCP tools.

1. **Prerequisite:** container tools need Container Manager running. If any call
   returns error 102, run
   `synology_package_control(package_id="ContainerManager", action="start")` (ask
   first), then retry.

2. **Always show current state first:** `synology_containers_list` (name, image,
   status) and, if relevant, `synology_projects_list` for Compose stacks and
   `synology_images_list` for local images.

3. **Then act on `$ARGUMENTS`:**
   - "status" / no args → just report the state above.
   - "start/stop/restart/delete <name>" → the matching
     `synology_container_start` / `_stop` / `_restart` / `_delete`. Stop, restart,
     and delete are disruptive and require `confirm=True` — confirm with the user,
     naming exactly which container and what it serves, before passing it.
   - "logs <name>" → `synology_container_logs`; "stats <name>" → `synology_container_stats`.
   - "deploy/pull <image>" → `synology_image_pull(repository=..., tag=...)`, then
     either `synology_container_create` for a single container or, preferred for
     anything with multiple services/volumes/env, `synology_project_create` with a
     docker-compose YAML you write from the user's requirements.

Report the resulting container/project list after any change. Never stop, restart,
or delete a container the user didn't explicitly name.
