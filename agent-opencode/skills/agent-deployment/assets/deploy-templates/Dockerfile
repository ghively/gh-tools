# Agent container — adapt image/deps to your project.
# Doctrine: pinned base, non-root, secrets ONLY via runtime env/secret store.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first for layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ ./src/
COPY evals/ ./evals/

# Never run agents as root — a prompt-injected tool call shouldn't own the box
RUN useradd --create-home agent
USER agent

# ANTHROPIC_API_KEY etc. come from the runtime (docker run -e / compose /
# orchestrator secret). If a credential is baked into this image, ship-check
# criterion 5 should have caught it.
ENTRYPOINT ["python", "src/agent.py"]
