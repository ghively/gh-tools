# ML Model Registry, experiment tracking, CI Catalog — and the honest AI story

Verified live against `gitlab.example.com` (GitLab 19.x **CE**). The ML/model side works on CE;
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
`https://gitlab.example.com/api/v4/projects/<id>/ml/mlflow`, authenticate with a token in
`MLFLOW_TRACKING_TOKEN` (a masked CI/CD variable), and `mlflow.log_model(...)` /
`mlflow.register_model(...)` from a `templates/ci/python.yml`-style job. The models then appear
via `model_registry(..., action="models")`.

### CI/CD Catalog (`ci_catalog` tool)
Reusable pipeline **components** published across the instance (CE). Verified:
`ci_catalog(action="list")` → `{ciCatalogResources:{count,nodes:{id,name,description,webPath,
starCount}}}`. Per-project: `ci_catalog(action="resource"/"versions", project=...)`. Use a
component in `.gitlab-ci.yml`: `include: - component: gitlab.example.com/<path>@<version>`.

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

## ML model lifecycle (the intended workflow)

1. **Train in CI** (a `templates/ci/python.yml`-style job): point an MLflow client at
   `MLFLOW_TRACKING_URI=https://gitlab.example.com/api/v4/projects/<id>/ml/mlflow`, authenticate
   with `MLFLOW_TRACKING_TOKEN` (a masked CI/CD variable — `ci_variables(..., action="create",
   params={masked: true})`), and:
   ```python
   import mlflow
   mlflow.set_experiment("my-experiment")
   with mlflow.start_run():
       mlflow.log_param("epochs", 10)
       mlflow.log_metric("accuracy", 0.94)
       mlflow.log_artifact("model.pkl")           # uploaded as a package
       mlflow.register_model("runs:/<run_id>/model", "my-model")  # creates a version
   ```
2. **Inspect**: `model_registry(project, action="models")` lists registered models + versions;
   `action="experiments"` shows runs/candidates; `action="packages"` lists artifact files.
3. **MLflow REST passthrough**: `model_registry(project, action="mlflow",
   mlflow_path="registered-models/search", params={})` — full MLflow 2.0 API:
   - `registered-models/{search,get,create,delete}` — model registry CRUD.
   - `model-versions/{search,get,create,delete,transition-stage}` — version lifecycle.
   - `runs/{search,get,delete}` — experiment runs.
   - `experiments/{search,get,create,delete}` — experiment CRUD.
4. **Deploy**: transition a version's stage (`model-versions/transition-stage` via MLflow REST)
   from `None` → `Staging` → `Production`. Downstream inference services query the
   `Production`-stage version.

## CI Catalog component authoring

A project becomes a catalog resource when:
1. The project has the catalog feature enabled (UI: Settings → CI/CD → CI/CD Catalog resource).
2. It contains `templates/` directory with component `.yml` files (a component = one reusable
   job template).
3. A version is cut (git tag `vX.Y.Z`).

Consumers include it: `include: - component: gitlab.example.com/<group>/<proj>/<component>@<version>`.
Inspect via `ci_catalog(action="list")` (instance) / `ci_catalog(action="resource"|"versions",
project=...)`. Use cases: org-wide deploy components, security scanning wrappers, language-
specific test templates — anything you'd otherwise copy-paste across projects.

## What Duo would unlock (if a license is later applied)

For planning, here's the EE-only AI surface that a Premium+Duo license adds:
- **Code Suggestions** — inline AI completions in the editor / MR diff.
- **Duo Chat** — conversational AI for explaining code, writing tests, fixing bugs.
- **Duo Workflow** — multi-step AI workflows (refactor across files, generate features).
- **Self-hosted models** (`aiSelfHostedModels`) — point Duo at a private LLM endpoint.
- **AI Catalog** (`aiCatalogItems`) — agent flows published to the instance.

These fields appear in GraphQL introspection on CE but are rejected at runtime with
`"Field 'X' doesn't exist on Query"` — a documented trap. If you ever apply a license, the
fields become callable; reach them via `gitlab_graphql` / `gitlab_rest`, and only then consider
a curated tool (it would 404 today). Until then: this instance has the model registry + MLflow
+ catalog, not Duo.
