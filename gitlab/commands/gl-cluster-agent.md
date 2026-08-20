---
description: Set up a GitLab Kubernetes Agent for a project (register, get the install snippet)
argument-hint: <project> <agent-name>
---

Bootstrap a GitLab Kubernetes Agent — the pull-model agent that bridges a cluster to GitLab.
Read the cluster agents reference. The agentk runs in your cluster; GitLab stores its config
in the repo under `.gitlab/agents/<name>/config.yaml`.

1. **Pre-flight** (read-only): `cluster_agents(project, action="list")` — existing agents.
    `get_project(project)` to confirm `cluster_agents_enabled` (it's on by default).
2. **Create the agent**: `cluster_agents(project, action="create", params={name: <agent-name>},
    confirm=true)`. Capture the returned `id`.
3. **Create an auth token**: `cluster_agents(project, action="create_token", agent_id=<id>,
    params={name: "<agent-name>-token"}, confirm=true)`. **The response includes `token` —
    relay it immediately** (one-time-only secret). This token is used in the install command.
4. **Generate the install snippet** for the user: the `kubectl` command to install agentk in
    the cluster:
    ```
    helm repo add gitlab https://charts.gitlab.io
    helm repo update
    helm upgrade --install gitlab-agent gitlab/gitlab-agent \
      --namespace gitlab-agent \
      --create-namespace \
      --set config.token=<relay-the-token-here> \
      --set config.kasAddress=wss://gitlab.example.com/-/kubernetes-agent/
    ```
    (KAS address from `gitlab_status().metadata.kas.externalUrl`.)
5. **Seed the agent config**: `write_files(project, [{action:"create",
    file_path:".gitlab/agents/<agent-name>/config.yaml",
    content: "gitops: {} # configure manifest paths here\nobservability: {}\n"}],
    commit_message="chore: seed gitlab agent config", confirm=true)`.
6. **Verify**: `cluster_agents(project, action="get", agent_id=<id>)` — after the user installs
    agentk, status fields populate. Report: agent name + id, token (relayed), KAS address,
    install command, config file path.

Common follow-ups: configure gitops sync paths under `gitops.manifest_paths` in the config
file; scope RBAC in the cluster to least privilege; rotate the token periodically via
`cluster_agents(..., action="create_token")` and update agentk.
