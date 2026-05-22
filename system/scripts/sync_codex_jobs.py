from __future__ import annotations

import argparse
from pathlib import Path

from system.services.codex_job_sync import CodexJobSync


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Codex job tracker into Hermes memory.")
    parser.add_argument("--jobs-path", type=Path, default=None)
    args = parser.parse_args()

    summary = CodexJobSync.create(source_path=args.jobs_path).sync()
    print(f"Synced {summary['total_open_jobs']} open Codex jobs into Hermes memory.")


if __name__ == "__main__":
    main()
