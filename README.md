# Catalog Enrichment — text-only build

A text-only build of the [NVIDIA Retail Catalog Enrichment blueprint](https://github.com/NVIDIA-AI-Blueprints/Retail-Catalog-Enrichment),
with every vision and image-generation component removed.

What remains is the evidence-and-copy half of the blueprint: take whatever product
facts you already hold, reconcile them against your existing catalog entry, and
return enriched, localized copy — plus PDF, web and policy evidence lanes to ground
it. Nothing in this build reads or produces an image.

## Why this build exists

The upstream blueprint is organized around a product photo: a vision model reads the
image, and the rest of the pipeline enriches, illustrates and re-renders it. If your
catalog is driven by a supplier feed rather than photography, roughly half of that
stack is inert — and it drags in four GPU services, a Next.js UI and an image
toolchain you never call.

This build keeps the half that works on text and drops the rest, so it can be run as
a service or have its modules imported directly into a batch pipeline.

## What it does

| Capability | Module | Endpoint |
|---|---|---|
| Reconcile a source observation against an existing catalog entry, then enrich and localize | `enrich.py` | `POST /enrich` |
| Generate shopper FAQs from enriched fields | `enrich.py` | `POST /faqs` |
| Extract grounded knowledge from a manual or datasheet PDF | `product_manual.py` | `POST /manual/extract` |
| Research the public web with source grounding and identity scoping | `web_insights.py` | `POST /research/product-insights` |
| Check copy against a library of policy PDFs | `policy.py`, `policy_library.py` | `POST /policies`, automatic on `/enrich` |
| Export ACP and UCP protocol schemas | `main.py` | `POST /protocols/generate` |

### The source observation

Upstream, the authoritative evidence about a product came from a vision model reading
a photo. Here it comes from the caller as a **source observation** — a plain JSON
object of observed facts:

```json
{
  "title": "Grohe Eurosmart single-lever basin mixer, chrome",
  "description": "Single-lever basin mixer with ceramic cartridge.",
  "categories": ["sanitary"],
  "tags": ["mixer", "basin"],
  "colors": ["chrome"]
}
```

Use a supplier feed row, a datasheet extract, a scraped spec table — anything you can
defend as a fact. The reconciliation chain that consumes it is unchanged from
upstream: a pre-filter drops user-supplied terms that conflict with the observation, a
merge step writes the copy, and a QA pass plus a **targeted repair** step fix any
identity regression that survives, rather than regenerating the whole record.

## Quick start

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e .

export NGC_API_KEY=...          # required
export EXA_API_KEY=...          # optional, enables /research/product-insights

uvicorn --app-dir src backend.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
curl -X POST http://localhost:8000/enrich \
  -F 'source_observation={"title":"Grohe Eurosmart basin mixer, chrome","categories":["sanitary"]}' \
  -F 'locale=en-GB'
```

Interactive API docs are at `http://localhost:8000/docs`. Full reference in
[docs/API.md](docs/API.md).

### Containers

```bash
docker compose up -d                              # backend + LLM NIM + embeddings NIM
docker compose -f docker-compose.rag.yml up -d    # Milvus, for the policy library
```

See [docs/DOCKER.md](docs/DOCKER.md).

## Configuration

Endpoints and retrieval parameters live in `shared/config/config.yaml`; environment
variables override the ones that matter per-deployment. See `.env.example`.

| Variable | Required | Purpose |
|---|---|---|
| `NGC_API_KEY` | Yes | LLM and embedding calls |
| `EXA_API_KEY` | No | Web insights; without it the endpoint returns `status: "disabled"` |
| `MILVUS_HOST` / `MILVUS_PORT` | No | Policy library vector store |

## Tests

```bash
PYTHONPATH=src pytest tests/ -q
```

166 tests, no network or GPU required — every external endpoint is mocked.

## What was removed

Deleted outright: `image.py` (FLUX 2D variation generation), `trellis.py` (3D asset
generation), `reflection.py` (VLM image-quality judging), `src/ui/` (the Next.js
front end, which is an image-upload workflow), `nginx.conf` (it only proxied that UI),
the deployment notebook, and `docs/PRD.md` (the upstream requirements document, most
of which specifies removed features).

Split rather than deleted: upstream `vlm.py` mixed the vision calls with the text-only
LLM chain. It is now `enrich.py`, carrying the second half — every function that took
image bytes is gone, and the prompts that treated a photo as the evidence channel now
name the source observation instead.

Endpoints `/vlm/analyze`, `/vlm/rich-product`, `/generate/variation` and `/generate/3d`
are gone; `/vlm/faqs` and `/vlm/manual/extract` are now `/faqs` and `/manual/extract`.
The `vlm-nim`, `flux-nim`, `trellis-nim`, `frontend` and `nginx` compose services and
the Pillow and HuggingFace-token dependencies went with them.

## Upstream

Derived from `NVIDIA-AI-Blueprints/Retail-Catalog-Enrichment`. Apache-2.0; see
[LICENSE](LICENSE). Bug fixes and features in the text lane are worth tracking
upstream — the vision lane is not.
