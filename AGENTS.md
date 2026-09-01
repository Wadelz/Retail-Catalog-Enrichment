# AGENTS.md - AI Assistant Instructions

Guidelines for AI assistants working on this project.

## Project Overview

**Project Name:** catalog-enrichment (text-only build)
**Upstream:** https://github.com/NVIDIA-AI-Blueprints/Retail-Catalog-Enrichment
**Purpose:** Enrich product catalog data from text evidence — reconciling observed
product facts against an existing catalog entry and grounding the result in PDF, web
and policy sources.

This is a derived build with every vision and image-generation component removed. If
you are about to add an image input, a vision model call, or an asset generator, you
are working against the point of this build — check first.

### Documentation Structure
- **[README.md](README.md)** — what this build is, quick start, what was removed
- **[docs/API.md](docs/API.md)** — complete API reference with examples
- **[docs/DOCKER.md](docs/DOCKER.md)** — container deployment
- **[docs/POLICY_COMPLIANCE.md](docs/POLICY_COMPLIANCE.md)** — policy library and compliance checks
- **[docs/PRODUCT_MANUAL_FAQS.md](docs/PRODUCT_MANUAL_FAQS.md)** — manual/datasheet PDF enrichment
- **[docs/WEB_INSIGHTS.md](docs/WEB_INSIGHTS.md)** — source-grounded web research
- **[AGENTS.md](AGENTS.md)** — this file

### Capabilities
- ✅ **Source reconciliation and enrichment** — merge-QA and targeted repair (`/enrich`)
- ✅ **Multi-language support** — 10 locales across English, Spanish, French
- ✅ **Product FAQ generation** — optionally grounded in a manual or datasheet PDF
- ✅ **Policy compliance** — PDF policy library with Milvus RAG and classification
- ✅ **Web insights** — Exa-backed research with identity scoping
- ✅ **Protocol schema export** — ACP and UCP
- ❌ **Removed** — image analysis, 2D variation generation, 3D assets, image quality reflection, web UI

## Architecture

```
source observation ──┐
                     ├─→ pre-filter ─→ merge ─→ merge-QA ─→ targeted repair ─→ enriched copy
existing catalog ────┘                                                              │
                                                                                    ├─→ FAQs
policy PDFs ─→ Milvus ─→ retrieval ─→ compliance decision ──────────────────────────┤
manual PDFs ─→ chunks ─→ embeddings ─→ per-topic retrieval ─────────────────────────┤
web ─→ Exa ─→ source packet ─→ identity scoping ────────────────────────────────────┘
```

| Module | Responsibility |
|---|---|
| `enrich.py` | LLM enrichment chain: pre-filter, merge, merge-QA, repair, FAQs, schema-field extraction |
| `product_manual.py` | PDF → chunks → embeddings → per-topic retrieval (transient, per-request) |
| `policy_library.py` | Persistent policy corpus over Milvus |
| `policy.py` | PDF text extraction, policy summarization, compliance decision + repair |
| `web_insights.py` | Deep Agents + Exa research, identity scoping, metric normalization |
| `config.py` | YAML config with environment overrides |
| `main.py` | FastAPI surface and ACP/UCP schema construction |

### The source observation contract

`build_enriched_result(observation, locale, product_data, brand_instructions)` takes a
plain dict of observed product facts — title, description, categories, tags, colors.

The observation is **authoritative for recorded facts**. `product_data` is the caller's
existing catalog entry and is **not** trusted: terms that conflict with the observation
are removed rather than merged. This asymmetry is deliberate and load-bearing — it is
what stops a stale catalog entry from surviving enrichment. Preserve it.

Where the observation comes from is the caller's business: a supplier feed row, a
datasheet extract, a scraped spec table. Do not reintroduce assumptions about a
particular source, and do not write prompts that name one.

## Build and Test Commands

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# Run the service
uvicorn --app-dir src backend.main:app --host 0.0.0.0 --port 8000 --reload

# Run the tests (no network, no GPU — all external endpoints are mocked)
PYTHONPATH=src pytest tests/ -q
```

### Environment
Create `.env` at the repo root:
- `NGC_API_KEY=...` (required)
- `EXA_API_KEY=...` (optional; without it `/research/product-insights` returns `status: "disabled"`)
- `NVIDIA_API_BASE_URL=https://integrate.api.nvidia.com/v1` (default)

### Endpoints
See [docs/API.md](docs/API.md) for the full reference.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/health/nims` | Liveness; LLM and embedding NIM status |
| POST | `/enrich` | Reconcile and enrich |
| POST | `/faqs` | FAQs from enriched fields |
| POST | `/manual/extract` | Knowledge from a manual/datasheet PDF |
| POST | `/research/product-insights` | Source-grounded web research |
| GET/POST/DELETE | `/policies` | Policy library management |
| POST | `/protocols/generate` | ACP and UCP schemas |

## Code Style Guidelines

### General Principles
- **Clarity over cleverness** — write code that is easy to understand and maintain
- **Consistent formatting** — use automated formatting tools when available
- **Meaningful names** — use descriptive variable, function, and class names
- **Documentation** — include docstrings and comments for complex logic

### File Organization
- Keep files focused on a single responsibility
- Organize code into logical modules; separate configuration from business logic
- Every `chat.completions.create` call must disable thinking via `extra_body` —
  `tests/test_llm_thinking_config.py` enforces this statically across `src/backend/`

## Testing Instructions

### Strategy
- **Unit tests** — test individual functions in isolation, with external endpoints mocked
- **Data validation tests** — schema compliance, transformation accuracy, malformed input
- **Static checks** — see the thinking-config test above

### Organization
- Tests live in `tests/`, mirroring the source module names
- Fixtures shared via `tests/conftest.py`; no test may make a network call
- Use descriptive test names that explain what is being tested

### Coverage Goals
- Aim for >80% coverage on critical paths
- Prioritize enrichment, reconciliation and retrieval logic
- Include error handling and edge cases

## Security Considerations

- **Input validation** — validate every request field; the PDF paths enforce type and size limits
- **Secrets** — use environment variables; never commit credentials
- **Dependencies** — keep them current; the build is pinned in `pyproject.toml`
- **External content** — web insight sources and uploaded PDFs are untrusted input.
  Boilerplate stripping exists for this reason; do not weaken it.
- **Logging** — log security-relevant events; never log API keys or full document text

## AI Assistant Guidelines

### When Working on This Project

1. **Understand the context**
   - Data-centric project; weigh data quality, cost and scalability in every decision
   - This build is deliberately text-only — do not reintroduce image handling

2. **Code quality**
   - Always run tests before suggesting changes
   - Follow established patterns; include error handling and logging

3. **LLM prompt rules**
   - **NEVER hardcode specific product examples in prompts.** Rules must be generic and
     work across all products. Do not write `"when the user says 'synthetic leather'
     and the source says 'leather', use the user's term"` — write `"when there is a
     conflict, prefer the user's terms for materials and specs"`.
   - Prompts are consumed by millions of products — every rule must generalize.
   - If a specific scenario fails, fix the underlying rule, not just the example.
   - Prefer generic prompt contracts, schemas, field separation and reusable rubrics.
     Do not add product-specific examples, literal-token filters, or one-off
     regex/string post-processing unless explicitly requested.
   - Prompts must not assume the observation came from any particular source.

4. **Documentation**
   - Update relevant documentation when making changes
   - Include examples in API documentation; keep this file current

5. **Communication**
   - Ask for clarification when requirements are ambiguous
   - Flag potential security or performance concerns

6. **Incremental development**
   - Start simple; iterate on feedback
   - Consider backwards compatibility

---

*Derived from the upstream NVIDIA blueprint's AGENTS.md. Update as the project evolves.*
