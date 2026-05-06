from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.literature.harvest import (  # noqa: E402
    DEFAULT_QUERY_TERMS,
    HarvestConfig,
    harvest_sources,
    write_harvest_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest flyback-design literature from public sources.")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--openalex-max", type=int, default=1500)
    parser.add_argument("--crossref-max", type=int, default=1200)
    parser.add_argument("--arxiv-max", type=int, default=300)
    parser.add_argument("--year-from", type=int, default=1990)
    parser.add_argument("--query", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_root or f"sources/flyback_literature_{stamp}"
    config = HarvestConfig(
        query_terms=args.query or list(DEFAULT_QUERY_TERMS),
        openalex_max_records=args.openalex_max,
        crossref_max_records=args.crossref_max,
        arxiv_max_records=args.arxiv_max,
        year_from=args.year_from,
        polite_email=os.getenv("OPENALEX_MAILTO") or os.getenv("CROSSREF_MAILTO"),
    )
    result = harvest_sources(config)
    paths = write_harvest_outputs(result, output_root)
    print(paths["output_dir"])
    print(paths["summary"])
    print(paths["benchmark_seed_csv"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
