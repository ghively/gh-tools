# Packages & registry — formats, push/pull, cleanup, dependency proxy

GitLab's package registry is one service with many format-specific facades. This file covers
which formats work on CE, how to push and pull each, cleanup policies, and how the container
registry + dependency proxy fit in.

## Package registry vs container registry vs dependency proxy

| Service | What it stores | Endpoint | Tier |
|---|---|---|---|
| **Package registry** | language packages (npm, pypi, maven, etc.) + generic files | `/api/v4/projects/:id/packages/...` | Free |
| **Container registry** | Docker / OCI images | `:5050` (separate port or path) + `/api/v4/projects/:id/registry/...` | Free (needs registry service) |
| **Dependency proxy** (group) | Docker image pull-through cache | `/groups/:id/dependency_proxy/containers` + GraphQL `dependencyProxySetting` | Free (group-level) |
| **Terraform Module registry** | terraform modules | `/api/v4/packages/terraform/modules/v1/...` | Free |
| **Terraform state** | terraform state files | `/projects/:id/terraform/state/:name` (CLI protocol) | Free |

All of these work on CE. The `packages` and `container_registry` MCP tools cover the read/
delete side; pushes use format-specific protocols documented here.

## Package formats supported on CE (and their endpoints)

| Format | Push | Pull | Notes |
|---|---|---|---|
| **generic** | `PUT /projects/:id/packages/generic/:name/:ver/:file` | `GET /projects/:id/packages/generic/:name/:ver/:file` | the universal fallback — any file, any version |
| **npm** | npm CLI configured against `https://gitlab.example.com/api/v4/projects/:id/packages/npm/` | same | scope with `@scope:registry=...` |
| **pypi** | twine upload | pip install `--index-url https://gitlab.example.com/api/v4/projects/:id/packages/pypi/simple` | needs `~/.pypirc` |
| **maven** | mvn deploy | mvn dependency get | `<repository>` URL with basic auth |
| **nuget** | dotnet nuget push | dotnet add package | source URL `https://gitlab.example.com/api/v4/projects/:id/packages/nuget/index.json` |
| **conda** | anaconda upload | conda install | less common |
| **composer** (PHP) | not user-pushable; tagged releases create packages | composer require | from git tags |
| **conan** (C++) | conan upload | conan install | recipe + binary packages |
| **debian** | `PUT /projects/:id/packages/debian` with `deb` file | apt-get install | needs distribution + component |
| **helm** | `helm cm-push` or curl PUT | `helm install` from repo | chart packages |
| **rubygems** | gem push | gem install | configured source |
| **terraform modules** | pushed as git tags | terraform init module block | module registry protocol |

## Pushing a generic package (the universal pattern)

```
curl --request PUT \
  --header "PRIVATE-TOKEN: <token>" \
  --upload-file path/to/file.tgz \
  "https://gitlab.example.com/api/v4/projects/<id>/packages/generic/<name>/<version>/<filename>"
```
Then `packages(project, action="get", package_id=N)` lists it, and anyone with read access
can pull via the matching GET URL. Use generic packages for: build artifacts you want to
share across projects, ML model binaries, release assets that don't fit Releases' link model.

## Listing, inspecting, deleting

```
packages(scope_type="project", scope_id=<pid>, action="list")           # all packages
packages(scope_type="group",  scope_id=<gid>, action="list")            # across a group
packages(..., action="get", package_id=N)                               # one package
packages(..., action="files", package_id=N)                             # files in a package
packages(..., action="delete", package_id=N, confirm=true)              # delete the whole package
```
For deleting a single file within a package: `gitlab_rest("DELETE",
"/projects/:id/packages/:pkgid/package_files/:fileid", confirm=true)`.

## Cleanup policies (keep the registry from exploding)

Each project can have a **packages cleanup policy** + a **container registry cleanup
policy** that prunes old versions. Configure via:

```
manage_project(action="update", project=..., params={
    "packages_cleanup_policy": {...}      # or via the dedicated endpoint
}, confirm=true)

# container registry cleanup:
gitlab_rest("PUT", "/projects/:id", body={
    "container_expiration_policy": {
        "enabled": true, "cadence": "1d", "keep_n": 10,
        "older_than": "90d", "name_regex": ".*"
    }
}, confirm=true)
```

A practical default: keep the last 10 versions, prune older than 90 days, exclude
`latest`/`stable`-named tags. `get_project(...)` shows the current
`container_expiration_policy` block.

## Container registry (Docker images)

The container registry runs on a separate endpoint (port `5050` here). Push via standard
docker:

```
docker login gitlab.example.com:5050 -u <username> -p <token>
docker tag myimage:latest gitlab.example.com:5050/myteam/myproj/myimage:latest
docker push gitlab.example.com:5050/myteam/myproj/myimage:latest
```
Read/manage via the `container_registry` MCP tool:
- `container_registry(action="repositories", scope_id=<pid>)` — list image repos.
- `container_registry(action="tags", repository_id=N)` — tags for a repo.
- `container_registry(action="tags_bulk_delete", repository_id=N,
  params={name_regex_delete: ".*-dev", keep_n: 5, older_than: "30d"}, confirm=true)`.

## Container + package protection rules (Free)

Tag-protection rules prevent non-Maintainers from pushing/deleting certain image tags. Same
shape exists for packages:

```
gitlab_rest("POST", "/projects/:id/registry/protection/repository/rules",
    body={minimum_access_level_for_push, minimum_access_level_for_delete,
          name_regex}, confirm=true)
gitlab_rest("POST", "/projects/:id/packages/protection/rules",
    body={package_name_pattern, package_type, minimum_access_level_for_push}, confirm=true)
```

## Dependency proxy (group-level Docker cache)

The dependency proxy lets a group pull Docker images through GitLab, caching upstream
images so you don't re-pull from Docker Hub on every job. Read its state via GraphQL:

```
dependency_proxy(group="myteam", action="settings")
# → {enabled: true, identity: null} on this instance
```
Pull through it: `docker pull gitlab.example.com:5050/myteam/<upstream-image>:tag` (GitLab
fetches and caches on first pull). Purge the cache:
`dependency_proxy(group, action="purge_cache", confirm=true)`.

## What doesn't work on CE

- **Package protection rule *enforcement* on push** works on Free; UI visibility of policy
  state varies. The rules themselves are Free.
- **Dependency proxy for npm/Maven packages** is Premium (the Docker proxy is Free).
- **Generic package rate limits** are per-project; high-throughput package servers should
  use a real artifact store (Nexus, Artifactory) and mirror into GitLab.

## Practical patterns

- **Build artifacts as generic packages**: `PUT /packages/generic/<proj>/<ci-commit-sha>/
  build.tar.gz` from a CI job, then downstream jobs / deploy scripts pull by SHA. Stable
  URLs, no separate artifact store.
- **Release assets via release links + generic packages**: publish to Releases (UI-visible)
  but store the actual binary as a generic package (stable URL, versioned, deletable).
- **Container registry + CI**: use `docker-build-push.yml` template; tag by `$CI_COMMIT_SHA`
  and additionally `:latest` only on the default branch (the template does this).
- **Cleanup**: set the container expiration policy on every project that builds images;
  without it, the registry grows unbounded.
