FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

# procps provides pgrep, used by the HEALTHCHECK below -- python:3.12-slim doesn't include it.
RUN apt-get update && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

# Non-root: least-privilege default for a container that reaches out to external APIs
# (Gemini, EDGAR, Qdrant) and writes to a mounted volume.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY prompts/ ./prompts/

ENV PATH="/app/.venv/bin:$PATH"
# data/ holds the DuckDB file and any cached filing content -- mounted as a volume (see
# docker-compose.yml) so it survives container restarts/rebuilds.
RUN mkdir -p /app/data && chown -R appuser:appuser /app
VOLUME ["/app/data"]

USER appuser

# No HTTP endpoint exists yet (this server is stdio-only; see Issue 10.2 for the planned SSE
# transport) so a true HTTP health check isn't possible here. This checks the server process
# is actually running, which is the closest honest equivalent for a stdio-transport container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD pgrep -f "src/server.py" || exit 1

CMD ["python", "src/server.py"]
