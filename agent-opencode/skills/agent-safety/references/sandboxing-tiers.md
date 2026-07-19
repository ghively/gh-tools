> Last verified: 2026-07. Sandbox capabilities and OpenCode permission features change with CLI, Docker, gVisor, Kata, and Firecracker releases; re-check docs before copying configs into production.

# Sandboxing Tiers

Isolation is layered. Hooks stop the agent from issuing known-dangerous operations; sandboxes limit damage if generated or untrusted code runs anyway.

OpenCode's permission model and the agent-foundry safety floor plugin provide the workspace write boundary and the destructive-command deny list. Use those first, then add OS/container isolation for untrusted execution.

## Isolation Ladder

| Tier | Boundary | Use When | Cost |
|---|---|---|---|
| Workspace permissions | Agent can write only allowed project paths | Normal coding work | Low |
| Rootless/non-root containers | Container root is not host root | Generated scripts, package installs | Low-medium |
| Hardened containers | Drop caps, no-new-privileges, read-only rootfs, seccomp/AppArmor | Untrusted code with limited dependencies | Medium |
| Network allowlist | Egress only to approved domains/services | External-content processing | Medium |
| gVisor/runsc | Userspace kernel intercepts syscalls | Higher-risk Linux workloads | Medium-high compatibility/perf cost |
| Kata or Firecracker microVM | VM boundary around workload | Strong isolation for untrusted code | Higher startup/ops cost |

GPU passthrough is only a controlled device-access example. Do not make GPU availability the center of the sandbox design unless the workload truly needs it.

## Threat To Isolation Tier

Pick the tier by the threat and the trust level of the code, not by what is easiest to spin up. A workspace permission is enough for trusted coding work; it is not enough for model-generated or community-supplied code.

| Threat / Workload | Minimum Tier |
|---|---|
| Trusted developer coding in the workspace | OpenCode permission rules + safety floor plugin |
| Package install or generated scripts in CI | Rootless/non-root container |
| Untrusted code with limited dependencies | Hardened container (cap-drop, no-new-privileges, read-only rootfs) |
| Agent processing external content with fetch | Hardened container + network allowlist |
| Higher-risk Linux workload needing syscall interception | gVisor/runsc |
| Strongly untrusted code, multi-tenant, or compliance-driven | Kata or Firecracker microVM |
| Any sensitive read paired with model output | Add a network allowlist regardless of other tiers |

Read access plus an open network is exfiltration. Whenever a tier grants read access to anything sensitive, pair it with the network allowlist row.

## Baseline Container Pattern

```bash
docker run --rm \
  --user 10001:10001 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --pids-limit=256 \
  --memory=2g \
  --cpus=2 \
  --network=none \
  -v "$PWD:/workspace:ro" \
  -w /workspace \
  IMAGE command
```

Each flag closes a specific gap:

- `--user 10001:10001` — the process is not root inside or outside the container.
- `--cap-drop=ALL` — no Linux capabilities; add back only the one or two the workload truly needs.
- `--security-opt=no-new-privileges` — no `setuid` escalation paths.
- `--read-only` — the root filesystem cannot be mutated; writes go to an explicit scratch mount.
- `--tmpfs /tmp:rw,noexec,nosuid,size=128m` — `/tmp` is writable but bounded and non-executable where practical.
- `--pids-limit`, `--memory`, `--cpus` — bound resource exhaustion (the fork-bomb family).
- `--network=none` — no egress by default; add an allowlisted network only when needed.
- `-v "$PWD:/workspace:ro"` — the workspace is read-only inside the sandbox.

Add writes only to a scratch mount. Add network only to a dedicated allowlisted network. Never mount credential directories into a sandbox.

## Rootless Docker

Docker rootless mode runs the daemon and containers as an unprivileged user using user namespaces. It requires `newuidmap`, `newgidmap`, and subordinate UID/GID ranges. Verify with `docker info` showing `rootless` in security options.

Rootless mode reduces daemon and container breakout impact, but it does not make untrusted code safe by itself. Keep capability dropping, read-only filesystems, and egress limits.

## Hardening Checklist

- `--user` is non-root.
- `--cap-drop=ALL` and add back only what is required.
- `--security-opt=no-new-privileges` is set.
- Root filesystem is read-only.
- Temporary paths are `tmpfs` with `noexec,nosuid` where practical.
- No host root, Docker socket, credential directory, `/proc`, `/sys`, or `/dev` mounts.
- Network is none by default, allowlisted when needed.
- Secrets are short-lived and injected only when necessary.
- Logs and artifacts are copied out explicitly, not via broad host mounts.

## Stronger Tiers

[gVisor](https://gvisor.dev/docs/) provides an OCI runtime, `runsc`, with a userspace application kernel between the workload and host kernel. It improves isolation but has syscall compatibility and performance tradeoffs.

[Firecracker](https://firecracker-microvm.github.io/) provides lightweight KVM microVMs with a minimal device model and jailer. It is strong isolation for service/container style workloads but requires more orchestration than a normal container.

Kata Containers wraps containers with a VM boundary and can be easier to integrate into container workflows than raw microVM management.

### Choosing Between The Stronger Tiers

The stronger tiers trade startup time, ops complexity, and sometimes syscall compatibility for a harder boundary. Choose by workload shape:

- gVisor/runsc fits best when you want a container-shaped workflow but need to intercept syscalls for higher-risk Linux workloads, and you can accept compatibility and performance costs.
- Firecracker fits best when you run many short-lived, strongly isolated workloads (multi-tenant execution, function-style jobs) and can invest in orchestration around the jailer and the minimal device model.
- Kata fits best when you want VM-strength isolation inside a Kubernetes or container-tooling workflow without building microVM orchestration yourself.

None of these make a `--privileged` container or a mounted Docker socket safe. The stronger tier raises the floor; it does not cancel out a dangerous mount.

## Verification

```bash
docker inspect CONTAINER --format '{{.Config.User}} {{.HostConfig.Privileged}} {{.HostConfig.ReadonlyRootfs}}'
docker inspect CONTAINER --format '{{.HostConfig.CapDrop}} {{.HostConfig.SecurityOpt}} {{.HostConfig.NetworkMode}}'
docker exec CONTAINER id
docker exec CONTAINER sh -lc 'touch /tmp/ok && touch /should-fail'
```

Read each line as a check, not a ritual:

- Line 1 confirms the user is non-root, `Privileged` is false, and the root filesystem is read-only.
- Line 2 confirms capabilities are dropped, `no-new-privileges` is set, and the network mode is what you expect (none or allowlisted).
- Line 3 confirms the running identity inside the container.
- Line 4 confirms writes succeed only where allowed (`/tmp/ok`) and fail where they should (`/should-fail`).

If any verification is ambiguous, treat the sandbox as unproven and do not run untrusted code in it.

## Pitfalls

- Running untrusted code with the sandbox off because "it was just a quick test." Fix: the default is sandbox-on for any generated or third-party code.
- Mounting the Docker socket, `/proc`, `/sys`, `/dev`, or a credential directory into the sandbox. Fix: never; these cancel the boundary.
- Using `--privileged` to work around a capability issue. Fix: add back the single required capability, never `--privileged`.
- Trusting rootless mode alone. Fix: rootless reduces daemon breakout impact; keep cap-drop, read-only rootfs, and egress limits.
- Granting read access without an egress allowlist. Fix: pair sensitive reads with network policy.
- Skipping verification because the config "looks right." Fix: run the four verification lines every time.
