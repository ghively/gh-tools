---
description: Explore a project's ML Model Registry and experiment tracking (CE-available)
argument-hint: <project>
---

Inspect the ML/AI assets in **$ARGUMENTS**. The model registry + MLflow experiment tracking work
on CE; GitLab **Duo / AI code-suggestions are EE-gated and 404 on this instance** — say so if asked.
Read `references/ai-and-model-registry.md`.

1. **Registered models**: `model_registry(project, action="models")` — id, name, version count,
   description, latest version. Summarize the catalog.
2. **Experiments**: `model_registry(project, action="experiments")` — experiment names + candidate
   (run) counts.
3. **MLflow detail** (MLflow-compatible clients log here): `model_registry(project, action="mlflow",
   mlflow_path="registered-models/search")`, `.../model-versions/search`, `.../runs/search`,
   `.../experiments/search`. These mirror the MLflow REST API 2.0 — the tracking URI a client would
   use is `https://git.hively.dev/api/v4/projects/<id>/ml/mlflow`.
4. **Artifacts**: `model_registry(project, action="packages")` — the ml_model package files/versions
   backing each model.
5. If the user asks about wiring CI to log a model: point them at the MLflow tracking URI above +
   a `MLFLOW_TRACKING_TOKEN` CI variable, and note `templates/ci/python.yml` as a base.

Report the model/experiment inventory. If empty, say the registry is set up but has no models yet.
