from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from news_agent.jobs.daily_pipeline import run_daily_pipeline
from news_agent.settings import get_settings
from news_agent.storage.db import get_engine, init_db
from news_agent.utils.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="AI News Brief agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run the daily pipeline once")
    p_run.add_argument("--config", type=Path, default=None, help="Path to YAML config")
    p_run.add_argument(
        "--mock-collectors",
        action="store_true",
        help="Include mock collector data (useful without network credentials)",
    )
    p_run.add_argument("--no-write", action="store_true", help="Skip writing report files")
    p_run.add_argument("--output-dir", type=Path, default=None)
    p_run.add_argument(
        "--simple",
        action="store_true",
        help="Lightweight run: no embedding clustering (one cluster per item), no LLM DB cache, fewer DB snapshots",
    )

    p_init = sub.add_parser("init-db", help="Create database tables")

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    log = logging.getLogger("news_agent.cli")

    if args.cmd == "init-db":
        engine = get_engine(settings.database_url)
        init_db(engine)
        log.info("Database initialized: %s", settings.database_url)
        return 0

    if args.cmd == "run":
        result = run_daily_pipeline(
            settings=settings,
            config_path=args.config,
            include_mock=args.mock_collectors,
            write_reports=not args.no_write,
            output_dir=args.output_dir,
            simple=args.simple,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
