#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0",
#   "httpx>=0.27",
# ]
# ///
"""GitLab CE MCP server.

Exposes a self-hosted GitLab instance (built and verified against GitLab 19.0.0
CE at git.hively.dev) to Claude through the Model Context Protocol. The design
is two-layered:

* A GENERIC passthrough (`gitlab_rest` / `gitlab_graphql` / `gitlab_api_search`)
  that can reach *any* of the ~170 REST resource domains and the full GraphQL
  schema (160 queries / 622 mutations on 19.0). This is what makes "control
  everything" true rather than aspirational.
* CURATED tools for the common jobs (projects, repo files, branches, merge
  requests, issues, CI/CD pipelines, runners, users/admin, groups, search,
  releases, webhooks, packages) so day-to-day tasks are a single clean call.

Safety: every write path is confirm-gated (`confirm=True` required); the tool
returns an explicit refusal otherwise. EE-only endpoints return plain 404 on
CE — error messages carry a hint about that so gaps are honestly reported.

All logging goes to stderr; stdout is reserved for the MCP protocol.

Run `uv run --script gitlab_server.py --selftest` for a live read-only audit
of every domain against the configured instance (no mutations).
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[gitlab-mcp]", *a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
def _truthy(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def _find_config_file() -> Optional[Path]:
    """Locate config.local.json without hardcoding an absolute path."""
    candidates = []
    if os.environ.get("GITLAB_CONFIG"):
        candidates.append(Path(os.environ["GITLAB_CONFIG"]))
    root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root_env:
        candidates.append(Path(root_env) / "config.local.json")
    here = Path(__file__).resolve().parent
    candidates.append(here.parent / "config.local.json")  # plugin root
    candidates.append(here / "config.local.json")
    candidates.append(Path.cwd() / "config.local.json")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def load_config() -> dict:
    """Resolve config from config.local.json (defaults) then env vars (overrides)."""
    cfg: dict = {}
    cf = _find_config_file()
    if cf:
        try:
            cfg = json.loads(cf.read_text(encoding="utf-8"))
            log(f"loaded config file: {cf}")
        except Exception as e:  # noqa: BLE001
            log(f"WARNING: could not parse {cf}: {e}")

    env = os.environ
    return {
        "base_url": (env.get("GITLAB_URL") or cfg.get("base_url") or "").rstrip("/"),
        "token": env.get("GITLAB_TOKEN") or cfg.get("token") or "",
        "verify_ssl": _truthy(env.get("GITLAB_VERIFY_SSL", cfg.get("verify_ssl", True)), True),
        "timeout": float(env.get("GITLAB_TIMEOUT") or cfg.get("timeout") or 30),
    }


CONFIG = load_config()
if not CONFIG["base_url"] or not CONFIG["token"]:
    log("ERROR: base_url and token are required (config.local.json or GITLAB_URL/GITLAB_TOKEN)")

_client = httpx.Client(
    base_url=CONFIG["base_url"],
    headers={"PRIVATE-TOKEN": CONFIG["token"]},
    verify=CONFIG["verify_ssl"],
    timeout=CONFIG["timeout"],
    follow_redirects=True,
)

EE_HINT = (
    "Note: on GitLab CE, EE-only (Premium/Ultimate) endpoints also return 404, "
    "so a 404 can mean 'resource missing' OR 'feature not in CE'."
)


# --------------------------------------------------------------------------- #
# Core REST / GraphQL clients                                                 #
# --------------------------------------------------------------------------- #
def _err(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = resp.text[:500]
    out = {"error": True, "status": resp.status_code, "message": body}
    if resp.status_code == 404:
        out["hint"] = EE_HINT
    if resp.status_code == 403:
        out["hint"] = "403: token lacks the scope/role, or the feature is disabled for this project/instance."
    return out


def rest(
    method: str,
    path: str,
    params: Optional[dict] = None,
    body: Optional[dict] = None,
    paginate: bool = False,
    max_pages: int = 5,
) -> Any:
    """Call any /api/v4 endpoint. Returns parsed JSON, or an error dict.

    With paginate=True, GETs follow X-Next-Page up to max_pages and return
    {"items": [...], "total": ..., "truncated": bool}.
    """
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/api/"):
        path = "/api/v4" + path
    method = method.upper()

    if not paginate or method != "GET":
        r = _client.request(method, path, params=params, json=body)
        if r.status_code >= 400:
            return _err(r)
        if r.status_code == 204 or not r.content:
            return {"ok": True, "status": r.status_code}
        ctype = r.headers.get("content-type", "")
        if "json" not in ctype:
            return {"ok": True, "status": r.status_code, "text": r.text[:20000]}
        return r.json()

    items: list = []
    total = None
    page_params = dict(params or {})
    page_params.setdefault("per_page", 100)
    pages = 0
    while pages < max_pages:
        r = _client.get(path, params=page_params)
        if r.status_code >= 400:
            return _err(r)
        chunk = r.json()
        if not isinstance(chunk, list):
            return chunk
        items.extend(chunk)
        total = r.headers.get("x-total") or total
        nxt = r.headers.get("x-next-page")
        pages += 1
        if not nxt:
            return {"items": items, "count": len(items), "total": total, "truncated": False}
        page_params["page"] = nxt
    return {"items": items, "count": len(items), "total": total, "truncated": True,
            "note": f"stopped after {max_pages} pages; raise max_pages to fetch more"}


_MUTATION_RE = re.compile(r"^\s*(#[^\n]*\n\s*)*mutation\b", re.IGNORECASE)


def gql(query: str, variables: Optional[dict] = None) -> Any:
    r = _client.post(
        "/api/graphql",
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {CONFIG['token']}"},
    )
    if r.status_code >= 400:
        return _err(r)
    return r.json()


def _proj(p: Any) -> str:
    """Project (or group) identifier: numeric id passes through, paths get URL-encoded."""
    s = str(p)
    return s if s.isdigit() else quote(s, safe="")


def _gate(confirm: bool, action: str) -> Optional[dict]:
    """Refuse writes unless the caller has confirmed with the user."""
    if confirm:
        return None
    return {
        "error": True,
        "confirm_required": True,
        "message": (
            f"REFUSED: this call would {action}. Ask the user for explicit approval, "
            "then re-run with confirm=true."
        ),
    }


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------- #
# Compact endpoint catalog (for gitlab_api_search)                            #
# --------------------------------------------------------------------------- #
# domain -> [endpoint templates]. Full map lives in the skill's api-map.md.
API_CATALOG: dict[str, list[str]] = {
    "projects": ["GET /projects", "GET /projects/:id", "POST /projects", "PUT /projects/:id",
                 "DELETE /projects/:id", "POST /projects/:id/archive", "POST /projects/:id/unarchive",
                 "POST /projects/:id/fork", "PUT /projects/:id/transfer", "POST /projects/:id/star",
                 "POST /projects/:id/housekeeping", "GET /projects/:id/languages",
                 "GET /users/:user_id/projects", "GET /projects/:id/forks"],
    "project export/import": ["POST /projects/:id/export", "GET /projects/:id/export",
                              "GET /projects/:id/export/download", "POST /projects/import",
                              "GET /projects/:id/import"],
    "repository": ["GET /projects/:id/repository/tree", "GET /projects/:id/repository/blobs/:sha",
                   "GET /projects/:id/repository/archive", "GET /projects/:id/repository/compare",
                   "GET /projects/:id/repository/contributors", "GET /projects/:id/repository/merge_base"],
    "repository files": ["GET /projects/:id/repository/files/:file_path", "GET .../files/:file_path/raw",
                         "POST/PUT/DELETE /projects/:id/repository/files/:file_path",
                         "GET .../files/:file_path/blame"],
    "commits": ["GET /projects/:id/repository/commits", "GET .../commits/:sha", "POST .../commits (multi-action)",
                "GET .../commits/:sha/diff", "GET .../commits/:sha/comments", "GET .../commits/:sha/refs",
                "POST .../commits/:sha/cherry_pick", "POST .../commits/:sha/revert",
                "GET .../commits/:sha/statuses", "POST /projects/:id/statuses/:sha"],
    "branches": ["GET /projects/:id/repository/branches", "POST .../branches", "DELETE .../branches/:name",
                 "DELETE .../merged_branches", "GET/POST/DELETE /projects/:id/protected_branches"],
    "tags": ["GET/POST /projects/:id/repository/tags", "DELETE .../tags/:name",
             "GET/POST/DELETE /projects/:id/protected_tags"],
    "merge requests": ["GET /merge_requests?scope=all", "GET /projects/:id/merge_requests",
                       "GET /projects/:id/merge_requests/:iid", "POST /projects/:id/merge_requests",
                       "PUT .../:iid", "PUT .../:iid/merge", "PUT .../:iid/rebase", "DELETE .../:iid",
                       "GET .../:iid/diffs", "GET .../:iid/commits", "GET .../:iid/pipelines",
                       "POST .../:iid/approve", "POST .../:iid/unapprove", "GET .../:iid/approvals",
                       "GET .../:iid/closes_issues", "GET .../:iid/related_issues"],
    "mr discussions/notes": ["GET/POST /projects/:id/merge_requests/:iid/discussions",
                             "POST .../discussions/:did/notes", "PUT .../discussions/:did (resolve)",
                             "GET/POST/PUT/DELETE /projects/:id/merge_requests/:iid/notes"],
    "draft notes": ["GET/POST/PUT/DELETE /projects/:id/merge_requests/:iid/draft_notes",
                    "POST .../draft_notes/bulk_publish"],
    "issues": ["GET /issues?scope=all", "GET /projects/:id/issues", "GET /projects/:id/issues/:iid",
               "POST /projects/:id/issues", "PUT .../:iid", "DELETE .../:iid", "POST .../:iid/move",
               "POST .../:iid/clone", "GET/POST/DELETE .../:iid/links", "GET .../:iid/related_merge_requests",
               "POST .../:iid/reset_spent_time", "POST .../:iid/time_estimate", "GET /issues_statistics"],
    "notes (issues/snippets)": ["GET/POST/PUT/DELETE /projects/:id/issues/:iid/notes",
                                "GET/POST/PUT/DELETE /projects/:id/snippets/:sid/notes"],
    "labels": ["GET/POST/PUT/DELETE /projects/:id/labels", "GET/POST/PUT/DELETE /groups/:id/labels",
               "PUT /projects/:id/labels/:lid/promote"],
    "milestones": ["GET/POST/PUT/DELETE /projects/:id/milestones", "GET/POST/PUT/DELETE /groups/:id/milestones",
                   "GET .../milestones/:mid/issues", "GET .../milestones/:mid/merge_requests"],
    "issue boards": ["GET/POST/PUT/DELETE /projects/:id/boards", "GET/POST/PUT/DELETE /groups/:id/boards",
                     ".../boards/:bid/lists"],
    "pipelines": ["GET /projects/:id/pipelines", "GET .../pipelines/:pid", "GET .../pipelines/latest",
                  "POST /projects/:id/pipeline", "POST .../pipelines/:pid/retry", "POST .../pipelines/:pid/cancel",
                  "DELETE .../pipelines/:pid", "GET .../pipelines/:pid/variables", "GET .../pipelines/:pid/test_report",
                  "PUT .../pipelines/:pid/metadata"],
    "jobs": ["GET /projects/:id/jobs", "GET /projects/:id/pipelines/:pid/jobs", "GET /projects/:id/jobs/:jid",
             "GET .../jobs/:jid/trace", "POST .../jobs/:jid/retry", "POST .../jobs/:jid/cancel",
             "POST .../jobs/:jid/play", "POST .../jobs/:jid/erase", "GET .../jobs/:jid/artifacts",
             "POST .../jobs/:jid/artifacts/keep", "DELETE .../jobs/:jid/artifacts", "GET /job (current CI job)"],
    "ci variables": ["GET/POST/PUT/DELETE /projects/:id/variables", "GET/POST/PUT/DELETE /groups/:id/variables",
                     "GET/POST/PUT/DELETE /admin/ci/variables (instance)"],
    "pipeline schedules": ["GET/POST/PUT/DELETE /projects/:id/pipeline_schedules",
                           "POST .../pipeline_schedules/:sid/play", "POST .../pipeline_schedules/:sid/take_ownership",
                           ".../pipeline_schedules/:sid/variables"],
    "pipeline triggers": ["GET/POST/PUT/DELETE /projects/:id/triggers", "POST /projects/:id/trigger/pipeline"],
    "ci lint": ["POST /projects/:id/ci/lint {content|dry_run}"],
    "runners": ["GET /runners", "GET /runners/all (admin)", "GET/PUT/DELETE /runners/:id", "GET /runners/:id/jobs",
                "POST /user/runners (create, 16.0+)", "GET/POST/DELETE /projects/:id/runners",
                "GET /groups/:id/runners", "POST /runners/verify"],
    "job token scope": ["GET/PATCH /projects/:id/job_token_scope", "GET/POST/DELETE .../job_token_scope/allowlist"],
    "users": ["GET /users (admin filters)", "GET /users/:id", "POST /users (admin)", "PUT /users/:id",
              "DELETE /users/:id", "POST /users/:id/block|unblock|activate|deactivate|ban|unban|approve|reject",
              "GET /users/:id/memberships", "GET /users/:id/projects", "GET /user", "GET /user/counts",
              "GET/POST/DELETE /users/:id/keys", "GET/POST/DELETE /users/:id/emails", "GET /users/:id/events"],
    "user tokens": ["GET /personal_access_tokens", "GET /personal_access_tokens/self",
                    "POST /personal_access_tokens/:id/rotate", "DELETE /personal_access_tokens/:id",
                    "POST /users/:id/personal_access_tokens (admin)",
                    "GET/POST/DELETE /users/:id/impersonation_tokens (admin)"],
    "groups": ["GET /groups", "GET /groups/:id", "POST /groups", "PUT /groups/:id", "DELETE /groups/:id",
               "POST /groups/:id/transfer", "GET /groups/:id/subgroups", "GET /groups/:id/descendant_groups",
               "GET /groups/:id/projects", "POST /groups/:id/projects/:pid (transfer project in)"],
    "members": ["GET /projects/:id/members[/all]", "GET /groups/:id/members[/all]",
                "POST/PUT/DELETE /projects/:id/members[/:uid]", "POST/PUT/DELETE /groups/:id/members[/:uid]"],
    "access requests": ["GET/POST /projects/:id/access_requests", "PUT .../access_requests/:uid/approve",
                        "DELETE .../access_requests/:uid", "same for /groups/:id"],
    "invitations": ["POST/GET /projects/:id/invitations", "PUT/DELETE .../invitations/:email",
                    "same for /groups/:id"],
    "admin settings": ["GET/PUT /application/settings", "GET/PUT /application/appearance",
                       "GET/PUT /application/plan_limits"],
    "admin ops": ["GET /application/statistics", "GET /sidekiq/queue_metrics", "GET /sidekiq/process_metrics",
                  "GET /sidekiq/job_stats", "GET /sidekiq/compound_metrics",
                  "DELETE /admin/sidekiq/queues/:queue", "GET/POST/PUT/DELETE /broadcast_messages",
                  "GET/POST/DELETE /hooks (system hooks)", "GET /keys/:id", "GET /keys?fingerprint=",
                  "GET/POST/PUT/DELETE /topics", "GET /namespaces", "GET/POST/DELETE /applications",
                  "GET /features", "POST /features/:name (instance feature flags)", "DELETE /features/:name"],
    "search": ["GET /search?scope=&search=", "GET /groups/:id/search", "GET /projects/:id/search",
               "scopes: projects issues merge_requests milestones users snippet_titles; "
               "project scope adds blobs commits wiki_blobs notes"],
    "releases": ["GET /projects/:id/releases", "GET .../releases/:tag", "POST/PUT/DELETE .../releases[/:tag]",
                 "GET/POST/PUT/DELETE .../releases/:tag/assets/links", "GET /groups/:id/releases"],
    "environments": ["GET/POST/PUT/DELETE /projects/:id/environments", "POST .../environments/:eid/stop",
                     "POST .../environments/review_apps_stop? (stop_stale)", "GET .../environments/:eid"],
    "deployments": ["GET /projects/:id/deployments", "GET .../deployments/:did", "POST /projects/:id/deployments",
                    "PUT .../deployments/:did", "GET .../deployments/:did/merge_requests"],
    "deploy keys": ["GET /deploy_keys (admin)", "GET/POST/PUT/DELETE /projects/:id/deploy_keys[/:kid]",
                    "POST /projects/:id/deploy_keys/:kid/enable"],
    "deploy tokens": ["GET /deploy_tokens (admin)", "GET/POST/DELETE /projects/:id/deploy_tokens[/:tid]",
                      "GET/POST/DELETE /groups/:id/deploy_tokens[/:tid]"],
    "freeze periods": ["GET/POST/PUT/DELETE /projects/:id/freeze_periods"],
    "webhooks": ["GET/POST/PUT/DELETE /projects/:id/hooks[/:hid]", "POST .../hooks/:hid/test/:trigger",
                 "GET/POST/DELETE /hooks (system)", "GET .../hooks/:hid/events (16.3+)"],
    "integrations": ["GET /projects/:id/integrations", "GET/PUT/DELETE /projects/:id/integrations/:slug"],
    "snippets": ["GET /snippets", "GET /snippets/all", "GET /snippets/public", "GET/POST/PUT/DELETE /snippets/:id",
                 "GET /snippets/:id/raw", "GET/POST/PUT/DELETE /projects/:id/snippets[/:sid]",
                 "GET /projects/:id/snippets/:sid/raw"],
    "wikis": ["GET /projects/:id/wikis", "GET/POST/PUT/DELETE /projects/:id/wikis[/:slug]",
              "POST /projects/:id/wikis/attachments"],
    "todos": ["GET /todos", "POST /todos/:id/mark_as_done", "POST /todos/mark_as_done"],
    "events": ["GET /events", "GET /users/:id/events", "GET /projects/:id/events"],
    "packages": ["GET /projects/:id/packages", "GET /groups/:id/packages", "GET .../packages/:pkgid",
                 "GET .../packages/:pkgid/package_files", "DELETE .../packages/:pkgid",
                 "generic upload: PUT /projects/:id/packages/generic/:name/:version/:file"],
    "container registry": ["GET /projects/:id/registry/repositories", "GET /groups/:id/registry/repositories",
                           "GET .../registry/repositories/:rid/tags", "GET .../tags/:name", "DELETE .../tags/:name",
                           "DELETE .../tags?name_regex_delete=", "DELETE /projects/:id/registry/repositories/:rid"],
    "badges": ["GET/POST/PUT/DELETE /projects/:id/badges[/:bid]", "GET/POST/PUT/DELETE /groups/:id/badges[/:bid]"],
    "remote mirrors": ["GET/POST/PUT/DELETE /projects/:id/remote_mirrors[/:mid]", "POST .../remote_mirrors/:mid/sync"],
    "feature flags (project)": ["GET/POST/PUT/DELETE /projects/:id/feature_flags[/:name]",
                                "GET/POST/PUT/DELETE /projects/:id/feature_flags_user_lists"],
    "error tracking": ["GET/PATCH /projects/:id/error_tracking/settings",
                       "GET/POST /projects/:id/error_tracking/client_keys"],
    "pages": ["GET /projects/:id/pages", "GET/PUT/DELETE /projects/:id/pages (settings)",
              "GET/POST/PUT/DELETE /projects/:id/pages/domains[/:domain]", "GET /pages/domains (admin)"],
    "clusters/agents": ["GET /projects/:id/cluster_agents", "GET/POST/DELETE .../cluster_agents[/:aid]",
                        ".../cluster_agents/:aid/tokens"],
    "notifications": ["GET/PUT /notification_settings", "GET/PUT /projects/:id/notification_settings",
                      "GET/PUT /groups/:id/notification_settings"],
    "markdown/misc": ["POST /markdown", "GET /version", "GET /metadata", "GET /avatar?email=",
                      "PUT /suggestions/:id/apply", "GET /namespaces/:id", "GET /projects/:id/templates/:type"],
    "protected packages/registry": ["GET/POST/PATCH/DELETE /projects/:id/packages/protection/rules",
                                    "GET/POST/PATCH/DELETE /projects/:id/registry/protection/repository/rules"],
    "emoji reactions": ["GET/POST/DELETE /projects/:id/issues/:iid/award_emoji",
                        "same for merge_requests and snippets, and notes"],
    "discussions (issues/commits)": ["GET/POST /projects/:id/issues/:iid/discussions",
                                     "GET/POST /projects/:id/commits/:sha/discussions"],
    "resource label events": ["GET /projects/:id/issues/:iid/resource_label_events",
                              "GET .../merge_requests/:iid/resource_label_events"],
    "storage moves (admin)": ["GET/POST /project_repository_storage_moves",
                              "GET/POST /group_repository_storage_moves", "GET/POST /snippet_repository_storage_moves"],
    "custom attributes (admin)": ["GET/PUT/DELETE /users/:id/custom_attributes[/:key]",
                                  "same for /projects/:id and /groups/:id"],
    "secure files": ["GET /projects/:id/secure_files", "GET .../secure_files/:fid",
                     "GET .../secure_files/:fid/download", "POST (multipart) / DELETE .../secure_files[/:fid]"],
    "model registry (ml)": ["REST: /projects/:id/packages/ml_models/... (client protocol)",
                            "GraphQL: project { mlModels { count nodes { name } } mlExperiments }"],
    "bulk imports (direct transfer)": ["GET /bulk_imports (404 until admin enables bulk_import_enabled)",
                                       "POST /bulk_imports {configuration:{url,access_token}, entities:[...]}",
                                       "GET /bulk_imports/:id/entities"],
    "dependency proxy (group)": ["DELETE /groups/:id/dependency_proxy/cache (purge)",
                                 "GraphQL: group { dependencyProxySetting { enabled } dependencyProxyManifests }"],
    "terraform": ["state backend: /projects/:id/terraform/state/:name (basic auth, terraform protocol)",
                  "module registry: /packages/terraform/modules/v1/..."],
    "graphql-only (CE-verified)": ["work items: project { workItems }", "alerts: project { alertManagementAlerts }",
                                   "CI catalog: ciCatalogResources", "achievements: group { achievements } + achievements* mutations"],
    "EE-only (404 on CE)": ["epics", "iterations", "merge_trains", "approval_rules", "audit_events",
                            "protected_environments", "group hooks", "group wikis", "member_roles",
                            "geo_nodes", "license (instance)", "vulnerabilities", "dependencies",
                            "external_status_checks", "ldap sync", "ssh_certificates",
                            "ALL Duo/AI (code_suggestions, duo workflows, ai* GraphQL — runtime-rejected on CE)"],
}


# --------------------------------------------------------------------------- #
# MCP server + generic tools                                                  #
# --------------------------------------------------------------------------- #
mcp = FastMCP("gitlab")


@mcp.tool()
def gitlab_status() -> dict:
    """Instance health snapshot: version, metadata, statistics, current user, token info.

    Start here. Verifies connectivity/auth and reports whether the token is admin.
    """
    out: dict = {"base_url": CONFIG["base_url"]}
    out["metadata"] = rest("GET", "/metadata")
    out["statistics"] = rest("GET", "/application/statistics")
    me = rest("GET", "/user")
    if isinstance(me, dict) and not me.get("error"):
        out["current_user"] = {k: me.get(k) for k in ("id", "username", "name", "is_admin", "email")}
    else:
        out["current_user"] = me
    tok = rest("GET", "/personal_access_tokens/self")
    if isinstance(tok, dict) and not tok.get("error"):
        out["token"] = {k: tok.get(k) for k in ("name", "scopes", "expires_at", "active")}
    else:
        out["token"] = tok
    return out


@mcp.tool()
def gitlab_rest(
    method: str,
    path: str,
    params: Optional[dict] = None,
    body: Optional[dict] = None,
    paginate: bool = False,
    max_pages: int = 5,
    confirm: bool = False,
) -> Any:
    """Generic passthrough to ANY GitLab REST endpoint (/api/v4 prefix optional).

    Reaches all ~170 resource domains — use gitlab_api_search or the gitlab-control
    skill's api-map for paths. GET/HEAD run freely; any other method requires
    confirm=true (ask the user first). paginate=true auto-follows pages for GETs.

    Examples: gitlab_rest("GET", "/projects/4/languages"),
    gitlab_rest("POST", "/projects/4/star", confirm=true)
    """
    if method.upper() not in ("GET", "HEAD"):
        g = _gate(confirm, f"execute {method.upper()} {path} (a write) against {CONFIG['base_url']}")
        if g:
            return g
    return rest(method, path, params=params, body=body, paginate=paginate, max_pages=max_pages)


@mcp.tool()
def gitlab_graphql(query: str, variables: Optional[dict] = None, confirm: bool = False) -> Any:
    """Run any GraphQL query/mutation against /api/graphql (19.0: 160 queries, 622 mutations).

    Queries run freely; mutations require confirm=true (ask the user first).
    GraphQL is the only API for some newer features and often the cheaper way to
    fetch nested data (e.g. project { mergeRequests { nodes { ... } } }).
    """
    if _MUTATION_RE.match(query):
        g = _gate(confirm, "execute a GraphQL MUTATION")
        if g:
            return g
    return gql(query, variables)


@mcp.tool()
def gitlab_api_search(keyword: str) -> dict:
    """Search the built-in endpoint catalog by keyword (e.g. 'runner', 'protected', 'wiki').

    Returns matching domains with endpoint templates. The full enumerated surface
    (172 REST domains + GraphQL root fields) lives in the gitlab-control skill's
    references/api-map.md.
    """
    kw = keyword.lower()
    hits = {}
    for domain, endpoints in API_CATALOG.items():
        matched = [e for e in endpoints if kw in e.lower()]
        if kw in domain.lower():
            hits[domain] = endpoints
        elif matched:
            hits[domain] = matched
    return hits or {"no_match": f"nothing in catalog for '{keyword}'; try gitlab_rest directly or check api-map.md"}


# --------------------------------------------------------------------------- #
# Curated: projects & repository                                              #
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_projects(
    search: Optional[str] = None,
    group: Optional[str] = None,
    membership: bool = False,
    archived: Optional[bool] = None,
    order_by: str = "last_activity_at",
    statistics: bool = False,
    limit: int = 50,
) -> Any:
    """List/search projects (instance-wide, or within a group if group is given).

    group accepts id or full path. statistics=true adds repo/storage sizes.
    """
    params = _clean({
        "search": search, "membership": membership or None, "archived": archived,
        "order_by": order_by, "statistics": statistics or None, "per_page": min(limit, 100),
    })
    path = f"/groups/{_proj(group)}/projects" if group else "/projects"
    data = rest("GET", path, params=params, paginate=limit > 100, max_pages=(limit // 100) + 1)
    if isinstance(data, list):
        keep = ("id", "path_with_namespace", "description", "default_branch", "visibility",
                "last_activity_at", "topics", "archived", "web_url", "statistics")
        return [{k: p.get(k) for k in keep if k in p} for p in data]
    return data


@mcp.tool()
def get_project(project: str, statistics: bool = True) -> Any:
    """Full detail for one project (id or 'namespace/path'), including enabled features."""
    return rest("GET", f"/projects/{_proj(project)}", params={"statistics": statistics})


@mcp.tool()
def manage_project(
    action: str,
    project: Optional[str] = None,
    params: Optional[dict] = None,
    confirm: bool = False,
) -> Any:
    """Project lifecycle: create|update|delete|archive|unarchive|fork|transfer|star|unstar|
    housekeeping|export|export_status|import_status. ALL actions require confirm=true
    except export_status/import_status.

    create: params={name, path?, namespace_id?, visibility?, ...} (no project arg).
    transfer: params={namespace: <id or path>}. fork: params={namespace_id?, name?, path?}.
    export/export_status: project-level export for backups.
    """
    reads = {"export_status", "import_status"}
    if action not in reads:
        g = _gate(confirm, f"{action} project {project or params}")
        if g:
            return g
    p = _proj(project) if project else None
    if action == "create":
        return rest("POST", "/projects", body=params)
    if action == "update":
        return rest("PUT", f"/projects/{p}", body=params)
    if action == "delete":
        return rest("DELETE", f"/projects/{p}")
    if action == "archive":
        return rest("POST", f"/projects/{p}/archive")
    if action == "unarchive":
        return rest("POST", f"/projects/{p}/unarchive")
    if action == "fork":
        return rest("POST", f"/projects/{p}/fork", body=params)
    if action == "transfer":
        return rest("PUT", f"/projects/{p}/transfer", params=params)
    if action == "star":
        return rest("POST", f"/projects/{p}/star")
    if action == "unstar":
        return rest("POST", f"/projects/{p}/unstar")
    if action == "housekeeping":
        return rest("POST", f"/projects/{p}/housekeeping", params=params)
    if action == "export":
        return rest("POST", f"/projects/{p}/export", body=params)
    if action == "export_status":
        return rest("GET", f"/projects/{p}/export")
    if action == "import_status":
        return rest("GET", f"/projects/{p}/import")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def repo_tree(project: str, path: str = "", ref: Optional[str] = None,
              recursive: bool = False, limit: int = 100) -> Any:
    """List repository files/dirs at a path (like `ls` / `find`)."""
    params = _clean({"path": path or None, "ref": ref, "recursive": recursive or None,
                     "per_page": min(limit, 100)})
    return rest("GET", f"/projects/{_proj(project)}/repository/tree", params=params,
                paginate=limit > 100, max_pages=(limit // 100) + 1)


@mcp.tool()
def read_file(project: str, file_path: str, ref: Optional[str] = None) -> Any:
    """Read one file from a repository (content is base64-decoded for you)."""
    enc = quote(file_path, safe="")
    # the files endpoint 400s without ref; HEAD = default branch
    data = rest("GET", f"/projects/{_proj(project)}/repository/files/{enc}",
                params={"ref": ref or "HEAD"})
    if isinstance(data, dict) and data.get("content") and data.get("encoding") == "base64":
        try:
            data["content"] = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            data["encoding"] = "text"
        except Exception:  # noqa: BLE001
            data["note"] = "binary file; content left base64-encoded"
    return data


@mcp.tool()
def write_files(project: str, branch: str, message: str, actions: list,
                start_branch: Optional[str] = None, confirm: bool = False) -> Any:
    """Commit one or more file changes in a single commit (create/update/delete/move).

    actions: [{"action": "create|update|delete|move", "file_path": "...",
    "content": "...", "previous_path": "..."}]. start_branch creates `branch`
    from it first. Requires confirm=true.
    """
    g = _gate(confirm, f"commit {len(actions)} file action(s) to {project}@{branch}")
    if g:
        return g
    body = _clean({"branch": branch, "commit_message": message, "actions": actions,
                   "start_branch": start_branch})
    return rest("POST", f"/projects/{_proj(project)}/repository/commits", body=body)


@mcp.tool()
def branches(project: str, action: str = "list", name: Optional[str] = None,
             ref: Optional[str] = None, search: Optional[str] = None,
             params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Branches: list|get|create|delete|delete_merged|protect|unprotect|protected_list.

    create needs name+ref. protect accepts params={push_access_level, merge_access_level,
    allow_force_push} (levels: 0 none, 30 dev, 40 maintainer). Writes require confirm=true.
    """
    p = _proj(project)
    if action == "list":
        return rest("GET", f"/projects/{p}/repository/branches", params=_clean({"search": search}))
    if action == "get":
        return rest("GET", f"/projects/{p}/repository/branches/{quote(name or '', safe='')}")
    if action == "protected_list":
        return rest("GET", f"/projects/{p}/protected_branches")
    g = _gate(confirm, f"{action} branch '{name}' on {project}")
    if g:
        return g
    if action == "create":
        return rest("POST", f"/projects/{p}/repository/branches", params={"branch": name, "ref": ref})
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/repository/branches/{quote(name or '', safe='')}")
    if action == "delete_merged":
        return rest("DELETE", f"/projects/{p}/repository/merged_branches")
    if action == "protect":
        body = {"name": name, **(params or {})}
        return rest("POST", f"/projects/{p}/protected_branches", body=body)
    if action == "unprotect":
        return rest("DELETE", f"/projects/{p}/protected_branches/{quote(name or '', safe='')}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def tags(project: str, action: str = "list", name: Optional[str] = None,
         ref: Optional[str] = None, message: Optional[str] = None,
         confirm: bool = False) -> Any:
    """Git tags: list|get|create|delete|protect|unprotect|protected_list. Writes need confirm=true."""
    p = _proj(project)
    if action == "list":
        return rest("GET", f"/projects/{p}/repository/tags")
    if action == "get":
        return rest("GET", f"/projects/{p}/repository/tags/{quote(name or '', safe='')}")
    if action == "protected_list":
        return rest("GET", f"/projects/{p}/protected_tags")
    g = _gate(confirm, f"{action} tag '{name}' on {project}")
    if g:
        return g
    if action == "create":
        return rest("POST", f"/projects/{p}/repository/tags",
                    params=_clean({"tag_name": name, "ref": ref, "message": message}))
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/repository/tags/{quote(name or '', safe='')}")
    if action == "protect":
        return rest("POST", f"/projects/{p}/protected_tags", body={"name": name})
    if action == "unprotect":
        return rest("DELETE", f"/projects/{p}/protected_tags/{quote(name or '', safe='')}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def commits(project: str, action: str = "list", sha: Optional[str] = None,
            ref: Optional[str] = None, path: Optional[str] = None,
            since: Optional[str] = None, until: Optional[str] = None,
            branch: Optional[str] = None, limit: int = 20, confirm: bool = False) -> Any:
    """Commits: list|get|diff|comments|refs|statuses|cherry_pick|revert.

    list filters: ref (branch/tag), path, since/until (ISO). cherry_pick/revert
    need sha + branch (target) and confirm=true.
    """
    p = _proj(project)
    if action == "list":
        params = _clean({"ref_name": ref, "path": path, "since": since, "until": until,
                         "per_page": min(limit, 100)})
        return rest("GET", f"/projects/{p}/repository/commits", params=params)
    if action in ("get", "diff", "comments", "refs", "statuses"):
        sub = {"get": "", "diff": "/diff", "comments": "/comments", "refs": "/refs",
               "statuses": "/statuses"}[action]
        return rest("GET", f"/projects/{p}/repository/commits/{sha}{sub}")
    g = _gate(confirm, f"{action} commit {sha} onto branch {branch} in {project}")
    if g:
        return g
    if action in ("cherry_pick", "revert"):
        return rest("POST", f"/projects/{p}/repository/commits/{sha}/{action}", body={"branch": branch})
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def compare_refs(project: str, from_ref: str, to_ref: str, straight: bool = False) -> Any:
    """Diff two branches/tags/SHAs (like `git diff from...to`)."""
    return rest("GET", f"/projects/{_proj(project)}/repository/compare",
                params={"from": from_ref, "to": to_ref, "straight": straight})


# --------------------------------------------------------------------------- #
# Curated: merge requests & issues                                            #
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_merge_requests(project: Optional[str] = None, group: Optional[str] = None,
                        state: str = "opened", search: Optional[str] = None,
                        target_branch: Optional[str] = None, author: Optional[str] = None,
                        limit: int = 50) -> Any:
    """List MRs — instance-wide (scope=all) by default, or for one project/group.

    state: opened|closed|merged|locked|all.
    """
    params = _clean({"state": None if state == "all" else state, "search": search,
                     "target_branch": target_branch, "author_username": author,
                     "scope": "all", "per_page": min(limit, 100)})
    if project:
        path = f"/projects/{_proj(project)}/merge_requests"
    elif group:
        path = f"/groups/{_proj(group)}/merge_requests"
    else:
        path = "/merge_requests"
    data = rest("GET", path, params=params)
    if isinstance(data, list):
        keep = ("iid", "project_id", "title", "state", "source_branch", "target_branch",
                "author", "merge_status", "detailed_merge_status", "draft", "web_url",
                "created_at", "updated_at")
        out = []
        for m in data:
            row = {k: m.get(k) for k in keep if k in m}
            if isinstance(row.get("author"), dict):
                row["author"] = row["author"].get("username")
            out.append(row)
        return out
    return data


@mcp.tool()
def get_merge_request(project: str, iid: int, include: str = "basic") -> Any:
    """One MR in depth. include: basic|diffs|commits|discussions|pipelines|approvals|all."""
    p = _proj(project)
    base = rest("GET", f"/projects/{p}/merge_requests/{iid}")
    if include == "basic" or (isinstance(base, dict) and base.get("error")):
        return base
    want = ["diffs", "commits", "discussions", "pipelines", "approvals"] if include == "all" else [include]
    out = {"merge_request": base}
    for w in want:
        out[w] = rest("GET", f"/projects/{p}/merge_requests/{iid}/{w}",
                      params={"per_page": 50})
    return out


@mcp.tool()
def manage_merge_request(project: str, action: str, iid: Optional[int] = None,
                         params: Optional[dict] = None, confirm: bool = False) -> Any:
    """MR lifecycle: create|update|merge|close|reopen|rebase|approve|unapprove|delete.

    create: params={source_branch, target_branch, title, description?, ...}.
    merge: params={squash?, should_remove_source_branch?, merge_when_pipeline_succeeds?}.
    All actions require confirm=true.
    """
    g = _gate(confirm, f"{action} merge request !{iid or '(new)'} in {project}")
    if g:
        return g
    p = _proj(project)
    if action == "create":
        return rest("POST", f"/projects/{p}/merge_requests", body=params)
    if action == "update":
        return rest("PUT", f"/projects/{p}/merge_requests/{iid}", body=params)
    if action in ("close", "reopen"):
        return rest("PUT", f"/projects/{p}/merge_requests/{iid}",
                    body={"state_event": "close" if action == "close" else "reopen"})
    if action == "merge":
        return rest("PUT", f"/projects/{p}/merge_requests/{iid}/merge", body=params)
    if action == "rebase":
        return rest("PUT", f"/projects/{p}/merge_requests/{iid}/rebase")
    if action == "approve":
        return rest("POST", f"/projects/{p}/merge_requests/{iid}/approve", body=params)
    if action == "unapprove":
        return rest("POST", f"/projects/{p}/merge_requests/{iid}/unapprove")
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/merge_requests/{iid}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def mr_discussions(project: str, iid: int, action: str = "list", body: Optional[str] = None,
                   discussion_id: Optional[str] = None, note_id: Optional[int] = None,
                   position: Optional[dict] = None, resolved: Optional[bool] = None,
                   confirm: bool = False) -> Any:
    """MR review threads: list|add|reply|resolve|edit_note|delete_note.

    add: body (+optional position dict for inline diff comments). reply: discussion_id+body.
    resolve: discussion_id+resolved. Writes require confirm=true.
    """
    p = _proj(project)
    base = f"/projects/{p}/merge_requests/{iid}/discussions"
    if action == "list":
        return rest("GET", base, params={"per_page": 100})
    g = _gate(confirm, f"{action} on MR !{iid} discussion in {project}")
    if g:
        return g
    if action == "add":
        return rest("POST", base, body=_clean({"body": body, "position": position}))
    if action == "reply":
        return rest("POST", f"{base}/{discussion_id}/notes", body={"body": body})
    if action == "resolve":
        return rest("PUT", f"{base}/{discussion_id}", params={"resolved": resolved})
    if action == "edit_note":
        return rest("PUT", f"{base}/{discussion_id}/notes/{note_id}", body={"body": body})
    if action == "delete_note":
        return rest("DELETE", f"{base}/{discussion_id}/notes/{note_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def list_issues(project: Optional[str] = None, group: Optional[str] = None,
                state: str = "opened", labels: Optional[str] = None,
                search: Optional[str] = None, assignee: Optional[str] = None,
                limit: int = 50) -> Any:
    """List issues — instance-wide (scope=all) by default, or per project/group.

    state: opened|closed|all. labels: comma-separated.
    """
    params = _clean({"state": None if state == "all" else state, "labels": labels,
                     "search": search, "assignee_username": assignee, "scope": "all",
                     "per_page": min(limit, 100)})
    if project:
        path = f"/projects/{_proj(project)}/issues"
    elif group:
        path = f"/groups/{_proj(group)}/issues"
    else:
        path = "/issues"
    data = rest("GET", path, params=params)
    if isinstance(data, list):
        keep = ("iid", "project_id", "title", "state", "labels", "assignees", "author",
                "milestone", "web_url", "created_at", "updated_at")
        out = []
        for i in data:
            row = {k: i.get(k) for k in keep if k in i}
            if isinstance(row.get("author"), dict):
                row["author"] = row["author"].get("username")
            if isinstance(row.get("assignees"), list):
                row["assignees"] = [a.get("username") for a in row["assignees"]]
            if isinstance(row.get("milestone"), dict):
                row["milestone"] = row["milestone"].get("title")
            out.append(row)
        return out
    return data


@mcp.tool()
def get_issue(project: str, iid: int, include: str = "basic") -> Any:
    """One issue in depth. include: basic|notes|links|related_merge_requests|all."""
    p = _proj(project)
    base = rest("GET", f"/projects/{p}/issues/{iid}")
    if include == "basic" or (isinstance(base, dict) and base.get("error")):
        return base
    want = ["notes", "links", "related_merge_requests"] if include == "all" else [include]
    out = {"issue": base}
    for w in want:
        out[w] = rest("GET", f"/projects/{p}/issues/{iid}/{w}", params={"per_page": 50})
    return out


@mcp.tool()
def manage_issue(project: str, action: str, iid: Optional[int] = None,
                 params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Issue lifecycle: create|update|close|reopen|delete|move|clone|add_note|link|unlink.

    create: params={title, description?, labels?, assignee_ids?, milestone_id?, ...}.
    move: params={to_project_id}. add_note: params={body}. link: params={target_project_id,
    target_issue_iid}. All require confirm=true.
    """
    g = _gate(confirm, f"{action} issue #{iid or '(new)'} in {project}")
    if g:
        return g
    p = _proj(project)
    if action == "create":
        return rest("POST", f"/projects/{p}/issues", body=params)
    if action == "update":
        return rest("PUT", f"/projects/{p}/issues/{iid}", body=params)
    if action in ("close", "reopen"):
        return rest("PUT", f"/projects/{p}/issues/{iid}",
                    body={"state_event": "close" if action == "close" else "reopen"})
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/issues/{iid}")
    if action == "move":
        return rest("POST", f"/projects/{p}/issues/{iid}/move", body=params)
    if action == "clone":
        return rest("POST", f"/projects/{p}/issues/{iid}/clone", body=params)
    if action == "add_note":
        return rest("POST", f"/projects/{p}/issues/{iid}/notes", body=params)
    if action == "link":
        return rest("POST", f"/projects/{p}/issues/{iid}/links", body=params)
    if action == "unlink":
        link_id = (params or {}).get("issue_link_id")
        return rest("DELETE", f"/projects/{p}/issues/{iid}/links/{link_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def labels(scope_type: str, scope_id: str, action: str = "list",
           name: Optional[str] = None, params: Optional[dict] = None,
           confirm: bool = False) -> Any:
    """Labels for a project or group: list|create|update|delete|promote.

    scope_type: project|group. create: name + params={color, description?}.
    promote (project label → group label) needs confirm. Writes require confirm=true.
    """
    base = f"/{'projects' if scope_type == 'project' else 'groups'}/{_proj(scope_id)}/labels"
    if action == "list":
        return rest("GET", base, params={"per_page": 100})
    g = _gate(confirm, f"{action} label '{name}' on {scope_type} {scope_id}")
    if g:
        return g
    if action == "create":
        return rest("POST", base, body={"name": name, **(params or {})})
    if action == "update":
        return rest("PUT", f"{base}/{quote(name or '', safe='')}", body=params)
    if action == "delete":
        return rest("DELETE", f"{base}/{quote(name or '', safe='')}")
    if action == "promote":
        return rest("PUT", f"{base}/{quote(name or '', safe='')}/promote")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def milestones(scope_type: str, scope_id: str, action: str = "list",
               milestone_id: Optional[int] = None, params: Optional[dict] = None,
               confirm: bool = False) -> Any:
    """Milestones for a project or group: list|get|issues|merge_requests|create|update|delete.

    scope_type: project|group. create: params={title, due_date?, description?}.
    Writes require confirm=true.
    """
    base = f"/{'projects' if scope_type == 'project' else 'groups'}/{_proj(scope_id)}/milestones"
    if action == "list":
        return rest("GET", base, params=params or {"state": "active"})
    if action == "get":
        return rest("GET", f"{base}/{milestone_id}")
    if action in ("issues", "merge_requests"):
        return rest("GET", f"{base}/{milestone_id}/{action}")
    g = _gate(confirm, f"{action} milestone {milestone_id or ''} on {scope_type} {scope_id}")
    if g:
        return g
    if action == "create":
        return rest("POST", base, body=params)
    if action == "update":
        return rest("PUT", f"{base}/{milestone_id}", body=params)
    if action == "delete":
        return rest("DELETE", f"{base}/{milestone_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


# --------------------------------------------------------------------------- #
# Curated: CI/CD                                                              #
# --------------------------------------------------------------------------- #
@mcp.tool()
def pipelines(project: str, action: str = "list", pipeline_id: Optional[int] = None,
              ref: Optional[str] = None, status: Optional[str] = None,
              variables: Optional[list] = None, limit: int = 20,
              confirm: bool = False) -> Any:
    """Pipelines: list|get|latest|variables|test_report|create|retry|cancel|delete.

    list filters: ref, status (running|pending|success|failed|canceled|skipped).
    create: ref + optional variables=[{key,value}]. Writes require confirm=true.
    """
    p = _proj(project)
    if action == "list":
        params = _clean({"ref": ref, "status": status, "per_page": min(limit, 100)})
        return rest("GET", f"/projects/{p}/pipelines", params=params)
    if action == "get":
        return rest("GET", f"/projects/{p}/pipelines/{pipeline_id}")
    if action == "latest":
        return rest("GET", f"/projects/{p}/pipelines/latest", params=_clean({"ref": ref}))
    if action in ("variables", "test_report"):
        return rest("GET", f"/projects/{p}/pipelines/{pipeline_id}/{action}")
    g = _gate(confirm, f"{action} pipeline {pipeline_id or f'(new on {ref})'} in {project}")
    if g:
        return g
    if action == "create":
        return rest("POST", f"/projects/{p}/pipeline",
                    body=_clean({"ref": ref, "variables": variables}))
    if action in ("retry", "cancel"):
        return rest("POST", f"/projects/{p}/pipelines/{pipeline_id}/{action}")
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/pipelines/{pipeline_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def jobs(project: str, action: str = "list", pipeline_id: Optional[int] = None,
         job_id: Optional[int] = None, scope: Optional[list] = None,
         tail: int = 200, confirm: bool = False) -> Any:
    """CI jobs: list (project-wide)|list_pipeline|get|log|retry|cancel|play|erase|artifacts_keep|artifacts_delete.

    log returns the last `tail` lines of the job trace. scope filters e.g.
    ["failed","running"]. Writes require confirm=true.
    """
    p = _proj(project)
    if action == "list":
        return rest("GET", f"/projects/{p}/jobs", params=_clean({"scope[]": scope, "per_page": 50}))
    if action == "list_pipeline":
        return rest("GET", f"/projects/{p}/pipelines/{pipeline_id}/jobs",
                    params=_clean({"scope[]": scope, "per_page": 100}))
    if action == "get":
        return rest("GET", f"/projects/{p}/jobs/{job_id}")
    if action == "log":
        r = _client.get(f"/api/v4/projects/{p}/jobs/{job_id}/trace")
        if r.status_code >= 400:
            return _err(r)
        lines = r.text.splitlines()
        return {"job_id": job_id, "total_lines": len(lines),
                "log_tail": "\n".join(lines[-tail:])}
    g = _gate(confirm, f"{action} job {job_id} in {project}")
    if g:
        return g
    if action in ("retry", "cancel", "play", "erase"):
        return rest("POST", f"/projects/{p}/jobs/{job_id}/{action}")
    if action == "artifacts_keep":
        return rest("POST", f"/projects/{p}/jobs/{job_id}/artifacts/keep")
    if action == "artifacts_delete":
        return rest("DELETE", f"/projects/{p}/jobs/{job_id}/artifacts")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def ci_variables(scope_type: str = "project", scope_id: Optional[str] = None,
                 action: str = "list", key: Optional[str] = None,
                 params: Optional[dict] = None, confirm: bool = False) -> Any:
    """CI/CD variables at project|group|instance scope: list|get|create|update|delete.

    instance scope needs admin (path /admin/ci/variables) and no scope_id.
    create: key + params={value, protected?, masked?, environment_scope?}.
    Writes require confirm=true. Values may be secrets — handle with care.
    """
    if scope_type == "instance":
        base = "/admin/ci/variables"
    elif scope_type == "group":
        base = f"/groups/{_proj(scope_id)}/variables"
    else:
        base = f"/projects/{_proj(scope_id)}/variables"
    if action == "list":
        return rest("GET", base, params={"per_page": 100})
    if action == "get":
        return rest("GET", f"{base}/{quote(key or '', safe='')}")
    g = _gate(confirm, f"{action} CI variable '{key}' at {scope_type} scope")
    if g:
        return g
    if action == "create":
        return rest("POST", base, body={"key": key, **(params or {})})
    if action == "update":
        return rest("PUT", f"{base}/{quote(key or '', safe='')}", body=params)
    if action == "delete":
        return rest("DELETE", f"{base}/{quote(key or '', safe='')}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def pipeline_schedules(project: str, action: str = "list", schedule_id: Optional[int] = None,
                       params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Pipeline schedules: list|get|pipelines|create|update|delete|play|take_ownership.

    create: params={description, ref, cron, cron_timezone?, active?}. Writes need confirm=true.
    """
    p = _proj(project)
    base = f"/projects/{p}/pipeline_schedules"
    if action == "list":
        return rest("GET", base)
    if action == "get":
        return rest("GET", f"{base}/{schedule_id}")
    if action == "pipelines":
        return rest("GET", f"{base}/{schedule_id}/pipelines")
    g = _gate(confirm, f"{action} pipeline schedule {schedule_id or '(new)'} in {project}")
    if g:
        return g
    if action == "create":
        return rest("POST", base, body=params)
    if action == "update":
        return rest("PUT", f"{base}/{schedule_id}", body=params)
    if action == "delete":
        return rest("DELETE", f"{base}/{schedule_id}")
    if action in ("play", "take_ownership"):
        return rest("POST", f"{base}/{schedule_id}/{action}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def runners(action: str = "list", scope: str = "instance", scope_id: Optional[str] = None,
            runner_id: Optional[int] = None, params: Optional[dict] = None,
            confirm: bool = False) -> Any:
    """CI runners: list|get|jobs|update|pause|resume|delete|create|assign|unassign.

    scope: instance (admin: /runners/all) | project | group. create makes a new
    runner via POST /user/runners: params={runner_type: instance_type|group_type|
    project_type, group_id?, project_id?, description?, tag_list?, run_untagged?}
    → returns the token. Writes require confirm=true.
    """
    if action == "list":
        if scope == "project":
            return rest("GET", f"/projects/{_proj(scope_id)}/runners", params=params)
        if scope == "group":
            return rest("GET", f"/groups/{_proj(scope_id)}/runners", params=params)
        return rest("GET", "/runners/all", params=params)
    if action == "get":
        return rest("GET", f"/runners/{runner_id}")
    if action == "jobs":
        return rest("GET", f"/runners/{runner_id}/jobs", params={"per_page": 20})
    g = _gate(confirm, f"{action} runner {runner_id or '(new)'}")
    if g:
        return g
    if action == "create":
        return rest("POST", "/user/runners", body=params)
    if action == "update":
        return rest("PUT", f"/runners/{runner_id}", body=params)
    if action == "pause":
        return rest("PUT", f"/runners/{runner_id}", body={"paused": True})
    if action == "resume":
        return rest("PUT", f"/runners/{runner_id}", body={"paused": False})
    if action == "delete":
        return rest("DELETE", f"/runners/{runner_id}")
    if action == "assign":
        return rest("POST", f"/projects/{_proj(scope_id)}/runners", body={"runner_id": runner_id})
    if action == "unassign":
        return rest("DELETE", f"/projects/{_proj(scope_id)}/runners/{runner_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def ci_lint(project: str, content: Optional[str] = None, ref: Optional[str] = None,
            dry_run: bool = False) -> Any:
    """Validate .gitlab-ci.yml. With content: lints that YAML in the project's context.
    Without: lints the project's current CI config (optionally at ref)."""
    p = _proj(project)
    if content is not None:
        return rest("POST", f"/projects/{p}/ci/lint", body=_clean({"content": content, "dry_run": dry_run or None}))
    return rest("GET", f"/projects/{p}/ci/lint", params=_clean({"ref": ref, "dry_run": dry_run or None}))


# --------------------------------------------------------------------------- #
# Curated: users, groups, admin                                               #
# --------------------------------------------------------------------------- #
@mcp.tool()
def users(action: str = "list", user_id: Optional[int] = None, search: Optional[str] = None,
          params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Users (most write actions need admin): list|get|memberships|keys|events|create|update|
    block|unblock|activate|deactivate|ban|unban|approve|reject|delete.

    list filters via search or params={active, blocked, admins, external, username}.
    create: params={email, username, name, password?|reset_password, admin?, skip_confirmation?}.
    delete: params={hard_delete?}. Writes require confirm=true.
    """
    if action == "list":
        return rest("GET", "/users", params=_clean({"search": search, "per_page": 50, **(params or {})}))
    if action == "get":
        return rest("GET", f"/users/{user_id}")
    if action == "memberships":
        return rest("GET", f"/users/{user_id}/memberships")
    if action == "keys":
        return rest("GET", f"/users/{user_id}/keys")
    if action == "events":
        return rest("GET", f"/users/{user_id}/events", params={"per_page": 30})
    g = _gate(confirm, f"{action} user {user_id or (params or {}).get('username', '(new)')}")
    if g:
        return g
    if action == "create":
        return rest("POST", "/users", body=params)
    if action == "update":
        return rest("PUT", f"/users/{user_id}", body=params)
    if action in ("block", "unblock", "activate", "deactivate", "ban", "unban", "approve", "reject"):
        return rest("POST", f"/users/{user_id}/{action}")
    if action == "delete":
        return rest("DELETE", f"/users/{user_id}", params=params)
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def user_tokens(action: str = "list", user_id: Optional[int] = None,
                token_id: Optional[int] = None, params: Optional[dict] = None,
                confirm: bool = False) -> Any:
    """Access tokens: list (all PATs, admin)|self|get|rotate|revoke|create_pat (admin, for a
    user)|impersonation_list|impersonation_create|impersonation_revoke.

    create_pat: user_id + params={name, scopes:[...], expires_at}. rotate returns the NEW
    token value — show it to the user immediately, it can't be retrieved again.
    Writes require confirm=true.
    """
    if action == "list":
        return rest("GET", "/personal_access_tokens", params=_clean({"user_id": user_id, "per_page": 50}))
    if action == "self":
        return rest("GET", "/personal_access_tokens/self")
    if action == "get":
        return rest("GET", f"/personal_access_tokens/{token_id}")
    if action == "impersonation_list":
        return rest("GET", f"/users/{user_id}/impersonation_tokens")
    g = _gate(confirm, f"{action} token {token_id or '(new)'} for user {user_id or 'self'}")
    if g:
        return g
    if action == "rotate":
        return rest("POST", f"/personal_access_tokens/{token_id}/rotate", params=params)
    if action == "revoke":
        return rest("DELETE", f"/personal_access_tokens/{token_id}")
    if action == "create_pat":
        return rest("POST", f"/users/{user_id}/personal_access_tokens", body=params)
    if action == "impersonation_create":
        return rest("POST", f"/users/{user_id}/impersonation_tokens", body=params)
    if action == "impersonation_revoke":
        return rest("DELETE", f"/users/{user_id}/impersonation_tokens/{token_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def groups(action: str = "list", group: Optional[str] = None, search: Optional[str] = None,
           params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Groups: list|get|subgroups|descendants|projects|create|update|delete|transfer.

    create: params={name, path, parent_id?, visibility?}. transfer: params={group_id}
    (omit to turn subgroup into top-level). Writes require confirm=true.
    """
    if action == "list":
        return rest("GET", "/groups", params=_clean({"search": search, "per_page": 100, **(params or {})}))
    if action == "get":
        return rest("GET", f"/groups/{_proj(group)}", params={"with_projects": False})
    if action == "subgroups":
        return rest("GET", f"/groups/{_proj(group)}/subgroups")
    if action == "descendants":
        return rest("GET", f"/groups/{_proj(group)}/descendant_groups")
    if action == "projects":
        return rest("GET", f"/groups/{_proj(group)}/projects", params={"per_page": 100})
    g = _gate(confirm, f"{action} group {group or (params or {}).get('path', '(new)')}")
    if g:
        return g
    if action == "create":
        return rest("POST", "/groups", body=params)
    if action == "update":
        return rest("PUT", f"/groups/{_proj(group)}", body=params)
    if action == "delete":
        return rest("DELETE", f"/groups/{_proj(group)}")
    if action == "transfer":
        return rest("POST", f"/groups/{_proj(group)}/transfer", params=params)
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def members(scope_type: str, scope_id: str, action: str = "list",
            user_id: Optional[int] = None, access_level: Optional[int] = None,
            params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Project/group membership: list|list_all (incl. inherited)|get|add|update|remove.

    scope_type: project|group. access_level: 10 guest, 20 reporter, 30 developer,
    40 maintainer, 50 owner. Writes require confirm=true.
    """
    base = f"/{'projects' if scope_type == 'project' else 'groups'}/{_proj(scope_id)}/members"
    if action == "list":
        return rest("GET", base, params={"per_page": 100})
    if action == "list_all":
        return rest("GET", f"{base}/all", params={"per_page": 100})
    if action == "get":
        return rest("GET", f"{base}/{user_id}")
    g = _gate(confirm, f"{action} member {user_id} on {scope_type} {scope_id}")
    if g:
        return g
    if action == "add":
        return rest("POST", base, body=_clean({"user_id": user_id, "access_level": access_level, **(params or {})}))
    if action == "update":
        return rest("PUT", f"{base}/{user_id}", body=_clean({"access_level": access_level, **(params or {})}))
    if action == "remove":
        return rest("DELETE", f"{base}/{user_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def admin_settings(action: str = "get", params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Instance-wide application settings (admin): get|update.

    update: params={setting: value, ...} — e.g. {signup_enabled: false}. Requires
    confirm=true; changes affect the whole instance.
    """
    if action == "get":
        return rest("GET", "/application/settings")
    g = _gate(confirm, f"change instance settings: {list((params or {}).keys())}")
    if g:
        return g
    if action == "update":
        return rest("PUT", "/application/settings", params=params)
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def admin_ops(area: str, action: str = "list", item_id: Optional[str] = None,
              params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Admin grab-bag. area: sidekiq|broadcast_messages|system_hooks|applications|topics|
    namespaces|keys|plan_limits|appearance|features|statistics.

    sidekiq: action=queue_metrics|process_metrics|job_stats|compound_metrics.
    features: instance feature flags — action=list|set|delete (set: item_id=flag name,
    params={value: true|false|percentage}). keys: item_id=key id or params={fingerprint}.
    Writes require confirm=true.
    """
    if area == "sidekiq":
        return rest("GET", f"/sidekiq/{action}")
    if area == "statistics":
        return rest("GET", "/application/statistics")
    if area == "broadcast_messages":
        if action == "list":
            return rest("GET", "/broadcast_messages")
        g = _gate(confirm, f"{action} broadcast message")
        if g:
            return g
        if action == "create":
            return rest("POST", "/broadcast_messages", body=params)
        if action == "update":
            return rest("PUT", f"/broadcast_messages/{item_id}", body=params)
        if action == "delete":
            return rest("DELETE", f"/broadcast_messages/{item_id}")
    if area == "system_hooks":
        if action == "list":
            return rest("GET", "/hooks")
        g = _gate(confirm, f"{action} system hook")
        if g:
            return g
        if action == "create":
            return rest("POST", "/hooks", body=params)
        if action == "delete":
            return rest("DELETE", f"/hooks/{item_id}")
    if area == "applications":
        if action == "list":
            return rest("GET", "/applications")
        g = _gate(confirm, f"{action} OAuth application")
        if g:
            return g
        if action == "create":
            return rest("POST", "/applications", body=params)
        if action == "delete":
            return rest("DELETE", f"/applications/{item_id}")
    if area == "topics":
        if action == "list":
            return rest("GET", "/topics")
        g = _gate(confirm, f"{action} topic")
        if g:
            return g
        if action == "create":
            return rest("POST", "/topics", body=params)
        if action == "update":
            return rest("PUT", f"/topics/{item_id}", body=params)
        if action == "delete":
            return rest("DELETE", f"/topics/{item_id}")
    if area == "namespaces":
        return rest("GET", "/namespaces", params=_clean({"search": (params or {}).get("search"), "per_page": 100}))
    if area == "keys":
        if item_id:
            return rest("GET", f"/keys/{item_id}")
        return rest("GET", "/keys", params=params)
    if area == "plan_limits":
        if action == "get" or action == "list":
            return rest("GET", "/application/plan_limits")
        g = _gate(confirm, "change plan limits")
        if g:
            return g
        return rest("PUT", "/application/plan_limits", params=params)
    if area == "appearance":
        if action == "get" or action == "list":
            return rest("GET", "/application/appearance")
        g = _gate(confirm, "change instance appearance")
        if g:
            return g
        return rest("PUT", "/application/appearance", params=params)
    if area == "features":
        if action == "list":
            return rest("GET", "/features")
        g = _gate(confirm, f"{action} instance feature flag '{item_id}'")
        if g:
            return g
        if action == "set":
            return rest("POST", f"/features/{quote(item_id or '', safe='')}", body=params)
        if action == "delete":
            return rest("DELETE", f"/features/{quote(item_id or '', safe='')}")
    return {"error": True, "message": f"unknown area/action '{area}/{action}'"}


# --------------------------------------------------------------------------- #
# Curated: search, releases, environments, hooks, misc                        #
# --------------------------------------------------------------------------- #
@mcp.tool()
def search_gitlab(term: str, scope: str = "projects", project: Optional[str] = None,
                  group: Optional[str] = None, limit: int = 20) -> Any:
    """Search the instance. scope: projects|issues|merge_requests|milestones|users|
    snippet_titles; within a project also: blobs (code!)|commits|wiki_blobs|notes.

    Code search (blobs) works per-project on CE without Elasticsearch; global code
    search needs Elasticsearch (not configured ⇒ 400 error).
    """
    params = {"scope": scope, "search": term, "per_page": min(limit, 100)}
    if project:
        return rest("GET", f"/projects/{_proj(project)}/search", params=params)
    if group:
        return rest("GET", f"/groups/{_proj(group)}/search", params=params)
    return rest("GET", "/search", params=params)


@mcp.tool()
def releases(project: str, action: str = "list", tag_name: Optional[str] = None,
             params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Releases: list|get|create|update|delete|links|link_create|link_delete.

    create: params={tag_name, ref? (if tag doesn't exist), name?, description?,
    assets?{links:[{name,url}]}}. Writes require confirm=true.
    """
    p = _proj(project)
    if action == "list":
        return rest("GET", f"/projects/{p}/releases")
    if action == "get":
        return rest("GET", f"/projects/{p}/releases/{quote(tag_name or '', safe='')}")
    if action == "links":
        return rest("GET", f"/projects/{p}/releases/{quote(tag_name or '', safe='')}/assets/links")
    g = _gate(confirm, f"{action} release '{tag_name or (params or {}).get('tag_name')}' in {project}")
    if g:
        return g
    if action == "create":
        return rest("POST", f"/projects/{p}/releases", body=params)
    if action == "update":
        return rest("PUT", f"/projects/{p}/releases/{quote(tag_name or '', safe='')}", body=params)
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/releases/{quote(tag_name or '', safe='')}")
    if action == "link_create":
        return rest("POST", f"/projects/{p}/releases/{quote(tag_name or '', safe='')}/assets/links", body=params)
    if action == "link_delete":
        link_id = (params or {}).get("link_id")
        return rest("DELETE", f"/projects/{p}/releases/{quote(tag_name or '', safe='')}/assets/links/{link_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def environments(project: str, action: str = "list", environment_id: Optional[int] = None,
                 params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Environments & deployments: list|get|create|update|delete|stop|deployments|deployment_get.

    create: params={name, external_url?, tier?}. deployments lists recent deploys.
    Writes require confirm=true.
    """
    p = _proj(project)
    if action == "list":
        return rest("GET", f"/projects/{p}/environments", params=params)
    if action == "get":
        return rest("GET", f"/projects/{p}/environments/{environment_id}")
    if action == "deployments":
        return rest("GET", f"/projects/{p}/deployments",
                    params=_clean({"per_page": 20, **(params or {})}))
    if action == "deployment_get":
        return rest("GET", f"/projects/{p}/deployments/{environment_id}")
    g = _gate(confirm, f"{action} environment {environment_id or '(new)'} in {project}")
    if g:
        return g
    if action == "create":
        return rest("POST", f"/projects/{p}/environments", body=params)
    if action == "update":
        return rest("PUT", f"/projects/{p}/environments/{environment_id}", body=params)
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/environments/{environment_id}")
    if action == "stop":
        return rest("POST", f"/projects/{p}/environments/{environment_id}/stop", body=params)
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def deploy_credentials(kind: str = "keys", scope_type: str = "project",
                       scope_id: Optional[str] = None, action: str = "list",
                       item_id: Optional[int] = None, params: Optional[dict] = None,
                       confirm: bool = False) -> Any:
    """Deploy keys & deploy tokens. kind: keys|tokens. scope_type: project|group|instance.

    keys are project-scoped SSH read[/write] keys (instance list is admin-only).
    tokens are registry/repo pull credentials. create key: params={title, key, can_push?}.
    create token: params={name, scopes:[read_repository|read_registry|...], expires_at?}.
    Writes require confirm=true.
    """
    if kind == "keys":
        if scope_type == "instance":
            return rest("GET", "/deploy_keys")
        base = f"/projects/{_proj(scope_id)}/deploy_keys"
    else:
        if scope_type == "instance":
            return rest("GET", "/deploy_tokens")
        base = f"/{'projects' if scope_type == 'project' else 'groups'}/{_proj(scope_id)}/deploy_tokens"
    if action == "list":
        return rest("GET", base)
    if action == "get":
        return rest("GET", f"{base}/{item_id}")
    g = _gate(confirm, f"{action} deploy {kind} on {scope_type} {scope_id}")
    if g:
        return g
    if action == "create":
        return rest("POST", base, body=params)
    if action == "update":
        return rest("PUT", f"{base}/{item_id}", body=params)
    if action == "delete":
        return rest("DELETE", f"{base}/{item_id}")
    if action == "enable":
        return rest("POST", f"{base}/{item_id}/enable")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def webhooks(scope_type: str = "project", scope_id: Optional[str] = None,
             action: str = "list", hook_id: Optional[int] = None,
             params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Webhooks: list|get|create|update|delete|test. scope_type: project|system.

    create: params={url, push_events?, merge_requests_events?, issues_events?,
    pipeline_events?, token?, enable_ssl_verification?}. test: params={trigger:
    "push_events"}. (Group hooks are EE-only — 404 on CE.) Writes require confirm=true.
    """
    if scope_type == "system":
        base = "/hooks"
    elif scope_type == "group":
        base = f"/groups/{_proj(scope_id)}/hooks"
    else:
        base = f"/projects/{_proj(scope_id)}/hooks"
    if action == "list":
        return rest("GET", base)
    if action == "get":
        return rest("GET", f"{base}/{hook_id}")
    g = _gate(confirm, f"{action} webhook {hook_id or '(new)'} on {scope_type} {scope_id or ''}")
    if g:
        return g
    if action == "create":
        return rest("POST", base, body=params)
    if action == "update":
        return rest("PUT", f"{base}/{hook_id}", body=params)
    if action == "delete":
        return rest("DELETE", f"{base}/{hook_id}")
    if action == "test":
        trigger = (params or {}).get("trigger", "push_events")
        return rest("POST", f"{base}/{hook_id}/test/{trigger}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def integrations(project: str, action: str = "list", name: Optional[str] = None,
                 params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Project integrations (Slack, Jira, Discord, webhooks-as-services, ...):
    list|get|update|disable. update: name (slug) + params with the integration's
    fields. Writes require confirm=true."""
    p = _proj(project)
    if action == "list":
        return rest("GET", f"/projects/{p}/integrations")
    if action == "get":
        return rest("GET", f"/projects/{p}/integrations/{name}")
    g = _gate(confirm, f"{action} integration '{name}' on {project}")
    if g:
        return g
    if action == "update":
        return rest("PUT", f"/projects/{p}/integrations/{name}", body=params)
    if action == "disable":
        return rest("DELETE", f"/projects/{p}/integrations/{name}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def snippets(scope: str = "personal", project: Optional[str] = None, action: str = "list",
             snippet_id: Optional[int] = None, params: Optional[dict] = None,
             confirm: bool = False) -> Any:
    """Snippets: scope personal|all (admin)|public|project. action: list|get|raw|create|update|delete.

    create: params={title, files:[{file_path, content}], visibility}. Writes need confirm=true.
    """
    if scope == "project" and project:
        base = f"/projects/{_proj(project)}/snippets"
    elif scope == "all":
        base = "/snippets/all"
    elif scope == "public":
        base = "/snippets/public"
    else:
        base = "/snippets"
    if action == "list":
        return rest("GET", base, params={"per_page": 50})
    root = f"/projects/{_proj(project)}/snippets" if project else "/snippets"
    if action == "get":
        return rest("GET", f"{root}/{snippet_id}")
    if action == "raw":
        return rest("GET", f"{root}/{snippet_id}/raw")
    g = _gate(confirm, f"{action} snippet {snippet_id or '(new)'}")
    if g:
        return g
    if action == "create":
        return rest("POST", root, body=params)
    if action == "update":
        return rest("PUT", f"{root}/{snippet_id}", body=params)
    if action == "delete":
        return rest("DELETE", f"{root}/{snippet_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def wikis(project: str, action: str = "list", slug: Optional[str] = None,
          params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Project wiki pages: list|get|create|update|delete.

    create/update: params={title, content, format?}. Writes require confirm=true.
    (Group wikis are EE-only.)
    """
    p = _proj(project)
    if action == "list":
        return rest("GET", f"/projects/{p}/wikis", params={"with_content": 0})
    if action == "get":
        return rest("GET", f"/projects/{p}/wikis/{quote(slug or '', safe='')}")
    g = _gate(confirm, f"{action} wiki page '{slug or (params or {}).get('title')}' in {project}")
    if g:
        return g
    if action == "create":
        return rest("POST", f"/projects/{p}/wikis", body=params)
    if action == "update":
        return rest("PUT", f"/projects/{p}/wikis/{quote(slug or '', safe='')}", body=params)
    if action == "delete":
        return rest("DELETE", f"/projects/{p}/wikis/{quote(slug or '', safe='')}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def packages(scope_type: str = "project", scope_id: Optional[str] = None,
             action: str = "list", package_id: Optional[int] = None,
             params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Package registry (npm/pypi/maven/generic/...): list|get|files|delete.

    scope_type: project|group. delete requires confirm=true.
    """
    base = f"/{'projects' if scope_type == 'project' else 'groups'}/{_proj(scope_id)}/packages"
    if action == "list":
        return rest("GET", base, params=_clean({"per_page": 50, **(params or {})}))
    if action == "get":
        return rest("GET", f"{base}/{package_id}")
    if action == "files":
        return rest("GET", f"{base}/{package_id}/package_files")
    g = _gate(confirm, f"delete package {package_id} from {scope_type} {scope_id}")
    if g:
        return g
    if action == "delete":
        return rest("DELETE", f"{base}/{package_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def container_registry(scope_type: str = "project", scope_id: Optional[str] = None,
                       action: str = "repositories", repository_id: Optional[int] = None,
                       tag_name: Optional[str] = None, params: Optional[dict] = None,
                       confirm: bool = False) -> Any:
    """Container registry: repositories|tags|tag_get|tag_delete|tags_bulk_delete|repo_delete.

    tags_bulk_delete: params={name_regex_delete, keep_n?, older_than?}. Deletes need
    confirm=true. 404 everywhere usually means the registry isn't enabled on the instance.
    """
    p = _proj(scope_id)
    if action == "repositories":
        base = f"/{'projects' if scope_type == 'project' else 'groups'}/{p}/registry/repositories"
        return rest("GET", base, params={"tags_count": True})
    if action == "tags":
        return rest("GET", f"/projects/{p}/registry/repositories/{repository_id}/tags",
                    params={"per_page": 50})
    if action == "tag_get":
        return rest("GET", f"/projects/{p}/registry/repositories/{repository_id}/tags/{tag_name}")
    g = _gate(confirm, f"{action} on registry repo {repository_id} ({scope_id})")
    if g:
        return g
    if action == "tag_delete":
        return rest("DELETE", f"/projects/{p}/registry/repositories/{repository_id}/tags/{tag_name}")
    if action == "tags_bulk_delete":
        return rest("DELETE", f"/projects/{p}/registry/repositories/{repository_id}/tags", params=params)
    if action == "repo_delete":
        return rest("DELETE", f"/projects/{p}/registry/repositories/{repository_id}")
    return {"error": True, "message": f"unknown action '{action}'"}


@mcp.tool()
def todos_and_events(action: str = "todos", target_id: Optional[int] = None,
                     project: Optional[str] = None, user: Optional[str] = None,
                     params: Optional[dict] = None, confirm: bool = False) -> Any:
    """Activity: todos|todo_done|todos_done_all|my_events|user_events|project_events.

    todo_done marks one todo done (target_id); todos_done_all marks everything
    (both need confirm=true).
    """
    if action == "todos":
        return rest("GET", "/todos", params=_clean({"per_page": 50, **(params or {})}))
    if action == "my_events":
        return rest("GET", "/events", params=_clean({"per_page": 30, **(params or {})}))
    if action == "user_events":
        return rest("GET", f"/users/{user}/events", params={"per_page": 30})
    if action == "project_events":
        return rest("GET", f"/projects/{_proj(project)}/events", params={"per_page": 30})
    g = _gate(confirm, f"mark todo(s) done ({target_id or 'ALL'})")
    if g:
        return g
    if action == "todo_done":
        return rest("POST", f"/todos/{target_id}/mark_as_done")
    if action == "todos_done_all":
        return rest("POST", "/todos/mark_as_done")
    return {"error": True, "message": f"unknown action '{action}'"}


# --------------------------------------------------------------------------- #
# Selftest — live read-only audit of every domain (no mutations)              #
# --------------------------------------------------------------------------- #
def _selftest() -> int:  # pragma: no cover
    """Read-only sweep across every domain + safe write-endpoint probes.

    A write probe sends an intentionally-invalid request (missing params) and treats
    400/422 as 'endpoint exists'; 404 as 'absent (or EE-only)'; nothing is mutated.
    """
    checks: list[tuple[str, str, Any]] = []

    def chk(domain: str, label: str, result: Any, ok_when=None):
        if isinstance(result, dict) and result.get("error"):
            status = result.get("status")
            verdict = f"FAIL({status})"
            if ok_when and status in ok_when:
                verdict = f"OK(status {status} = endpoint exists)"
        else:
            verdict = "OK"
        checks.append((domain, label, verdict))
        print(f"  [{verdict:>26}] {domain}: {label}", file=sys.stderr)

    tp = os.environ.get("GITLAB_TEST_PROJECT", "gregory/hermes-vault")
    tg = os.environ.get("GITLAB_TEST_GROUP", "gregory")

    print("== core ==", file=sys.stderr)
    chk("core", "metadata", rest("GET", "/metadata"))
    chk("core", "statistics", rest("GET", "/application/statistics"))
    chk("core", "current user", rest("GET", "/user"))
    chk("core", "token self", rest("GET", "/personal_access_tokens/self"))
    chk("core", "graphql currentUser", gql("{ currentUser { username } }"))

    print("== projects/repo ==", file=sys.stderr)
    chk("projects", "list", rest("GET", "/projects", params={"per_page": 2}))
    chk("projects", "get by path", rest("GET", f"/projects/{_proj(tp)}"))
    chk("projects", "languages", rest("GET", f"/projects/{_proj(tp)}/languages"))
    chk("repo", "tree", rest("GET", f"/projects/{_proj(tp)}/repository/tree", params={"per_page": 5}))
    chk("repo", "branches", rest("GET", f"/projects/{_proj(tp)}/repository/branches"))
    chk("repo", "protected branches", rest("GET", f"/projects/{_proj(tp)}/protected_branches"))
    chk("repo", "tags", rest("GET", f"/projects/{_proj(tp)}/repository/tags"))
    chk("repo", "commits", rest("GET", f"/projects/{_proj(tp)}/repository/commits", params={"per_page": 2}))
    chk("repo", "contributors", rest("GET", f"/projects/{_proj(tp)}/repository/contributors"))

    print("== collaboration ==", file=sys.stderr)
    chk("mrs", "list all", rest("GET", "/merge_requests", params={"scope": "all", "state": "all", "per_page": 2}))
    chk("issues", "list all", rest("GET", "/issues", params={"scope": "all", "state": "all", "per_page": 2}))
    chk("issues", "statistics", rest("GET", "/issues_statistics", params={"scope": "all"}))
    chk("labels", "project labels", rest("GET", f"/projects/{_proj(tp)}/labels"))
    chk("milestones", "project milestones", rest("GET", f"/projects/{_proj(tp)}/milestones"))
    chk("boards", "project boards", rest("GET", f"/projects/{_proj(tp)}/boards"))
    chk("discussions", "issue notes probe", rest("GET", f"/projects/{_proj(tp)}/issues", params={"per_page": 1}))

    print("== ci/cd ==", file=sys.stderr)
    chk("pipelines", "list", rest("GET", f"/projects/{_proj(tp)}/pipelines", params={"per_page": 2}))
    chk("jobs", "list", rest("GET", f"/projects/{_proj(tp)}/jobs", params={"per_page": 2}))
    chk("ci vars", "project", rest("GET", f"/projects/{_proj(tp)}/variables"))
    chk("ci vars", "group", rest("GET", f"/groups/{_proj(tg)}/variables"))
    chk("ci vars", "instance (admin)", rest("GET", "/admin/ci/variables"))
    chk("schedules", "list", rest("GET", f"/projects/{_proj(tp)}/pipeline_schedules"))
    chk("triggers", "list", rest("GET", f"/projects/{_proj(tp)}/triggers"))
    chk("runners", "all (admin)", rest("GET", "/runners/all"))
    chk("lint", "project ci lint GET", rest("GET", f"/projects/{_proj(tp)}/ci/lint"))
    chk("job token scope", "get", rest("GET", f"/projects/{_proj(tp)}/job_token_scope"))

    print("== users/groups/admin ==", file=sys.stderr)
    chk("users", "list", rest("GET", "/users", params={"per_page": 2}))
    chk("groups", "list", rest("GET", "/groups", params={"per_page": 2}))
    chk("members", "project members/all", rest("GET", f"/projects/{_proj(tp)}/members/all"))
    chk("tokens", "all PATs (admin)", rest("GET", "/personal_access_tokens", params={"per_page": 2}))
    chk("admin", "settings", rest("GET", "/application/settings"))
    chk("admin", "sidekiq compound_metrics", rest("GET", "/sidekiq/compound_metrics"))
    chk("admin", "broadcast_messages", rest("GET", "/broadcast_messages"))
    chk("admin", "system hooks", rest("GET", "/hooks"))
    chk("admin", "applications", rest("GET", "/applications"))
    chk("admin", "topics", rest("GET", "/topics"))
    chk("admin", "namespaces", rest("GET", "/namespaces", params={"per_page": 2}))
    chk("admin", "plan_limits", rest("GET", "/application/plan_limits"))
    chk("admin", "appearance", rest("GET", "/application/appearance"))
    chk("admin", "instance feature flags", rest("GET", "/features"))
    chk("admin", "deploy_keys (all)", rest("GET", "/deploy_keys"))
    chk("admin", "deploy_tokens (all)", rest("GET", "/deploy_tokens"))

    print("== search/releases/deploy/misc ==", file=sys.stderr)
    chk("search", "global projects", rest("GET", "/search", params={"scope": "projects", "search": "a"}))
    chk("search", "project blobs (code)", rest("GET", f"/projects/{_proj(tp)}/search",
                                               params={"scope": "blobs", "search": "the"}))
    chk("releases", "list", rest("GET", f"/projects/{_proj(tp)}/releases"))
    chk("environments", "list", rest("GET", f"/projects/{_proj(tp)}/environments"))
    chk("deployments", "list", rest("GET", f"/projects/{_proj(tp)}/deployments"))
    chk("freeze", "freeze_periods", rest("GET", f"/projects/{_proj(tp)}/freeze_periods"))
    chk("hooks", "project hooks", rest("GET", f"/projects/{_proj(tp)}/hooks"))
    chk("integrations", "list", rest("GET", f"/projects/{_proj(tp)}/integrations"))
    chk("snippets", "personal", rest("GET", "/snippets"))
    chk("snippets", "all (admin)", rest("GET", "/snippets/all", params={"per_page": 2}))
    chk("wikis", "project wikis", rest("GET", f"/projects/{_proj(tp)}/wikis"))
    chk("todos", "list", rest("GET", "/todos", params={"per_page": 2}))
    chk("events", "my events", rest("GET", "/events", params={"per_page": 2}))
    chk("packages", "project", rest("GET", f"/projects/{_proj(tp)}/packages"))
    chk("registry", "project repos", rest("GET", f"/projects/{_proj(tp)}/registry/repositories"))
    chk("badges", "project", rest("GET", f"/projects/{_proj(tp)}/badges"))
    chk("mirrors", "remote_mirrors", rest("GET", f"/projects/{_proj(tp)}/remote_mirrors"))
    chk("feature flags", "project", rest("GET", f"/projects/{_proj(tp)}/feature_flags"))
    chk("error tracking", "settings", rest("GET", f"/projects/{_proj(tp)}/error_tracking/settings"))
    chk("pages", "project pages", rest("GET", f"/projects/{_proj(tp)}/pages"))
    chk("clusters", "cluster_agents", rest("GET", f"/projects/{_proj(tp)}/cluster_agents"))
    chk("notifications", "settings", rest("GET", "/notification_settings"))
    chk("markdown", "render", rest("POST", "/markdown", body={"text": "**hi**"}))
    chk("misc", "avatar", rest("GET", "/avatar", params={"email": "x@example.com"}))
    chk("storage moves", "project moves (admin)", rest("GET", "/project_repository_storage_moves",
                                                       params={"per_page": 2}))

    print("== EE-only probes (expect 404 on CE) ==", file=sys.stderr)
    chk("EE", "epics", rest("GET", f"/groups/{_proj(tg)}/epics"), ok_when=())
    chk("EE", "iterations", rest("GET", f"/groups/{_proj(tg)}/iterations"), ok_when=())
    chk("EE", "merge_trains", rest("GET", f"/projects/{_proj(tp)}/merge_trains"), ok_when=())
    chk("EE", "audit_events", rest("GET", "/audit_events"), ok_when=())
    chk("EE", "license", rest("GET", "/license"), ok_when=())
    chk("EE", "group hooks", rest("GET", f"/groups/{_proj(tg)}/hooks"), ok_when=())
    chk("EE", "group wikis", rest("GET", f"/groups/{_proj(tg)}/wikis"), ok_when=())
    chk("EE", "protected environments", rest("GET", f"/projects/{_proj(tp)}/protected_environments"), ok_when=())

    print("== safe write-endpoint probes (no mutation: invalid params → 400 proves existence) ==", file=sys.stderr)
    chk("write-probe", "POST /projects (no body)", rest("POST", "/projects"), ok_when=(400,))
    chk("write-probe", "POST branches (no params)",
        rest("POST", f"/projects/{_proj(tp)}/repository/branches"), ok_when=(400,))
    chk("write-probe", "POST commits (no body)",
        rest("POST", f"/projects/{_proj(tp)}/repository/commits"), ok_when=(400,))
    chk("write-probe", "POST MR (no body)",
        rest("POST", f"/projects/{_proj(tp)}/merge_requests"), ok_when=(400,))
    chk("write-probe", "POST issue (no body)",
        rest("POST", f"/projects/{_proj(tp)}/issues"), ok_when=(400,))
    chk("write-probe", "POST pipeline (no ref)",
        rest("POST", f"/projects/{_proj(tp)}/pipeline"), ok_when=(400,))
    chk("write-probe", "POST users (no body, admin)", rest("POST", "/users"), ok_when=(400,))
    chk("write-probe", "POST groups (no body)", rest("POST", "/groups"), ok_when=(400,))
    chk("write-probe", "POST hooks (no url)",
        rest("POST", f"/projects/{_proj(tp)}/hooks"), ok_when=(400,))
    chk("write-probe", "POST /user/runners (no body)", rest("POST", "/user/runners"), ok_when=(400,))
    chk("write-probe", "POST release (no body)",
        rest("POST", f"/projects/{_proj(tp)}/releases"), ok_when=(400,))
    chk("write-probe", "POST project variable (no body)",
        rest("POST", f"/projects/{_proj(tp)}/variables"), ok_when=(400,))
    chk("write-probe", "PUT app settings (no params)", rest("PUT", "/application/settings"),
        ok_when=(400,))

    fails = [c for c in checks if c[2].startswith("FAIL")]
    print(f"\n{len(checks)} checks, {len(fails)} failures", file=sys.stderr)
    for d, l, v in fails:
        print(f"  FAIL {d}: {l} -> {v}", file=sys.stderr)
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    log(f"starting GitLab MCP server for {CONFIG['base_url']}")
    mcp.run()
