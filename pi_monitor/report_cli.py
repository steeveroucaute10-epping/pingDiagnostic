#!/usr/bin/env python3
"""
CLI to print network report when MCP is unavailable.
Use as exec fallback for nanobot when MCP tools are not configured.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_monitor.config import load_config
from pi_monitor.storage import get_connection, get_default_db_path, get_weekly_report


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Print network diagnostic report")
    parser.add_argument("--days", type=int, default=7, help="Number of days to include")
    args = parser.parse_args()

    config = load_config()
    if config.get("db_path"):
        db_path = Path(config["db_path"])
    elif config.get("data_dir"):
        db_path = Path(config["data_dir"]) / "pi_monitor.db"
    else:
        db_path = get_default_db_path()

    if not db_path.exists():
        print("No database found. Is the pi_monitor daemon running?")
        sys.exit(1)

    with get_connection(db_path) as conn:
        print(get_weekly_report(conn, days=args.days))


if __name__ == "__main__":
    main()
