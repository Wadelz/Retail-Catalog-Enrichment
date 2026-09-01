# API Documentation

This document provides detailed information about the Catalog Enrichment System API endpoints.

## Base URL

- **Local Development**: `http://localhost:8000`
- **Docker Deployment**: `http://localhost:8000`

## Health & Info Endpoints

### GET `/`
Returns a plaintext greeting message.

**Response**: 
```
Catalog Enrichment Backend
```

### GET `/health`
Health check endpoint for monitoring service status.

**Response**:
```json
{
  "status": "ok"
}
```

---

## API Endpoints

### Modular Pipeline Workflow

The API provides a modular approach for optimal performance and flexibility:

- **1) Policy Library (`/policies`)** - Load the policy PDFs that enrichment is checked against
- **2) Product Enrichment (POST `/enrich`)** - Reconcile a source observation into enriched catalog copy
- **3) FAQ Generation (POST `/faqs`)** - Generate product FAQs from enriched data
- **3.5) Manual Knowledge Extraction (POST `/manual/extract`)** - Extract knowledge from a product manual or datasheet PDF to enrich FAQs
- **4) Product Web Insights (POST `/research/product-insights`)** - Research public web information about the enriched product
- **5) Protocol Schema Generation (POST `/protocols/generate`)** - Generate ACP and UCP schemas

**Benefits of this approach:**
- Return core product fields immediately
- Load FAQs, web insights and protocol schemas independently
- Cache enrichment results and re-run downstream steps cheaply
- Better error handling for each step
- Each step fails independently without blocking the others

## 1️⃣ Policy Library: `/policies`

Manage the persistent PDF policy library used during analysis.

Policy documents are handled as a persistent single-user RAG library:
- uploaded PDFs are parsed and normalized into structured policy summaries
- normalized policy records are embedded and stored in Milvus
- `/enrich` automatically performs semantic retrieval against the loaded policy library
- the compliance classifier receives the analyzed product plus the retrieved policy records

### GET `/policies`

Returns metadata for the currently loaded policy library.

### Response Schema

```json
{
  "documents": [
    {
      "document_hash": "string",
      "filename": "string",
      "file_size": 12345,
      "chunk_count": 10,
      "created_at": 1735689600,
      "updated_at": 1735689600
    }
  ]
}
```

`chunk_count` is the number of indexed policy records generated from the normalized PDF, not the raw page count.

### POST `/policies`

**Content-Type**: `multipart/form-data`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `files` | file[] | Yes | One or more PDF files to add to the persistent policy library |
| `locale` | string | No | Locale used when normalizing newly uploaded policies (default: `en-US`) |

### POST Example

```bash
curl -X POST \
  -F "locale=en-US" \
  -F "files=@policy-a.pdf;type=application/pdf" \
  -F "files=@policy-b.pdf;type=application/pdf" \
  http://localhost:8000/policies
```

### POST Response Schema

```json
{
  "documents": [
    {
      "document_hash": "string",
      "filename": "string",
      "file_size": 12345,
      "chunk_count": 10,
      "created_at": 1735689600,
      "updated_at": 1735689600
    }
  ],
  "results": [
    {
      "document_hash": "string",
      "filename": "string",
      "chunk_count": 10,
      "already_loaded": false,
      "processed": true
    }
  ]
}
```

Notes:
- repeated uploads of the same PDF are deduplicated by content hash
- `already_loaded=true` means the document was already present in the library
- `processed=true` means the upload was newly parsed, normalized, embedded, and indexed

### DELETE `/policies`

Clears the persistent policy library, including stored PDF artifacts and vector embeddings.

```bash
curl -X DELETE http://localhost:8000/policies
```

### DELETE Response

```json
{
  "status": "ok"
}
```

---

## 2️⃣ Product Enrichment: `/enrich`

Reconcile a source observation against an existing catalog entry and return enriched, localized catalog copy.

The **source observation** is whatever authoritative product evidence you already hold: a supplier feed row, a datasheet extract, a scraped spec table. It is treated as ground truth for recorded facts. The optional **product_data** is your current catalog entry; it is reconciled against the observation rather than trusted, so stale or conflicting terms are removed instead of merged.

### Request Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source_observation` | string (JSON object) | Yes | Observed product facts. Must include a non-empty `title`. |
| `locale` | string | No | Target locale (default `en-US`). |
| `product_data` | string (JSON object) | No | Existing catalog entry to reconcile against the observation. |
| `brand_instructions` | string | No | Brand voice, tone, style and taxonomy guidance. |

### Source Observation Schema

```json
{
  "title": "Grohe Eurosmart single-lever basin mixer, chrome",
  "description": "Single-lever basin mixer with ceramic cartridge.",
  "categories": ["sanitary"],
  "tags": ["mixer", "basin"],
  "colors": ["chrome"]
}
```

### Response Schema

| Field | Type | Description |
|---|---|---|
| `title` | string | Enriched, localized title. |
| `description` | string | Expanded, localized description. |
| `categories` | array | Validated categories. |
| `tags` | array | Expanded tag list. |
| `colors` | array | Normalized color palette. |
| `locale` | string | Echo of the requested locale. |
| `enhanced_product` | object | Present only when `product_data` was supplied: the reconciled record. |
| `policy_decision` | object | Present only when a policy library is loaded. See `/policies`. |

### Usage Example

```bash
curl -X POST http://localhost:8000/enrich \
  -F 'source_observation={"title":"Grohe Eurosmart basin mixer, chrome","categories":["sanitary"]}' \
  -F 'locale=en-GB'
```

With an existing catalog entry to reconcile:

```bash
curl -X POST http://localhost:8000/enrich \
  -F 'source_observation={"title":"Grohe Eurosmart basin mixer, chrome"}' \
  -F 'product_data={"title":"Chrome tap","tags":["bathroom"]}' \
  -F 'brand_instructions=Plain, factual tone. No superlatives.'
```

### Notes

- Reconciliation is multi-stage: a pre-filter removes user terms that conflict with the observation, a merge step produces the copy, and a QA pass plus a targeted repair step resolve any identity regression that survives.
- No claim is invented: the model is constrained to facts present in the source observation or the supplied product data.


## 3️⃣ FAQ Generation: `/faqs`

Generate frequently asked questions and answers for a product based on its enriched catalog data. Designed to be called after `/enrich` completes, using the enriched result as input.

Without a product manual: generates 3-5 basic FAQs from the product data.
With manual knowledge (from `/manual/extract`): generates up to 10 richer FAQs that draw from both the product data and the manual, surfacing details that go beyond the description.

**Endpoint**: `POST /faqs`
**Content-Type**: `multipart/form-data`

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | No | Product title from enrichment |
| `description` | string | No | Product description from enrichment |
| `categories` | JSON string | No | Categories array (default: `[]`) |
| `tags` | JSON string | No | Tags array (default: `[]`) |
| `colors` | JSON string | No | Colors array (default: `[]`) |
| `locale` | string | No | Regional locale code (default: `en-US`) |
| `manual_knowledge` | JSON string | No | Extracted manual knowledge from `/manual/extract` |

### Response Schema

```json
{
  "faqs": [
    {
      "question": "string",
      "answer": "string"
    }
  ]
}
```

### Usage Example (Basic)

```bash
# Call after /enrich to generate FAQs from enriched data
curl -X POST \
  -F "title=Craftsman 20V Cordless Lawn Mower" \
  -F "description=A cordless lawn mower featuring a black and red design..." \
  -F 'categories=["electronics"]' \
  -F 'tags=["cordless","lawn mower","Craftsman"]' \
  -F 'colors=["black","red"]' \
  -F "locale=en-US" \
  http://localhost:8000/faqs
```

### Usage Example (With Product Manual)

```bash
# First extract knowledge from the manual, then pass it to FAQ generation
KNOWLEDGE=$(curl -s -X POST \
  -F "file=@mower-manual.pdf" \
  -F "title=Craftsman 20V Cordless Lawn Mower" \
  -F 'categories=["electronics"]' \
  http://localhost:8000/manual/extract | jq -c '.knowledge')

curl -X POST \
  -F "title=Craftsman 20V Cordless Lawn Mower" \
  -F "description=A cordless lawn mower featuring a black and red design..." \
  -F 'categories=["electronics"]' \
  -F 'tags=["cordless","lawn mower","Craftsman"]' \
  -F 'colors=["black","red"]' \
  -F "locale=en-US" \
  -F "manual_knowledge=$KNOWLEDGE" \
  http://localhost:8000/faqs
```

### Example Response

```json
{
  "faqs": [
    {
      "question": "What type of battery does this mower use?",
      "answer": "This mower operates on a 20V cordless battery system, providing the flexibility to mow without a power cord."
    },
    {
      "question": "Does this mower come with a grass collection bag?",
      "answer": "Yes, it includes a rear-mounted grass collection bag for convenient clippings management."
    },
    {
      "question": "What are the main colors of this mower?",
      "answer": "The mower features a black and red color scheme with prominent Craftsman branding."
    }
  ]
}
```

---

## 3.5️⃣ Product Manual Knowledge Extraction: `/manual/extract`

Extract structured knowledge from a product manual PDF using targeted RAG. The endpoint processes the PDF, generates product-type-specific queries via the LLM (using title + categories, not description, to avoid duplicating what the description already covers), and retrieves relevant chunks from the manual for each topic.

This endpoint is **stateless** — all embeddings are computed in-memory and freed after the response. It can handle concurrent requests for different products.

**Endpoint**: `POST /manual/extract`
**Content-Type**: `multipart/form-data`

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | file | Yes | Product manual PDF (max 50 MB) |
| `title` | string | No | Product title (used to generate relevant queries) |
| `categories` | JSON string | No | Product categories array (used to generate relevant queries) |
| `locale` | string | No | Regional locale code (default: `en-US`) |

### Response Schema

```json
{
  "filename": "string",
  "chunk_count": 42,
  "knowledge": {
    "battery_life": "The speaker provides up to 12 hours of continuous playback...",
    "waterproof_rating": "IPX7 rated, can be submerged up to 1 meter for 30 minutes...",
    "care_instructions": "Clean with a damp cloth. Do not use abrasive cleaners..."
  }
}
```

The `knowledge` object contains topic keys (dynamically generated by the LLM based on product type) mapped to the relevant text extracted from the manual. Topics with no relevant content are empty strings.

### Usage Example

```bash
curl -X POST \
  -F "file=@speaker-manual.pdf;type=application/pdf" \
  -F "title=JBL Flip 6 Portable Speaker" \
  -F 'categories=["electronics"]' \
  -F "locale=en-US" \
  http://localhost:8000/manual/extract
```

### Batch Script Example

```bash
# Process multiple products concurrently (each request is independent)
for product in products/*.json; do
  TITLE=$(jq -r '.title' "$product")
  CATS=$(jq -c '.categories' "$product")
  PDF=$(jq -r '.manual_pdf' "$product")

  KNOWLEDGE=$(curl -s -X POST \
    -F "file=@$PDF" \
    -F "title=$TITLE" \
    -F "categories=$CATS" \
    http://localhost:8000/manual/extract | jq -c '.knowledge')

  curl -s -X POST \
    -F "title=$TITLE" \
    -F "description=$(jq -r '.description' "$product")" \
    -F "categories=$CATS" \
    -F "manual_knowledge=$KNOWLEDGE" \
    http://localhost:8000/faqs
done
```

---

## 4️⃣ Product Web Insights: `/research/product-insights`

Research public web information about a product using a Deep Agents research agent with Exa search. Exa retrieves search results, highlights, and text excerpts only; Nemotron/Deep Agent performs the summarization and dashboard synthesis. Designed to be called after `/enrich` completes, using the enriched title as the primary product and brand disambiguation input.

The endpoint is informational. It returns source-backed insights for display in the UI and does not automatically modify the enriched title, description, FAQs, or protocol schemas.

**Endpoint**: `POST /research/product-insights`
**Content-Type**: `multipart/form-data`

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | Yes | Enriched product title from `/enrich`. Used as the primary product and brand search signal. |
| `description` | string | No | Enriched product description. Used only for disambiguation. |
| `categories` | JSON string | No | Categories array (default: `[]`) |
| `tags` | JSON string | No | Tags array (default: `[]`) |
| `locale` | string | No | Regional locale code (default: `en-US`) |
| `max_results` | integer | No | Maximum Exa results per query (default: 8, max: 20) |

### Response Schema

```json
{
  "summary": "string",
  "pros": ["string"],
  "cons": ["string"],
  "use_cases": ["string"],
  "customer_insights": ["string"],
  "purchase_considerations": ["string"],
  "search_queries": ["string"],
  "sources": [
    {
      "title": "string",
      "url": "string",
      "published_date": "string|null",
      "snippet": "string"
    }
  ],
  "warnings": ["string"],
  "locale": "en-US",
  "research_scope": "product_specific|brand_level|category_level|insufficient_identity",
  "identity_confidence": "high|medium|low|none",
  "detected_brand": "string|null",
  "detected_model": "string|null",
  "scope_note": "string",
  "identity_evidence": ["string"],
  "report": {
    "executive_summary": "string",
    "positioning_tags": ["string"],
    "metrics": {
      "customer_sentiment": {
        "label": "Positive",
        "score": 82,
        "scale": "percent",
        "rationale": "string"
      },
      "build_quality": {
        "label": "Premium",
        "score": 8.4,
        "scale": "label",
        "rationale": "string"
      },
      "price_segment": {
        "label": "High-end",
        "score": null,
        "scale": "label",
        "rationale": "string"
      },
      "retail_confidence": {
        "label": "Strong",
        "score": 8.9,
        "scale": "rating_10",
        "rationale": "string"
      }
    },
    "retail_insights": [
      {
        "type": "positive",
        "title": "string",
        "detail": "string"
      }
    ],
    "primary_use_cases": [
      {
        "title": "string",
        "detail": "string"
      }
    ],
    "customer_sentiment_summary": "string"
  }
}
```

The flat fields remain for compatibility. The UI prefers `report` when present and falls back to the flat fields for older or mocked responses. The identity fields describe whether research is product-specific, brand-level, category-level, or too ambiguous. Brand/model detection is source-evidence-based, not a deterministic title-token heuristic. For titles where sources do not reliably confirm a brand or model, the endpoint returns category-level context, clears brand/model, and suppresses product-specific numeric sentiment or confidence scores.

### Usage Example

```bash
curl -X POST \
  -F "title=JBL Flip 6 Portable Bluetooth Speaker" \
  -F "description=A compact waterproof Bluetooth speaker with bold sound." \
  -F 'categories=["electronics"]' \
  -F 'tags=["bluetooth","speaker","portable","waterproof"]' \
  -F "locale=en-US" \
  http://localhost:8000/research/product-insights
```

### Example Response

```json
{
  "summary": "Public sources commonly position this product as a rugged portable speaker for travel, poolside use, and everyday listening.",
  "pros": [
    "Portable size and durable design are recurring positive themes.",
    "Water resistance is frequently highlighted for outdoor use."
  ],
  "cons": [
    "Some sources mention limited stereo separation from the compact form factor."
  ],
  "use_cases": [
    "Poolside listening",
    "Travel and camping",
    "Small room audio"
  ],
  "customer_insights": [
    "Buyers often compare battery life, durability, and bass response against similar portable speakers."
  ],
  "purchase_considerations": [
    "Clarify waterproof rating, battery runtime, and compatibility details in downstream catalog copy."
  ],
  "search_queries": [
    "JBL Flip 6 Portable Bluetooth Speaker review",
    "JBL Flip 6 Portable Bluetooth Speaker pros cons",
    "JBL Flip 6 Portable Bluetooth Speaker how people use"
  ],
  "sources": [
    {
      "title": "JBL Flip 6 product page",
      "url": "https://example.com/product",
      "published_date": null,
      "snippet": "Short source excerpt or highlight."
    }
  ],
  "warnings": [],
  "locale": "en-US",
  "research_scope": "product_specific",
  "identity_confidence": "high",
  "detected_brand": "JBL",
  "detected_model": "Flip 6",
  "scope_note": "Sources appear to match a specific product identity.",
  "identity_evidence": [
    "Official and retailer pages match the JBL Flip 6 title and product type."
  ],
  "report": {
    "executive_summary": "Public sources position the product as a rugged portable speaker for travel, poolside use, and everyday listening.",
    "positioning_tags": ["Rugged portable audio", "Outdoor use", "Water resistant"],
    "metrics": {
      "customer_sentiment": {
        "label": "Positive",
        "score": 84,
        "scale": "percent",
        "rationale": "Available review snippets skew toward durability and portability."
      },
      "build_quality": {
        "label": "Durable",
        "score": 8.2,
        "scale": "label",
        "rationale": "Sources repeatedly mention rugged construction and water resistance."
      },
      "price_segment": {
        "label": "Mid-market",
        "score": null,
        "scale": "label",
        "rationale": "Retail listings place it among mainstream portable speakers."
      },
      "retail_confidence": {
        "label": "Strong",
        "score": 8.1,
        "scale": "rating_10",
        "rationale": "Source coverage is relevant and consistent."
      }
    },
    "retail_insights": [
      {
        "type": "positive",
        "title": "Durable positioning",
        "detail": "Public sources emphasize portability and rugged everyday use."
      }
    ],
    "primary_use_cases": [
      {
        "title": "Outdoor listening",
        "detail": "Sources describe poolside, travel, and camping use cases."
      }
    ],
    "customer_sentiment_summary": "Buyers tend to compare durability, battery life, and sound quality against similar portable speakers."
  }
}
```

### Notes

- Uses `EXA_API_KEY` and the existing Nemotron LLM configuration when Web Insights is enabled. If `EXA_API_KEY` is not configured, the endpoint returns a 200 response with `status: "disabled"`, empty insight arrays, and a user-facing configuration message.
- Uses the Deep Agents SDK as the research harness and Exa as the retrieval tool.
- LLM-generated dashboard scores are returned only as source-backed directional signals; thin coverage returns warnings and neutral metric fallbacks.
- Web claims should be treated as external context. Sources are returned for auditability but are not listed in the default dashboard view.
- Failure to generate web insights should not block enrichment, FAQs, or protocol schemas.

---

## 5️⃣ Protocol Schema Generation: `/protocols/generate`

Generate ACP (Agentic Commerce Protocol) and UCP (Unified Commerce Protocol) schema instances from enriched product data. Uses an LLM call to extract structured attributes (brand, material, product details, etc.) from the enriched title and description, then merges them into both schema templates.

**`POST /protocols/generate`**

Content-Type: `multipart/form-data`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | No | Enriched product title |
| `description` | string | No | Enriched product description |
| `categories` | JSON string | No | Categories array (default: `[]`) |
| `tags` | JSON string | No | Tags array (default: `[]`) |
| `colors` | JSON string | No | Colors array (default: `[]`) |
| `faqs` | JSON string | No | FAQs array (default: `[]`) |
| `locale` | string | No | Regional locale code (default: `en-US`) |

### Response Schema

```json
{
  "acp": {
    "product": {
      "id": null,
      "title": "Nature Made Fish Oil Softgels...",
      "description": "Support your heart health...",
      "brand": "Nature Made",
      "attributes": { "colors": ["brown", "yellow"], "material": null, "condition": "new", ... },
      "categories": ["health", "supplements"],
      "tags": ["fish oil", "omega-3", ...],
      "images": { ... },
      "identifiers": { "gtin": null, "mpn": null, "sku": null },
      "dimensions": { ... },
      "details": [{ "attribute_name": "Omega-3 Content", "attribute_value": "360 mg" }, ...],
      "highlights": ["Supports heart health", ...]
    },
    "pricing": { "availability": "in_stock", "price": null, ... },
    "faqs": [{ "question": "...", "answer": "..." }, ...],
    "agent_actions": { "discoverable": true, "buyable": true, "returnable": true, ... },
    "fulfillment": { ... },
    "campaigns": { "short_title": "Nature Made Fish Oil 300ct", ... },
    "certifications": [],
    "energy_efficiency": { ... },
    "bundling": { ... },
    "marketplace": { ... },
    "metadata": { "enrichment_source": "nvidia-catalog-enrichment", ... }
  },
  "ucp": {
    "structured_title": { "digital_source_type": "trained_algorithmic_media", "content": "..." },
    "structured_description": { "digital_source_type": "trained_algorithmic_media", "content": "..." },
    "brand": "Nature Made",
    "color": "brown / yellow",
    "condition": "new",
    "product_type": "health > supplements",
    "google_product_category": "Health > Vitamins & Supplements > Fish Oil",
    "product_detail": [{ "attribute_name": "...", "attribute_value": "..." }],
    "product_highlight": ["..."],
    "faqs": [{ "question": "...", "answer": "..." }],
    "price": { "amount": null, "currency": null },
    "shipping": [],
    ...
  }
}
```

### Usage Example

```bash
curl -X POST \
  -F "title=Nature Made Fish Oil Softgels, 1200 mg, 300 Count" \
  -F "description=Support your heart health with Omega-3 fatty acids." \
  -F 'categories=["health","supplements"]' \
  -F 'tags=["fish oil","omega-3","heart health"]' \
  -F 'colors=["brown","yellow"]' \
  -F 'faqs=[{"question":"Is it mercury-free?","answer":"Yes, purified to remove mercury."}]' \
  -F "locale=en-US" \
  http://localhost:8000/protocols/generate
```

**Notes:**
- Calls the LLM once to extract structured fields (brand, material, age_group, gender, short_title, google_product_category, product_details, product_highlights), then builds both schemas from the same extraction
- ACP schema includes agent actions, fulfillment, and campaigns sections for agentic commerce
- UCP schema follows the Google Merchant Center Product Data Specification with `structured_title`/`structured_description` using `digital_source_type: "trained_algorithmic_media"` for AI-generated content
- Fields not derivable from enriched data are set to `null` for the consumer to fill in
- Deterministic defaults: `availability` = `"in_stock"`, `condition` = `"new"`, `adult` = `false`, `is_bundle` = `false`

---

## Supported Locales

The API supports 10 regional locales for language and cultural context:

### English Variants
- `en-US` - American English (default)
- `en-GB` - British English  
- `en-AU` - Australian English
- `en-CA` - Canadian English

### Spanish Variants
- `es-ES` - Spain Spanish (uses "ordenador")
- `es-MX` - Mexican Spanish (uses "computadora") 
- `es-AR` - Argentinian Spanish
- `es-CO` - Colombian Spanish

### French Variants
- `fr-FR` - Metropolitan French
- `fr-CA` - Quebec French (Canadian)

---

## Error Responses

All endpoints return standard HTTP status codes:

- **200**: Success
- **400**: Bad Request (invalid parameters)
- **422**: Unprocessable Entity (validation error)
- **500**: Internal Server Error

Error response format:
```json
{
  "detail": "Error message description"
}
```
