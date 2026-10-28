# Danube Properties - AI Chatbot Backend (Phase 1)

FastAPI backend for the Danube chatbot serving **Direct Sales** and **Broker** users in **English, Hindi and Arabic**. It answers only from three grounded sources: Salesforce inventory (Project + Units APIs, always live), marketing content (metadata index + live link resolver) and Excel app-walkthrough guides (Pinecone RAG returning redirect URLs).

Design references: Business Requirements v1.2, Framework Specification v0.1, Architecture diagram.

## How the folders map to the request flow

| Step | What happens | Folder / file |
|------|--------------|---------------|
| 1 | Request passes Azure APIM (IP allow-list, rate limit, TLS) | outside the app (Azure) |
| 2 | Token signature + expiry validated | `core/auth.py`, `middleware/auth_middleware.py` |
| 3 | Session resolved (`new_conversation` wins over old `session_id`) | `services/session_service.py` |
| 4 | RBAC enforced **pre-retrieval** (inventory only) | `security/rbac_filter.py`, `services/rbac_service.py` |
| 5 | Cache lookup (marketing/walkthrough only): Redis then pgvector | `services/cache_service.py` |
| 6 | LLM 1 router: intent + language + query expansion | `services/router_service.py`, `prompts/router_v1.md` |
| 7 | Retrieval: 3 separate paths + live link resolver | `retrieval/` |
| 8 | Presidio masks URLs/PII before the LLM | `security/masking.py` |
| 9 | LLM 2 generation (streamed, answer + 3 chips in one call) | `services/generation_service.py` |
| 10 | Guardrail + LLM-as-judge + response composer | `services/guardrail_service.py`, `judge_service.py`, `response_composer.py` |
| 11 | Persist turn + structured logs | `persistence/`, `observability/` |
| 12 | Offline evaluation (DeepEval + MLflow) | `evaluation/` |
| 13 | Secrets from Key Vault, retry/backoff on cold start | `core/keyvault.py` |

## Project structure

```
danube-chatbot-backend/
├── README.md                                # Setup, env vars, run/test/deploy steps, and folder-to-flow-step map
├── requirements.txt                         # Pinned runtime + offline-evaluation dependencies
├── pyproject.toml                           # Ruff, mypy and pytest configuration
├── alembic.ini                              # Alembic migration config (Postgres + pgvector schema)
├── .env                                     # Local-dev values only (placeholders) - prod secrets come from Key Vault
├── .env.example                             # Committed template listing every variable, no real values
├── .gitignore                               # Excludes .env, venvs, __pycache__, logs, MLflow runs
├── .dockerignore                            # Keeps tests/logs/local files out of the (future) Docker build
├── Dockerfile                               # Container build, kept for a later phase - not used by Phase 1 git-push deploy
├── main.py                                  # App factory: routers, middleware order, startup checks (Key Vault, DB, Redis, Pinecone)
├── app/                                     # contains all working functionality
│   ├── api/                                 # HTTP layer only - no business logic
│        ├── __init__.py                     # Marks the folder as a Python package
│        └── v1/                             # Versioned routes (Steps 1-3 entry point)
│          ├── __init__.py                   # Marks the folder as a Python package
│          ├── router.py                     # Aggregates all v1 routers under /api/v1
│          ├── chat.py                       # POST /chat - runs pipeline, streams SSE tokens then final "done" packet
│          ├── sessions.py                   # GET session list / single session history (user's own only)
│          ├── feedback.py                   # POST thumbs up/down per message_id (feeds the observability feedback signal)
│          └── health.py                     # GET /health (liveness) and /ready (DB, Redis, Pinecone, Key Vault checks)
│        └── apim_test.py                    # Provides a simple endpoint for checking that requests reach FastAPI through APIM
│   ├── handlers/                            # Executes work for each classified intent
│        ├── __init__.py                     # Marks the folder as a Python package
│        ├── dispatcher.py                   # Sends each classified intent to its matching handler
│        └── marketing_handler.py            # Finds requested project materials and prepares HTML cards and download links
│        └── sample_api.py                   # Makes a sample external API request with retry handling
│        └── streaming_service.py            # Routes chat requests, streams responses, and loads or saves conversation history
│   ├── templates/                           # HTML templates used to render marketing materials
│        ├── cards/                          # Reusable HTML cards for marketing assets and project information
│        │    ├── block 2.html.j2            # Renders a block of marketing content
│        │    ├── brochure.html.j2           # Renders brochure details and download links
│        │    ├── compare 2.html.j2          # Renders project or unit comparison details
│        │    ├── floor_plan.html.j2         # Renders floor-plan details and links
│        │    ├── gallery.html.j2            # Renders an image gallery
│        │    ├── language_list.html.j2      # Renders available language options
│        │    ├── listing 2.html.j2          # Renders a list of available items
│        │    ├── payment 2.html.j2          # Renders payment-plan details
│        │    ├── project_overview.html.j2   # Renders a project overview
│        │    ├── version_check.html.j2      # Renders version-check information
│        │    ├── video.html.j2              # Renders video details and links
│        │    └── zip_download.html.j2       # Renders a ZIP-file download link
│        └── dev/                            # Local development chat-test page and route
│             ├── chat_harness.py            # Serves the development chat-test page
│             └── chat_test.html             # Provides the browser-based chat test interface
│   ├── core/                                # App-wide building blocks (Step 2, Step 13)
│        └── __init__.py                     # Marks the folder as a Python package
│        └── config.py                       # Pydantic Settings: env vars + thresholds (cache TTL, RAG 0.7, sync 18h, top-k)
│        └── keyvault.py                     # Key Vault client bootstrap with retry/backoff on cold start
│        └── auth.py                         # Token signature + expiry verification (PyJWT) -> RBAC claims
│        └── clients.py                      # Creates connections to external services in one place (with a URL and a password)
│        └── dependencies.py                 # Provides DB, Redis, Pinecone, user, etc. to FastAPI routes
│        └── startup_checks.py               # Connectivity checks run before the app accepts traffic
│        └── prompt_loader.py                # Loads versioned markdown prompts and records the version used per turn
│        └── constants.py                    # Stores fixed values used throughout the application in one place (languages, roles etc) 
│        └── exceptions.py                   # Defines the different types of errors in the application
│   ├── middleware/                          # Cross-cutting request handling
│        └── __init__.py                     # Marks the folder as a Python package
│        └── auth_middleware.py              # Rejects missing/expired/tampered tokens before any route runs
│        └── correlation_id.py               # Injects a correlation ID to trace one turn end-to-end
│        └── exception_handlers.py           # Defines how errors are handled and shown to the user
│   ├── schemas/                             # Pydantic request/response models
│        └── __init__.py                     # Marks the folder as a Python package
│        └── chat.py                         # ChatRequest, ChatResponse, FollowUpChip, ResolvedLink
│        └── auth.py                         # TokenClaims / RBAC claims model (user_id, role, region, entitlements)
│        └── session.py                      # SessionRecord and ChatTurn models
│        └── marketing.py                    # One consistent structure of Marketing API 
│        └── generation.py                   # It defines what generation LLM should return 
│        └── handler_result.py               # Common streaming response structure for all functionalities 
│        └── routing.py                      # RouterOutput: intents/sub-intents, language tag, expanded queries
│        └── retrieval.py                    # RetrievedChunk, RetrievalResult, source-type enum
│        └── streaming.py                    # SSE event models (token, done)
│        └── errors.py                       # Standard error payload model
│   ├── services/                            # Core business logic, one module per responsibility
│        └── __init__.py                     # Marks the folder as a Python package
│        └── api_cache_service.py            # Manages Redis caching of reusable API responses
│        └── chat_orchestrator.py            # Runs full turn: session > RBAC > cache > route > retrieve > generate > verify > persist
│        └── session_service.py              # New-vs-existing session resolution and short memory window (last N turns)
│        └── rbac_service.py                 # Decides which roles may use the inventory path (Step 4)
│        └── session_timeout_service.py      # common session-timeout utility
│        └── cache_service.py                # Redis (~6h) then pgvector semantic cache; skipped for inventory
│        └── router_service.py               # LLM 1: intent classification, language tag, query expansion, sub-intent split
│        └── retrieval_service.py            # Dispatches to the correct retrieval path(s) per intent
│        └── template_service.py             # Renders existing HTML files using data returned by API
│        └── marketing_service.py            # It reads existing Redis cache , searches and returns the relevant files
│        └── conversation_context_service.py # This stores the session, recent messages, current project, and any pending clarification.
│        └── project_catalog_service.py      # Retrieves the project names dynamically from Redis
│        └── context_builder.py              # Builds token-budgeted, per-source grounded context with top-k limits
│        └── generation_service.py           # LLM 2: streamed answer in detected language, structured output with chips
│        └── guardrail_service.py            # Input scope check and output safety/PII/groundedness check (Foundry / Content Safety)
│        └── judge_service.py                # LLM 3: scores answer vs. retrieved chunks; flags low groundedness
│        └── chip_service.py                 # Hybrid chips: intent template first, LLM fallback only if no match
│        └── language_service.py             # Language-tag fallback rules (previous turn, else English)
│        └── fallback_service.py             # Fixed localized fallback for empty retrieval or failed judge
│        └── response_composer.py            # Assembles answer + 3 chips + resolved links; re-injects masked URLs
│   ├── retrieval/                           # Three source-specific paths, not one generic search
│        └── __init__.py                     # Marks the folder as a Python package
│        └── base.py                         # Defines common rules that all retrieval systems must follow
│        └── currency_api_client.py          # Calls the Currency Rate API and retrieves the latest exchange-rate data.
│        └── salesforce_client.py            # Salesforce HTTP client with retry (Project API + Units API)
│        └── inventory_connector.py          # Live-only: routes to Project API (aggregate) or Units API (per-unit)
│        └── marketing_api_client.py         # Marketing Materials API client with retry (full catalog, no filter)
│        └── marketing_index.py              # Multi-query metadata match against the marketing index (structured, not RAG)
│        └── live_link_resolver.py           # Fetches a fresh non-expired download URL after project/folder match
│        └── walkthrough_rag.py              # Embeds query, matches Pinecone, returns redirect URL (0.7 threshold)
│        └── embeddings.py                   # Azure text-embedding-ada-002 wrapper
│        └── staleness.py                    # Checks whether the marketing index is too old before using it
│   ├── persistence/                         # Database access - user-scoped
│        └── __init__.py                     # Marks the folder as a Python package
│        └── database.py                     # Async Postgres engine/session factory
│        └── models.py                       # Tables: sessions, chat_turns, query_log, semantic_cache, marketing_metadata, sync_state
│        └── models.txt                      # contains all the information about each column of table
│        └── redis_store.py                  # Redis wrapper for the short-lived (~6h) cache
│        └── blob_storage.py                 # Azure Blob wrapper for downloaded marketing images/videos
│        └── repositories/                   # Handles reading and saving data in the database
│          ├── __init__.py                   # Marks the folder as a Python package
│          ├── session_repo.py               # Create/fetch sessions, always scoped to user_id
│          ├── chat_history_repo.py          # Store/read per-turn history for a specific session
│          ├── query_log_repo.py             # Append-only per-turn query log (storage only in Phase 1)
│          ├── semantic_cache_repo.py        # pgvector similarity lookup and expiry of cached answers
│          ├── marketing_metadata_repo.py    # Upsert/query the marketing metadata index
│          ├── sync_state_repo.py            # Read/write last successful sync timestamp
│        └── migrations/                     # Contains changes made to the database table structure (Alembic migrations)
│          ├── env.py                        # Tells Alembic how to connect to the database and find the tables
│          ├── script.py.mako                # Template used by Alembic to create new migration files
│   ├── security/                            # Masking and access control (Steps 4 and 8)
│        └── __init__.py                     # Marks the folder as a Python package
│        └── masking.py                      # Presidio masking of URLs/PII before the LLM; keeps placeholder-to-URL map
│        └── rbac_filter.py                  # Pre-retrieval RBAC filter - blocked queries never reach Salesforce or the LLM
│        └── permissions.py                  # Role/region/entitlement to capability matrix
│   ├── localization/                        # does the language work : English, Hindi, Arabic support
│        └── __init__.py                     # Marks the folder as a Python package
│        └── language_detector.py            # Validates the router's language tag; handles code-mixed / numeric-only input
│        └── translator.py                   # Translates a missing chip/fallback string into the detected language
│        └── locales/                        # stores the translated text
│          ├── en.json                       # English fallback message, error strings, intent-mapped chip templates
│          ├── hi.json                       # Hindi equivalents
│          ├── ar.json                       # Arabic equivalents (RTL handled by the UI)
│   ├── prompts/                             # Version-controlled prompt templates (plain markdown)
│        └── README.md                       # Naming and versioning rules for prompts
│        └── router_v1.md                    # Router: intent, language, query expansion, sub-intent split
│        └── generation_system_v1.md         # Shared grounding rules and structured-output contract (answer + 3 chips)
│        └── generation_inventory_v1.md      # Inventory answer prompt built from structured API fields
│        └── generation_marketing_v1.md      # Marketing answer prompt (masked link placeholders)
│        └── generation_walkthrough_v1.md    # App-walkthrough answer prompt (redirect URL)
│        └── chip_generation_v1.md           # Dynamic chip fallback prompt
│        └── judge_v1.md                     # LLM-as-judge: groundedness, relevance, role-correctness
│   ├── observability/                       # Logging, tracing, metrics (Step 11)
│        └── __init__.py                     # Marks the folder as a Python package
│        └── logger.py                       # Structured JSON logger; PII masked at the point of logging
│        └── app_insights.py                 # Application Insights / Azure Monitor exporter setup
│        └── tracing.py                      # OpenTelemetry tracing setup for FastAPI, httpx, Redis, SQLAlchemy
│        └── metrics.py                      # Counters/histograms: latency, tokens, cache hit rate, guardrail outcomes
│   ├── evaluation/                          # Offline only - never in the live request path (Step 12)
│   ├── scripts/                             # Operational jobs
│        └── __init__.py                     # Marks the folder as a Python package
│        └── refresh_api_cache.py            # Refreshes cached API content in Redis; designed to run every 12 hours
│        └── cache_scheduler.py              # Schedules reusable API refresh function at midnight and noon UTC.
│        └── sync_marketing_metadata.py      # 6-12h cron: full catalog to marketing index, with last-sync check
│        └── check_sync_staleness.py         # Alerts when last successful sync exceeds 18 hours
│        └── ingest_walkthrough_excel.py     # Extracts titles/tags/URLs from Excel, embeds, upserts to Pinecone
│   ├── functions/                           # Azure Functions app for background jobs (separate from the request path)
│        └── function_app.py                 # Timer trigger that calls the sync and staleness scripts
│        └── host.json                       # Azure Functions host configuration
│        └── requirements.txt                # Slim dependencies for the Functions app only
│   ├── utils/                               # Shared helpers with no business logic
│        └── __init__.py                     # Marks the folder as a Python package
│        └── ids.py                          # UUID generation for sessions and messages
│        └── formatters.py                   # Response and log formatting helpers
│        └── time_utils.py                   # UTC timestamps, expiry and staleness math
│        └── retry.py                        # Retry/backoff decorator for Key Vault and source APIs
│        └── sse.py                          # Server-Sent Events encoding for token / done events
└── tests/                                   # Mirrors the source tree; one test module per rule/path
```

## Prerequisites
- Python 3.11
- PostgreSQL with the `pgvector` extension
- Redis
- Access to: Azure OpenAI, Azure Key Vault, Pinecone, Salesforce Project/Units APIs, Marketing Materials API

## Local setup (VS Code)
```bash
python -3.11 -m venv myenv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg   # NLP model used by Presidio
cp .env.example .env                 # fill in local values
python scripts/init_db.py            # pgvector extension + tables
alembic upgrade head
uvicorn main:app --reload --port 8000
```
Open the folder in VS Code and use the **Run API (uvicorn)** debug config from `.vscode/launch.json`.

## Environment variables
See `.env.example` for the full list. In production only `APP_ENV` and `KEY_VAULT_URI` are set; every connection string and API key (Postgres, Redis, Pinecone, Azure OpenAI, Salesforce, Marketing API) is read from **Azure Key Vault** at startup and never logged. Key tunables: `CACHE_TTL_SECONDS` (21600), `RAG_SIMILARITY_THRESHOLD` (0.7), `MARKETING_SYNC_STALE_AFTER_HOURS` (18), `MEMORY_WINDOW_TURNS`, `TOP_K_*`.


## Deployment (Phase 1)
Local Git deployment to Azure App Service - **no container is built**.
1. Set the App Service Startup Command to `startup.sh`.
2. Set `APP_ENV=prod` and `KEY_VAULT_URI`; grant the App Service managed identity access to Key Vault.
3. `git push azure main`.
4. Deploy `functions/` separately as an Azure Functions app (marketing sync every 6-12h + staleness check).

The `Dockerfile` and `.dockerignore` are kept for a later phase only.

## Key behaviours to preserve
- Inventory data is **never cached** and is fetched **live** per turn; only one of Project API / Units API is called per turn.
- RBAC is enforced **before** retrieval - restricted data is never fetched.
- Download URLs are masked before the LLM and re-injected by the response composer; links are resolved fresh, never cached.
- No retrieved content (or low judge score) returns the fixed localized fallback, never a guessed answer.
- Every response carries exactly 3 follow-up chips (template first, LLM fallback only if no match).
- Answer text streams token-by-token; chips, links and guardrail status arrive in the final `done` event.
- Logs store chunk references, not full documents, with PII masked at the point of logging (30-day retention in Application Insights).

## Out of scope (Phase 1)
Voice, ROI calculator, reporting/Power BI, admin dashboard, conversation-review workflow, KB management UI, human escalation path.