# How to use AI News Brief

Step-by-step guide for running the pipeline on your machine and (optionally) on a schedule or in GitHub Actions.

## Prerequisites

- **Python 3.11+** (3.12 works; matches the example GitHub Actions workflow).
- **Internet access** for RSS feeds and OpenAI (unless you use mock collectors and accept stub scoring).
- An **OpenAI API key** if you want real LLM scoring, embeddings, clustering, and the daily brief. Without a key, the pipeline falls back to neutral scores and stub brief content.

## 1. Clone and enter the project

```powershell
cd "path\to\AI News Finder"
```

Use the folder that contains `pyproject.toml` and `config/`.

## 2. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On first use, if execution policy blocks activation, run once (as Administrator if needed):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 3. Install the package

**Editable install with dev dependencies (tests):**

```powershell
pip install -e ".[dev]"
```

**PostgreSQL only** (if you use `DATABASE_URL` with Postgres):

```powershell
pip install -e ".[dev,postgres]"
```

## 4. Configure environment variables

1. Copy the example file:

   ```powershell
   copy .env.example .env
   ```

2. Edit `.env` and set at least:

   | Variable | Purpose |
   | --- | --- |
   | `OPENAI_API_KEY` | Required for real scoring, embeddings, and brief generation. |
   | `DATABASE_URL` | Default is SQLite under `./data/`; create the DB with `init-db` (below). |
   | `NEWS_AGENT_CONFIG` | Defaults to `config/default.yaml`. |

3. **Never commit `.env`** — it is listed in `.gitignore`. Keep keys out of screenshots and chats.

Optional collectors:

- **Reddit:** set `REDDIT_ENABLED=true` and fill `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and a sensible `REDDIT_USER_AGENT`. Register an app at [Reddit apps](https://www.reddit.com/prefs/apps).
- **X/Twitter:** set `TWITTER_ENABLED=true` and `TWITTER_BEARER_TOKEN` if your tier allows recent search.

To avoid Reddit/Twitter network calls while iterating, set `MOCK_EXTERNAL_APIS=true`.

## 5. Initialize the database (full pipeline)

SQLite needs the `./data` directory; the app expects a file path like `sqlite:///./data/news_agent.sqlite3`.

```powershell
python -m news_agent.cli init-db
```

Skip this if you only use **`run --simple`** and never need DB snapshots (see below).

## 6. Run the pipeline

### Full pipeline (default)

Fetches feeds, normalizes, dedupes, scores with OpenAI, clusters with embeddings, generates the brief, writes reports, and persists to the DB:

```powershell
python -m news_agent.cli run
```

Console prints JSON with `run_id`, `stats`, and paths to artifacts.

### Lighter run: `--simple`

Skips embedding clustering (one cluster per scored item), skips LLM SQLite cache, and reduces DB snapshot usage — still writes Markdown and Word outputs:

```powershell
python -m news_agent.cli run --simple
```

### Demo / offline-friendly

Includes deterministic mock items (useful without network credentials):

```powershell
python -m news_agent.cli run --mock-collectors
```

Combine with `--simple` if you want a minimal path:

```powershell
python -m news_agent.cli run --mock-collectors --simple
```

### Custom config or output

```powershell
python -m news_agent.cli run --config config\default.yaml
python -m news_agent.cli run --output-dir path\to\folder
```

Skip writing report files (still runs pipeline logic):

```powershell
python -m news_agent.cli run --no-write
```

### Console entry point

After install, you can also use:

```powershell
ai-news-brief run
ai-news-brief init-db
```

## 7. Where to find outputs

Reports are written under **`outputs/`**, typically in a dated folder, for example:

- `outputs\YYYY_MM_DD\brief_*.md`
- `outputs\YYYY_MM_DD\brief_*.docx`

See `examples/sample_report.md` for a stylized example of the Markdown shape.

## 8. Tune behavior (`config/default.yaml`)

Edit YAML (not code) to change:

- **RSS feeds** — `rss_feeds`: add URLs and map `weight_key` to `source_weights`.
- **Prefilter** — length limits, blocked URL patterns, fluff keywords.
- **Scoring thresholds** — min scores, hype/slop rejection limits.
- **Report** — `top_stories` (digest size) and `max_top_stories_per_source_id` (spread across sources).

Point the app at another file with `--config` or `NEWS_AGENT_CONFIG` in `.env`.

## 9. Schedule a daily run

### Windows Task Scheduler

- Trigger: daily at your preferred local time (e.g. 8:00 AM).
- Action: `powershell.exe`
- Arguments: `-File "C:\full\path\to\AI News Finder\scripts\run_daily.ps1"`

The script activates the repo’s `.venv` if present, then runs `python -m news_agent.cli run`.

### Linux / macOS cron

See `scripts/crontab.example` and adapt paths and user.

### GitHub Actions

The repository includes a **template** at `docs/github-workflow-daily_brief.yml`. Copy it to `.github/workflows/daily_brief.yml` in your fork, then:

1. Add repository secret **`OPENAI_API_KEY`**.
2. Adjust the `cron` schedule — Actions use **UTC**, not local time.
3. Optionally enable the commented “commit reports” step if you want outputs pushed to a branch.

## 10. Run tests

```powershell
pytest -q
```

Smoke tests cover the pipeline with mocks and no live OpenAI key.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `OPENAI_API_KEY` errors or empty briefs | Key set in `.env`, billing/quota on the OpenAI account, model name (`OPENAI_MODEL`) available to your key. |
| No Reddit/Twitter items | `REDDIT_ENABLED` / `TWITTER_ENABLED`, credentials, and whether APIs return data for your tier; try `MOCK_EXTERNAL_APIS=true` to isolate RSS. |
| SQLite errors | Run `init-db`; ensure `DATABASE_URL` path is writable; on CI, some runners need `./data` created first. |
| Empty or sparse RSS | Feed URL changed or blocked; add feeds in `config/default.yaml`. Some feeds block datacenter IPs (e.g. certain cloud runners). |
| Wrong “last 24 hours” window | Optional: set `PIPELINE_SINCE_HOURS` in `.env` for tests or custom windows. |

For deeper architecture, scoring rubric, and prompt file layout, see **README.md**.
