# LLM Tracing with Arize Phoenix

The backend can export OpenTelemetry traces for every LLM call to
[Arize Phoenix](https://arize.com/docs/phoenix), giving you per-request latency,
token counts, prompts, completions, and tool/chain structure in a local UI.

Tracing is **off by default** and **additive**: no business logic changes when it
is on, and every failure path degrades to "no traces" rather than raising. An
unreachable collector will not stop or slow the API from serving.

## What gets traced

Two instrumentors cover the two ways this backend reaches a model:

| Instrumentor | Covers |
| --- | --- |
| `openinference-instrumentation-openai` | The raw `openai` SDK calls in `vlm.py`, `image.py`, `policy.py`, `policy_library.py`, `product_manual.py`, `reflection.py` — all pointed at NVIDIA NIM endpoints |
| `openinference-instrumentation-langchain` | The deepagents/LangGraph agent in `web_insights.py`, including its `web_search` tool spans and chain structure |

`deepagents` is built on LangGraph, which the LangChain instrumentor already
covers, so the agent's tool calls and chain boundaries appear without any
hand-written spans.

## Quick start

Bring up the collector and point the backend at it:

```bash
docker compose up -d phoenix
export TRACING_ENABLED=true
```

Then open the Phoenix UI at <http://localhost:6006> and trigger any enrichment
request. Spans appear under the project name `catalog-enrichment`.

For local development without Docker, Phoenix can also run from pip:

```bash
pip install arize-phoenix
phoenix serve
```

## Configuration

Settings resolve as **environment variable → `shared/config/config.yaml` → built-in
default**, the same precedence the rest of the project uses.

| Environment variable | `config.yaml` key | Default | Meaning |
| --- | --- | --- | --- |
| `TRACING_ENABLED` | `tracing.enabled` | `false` | Master switch. Accepts `1`, `true`, `yes`, `on` |
| `PHOENIX_COLLECTOR_ENDPOINT` | `tracing.endpoint` | `http://localhost:6006/v1/traces` | OTLP/HTTP trace endpoint |
| `PHOENIX_PROJECT_NAME` | `tracing.project_name` | `catalog-enrichment` | Groups spans in the Phoenix UI |

Under Docker Compose the backend defaults to `http://phoenix:6006/v1/traces`, the
compose service name. The `phoenix` service intentionally has **no**
`depends_on` relationship from `backend`, so the API never waits on it.

## How it is wired

`src/backend/tracing.py` owns setup. `setup_tracing()` is called from the FastAPI
`lifespan` hook in `main.py` *before* `policy_library.initialize()`, because
instrumentors must be installed ahead of the first LLM client construction.
`shutdown_tracing()` runs after `yield` to force-flush the batch span processor —
without it, spans buffered from the last requests before shutdown are dropped.

The `TracerProvider` and exporter are built by `phoenix.otel.register()` rather
than by hand; hand-rolling them is the usual way to end up with spans that are
recorded but never exported.

## Troubleshooting

**No traces appear.** Confirm `TRACING_ENABLED=true` is actually set in the
backend's environment, then check the startup log for the line beginning
`Phoenix tracing enabled:` — it prints the resolved project, endpoint, and which
instrumentors loaded. If it instead logs `Tracing disabled`, the flag did not
reach the process.

**`arize-phoenix-otel not installed`.** The tracing dependencies are declared in
`pyproject.toml`; run `uv sync` (or `pip install -e .`) to pick them up.

**Spans stop at the LLM call for web insights.** That path goes through
LangChain, not the raw SDK. If only `openai` shows in the `instrumented=` list at
startup, `openinference-instrumentation-langchain` is missing.

**Short-lived scripts lose spans.** The batch processor exports on a timer, so
anything that calls the backend modules outside the FastAPI lifespan must call
`shutdown_tracing()` before exiting.
