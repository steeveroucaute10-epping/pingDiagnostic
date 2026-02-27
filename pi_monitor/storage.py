#!/usr/bin/env python3
"""
Long-term storage for ping and speedtest diagnostics.
Uses SQLite for persistence and aggregation queries.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional


def get_default_db_path() -> Path:
    """Get default database path (next to pi_monitor module)."""
    base = Path(__file__).resolve().parent.parent
    return base / "data" / "pi_monitor.db"


@contextmanager
def get_connection(db_path: Optional[Path] = None):
    """Context manager for SQLite connection."""
    path = db_path or get_default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ping_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            target_ip TEXT NOT NULL,
            duration_ms REAL,
            status TEXT NOT NULL,
            computer_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ping_timestamp ON ping_results(timestamp);
        CREATE INDEX IF NOT EXISTS idx_ping_target ON ping_results(target_ip);
        CREATE INDEX IF NOT EXISTS idx_ping_status ON ping_results(status);

        CREATE TABLE IF NOT EXISTS speedtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            download_mbps REAL,
            upload_mbps REAL,
            ping_ms REAL,
            status TEXT NOT NULL,
            error TEXT,
            computer_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_speedtest_timestamp ON speedtest_results(timestamp);
        CREATE INDEX IF NOT EXISTS idx_speedtest_status ON speedtest_results(status);
    """)


def insert_ping(
    conn: sqlite3.Connection,
    timestamp: datetime,
    target_ip: str,
    duration_ms: Optional[float],
    status: str,
    computer_name: str = "unknown",
) -> None:
    """Insert a single ping result."""
    ts_str = timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
    conn.execute(
        """
        INSERT INTO ping_results (timestamp, target_ip, duration_ms, status, computer_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ts_str, target_ip, duration_ms, status, computer_name),
    )


def insert_speedtest(
    conn: sqlite3.Connection,
    timestamp: datetime,
    download_mbps: float,
    upload_mbps: float,
    ping_ms: float,
    status: str,
    error: Optional[str],
    computer_name: str = "unknown",
) -> None:
    """Insert a single speedtest result."""
    ts_str = timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
    conn.execute(
        """
        INSERT INTO speedtest_results
        (timestamp, download_mbps, upload_mbps, ping_ms, status, error, computer_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ts_str, download_mbps, upload_mbps, ping_ms, status, error, computer_name),
    )


def get_ping_outage_report(
    conn: sqlite3.Connection,
    days: int = 7,
    target_ip: Optional[str] = None,
) -> dict:
    """
    Compute outage statistics for the given period.
    Returns: outage count, total outage time, disruptions per hour, etc.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    target_filter = "AND target_ip = ?" if target_ip else ""
    params = [since] if not target_ip else [since, target_ip]

    # Get all ping results in order
    rows = conn.execute(
        f"""
        SELECT timestamp, target_ip, duration_ms, status
        FROM ping_results
        WHERE timestamp >= ?
        {target_filter}
        ORDER BY timestamp
        """,
        params,
    ).fetchall()

    if not rows:
        return {
            "days": days,
            "target_ip": target_ip,
            "total_pings": 0,
            "success_count": 0,
            "timeout_count": 0,
            "outage_groups": 0,
            "outages_per_day": 0.0,
            "total_outage_seconds": 0.0,
            "uptime_percent": 100.0,
        }

    # Group by target for per-target stats
    by_target = {}
    for r in rows:
        ip = r["target_ip"]
        if ip not in by_target:
            by_target[ip] = []
        by_target[ip].append(dict(r))

    # Compute outage clusters (consecutive timeouts)
    def analyze_outages(entries: list) -> dict:
        total = len(entries)
        success = sum(1 for e in entries if e["status"] == "success")
        timeout = sum(1 for e in entries if e["status"] == "timeout")
        groups = 0
        in_outage = False
        for e in entries:
            if e["status"] == "timeout":
                if not in_outage:
                    groups += 1
                    in_outage = True
            else:
                in_outage = False

        # Estimate interval from first two timestamps
        interval_sec = 1.0
        if len(entries) >= 2:
            t0 = datetime.fromisoformat(entries[0]["timestamp"])
            t1 = datetime.fromisoformat(entries[1]["timestamp"])
            interval_sec = (t1 - t0).total_seconds() or 1.0

        total_outage_sec = groups * interval_sec  # Approximate
        if total > 0:
            total_sec = (datetime.fromisoformat(entries[-1]["timestamp"]) -
                         datetime.fromisoformat(entries[0]["timestamp"])).total_seconds()
            total_sec = max(total_sec, 1)
            uptime = 100.0 * (1 - (total_outage_sec / total_sec)) if total_sec else 100.0
        else:
            uptime = 100.0

        return {
            "total_pings": total,
            "success_count": success,
            "timeout_count": timeout,
            "outage_groups": groups,
            "outages_per_day": groups / max(days, 0.001),
            "total_outage_seconds": total_outage_sec,
            "uptime_percent": min(100.0, max(0.0, uptime)),
        }

    first_analysis = analyze_outages(rows)
    first_analysis["days"] = days
    first_analysis["target_ip"] = target_ip
    first_analysis["targets"] = {
        ip: analyze_outages(ents) for ip, ents in by_target.items()
    }
    return first_analysis


def get_speedtest_summary(
    conn: sqlite3.Connection,
    days: int = 7,
) -> dict:
    """Get speedtest summary for the given period."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT timestamp, download_mbps, upload_mbps, ping_ms, status
        FROM speedtest_results
        WHERE timestamp >= ? AND status = 'OK'
        ORDER BY timestamp
        """,
        [since],
    ).fetchall()

    if not rows:
        return {
            "days": days,
            "count": 0,
            "download_mbps": {"avg": 0, "min": 0, "max": 0, "median": 0},
            "upload_mbps": {"avg": 0, "min": 0, "max": 0, "median": 0},
            "ping_ms": {"avg": 0, "min": 0, "max": 0, "median": 0},
            "stability_note": "No data",
        }

    downloads = [r["download_mbps"] for r in rows]
    uploads = [r["upload_mbps"] for r in rows]
    pings = [r["ping_ms"] for r in rows]

    def stats(vals):
        if not vals:
            return {"avg": 0, "min": 0, "max": 0, "median": 0}
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        return {
            "avg": sum(vals) / n,
            "min": min(vals),
            "max": max(vals),
            "median": sorted_vals[n // 2],
        }

    # Stability: coefficient of variation
    dl_std = (sum((x - sum(downloads) / len(downloads)) ** 2 for x in downloads) / len(downloads)) ** 0.5
    dl_mean = sum(downloads) / len(downloads)
    cv = (dl_std / dl_mean * 100) if dl_mean else 0
    stability = "stable" if cv < 30 else "variable" if cv < 60 else "unstable"

    return {
        "days": days,
        "count": len(rows),
        "download_mbps": stats(downloads),
        "upload_mbps": stats(uploads),
        "ping_ms": stats(pings),
        "stability": stability,
        "stability_cv_percent": round(cv, 1),
    }


def get_latency_summary(
    conn: sqlite3.Connection,
    days: int = 7,
    target_ip: Optional[str] = None,
) -> dict:
    """Get ping latency summary for successful pings."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    target_filter = "AND target_ip = ?" if target_ip else ""
    params = [since] if not target_ip else [since, target_ip]

    rows = conn.execute(
        f"""
        SELECT target_ip, duration_ms
        FROM ping_results
        WHERE timestamp >= ? AND status = 'success' AND duration_ms IS NOT NULL
        {target_filter}
        """,
        params,
    ).fetchall()

    if not rows:
        return {"days": days, "target_ip": target_ip, "count": 0, "avg_ms": 0, "min_ms": 0, "max_ms": 0}

    durations = [r["duration_ms"] for r in rows]
    return {
        "days": days,
        "target_ip": target_ip,
        "count": len(durations),
        "avg_ms": round(sum(durations) / len(durations), 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
        "median_ms": round(sorted(durations)[len(durations) // 2], 2),
    }


def delete_old_data(
    conn: sqlite3.Connection,
    retention_days: int = 30,
) -> dict:
    """
    Delete ping and speedtest rows older than retention_days.
    Returns counts of deleted rows.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

    cur = conn.execute(
        "DELETE FROM ping_results WHERE timestamp < ?",
        (cutoff,),
    )
    ping_deleted = cur.rowcount

    cur = conn.execute(
        "DELETE FROM speedtest_results WHERE timestamp < ?",
        (cutoff,),
    )
    speedtest_deleted = cur.rowcount

    return {"ping_deleted": ping_deleted, "speedtest_deleted": speedtest_deleted}


def run_vacuum(conn: sqlite3.Connection) -> None:
    """Reclaim disk space after deletions. Can be slow on large DBs."""
    conn.execute("VACUUM")


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Get row counts for storage monitoring."""
    ping_count = conn.execute("SELECT COUNT(*) FROM ping_results").fetchone()[0]
    speedtest_count = conn.execute("SELECT COUNT(*) FROM speedtest_results").fetchone()[0]
    return {"ping_rows": ping_count, "speedtest_rows": speedtest_count}


def get_weekly_report(conn: sqlite3.Connection, days: int = 7) -> str:
    """Generate a human-readable weekly report."""
    outage = get_ping_outage_report(conn, days=days)
    speed = get_speedtest_summary(conn, days=days)
    latency = get_latency_summary(conn, days=days)

    lines = [
        f"=== Network Diagnostic Report (last {days} days) ===",
        "",
        "PING / OUTAGES",
        f"  Total pings: {outage.get('total_pings', 0)}",
        f"  Success rate: {outage.get('success_count', 0)}/{outage.get('total_pings', 1)}",
        f"  Outage events: {outage.get('outage_groups', 0)}",
        f"  Outages per day: {outage.get('outages_per_day', 0):.1f}",
        f"  Uptime: {outage.get('uptime_percent', 100):.1f}%",
        "",
        "SPEEDTEST",
        f"  Tests: {speed.get('count', 0)}",
        f"  Download: avg {speed.get('download_mbps', {}).get('avg', 0):.1f} Mbps "
        f"(min {speed.get('download_mbps', {}).get('min', 0):.1f}, max {speed.get('download_mbps', {}).get('max', 0):.1f})",
        f"  Upload: avg {speed.get('upload_mbps', {}).get('avg', 0):.1f} Mbps "
        f"(min {speed.get('upload_mbps', {}).get('min', 0):.1f}, max {speed.get('upload_mbps', {}).get('max', 0):.1f})",
        f"  Stability: {speed.get('stability', 'N/A')}",
        "",
        "LATENCY (successful pings)",
        f"  Avg: {latency.get('avg_ms', 0):.1f} ms",
        f"  Min: {latency.get('min_ms', 0):.1f} ms, Max: {latency.get('max_ms', 0):.1f} ms",
    ]
    return "\n".join(lines)
