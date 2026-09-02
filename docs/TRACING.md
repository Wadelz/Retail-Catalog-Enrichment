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

The compose network is declared `external`, so create it once if you have not
already, then bring up the collector:

```bash
docker network create catalog-network || true

# The phoenix service enables auth by default and will not start without this.
echo "PHOENIX_SECRET=$(openssl rand -hex 32)" >> .env

docker compose up -d phoenix
```

Log in at <http://localhost:6006>, create a system key under **Settings → API
Keys**, and put it in `.env` so the exporter can authenticate:

```bash
TRACING_ENABLED=true
PHOENIX_API_KEY=<the system key>
```

Trigger any enrichment request and spans appear under the project
`catalog-enrichment`.

For a collector reachable from nothing but localhost, `PHOENIX_ENABLE_AUTH=false`
skips the secret and key entirely. Do not do this for anything exposed — see
[Exposing the collector](#exposing-the-collector).

Phoenix can also run from pip, but **only on Python 3.12+** — on 3.11 it fails at
import with `ValueError: mutable default <class 'mappingproxy'>`. The Docker
image bundles its own interpreter and avoids the question:

```bash
pip install arize-phoenix   # Python 3.12+ only
phoenix serve
```

## Chain spans: grouping a multi-step operation

The instrumentors alone produce one span per LLM call, all at the root of the
trace. A single enrichment can make several calls, and flat spans give no way to
tell which belong to the same operation or where the time went.

`@tracer.chain` wraps an orchestrating function in a CHAIN span so its LLM calls
nest beneath it:

```
extract_vlm_observation          CHAIN    1.57s
  └─ ChatCompletion              LLM      1.55s
```

Currently decorated — the functions that coordinate more than one model step:

| Module | Function |
| --- | --- |
| `vlm.py` | `extract_vlm_observation`, `extract_rich_product_json`, `build_enriched_vlm_result`, `_call_nemotron_enhance` |
| `policy.py` | `evaluate_policy_compliance` |
| `product_manual.py` | `process_manual_pdf`, `extract_manual_knowledge` |
| `image.py` | `generate_image_variation` |
| `reflection.py` | `evaluate_image_quality` |

To add another, import the tracer and decorate:

```python
from backend.tracing import tracer

@tracer.chain
def my_orchestrator(...):
    ...
```

The decorator sets the span kind, `input.value`/`output.value`, and terminal
status automatically, so it cannot emit the `UNSET`/incomplete spans a
hand-rolled span easily does. It returns the function's value unchanged and lets
exceptions propagate — a failure is recorded on the span, not swallowed.

**Do not decorate a function whose only job is one LLM call.** The instrumentor
already produces that span; wrapping it adds a redundant parent. Decorate the
function that *coordinates* steps.

`web_insights.py` is deliberately undecorated: its deepagents/LangGraph agent
emits its own chain and tool spans through the LangChain instrumentor, and a
manual CHAIN span there would duplicate that structure.

Applying the decorators is safe when tracing is off: the tracer resolves to a
no-op provider and the functions run untouched.

## Querying traces from Claude Code (MCP)

`.mcp.json` registers the Phoenix MCP server, so an agent session can read this
project's traces directly instead of you clicking through the UI — "which spans
errored today", "show me the slowest trace", "what did the VLM return on that
failed call".

It reads three variables from your environment:

```bash
PHOENIX_BASE_URL=http://localhost:6006   # site root, NOT the /v1/traces endpoint
PHOENIX_API_KEY=<system key>
PHOENIX_PROJECT_NAME=catalog-enrichment
```

The key is referenced, never inlined — `.mcp.json` is committed, so a literal key
there would be a leak.

**It is not read-only.** Alongside the read tools (`list-traces`, `get-trace`,
`get-spans`, `list-projects`, `list-sessions`, dataset and experiment queries) it
exposes `upsert-prompt` and `add-dataset-examples`, which write to your Phoenix.

MCP servers are loaded when a session starts, so a running session will not pick
this up until it is restarted.

## Exposing the collector

A local collector is reachable only from the machine it runs on. To see traces
from a remote or containerised backend, either tunnel to a local Phoenix:

```bash
cloudflared tunnel --url http://localhost:6006
export PHOENIX_COLLECTOR_ENDPOINT=https://<tunnel-host>/v1/traces
```

…or use hosted Phoenix Cloud, which is **hostname-scoped per space** (not a
shared host with a path prefix):

```bash
export PHOENIX_COLLECTOR_ENDPOINT=https://<your-space>.arize.com/v1/traces
export PHOENIX_API_KEY=...
```

**Keep auth on for anything exposed.** A tunnel URL is public to anyone holding
it, and spans carry full prompts and model completions. Note that
`phoenix-demo.arize.com` is a public read-only demo: it returns `403 The Phoenix
REST API is disabled in read-only mode` for every write, so traces sent there are
silently dropped.

No code change is needed for auth. `phoenix.otel.register()` falls back to the
`PHOENIX_API_KEY` environment variable when no `api_key` argument is passed and
sets the `authorization: Bearer …` header itself; the startup banner shows
`Transport Headers: {'authorization': '****'}` when it took effect. Keep the key
in `.env` or a secret store — it must never be committed.

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

**Startup logs `Phoenix tracing unavailable (mutable default <class 'mappingproxy'> ...)`.**
This appears when the full `arize-phoenix` *server* package is installed into
the same environment on Python 3.11: importing `phoenix.otel` executes the
phoenix package body, which pulls in `phoenix.trace.dsl` and fails on that
interpreter. The backend only needs `arize-phoenix-otel` (the lightweight
exporter), which is what `pyproject.toml` declares — uninstall `arize-phoenix`
from the app environment and run the collector from the Docker image instead.
Tracing is skipped in this case; the API still starts and serves normally.

**Spans stop at the LLM call for web insights.** That path goes through
LangChain, not the raw SDK. If only `openai` shows in the `instrumented=` list at
startup, `openinference-instrumentation-langchain` is missing.

**Short-lived scripts lose spans.** The batch processor exports on a timer, so
anything that calls the backend modules outside the FastAPI lifespan must call
`shutdown_tracing()` before exiting.
