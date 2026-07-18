# ML Model Registry, experiment tracking, CI Catalog — and the honest AI story

Verified live against `git.hively.dev` (GitLab 19.0.0 **CE**). The ML/model side works on CE;
GitLab **Duo / AI is EE-gated and 404s here**. Tools: `model_registry`, `ci_catalog`.

## What works on CE (verified live)

### ML Model Registry (`model_registry` tool)
GitLab has a built-in model registry + experiment tracking, **MLflow-compatible**. All CE.
- **Models**: `model_registry(project, action="models")` — GraphQL `project.mlModels`
  (id, name, versionCount, description, latestVersion, createdAt). Verified: returns a valid
  `{mlModels:{count,nodes}}` structure.
- **Experiments**: `model_registry(project, action="experiments")` — `project.mlExperiments`
  (id, name, candidateCount) — runs/candidates tracked per experiment.
- **MLflow REST passthrough**: `model_registry(project, action="mlflow", mlflow_path=...)` →
  `GET /projects/:id/ml/mlflow/api/2.0/mlflow/<path>`. Verified working:
  `registered-models/search` → `{registered_models:[], next_page_token}`. Other MLflow 2.0
  paths: `model-versions/search`, `runs/search`, `experiments/search`, `registered-models/get`.
- **Artifacts**: `model_registry(project, action="packages")` → `packages?package_type=ml_model`.

**Logging a model from CI** (the intended workflow): point an MLflow client at the tracking URI
`https://git.hively.dev/api/v4/projects/<id>/ml/mlflow`, authenticate with a token in
`MLFLOW_TRACKING_TOKEN` (a masked CI/CD variable), and `mlflow.log_model(...)` /
`mlflow.register_model(...)` from a `templates/ci/python.yml`-style job. The models then appear
via `model_registry(..., action="models")`.

### CI/CD Catalog (`ci_catalog` tool)
Reusable pipeline **components** published across the instance (CE). Verified:
`ci_catalog(action="list")` → `{ciCatalogResources:{count,nodes:{id,name,description,webPath,
starCount}}}`. Per-project: `ci_catalog(action="resource"/"versions", project=...)`. Use a
component in `.gitlab-ci.yml`: `include: - component: git.hively.dev/<path>@<version>`.

Also CE-available (from the prior build's verified notes): work items, secure files, service
desk (needs incoming-email), terraform state/module registry, direct-transfer imports
(`/bulk_imports`), achievements, alert management.

## What does NOT work on this CE instance (verified 404 / absent)

- **GitLab Duo / AI code suggestions**: `/code_suggestions/completions` → **404**.
- **Duo Agent Platform / AI workflows**: `/ai/duo_workflows/workflows` → **404**.
- **Duo Chat / AI GraphQL**: `aiChatAvailableModels` and the `ai*`/`duo*` GraphQL fields
  **don't exist in the schema** on this edition (`"Field 'aiChatAvailableModels' doesn't exist"`).

These are Premium/Ultimate + a Duo add-on. If a license is later applied, the REST routes and
GraphQL fields become available — reach them with `gitlab_rest`/`gitlab_graphql`; don't build a
curated tool against them until the instance actually has them (they'd 404 today).

## Honest framing when asked about "AI features"

On this CE instance, "AI/ML" means the **model registry + MLflow experiment tracking + CI
catalog** — real, working, and covered by `model_registry`/`ci_catalog`. GitLab's *generative* AI
(Duo chat, code suggestions, AI-native agent flows) is **not available** here. Never present Duo
as working; point to the model registry as the CE-real capability, and note Duo needs an
EE license + Duo add-on.
