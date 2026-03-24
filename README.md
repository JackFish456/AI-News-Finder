# AI News Brief Agent

**Daily AI news digest:** ingest from **RSS**, optional **Reddit** and **X/Twitter**, then run a staged pipeline — **fetch → normalize → dedupe → heuristic prefilter → OpenAI scoring → embedding clustering → OpenAI daily brief → export (Markdown + Word `.docx`)**.

The codebase is built for **maintainability**: modular collectors, **Pydantic** models, **SQLite or Postgres**, **versioned prompt files** (`.txt`), and **structured logging** with **retries** on OpenAI calls.

**New here?** Follow **[HOW_TO_USE.md](HOW_TO_USE.md)** for install, environment variables, commands, scheduling, and troubleshooting.

---

## Contents

- [Quick start](#quick-start)
- [What you get](#what-you-get)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Configuration](#configuration)
- [Running the pipeline](#running-the-pipeline)
- [Outputs](#outputs)
- [Scheduling & automation](#scheduling--automation)
- [OpenAI prompts (versioned)](#openai-prompts-versioned)
- [Tests](#tests)
- [External APIs & limits](#external-apis--limits)

---

## Quick start

```powershell
cd "path\to\AI News Finder"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # add OPENAI_API_KEY and review DATABASE_URL
python -m news_agent.cli init-db
python -m news_agent.cli run
```

Use **`python -m news_agent.cli run --simple`** for a lighter path: no embedding clustering (one cluster per scored item), no LLM SQLite cache for scoring/brief, and fewer DB snapshots — while still writing Markdown and Word outputs.

Full step-by-step instructions: **[HOW_TO_USE.md](HOW_TO_USE.md)**.

---

## What you get

| Capability | Description |
| --- | --- |
| **Multi-source ingest** | RSS by default; Reddit and Twitter when enabled and credentialed. |
| **Cost-aware filtering** | URL + fingerprint dedupe and heuristics **before** LLM calls. |
| **Explainable scoring** | LLM returns structured scores; code computes a weighted `final_score` with penalties. |
| **Story clustering** | Embeddings + greedy cosine merge (skipped in `--simple` mode). |
| **Daily brief** | Model-generated sections + digest capped by config (`report.top_stories`). |
| **Exports** | Timestamped **Markdown** and **Word** under `outputs/`. |

---

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

---

## Repository layout

| Path | Role |
| --- | --- |
| `src/news_agent/collectors/` | Source adapters (`SourceCollector` ABC, RSS / Reddit / Twitter / mock) |
| `src/news_agent/normalizers/` | `RawIngest` → `ContentItem` |
| `src/news_agent/filters/` | URL/fingerprint dedupe + deterministic prefilters |
| `src/news_agent/scoring/` | OpenAI structured JSON → `ItemScores` + `final_score` |
| `src/news_agent/clustering/` | Embeddings + greedy cosine merge → `StoryCluster` |
| `src/news_agent/summarization/` | Daily brief JSON → `DailyBriefReport` |
| `src/news_agent/reporting/` | Markdown and Word (`.docx`) exporters |
| `src/news_agent/storage/` | SQLAlchemy models, snapshots, LLM cache |
| `src/news_agent/jobs/` | Orchestration (`run_daily_pipeline`) |
| `src/news_agent/prompts/` | **Versioned** `.txt` templates |
| `config/default.yaml` | Feeds, weights, thresholds |
| `tests/` | Unit and smoke tests |
| `docs/github-workflow-daily_brief.yml` | **Template** GitHub Actions workflow (copy to `.github/workflows/`) |

---

## Data model (summary)

| Model | Role |
| --- | --- |
| `RawIngest` | Collector-native row before normalization |
| `ContentItem` | Unified item: source metadata, text, engagement, audit `history[]` |
| `ItemScores` | Explainable LLM scores + computed `final_score` |
| `StoryCluster` | Event cluster: canonical item, members, supporting URLs |
| `DailyBriefReport` | Final sections + `BriefEntry` rows for rendering |

Persistence tables (see `src/news_agent/storage/orm.py`): `pipeline_runs`, `items` (JSON snapshots per stage), `clusters`, `llm_cache`, `report_artifacts`.

---

## Configuration

### Environment variables

See **`.env.example`**. Minimum for full functionality:

- **`OPENAI_API_KEY`** — required for real scoring, embeddings, and brief generation (without it, neutral fallback scores + stub brief sections are used).
- **`DATABASE_URL`** — default SQLite file under `./data/` (run `init-db` once after install).
- **`REDDIT_*`** — set `REDDIT_ENABLED=true` **and** OAuth app credentials for Reddit ingestion.
- **`TWITTER_BEARER_TOKEN`** — set `TWITTER_ENABLED=true` for recent search (tier / billing may apply).

Optional Postgres:

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/news_agent
pip install "psycopg[binary]"
```

### YAML (`config/default.yaml`)

- **`source_weights`** — multiplicative boost per feed / `source_type` after LLM scoring.
- **`prefilter`** — length limits, `block_url_patterns`, fluff keywords, slop phrases (deterministic; runs before LLM).
- **`dedupe` / clustering** — embedding batch size and cosine merge threshold.
- **`scoring`** — min scores, hype/slop rejection limits, LLM cache TTL.
- **`report`** — `top_stories` (digest size) and `max_top_stories_per_source_id` (spread across sources).
- **`rss_feeds`**, **`reddit_subreddits`**, **`twitter_queries`** — ingest sources.

**First-pass filtering (deterministic):** drop items outside length bounds; drop blocked URL patterns; optional fluff-keyword rejection; flag slop phrases for LLM penalties.

**First-pass scoring (LLM + code):** prompts in `src/news_agent/prompts/`; combination logic in `compute_final_score()` — weighted blend of importance, credibility, novelty, substance; penalties for hype and AI-slop signals; multiplied by `source_weights`. Thresholds gate `rejected` vs `accepted` vs `overhyped`.

---

## Running the pipeline

```powershell
# One-shot (writes outputs\YYYY_MM_DD\brief_*.md|.docx)
python -m news_agent.cli run

# Deterministic mock items (demos / limited network)
python -m news_agent.cli run --mock-collectors

# Lighter run: skip embedding clustering + LLM DB cache
python -m news_agent.cli run --simple

# Custom config
python -m news_agent.cli run --config config\default.yaml
```

Console prints JSON with `run_id`, `stats`, and artifact paths.

Installed package entry point:

```powershell
ai-news-brief run
ai-news-brief init-db
```

---

## Outputs

- **Folder:** `outputs/` (dated subfolders).
- **Formats:** Markdown and Word (`.docx`) optimized for reading in Microsoft Word.
- **Digest size:** `report.top_stories` (default **7**) caps the digest after the brief model runs. **`report.max_top_stories_per_source_id`** (default **2**) spreads the digest across distinct ingest `source_id` values where possible, backfilling from other clusters.
- **Sample:** `examples/sample_report.md`.

**RSS times:** entry timestamps are parsed as **timezone-aware UTC** (RFC strings with offsets are normalized; naive values are treated as UTC) so the `since` window aligns with pipeline cutoff times.

---

## Scheduling & automation

| Method | Notes |
| --- | --- |
| **Windows Task Scheduler** | Daily trigger; run `scripts\run_daily.ps1` with PowerShell. |
| **cron** | See `scripts/crontab.example`. |
| **GitHub Actions** | Copy `docs/github-workflow-daily_brief.yml` → `.github/workflows/daily_brief.yml`. Actions use **UTC** — adjust `cron`. Add secret **`OPENAI_API_KEY`**. Artifact upload is included; optional git commit step is commented in the template. |

---

## OpenAI prompts (versioned)

| File | Purpose |
| --- | --- |
| `post_quality_v1.txt` | Post quality + classification + scores JSON schema |
| `ai_slop_signals_v1.txt` | Injected slop/spam checklist |
| `story_importance_v1.txt` | Optional standalone tier rubric |
| `daily_brief_v1.txt` | Final brief JSON schema |

---

## Tests

```powershell
pytest -q
```

`tests/test_daily_pipeline_smoke.py` runs the full pipeline with mock collectors, no OpenAI key, and `--simple`-equivalent settings (offline-safe) and checks Markdown output plus non-empty `top_stories`.

---

## External APIs & limits

- **Reddit:** requires a registered app + `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` (application-only OAuth). Private subs or higher limits may need a user OAuth flow (not implemented here).
- **X/Twitter:** `TWITTER_BEARER_TOKEN` must allow recent search; many orgs need paid tiers — the collector may return little or nothing without valid access.
- **RSS:** no key required; some feeds may block datacenter IPs (e.g. some CI runners). Add or change feeds in `config/default.yaml`.
- **Local iteration:** set `MOCK_EXTERNAL_APIS=true` to skip Reddit/Twitter network calls.

---

## License

MIT — see `pyproject.toml`.
