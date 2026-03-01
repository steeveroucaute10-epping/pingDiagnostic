#!/usr/bin/env python3
"""
Long-term storage for ping and speedtest diagnostics.
Uses SQLite for persistence and aggregation queries.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional, Tuple


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

        CREATE TABLE IF NOT EXISTS network_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            start_timestamp TEXT NOT NULL,
            end_timestamp TEXT NOT NULL,
            duration_seconds REAL NOT NULL,
            affected_targets TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_network_events_start ON network_events(start_timestamp);
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


def has_overlapping_event(
    conn: sqlite3.Connection,
    start_ts: datetime,
    end_ts: datetime,
) -> bool:
    """Check if an event overlapping [start_ts, end_ts] already exists."""
    start_str = start_ts.isoformat() if isinstance(start_ts, datetime) else start_ts
    end_str = end_ts.isoformat() if isinstance(end_ts, datetime) else end_ts
    row = conn.execute(
        """
        SELECT 1 FROM network_events
        WHERE start_timestamp <= ? AND end_timestamp >= ?
        LIMIT 1
        """,
        (end_str, start_str),
    ).fetchone()
    return row is not None


def insert_network_event(
    conn: sqlite3.Connection,
    event_type: str,
    start_timestamp: "datetime",
    end_timestamp: "datetime",
    duration_seconds: float,
    affected_targets: Optional[str] = None,
) -> None:
    """Insert a network outage event (skips if overlapping event exists)."""
    start_str = start_timestamp.isoformat() if isinstance(start_timestamp, datetime) else start_timestamp
    end_str = end_timestamp.isoformat() if isinstance(end_timestamp, datetime) else end_timestamp
    if has_overlapping_event(conn, start_timestamp, end_timestamp):
        return
    conn.execute(
        """
        INSERT INTO network_events (event_type, start_timestamp, end_timestamp, duration_seconds, affected_targets)
        VALUES (?, ?, ?, ?, ?)
        """,
        (event_type, start_str, end_str, duration_seconds, affected_targets),
    )


def detect_affected_targets(
    conn: sqlite3.Connection,
    start_ts: datetime,
    end_ts: datetime,
    targets: list,
    trigger_target: str,
) -> str:
    """
    Determine affected_targets for an outage: 'both', 'gateway', or 'internet'.
    Checks if the other target(s) also had timeouts during the outage window.
    """
    start_str = start_ts.isoformat()
    end_str = end_ts.isoformat()
    other_targets = [t for t in targets if t != trigger_target]
    if not other_targets:
        return "gateway" if trigger_target == targets[0] else "internet"

    # For each other target, count timeouts vs total in window
    both_failed = True
    for other in other_targets:
        rows = conn.execute(
            """
            SELECT status FROM ping_results
            WHERE target_ip = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
            """,
            (other, start_str, end_str),
        ).fetchall()
        if not rows:
            both_failed = False
            break
        timeout_like = sum(1 for r in rows if r["status"] in ("timeout", "error", "unreachable"))
        if timeout_like / len(rows) < 0.5:
            both_failed = False
            break

    if both_failed:
        return "both"
    return "gateway" if trigger_target == targets[0] else "internet"


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


def resolve_time_range(
    days: Optional[int] = None,
    hours: Optional[float] = None,
    date: Optional[str] = None,
) -> Tuple[datetime, datetime]:
    """Return (since, until) for the given filter. Precedence: date > hours > days (default 7)."""
    now = datetime.now(timezone.utc)
    if date:
        if date.lower() == "yesterday":
            since = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            until = since + timedelta(days=1)
        else:
            since = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
            until = since + timedelta(days=1)
    elif hours is not None:
        since = now - timedelta(hours=hours)
        until = now
    else:
        since = now - timedelta(days=days or 7)
        until = now
    return since, until


def get_outages(
    conn: sqlite3.Connection,
    since_ts: datetime,
    until_ts: datetime,
) -> list:
    """Get network outage events in the given time range."""
    since_str = since_ts.isoformat()
    until_str = until_ts.isoformat()
    rows = conn.execute(
        """
        SELECT start_timestamp, end_timestamp, duration_seconds, event_type, affected_targets
        FROM network_events
        WHERE start_timestamp >= ? AND start_timestamp < ?
        ORDER BY start_timestamp
        """,
        (since_str, until_str),
    ).fetchall()
    return [
        {
            "start": r["start_timestamp"],
            "end": r["end_timestamp"],
            "duration_seconds": r["duration_seconds"],
            "event_type": r["event_type"],
            "affected_targets": r["affected_targets"],
        }
        for r in rows
    ]


def get_outage_intervals(
    conn: sqlite3.Connection,
    since_ts: datetime,
    until_ts: datetime,
) -> dict:
    """Get intervals between consecutive outages and median interval."""
    outages = get_outages(conn, since_ts, until_ts)
    if len(outages) < 2:
        return {"intervals_seconds": [], "median_seconds": None, "count": len(outages)}

    starts = [o["start"] for o in outages]
    intervals = []
    for i in range(1, len(starts)):
        t0 = datetime.fromisoformat(starts[i - 1])
        t1 = datetime.fromisoformat(starts[i])
        intervals.append((t1 - t0).total_seconds())

    sorted_intervals = sorted(intervals)
    n = len(sorted_intervals)
    median = sorted_intervals[n // 2] if n % 2 else (sorted_intervals[n // 2 - 1] + sorted_intervals[n // 2]) / 2

    return {
        "intervals_seconds": intervals,
        "median_seconds": median,
        "count": len(outages),
    }


def get_outage_duration_stats(
    conn: sqlite3.Connection,
    since_ts: datetime,
    until_ts: datetime,
) -> dict:
    """Get duration statistics for outages (min, max, avg, median, p96)."""
    outages = get_outages(conn, since_ts, until_ts)
    if not outages:
        return {
            "median_seconds": None,
            "min_seconds": None,
            "max_seconds": None,
            "avg_seconds": None,
            "p96_seconds": None,
            "count": 0,
        }

    durations = [o["duration_seconds"] for o in outages]
    n = len(durations)
    sorted_d = sorted(durations)
    median = sorted_d[n // 2] if n % 2 else (sorted_d[n // 2 - 1] + sorted_d[n // 2]) / 2
    p96_idx = int(n * 0.96) - 1 if n > 0 else 0
    p96_idx = max(0, min(p96_idx, n - 1))
    p96 = sorted_d[p96_idx]

    return {
        "median_seconds": round(median, 2),
        "min_seconds": round(min(durations), 2),
        "max_seconds": round(max(durations), 2),
        "avg_seconds": round(sum(durations) / n, 2),
        "p96_seconds": round(p96, 2),
        "count": n,
    }


def delete_old_data(
    conn: sqlite3.Connection,
    retention_days: int = 30,
) -> dict:
    """
    Delete ping, speedtest, and network_events rows older than retention_days.
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

    cur = conn.execute(
        "DELETE FROM network_events WHERE start_timestamp < ?",
        (cutoff,),
    )
    events_deleted = cur.rowcount

    return {
        "ping_deleted": ping_deleted,
        "speedtest_deleted": speedtest_deleted,
        "events_deleted": events_deleted,
    }


def run_vacuum(conn: sqlite3.Connection) -> None:
    """Reclaim disk space after deletions. Can be slow on large DBs."""
    conn.execute("VACUUM")


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Get row counts for storage monitoring."""
    ping_count = conn.execute("SELECT COUNT(*) FROM ping_results").fetchone()[0]
    speedtest_count = conn.execute("SELECT COUNT(*) FROM speedtest_results").fetchone()[0]
    events_count = conn.execute("SELECT COUNT(*) FROM network_events").fetchone()[0]
    return {"ping_rows": ping_count, "speedtest_rows": speedtest_count, "events_rows": events_count}


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
