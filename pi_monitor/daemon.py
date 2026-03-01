#!/usr/bin/env python3
"""
Pi Monitor Daemon - runs ping and speedtest diagnostics permanently.
Non-interactive, persists to SQLite for long-term analysis.
"""

import subprocess
import re
import sys
import signal
import os
import socket
import time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_monitor.config import load_config
from pi_monitor.storage import (
    get_connection,
    get_default_db_path,
    init_schema,
    insert_ping,
    insert_speedtest,
    insert_network_event,
    detect_affected_targets,
    delete_old_data,
    run_vacuum,
    get_db_stats,
)

try:
    import ntplib
    HAS_NTPLIB = True
except ImportError:
    HAS_NTPLIB = False

try:
    import speedtest
    HAS_SPEEDTEST = True
except ImportError:
    HAS_SPEEDTEST = False


def get_computer_name() -> str:
    name = os.environ.get("COMPUTERNAME") or os.environ.get("COMPUTER_NAME")
    if name:
        return name
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def get_time_offset() -> float:
    """Get NTP offset in seconds for timestamp correction."""
    if not HAS_NTPLIB:
        return 0.0
    try:
        client = ntplib.NTPClient()
        response = client.request("pool.ntp.org", version=3, timeout=5)
        ntp_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
        local_time = datetime.now(timezone.utc)
        return (local_time - ntp_time).total_seconds()
    except Exception:
        return 0.0


def run_ping(target_ip: str, platform: str, timeout_sec: float = 2.0) -> dict:
    """Run a single ping and return status, duration_ms. Uses strict timeout to avoid hanging when interface fails."""
    try:
        if platform == "windows":
            cmd = f"ping -n 1 -w 1000 {target_ip}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_sec)
        else:
            cmd = ["ping", "-c", "1", "-W", "1", target_ip]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)

        output = result.stdout + result.stderr
        output_lower = output.lower()

        if result.returncode == 0 and ("reply from" in output_lower or "bytes from" in output_lower):
            time_match = re.search(r"time[=:](\d+\.?\d*)\s*ms", output, re.IGNORECASE)
            if not time_match:
                time_match = re.search(r"time[<=:](\d+)", output, re.IGNORECASE)
            duration = float(time_match.group(1)) if time_match else None
            return {"status": "success", "duration_ms": duration}
        elif result.returncode == 1 or "timed out" in output_lower or "timeout" in output_lower:
            return {"status": "timeout", "duration_ms": None}
        else:
            return {"status": "unreachable", "duration_ms": None}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "duration_ms": None}
    except Exception:
        return {"status": "error", "duration_ms": None}


def run_speedtest_once() -> dict:
    """Run a single speedtest."""
    if not HAS_SPEEDTEST:
        return {
            "download_mbps": 0,
            "upload_mbps": 0,
            "ping_ms": 0,
            "status": "ERROR",
            "error": "speedtest-cli not installed",
        }
    try:
        st = speedtest.Speedtest(secure=True)
        st.get_best_server()
        download_bps = st.download()
        upload_bps = st.upload()
        ping_ms = st.results.ping
        return {
            "download_mbps": download_bps / 1_000_000,
            "upload_mbps": upload_bps / 1_000_000,
            "ping_ms": float(ping_ms),
            "status": "OK",
            "error": None,
        }
    except Exception as e:
        return {
            "download_mbps": 0,
            "upload_mbps": 0,
            "ping_ms": 0,
            "status": "ERROR",
            "error": str(e),
        }


def ping_worker(config: dict, db_path: Path, stop_event: threading.Event) -> None:
    """Background thread: continuous ping to all targets."""
    targets = config.get("ping_targets", ["192.168.1.1", "8.8.8.8"])
    interval = config.get("ping_interval_seconds", 1)
    ping_timeout = config.get("ping_timeout_seconds", 2.0)
    min_consecutive = config.get("outage_min_consecutive_timeouts", 10)
    computer = config.get("computer_name") or get_computer_name()
    time_offset = get_time_offset()
    platform = "windows" if os.name == "nt" else "linux"

    # Outage detection state: per-target consecutive timeout count and outage start
    outage_state = {t: {"consecutive": 0, "start_ts": None} for t in targets}

    while not stop_event.is_set():
        sync_time = datetime.now(timezone.utc) - timedelta(seconds=time_offset)
        cycle_results = {t: None for t in targets}
        for target in targets:
            if stop_event.is_set():
                break
            result = run_ping(target, platform, timeout_sec=ping_timeout)
            cycle_results[target] = result
            try:
                with get_connection(db_path) as conn:
                    init_schema(conn)
                    insert_ping(
                        conn,
                        sync_time,
                        target,
                        result.get("duration_ms"),
                        result["status"],
                        computer,
                    )
            except Exception as e:
                print(f"[ping] DB error: {e}", file=sys.stderr)

            # Outage detection: track consecutive timeouts
            if result["status"] in ("timeout", "error", "unreachable"):
                outage_state[target]["consecutive"] += 1
                if outage_state[target]["start_ts"] is None and outage_state[target]["consecutive"] >= min_consecutive:
                    # First cycle where we hit 10+ consecutive - start_ts was set at cycle 10
                    # We need to backdate to when we first hit 10
                    outage_state[target]["start_ts"] = sync_time - timedelta(seconds=(outage_state[target]["consecutive"] - 1) * interval)
            else:
                if outage_state[target]["consecutive"] >= min_consecutive and outage_state[target]["start_ts"] is not None:
                    # Outage ended - record event
                    end_ts = sync_time
                    start_ts = outage_state[target]["start_ts"]
                    duration = (end_ts - start_ts).total_seconds()
                    try:
                        with get_connection(db_path) as conn:
                            affected = detect_affected_targets(
                                conn, start_ts, end_ts, targets, target
                            )
                            event_type = {
                                "both": "MESH_FAILURE",
                                "gateway": "LOCAL_OUTAGE",
                                "internet": "INTERNET_OUTAGE",
                            }[affected]
                            insert_network_event(
                                conn,
                                event_type,
                                start_ts,
                                end_ts,
                                duration,
                                affected,
                            )
                    except Exception as ex:
                        print(f"[outage] Error recording event: {ex}", file=sys.stderr)
                outage_state[target]["consecutive"] = 0
                outage_state[target]["start_ts"] = None

        stop_event.wait(interval)


def speedtest_worker(config: dict, db_path: Path, stop_event: threading.Event) -> None:
    """Background thread: periodic speedtests."""
    interval_min = config.get("speedtest_interval_minutes", 15)
    computer = config.get("computer_name") or get_computer_name()
    time_offset = get_time_offset()

    while not stop_event.is_set():
        sync_time = datetime.now(timezone.utc) - timedelta(seconds=time_offset)
        result = run_speedtest_once()
        try:
            with get_connection(db_path) as conn:
                init_schema(conn)
                insert_speedtest(
                    conn,
                    sync_time,
                    result["download_mbps"],
                    result["upload_mbps"],
                    result["ping_ms"],
                    result["status"],
                    result.get("error"),
                    computer,
                )
        except Exception as e:
            print(f"[speedtest] DB error: {e}", file=sys.stderr)

        # Sleep in 1-second chunks to allow quick shutdown
        for _ in range(int(interval_min * 60)):
            if stop_event.is_set():
                break
            stop_event.wait(1)


def cleanup_worker(db_path: Path, config: dict, stop_event: threading.Event) -> None:
    """Background thread: periodic retention cleanup (every 24h)."""
    retention = config.get("retention_days", 30)
    vacuum = config.get("vacuum_after_cleanup", True)
    interval_sec = 24 * 3600  # 24 hours

    while not stop_event.is_set():
        stop_event.wait(interval_sec)
        if stop_event.is_set():
            break
        try:
            with get_connection(db_path) as conn:
                deleted = delete_old_data(conn, retention_days=retention)
                total = deleted["ping_deleted"] + deleted["speedtest_deleted"] + deleted.get("events_deleted", 0)
                if total > 0:
                    print(f"[cleanup] Deleted {deleted['ping_deleted']} ping, "
                          f"{deleted['speedtest_deleted']} speedtest, "
                          f"{deleted.get('events_deleted', 0)} events (>{retention}d old)")
                    if vacuum:
                        run_vacuum(conn)
                        print("[cleanup] VACUUM completed")
        except Exception as e:
            print(f"[cleanup] Error: {e}", file=sys.stderr)


def run_startup_cleanup(db_path: Path, config: dict) -> None:
    """Run retention cleanup on daemon startup."""
    retention = config.get("retention_days", 30)
    vacuum = config.get("vacuum_after_cleanup", True)
    try:
        with get_connection(db_path) as conn:
            deleted = delete_old_data(conn, retention_days=retention)
            total = deleted["ping_deleted"] + deleted["speedtest_deleted"] + deleted.get("events_deleted", 0)
            if total > 0:
                print(f"[startup] Cleanup: deleted {deleted['ping_deleted']} ping, "
                      f"{deleted['speedtest_deleted']} speedtest, "
                      f"{deleted.get('events_deleted', 0)} events (>{retention}d old)")
                if vacuum:
                    run_vacuum(conn)
                    print("[startup] VACUUM completed")
            stats = get_db_stats(conn)
            print(f"[startup] DB: {stats['ping_rows']} ping rows, {stats['speedtest_rows']} speedtest, {stats.get('events_rows', 0)} events")
    except Exception as e:
        print(f"[startup] Cleanup error: {e}", file=sys.stderr)


def main() -> None:
    config = load_config()
    db_path = None
    if config.get("db_path"):
        db_path = Path(config["db_path"])
    elif config.get("data_dir"):
        db_path = Path(config["data_dir"]) / "pi_monitor.db"
    else:
        db_path = get_default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize DB and run startup cleanup
    with get_connection(db_path) as conn:
        init_schema(conn)
    run_startup_cleanup(db_path, config)

    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda s, f: stop_event.set())
    signal.signal(signal.SIGTERM, lambda s, f: stop_event.set())

    print("Pi Monitor daemon starting...")
    print(f"  Ping targets: {config.get('ping_targets')}")
    print(f"  Ping interval: {config.get('ping_interval_seconds')}s")
    print(f"  Speedtest interval: {config.get('speedtest_interval_minutes')} min")
    print(f"  Retention: {config.get('retention_days', 30)} days")
    print(f"  Database: {db_path}")
    if config.get("api_enabled", True):
        print(f"  API: run 'python -m pi_monitor.api' separately for dashboard access")
    print("Press Ctrl+C to stop.\n")

    t_cleanup = threading.Thread(
        target=cleanup_worker,
        args=(db_path, config, stop_event),
    )
    t_cleanup.daemon = True
    t_cleanup.start()

    t_ping = threading.Thread(target=ping_worker, args=(config, db_path, stop_event))
    t_speed = threading.Thread(target=speedtest_worker, args=(config, db_path, stop_event))
    t_ping.daemon = True
    t_speed.daemon = True
    t_ping.start()
    t_speed.start()

    try:
        t_ping.join()
        t_speed.join()
        t_cleanup.join()
    except KeyboardInterrupt:
        pass
    print("\nPi Monitor daemon stopped.")


if __name__ == "__main__":
    main()
