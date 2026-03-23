# AI News Brief Agent

Production-oriented Python repo that ingests AI-related content from **RSS**, **Reddit** (optional OAuth), and **X/Twitter** (optional bearer token), then runs a staged pipeline:

**fetch → normalize → dedupe → heuristic prefilter → OpenAI scoring → embedding clustering → OpenAI daily brief → export (Markdown + Word `.docx`)**

Use **`python -m news_agent.cli run --simple`** for a lighter path: no embedding clustering (one cluster per scored item), no LLM SQLite cache for scoring/brief, and no DB persistence dependency—while still writing the same Markdown/Word outputs.

The design favors **modular collectors**, **Pydantic schemas**, **SQLite or Postgres** persistence, **versioned prompt files**, and **structured logging** with **retries** on OpenAI calls.

## Architecture

```mermaid
flowchart LR
  subgraph ingest [Ingest]
    RSS[RSS collectors]
    RD[Reddit collector]
    TW[Twitter collector]
  end
  subgraph core [Core pipeline]
    N[Normalize ContentItem]
    D[Dedupe URL + fingerprint]
    H[Heuristic prefilter]
    S[OpenAI score + gate]
    C[Embed + cluster]
    B[OpenAI brief]
  end
  subgraph out [Outputs]
    MD[Markdown]
    DOCX[Word docx]
    DB[(SQLite/Postgres)]
  end
  RSS --> N
  RD --> N
  TW --> N
  N --> D --> H --> S --> C --> B
  B --> MD
  B --> DOCX
  S --> DB
  C --> DB
```

### Layout

- `src/news_agent/collectors/` — source adapters (`SourceCollector` ABC, RSS/Reddit/Twitter/mock)
- `src/news_agent/normalizers/` — `RawIngest` → `ContentItem`
- `src/news_agent/filters/` — URL/fingerprint dedupe + deterministic prefilters
- `src/news_agent/scoring/` — OpenAI structured JSON → `ItemScores` + `final_score`
- `src/news_agent/clustering/` — embeddings + greedy cosine merge → `StoryCluster`
- `src/news_agent/summarization/` — daily brief JSON → `DailyBriefReport`
- `src/news_agent/reporting/` — Markdown and Word (`.docx`) exporters
- `src/news_agent/storage/` — SQLAlchemy models, snapshots, LLM cache
- `src/news_agent/jobs/` — orchestration (`run_daily_pipeline`)
- `src/news_agent/prompts/` — **versioned** `.txt` templates (not hardcoded in code)
- `config/default.yaml` — feeds, weights, thresholds
- `tests/` — unit tests for dedupe, heuristics, scoring math

## Recommended data model

| Model | Role |
| --- | --- |
| `RawIngest` | Collector-native row before normalization |
| `ContentItem` | Unified item: source metadata, text, engagement, audit `history[]` |
| `ItemScores` | Explainable LLM scores + computed `final_score` |
| `StoryCluster` | Event cluster: canonical item, members, supporting URLs |
| `DailyBriefReport` | Final sections + `BriefEntry` rows for rendering |

Persistence tables (see `src/news_agent/storage/orm.py`): `pipeline_runs`, `items` (JSON snapshots per stage), `clusters`, `llm_cache`, `report_artifacts`.

## First-pass filtering rubric (deterministic)

Configured under `prefilter` in `config/default.yaml`:

- Drop items shorter than `min_text_length` or longer than `max_text_length`.
- Drop items whose URL matches `block_url_patterns` (e.g. tracking noise).
- Optionally drop when many `fluff_keywords` appear (engagement bait / meme language).
- Flag (but do not necessarily drop) known `slop_phrases` so the LLM can apply `ai_slop_penalty`.

URL + body-fingerprint dedupe runs **before** LLM calls to save cost.

## First-pass scoring rubric (LLM + code)

The LLM returns 0–100 fields with rationales (`src/news_agent/prompts/post_quality_v1.txt` + `ai_slop_signals_v1.txt`). Code combines them in `compute_final_score()`:

- Weighted blend of importance, credibility, novelty, substance.
- Subtract scaled penalties for hype and AI-slop signals.
- Multiply by `source_weights` from config (per-feed or per `source_type`).

Thresholds in `config/default.yaml` under `scoring` gate `rejected` vs `accepted` vs `overhyped` (high hype but not auto-spam).

## Setup

```powershell
cd "path\to\AI News Finder"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # then fill secrets
python -m news_agent.cli init-db
```

### Environment variables

See `.env.example`. Minimum for full functionality:

- `OPENAI_API_KEY` — required for real scoring, embeddings, and brief generation (without it, neutral fallback scores + stub brief sections are used).
- `DATABASE_URL` — default SQLite file under `./data/` (run `init-db` once after install).
- `REDDIT_*` — set `REDDIT_ENABLED=true` **and** OAuth app credentials for Reddit ingestion.
- `TWITTER_BEARER_TOKEN` — set `TWITTER_ENABLED=true` for recent search (tier / billing may apply).

Optional Postgres:

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/news_agent
pip install "psycopg[binary]"
```

## Run

```powershell
# One-shot pipeline (writes outputs\YYYY_MM_DD\brief_*.md|.docx)
python -m news_agent.cli run

# Include deterministic mock items (good for demos)
python -m news_agent.cli run --mock-collectors

# Lighter run: skip embedding clustering + LLM DB cache (see docstring / README)
python -m news_agent.cli run --simple

# Custom config path
python -m news_agent.cli run --config config\default.yaml
```

Console prints a JSON summary with `run_id`, `stats`, and artifact paths.

## Scheduling (8:00 AM local)

- **Windows Task Scheduler**: trigger daily at 08:00, action `powershell.exe`, argument `-File "...\scripts\run_daily.ps1"`.
- **cron** (server local time): see `scripts/crontab.example`.
- **GitHub Actions**: `.github/workflows/daily_brief.yml` — **Actions use UTC**, so adjust the cron to match your timezone (example comment in the workflow file). Add repository secret `OPENAI_API_KEY`.

## OpenAI prompt templates (versioned)

| File | Purpose |
| --- | --- |
| `post_quality_v1.txt` | Post quality + classification + scores JSON schema |
| `ai_slop_signals_v1.txt` | Injected slop/spam checklist |
| `story_importance_v1.txt` | Optional standalone tier rubric |
| `daily_brief_v1.txt` | Final brief JSON schema |

## External API notes / TODOs

- **Reddit**: requires a registered app + `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` (application-only OAuth). Private subs or higher limits may need a user OAuth flow (not implemented here).
- **X/Twitter**: `TWITTER_BEARER_TOKEN` must have access to recent search; many orgs need paid tiers — collector is structured but often returns empty without valid access.
- **RSS**: no key required; some feeds may block datacenter IPs (GitHub Actions); add more feeds in `config/default.yaml`.
- Set `MOCK_EXTERNAL_APIS=true` to skip Reddit/Twitter network calls while iterating locally.

## Tests

```powershell
pytest -q
```

`tests/test_daily_pipeline_smoke.py` runs the full pipeline with mock collectors, no OpenAI key, and `--simple`-equivalent settings (offline-safe) and checks Markdown output plus non-empty `top_stories`.

## Sample output

See `examples/sample_report.md` for a stylized brief. Real runs emit timestamped files under `outputs/`.

**Report size:** `config/default.yaml` → `report.top_stories` (default **7**) caps the digest after the brief model runs. **`report.max_top_stories_per_source_id`** (default **2**) then spreads the digest across distinct ingest `source_id` values where possible, backfilling from other clusters to keep the digest full. The **Word** file (`.docx`) is optimized for reading in Microsoft Word.

**RSS times:** entry timestamps are parsed as **timezone-aware UTC** (RFC strings with offsets are normalized; naive values are treated as UTC) so the `since` window compares consistently with pipeline cutoff times.
