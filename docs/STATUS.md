# Project Status – V2 Milestone 1: Persistence

Release tag: `v2-m1-persistence` (commit `4575c83`). This snapshot captures the repository after landing the first persistence-focused milestone for the natural-language (V2) workflow.

## Shipped Features
- **V1 strict pipeline** – `/upload-audio` still powers the original workflow (transcribe, strict parser, CSV export, SQLite persistence of transcripts + events).
- **V2 chunk pipeline with storage** – `/chunks/decompose` now records narration chunks, raw/model outputs, and projected events in dedicated tables; `/chunks/{id}` retrieves the latest decomposition snapshot.
- **Match-level V2 aggregation** – `/matches/{match_id}/v2-events` returns every projected event (with chunk metadata) for a match/period, suitable for QA or analysis tooling.
- **StatsBomb ingestion scaffolding** – `/statsbomb/raw` stores raw JSON blobs, and `/statsbomb/matches/{match_id}/projection` upserts `sb_matches` rows and rewrites the hybrid `sb_events` table.
- **Migration + bookkeeping** – `backend/migrate.py` plus `backend/migrations/20251215_01_add_v2_and_statsbomb.sql` create all V2/StatsBomb tables and a `schema_migrations` ledger.

## Current API Endpoints
| Endpoint | Method | Description |
| --- | --- | --- |
| `/` | GET | Minimal HTML form to exercise `/upload-audio`. |
| `/upload-audio` | POST | V1 strict pipeline (transcribe, parse, CSV + SQLite persistence). |
| `/chunks/decompose` | POST | V2 chunk decomposition (persists chunk, decomposition metadata, projected events). |
| `/chunks/{chunk_id}` | GET | Fetch chunk metadata + latest decomposition + projected events. |
| `/matches/{match_id}/events` | GET | Legacy V1 events for a match/period. |
| `/matches/{match_id}/v2-events` | GET | All V2 projected events for a match/period (includes chunk metadata). |
| `/uploads` | GET | List recent uploads (V1 runs). |
| `/uploads/{upload_id}` | GET | Detailed view of a single V1 upload. |
| `/transcripts/{filename}` | GET | Download stored timestamped transcript (V1). |
| `/events/{filename}` | GET | Download stored events CSV (V1). |
| `/statsbomb/raw` | POST | Persist raw StatsBomb JSON payloads for auditing. |
| `/statsbomb/matches/{match_id}/projection` | POST | Upsert `sb_matches` row and rewrite `sb_events` for a match; optionally records a raw snapshot. |

## Database Tables (SQLite)
- `schema_migrations` – migration bookkeeping.
- `matches`, `uploads`, `events` – original V1 pipeline storage (match metadata, upload metadata, structured events).
- `narration_chunks` – V2 narration metadata (window, transcript, status).
- `chunk_decompositions` – raw LLM output, parsed JSON envelope, timing/cost data per chunk.
- `v2_events` – hybrid projection of decomposed events (columns + `extra_fields` JSON).
- `sb_raw_files` – raw StatsBomb JSON payloads (lossless ingest log).
- `sb_matches` – canonical match metadata projection.
- `sb_events` – hybrid StatsBomb event records (core columns + lossless JSON).

## Migration Runner & Smoke Tests
- **Migration runner** – `backend/migrate.py` executes any SQL file in `backend/migrations/` (currently `20251215_01_add_v2_and_statsbomb.sql`) and records completion in `schema_migrations`.
- **Smoke-test coverage (FastAPI TestClient)**:
  - `POST /chunks/decompose` success path: fake LLM response produced a stored chunk/decomposition and `/chunks/{id}` reflected persisted metadata + projected event.
  - `POST /chunks/decompose` failure path: simulated parse error returned HTTP 422 and `/chunks/{id}` showed `status=error` with `raw_llm_text` captured.
  - `GET /chunks/{id}` confirmed deterministic “latest decomposition” ordering (created_at DESC, id DESC).

## Next Milestone Candidates
- Build lightweight QA/visualization tooling for `/matches/{match_id}/v2-events` (comparisons, filters, CSV export).
- Extend chunk workflow with re-run / retry controls and richer prompt-version metadata.
- Wire StatsBomb projections into downstream analytics helpers (quick filters, dashboards).
- Harden pagination/filtering for `/uploads`, `/chunks`, and match endpoints to support longer sessions.
