#!/usr/bin/env python3
"""
HTTP API server for pi_monitor - serves dashboard-compatible data from SQLite.
Run on the Pi to expose stats on the local network.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_monitor.config import load_config
from pi_monitor.storage import get_connection, get_default_db_path

try:
    from flask import Flask, jsonify
    from flask_cors import CORS
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

# Max points per target for ping (downsample if more)
PING_MAX_POINTS = 5000
# Hours of ping data to include
PING_HOURS = 6
# Days of speedtest data
SPEEDTEST_DAYS = 7


def _get_db_path() -> Path:
    config = load_config()
    if config.get("db_path"):
        return Path(config["db_path"])
    if config.get("data_dir"):
        return Path(config["data_dir"]) / "pi_monitor.db"
    return get_default_db_path()


def _downsample(items: list, max_points: int) -> list:
    """Downsample by taking evenly spaced items."""
    if len(items) <= max_points:
        return items
    step = len(items) / max_points
    return [items[int(i * step)] for i in range(max_points)]


def _build_dashboard_data(db_path: Path) -> dict:
    """Build dashboard-compatible payload from SQLite."""
    if not db_path.exists():
        return {"ping": None, "speedtest": None}

    ping_cutoff = (datetime.now(timezone.utc) - timedelta(hours=PING_HOURS)).isoformat()
    speedtest_cutoff = (datetime.now(timezone.utc) - timedelta(days=SPEEDTEST_DAYS)).isoformat()

    with get_connection(db_path) as conn:
        # Ping: per target, last N hours
        ping_rows = conn.execute(
            """
            SELECT timestamp, target_ip, duration_ms, status
            FROM ping_results
            WHERE timestamp >= ?
            ORDER BY timestamp
            """,
            [ping_cutoff],
        ).fetchall()

        targets = defaultdict(list)
        for r in ping_rows:
            targets[r["target_ip"]].append({
                "timestamp": r["timestamp"],
                "duration": r["duration_ms"],
                "status": r["status"],
            })

        # Downsample per target; get computer_name from first row if available
        ping_targets = {}
        computer_name = "Pi Monitor"
        first_row = conn.execute(
            "SELECT computer_name FROM ping_results LIMIT 1"
        ).fetchone()
        if first_row and first_row["computer_name"]:
            computer_name = first_row["computer_name"]

        for ip, data in targets.items():
            sampled = _downsample(data, PING_MAX_POINTS)
            ping_targets[ip] = {
                "target_ip": ip,
                "ping_count": len(data),
                "success_count": sum(1 for d in data if d["status"] == "success"),
                "timeout_count": sum(1 for d in data if d["status"] == "timeout"),
                "ping_data": sampled,
            }

        ping_data = None
        if ping_targets:
            ping_data = {
                "run_name": "pi_monitor",
                "computer_name": computer_name,
                "start_time": min(
                    r["timestamp"]
                    for t in targets.values()
                    for r in t
                ) if targets else None,
                "time_sync_info": {"success": True},
                "targets": ping_targets,
            }

        # Speedtest: last N days
        speed_rows = conn.execute(
            """
            SELECT timestamp, download_mbps, upload_mbps, ping_ms, status, error
            FROM speedtest_results
            WHERE timestamp >= ?
            ORDER BY timestamp
            """,
            [speedtest_cutoff],
        ).fetchall()

        speedtest_data = None
        if speed_rows:
            measurements = [
                {
                    "timestamp": r["timestamp"],
                    "download_mbps": r["download_mbps"],
                    "upload_mbps": r["upload_mbps"],
                    "ping_ms": r["ping_ms"],
                    "status": r["status"],
                    "error": r["error"],
                }
                for r in speed_rows
            ]
            speedtest_data = {
                "run_name": "pi_monitor",
                "computer_name": computer_name,
                "start_time": speed_rows[0]["timestamp"] if speed_rows else None,
                "time_sync_info": {"success": True},
                "interval_minutes": 15,
                "measurements": measurements,
            }

    return {"ping": ping_data, "speedtest": speedtest_data}


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    db_path = _get_db_path()

    @app.route("/api/data")
    def get_data():
        data = _build_dashboard_data(db_path)
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return jsonify(data)

    @app.route("/api/ping")
    def get_ping():
        data = _build_dashboard_data(db_path)
        return jsonify(data.get("ping") or {})

    @app.route("/api/speedtest")
    def get_speedtest():
        data = _build_dashboard_data(db_path)
        return jsonify(data.get("speedtest") or {})

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "db_exists": db_path.exists()})

    return app


def run_server(host: str = "0.0.0.0", port: int = 5001) -> None:
    """Run the API server (for use from daemon or standalone)."""
    if not HAS_FLASK:
        print("flask and flask-cors required. Run: pip install flask flask-cors")
        sys.exit(1)
    app = create_app()
    print(f"Pi Monitor API: http://{host}:{port}")
    print(f"  /api/data, /api/ping, /api/speedtest, /api/health")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=5001)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
