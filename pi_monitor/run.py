#!/usr/bin/env python3
"""
MCP server for Pi Network Monitor.
Exposes tools for nanobot to query ping/speedtest diagnostics and reports.
"""

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure we can import from parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from fastmcp import FastMCP
except ImportError:
    print("fastmcp not installed. Run: pip install fastmcp", file=sys.stderr)
    sys.exit(1)

from pi_monitor.config import load_config
from pi_monitor.storage import (
    get_connection,
    get_default_db_path,
    get_ping_outage_report,
    get_speedtest_summary,
    get_latency_summary,
    get_weekly_report,
    get_db_stats,
)


def _get_db_path() -> Path:
    """Resolve database path from config or default."""
    config = load_config()
    if config.get("db_path"):
        return Path(config["db_path"])
    if config.get("data_dir"):
        return Path(config["data_dir"]) / "pi_monitor.db"
    return get_default_db_path()


mcp = FastMCP(
    name="Pi Network Monitor",
    instructions="Query persistent ping and speedtest diagnostics from a Raspberry Pi running the pi_monitor daemon.",
)


@mcp.tool
def ping_outage_report(days: int = 7, target_ip: Optional[str] = None) -> str:
    """
    Get ping outage statistics for the last N days.
    Returns outage count, success rate, uptime percent, and outages per day.
    Optionally filter by target_ip (e.g. '192.168.1.1' or '8.8.8.8').
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return json.dumps({"error": "No database found. Is the pi_monitor daemon running?"})
    with get_connection(db_path) as conn:
        report = get_ping_outage_report(conn, days=days, target_ip=target_ip)
    return json.dumps(report, indent=2)


@mcp.tool
def speedtest_summary(days: int = 7) -> str:
    """
    Get speedtest summary for the last N days.
    Returns download/upload averages, min, max, median, and stability.
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return json.dumps({"error": "No database found. Is the pi_monitor daemon running?"})
    with get_connection(db_path) as conn:
        summary = get_speedtest_summary(conn, days=days)
    return json.dumps(summary, indent=2)


@mcp.tool
def latency_summary(days: int = 7, target_ip: Optional[str] = None) -> str:
    """
    Get ping latency summary (avg, min, max) for successful pings over the last N days.
    Optionally filter by target_ip.
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return json.dumps({"error": "No database found. Is the pi_monitor daemon running?"})
    with get_connection(db_path) as conn:
        summary = get_latency_summary(conn, days=days, target_ip=target_ip)
    return json.dumps(summary, indent=2)


@mcp.tool
def storage_stats() -> str:
    """
    Get database storage stats: row counts for ping and speedtest tables.
    Useful to monitor data volume and retention.
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return json.dumps({"error": "No database found. Is the pi_monitor daemon running?"})
    with get_connection(db_path) as conn:
        stats = get_db_stats(conn)
    stats["db_path"] = str(db_path)
    return json.dumps(stats, indent=2)


@mcp.tool
def weekly_network_report(days: int = 7) -> str:
    """
    Get a human-readable weekly network report combining outages, speedtest, and latency.
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return "No database found. Is the pi_monitor daemon running?"
    with get_connection(db_path) as conn:
        return get_weekly_report(conn, days=days)


if __name__ == "__main__":
    mcp.run()
