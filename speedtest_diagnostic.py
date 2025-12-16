#!/usr/bin/env python3
"""
Speed Test Diagnostic Tool
Periodically runs speed tests (download & upload) and logs results with
NTP-synchronized timestamps, plus an aggregated performance chart.
"""

import sys
import os
import socket
import signal
import statistics
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time as _time

try:
    import ntplib
    HAS_NTPLIB = True
except ImportError:
    HAS_NTPLIB = False

try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend for headless use
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed. Speedtest visualization will be disabled.")

try:
    # Provided by the `speedtest-cli` package
    import speedtest
    HAS_SPEEDTEST = True
except ImportError:
    HAS_SPEEDTEST = False
    print("Warning: speedtest-cli not installed. Install with:")
    print("  python -m pip install speedtest-cli")


def to_camel_case(name):
    """Convert a run name to camelCase for use in filenames"""
    if not name:
        return ""
    import re
    # Split by spaces, underscores, hyphens, or other separators
    words = re.split(r'[\s_\-]+', name.strip())
    # First word lowercase, subsequent words capitalized
    camel_words = [words[0].lower()] + [w.capitalize() for w in words[1:] if w]
    return ''.join(camel_words)


def query_ntp_time(ntp_server: str = "pool.ntp.org"):
    """
    Query NTP server to get accurate time and calculate offset (script-level sync).
    Copied from ping_diagnostic.py to keep behavior aligned.
    """
    try:
        if HAS_NTPLIB:
            client = ntplib.NTPClient()
            response = client.request(ntp_server, version=3, timeout=5)
            ntp_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
            local_time = datetime.now(timezone.utc)
            offset_seconds = (local_time - ntp_time).total_seconds()
            return {
                "success": True,
                "ntp_time": ntp_time,
                "local_time": local_time,
                "offset_seconds": offset_seconds,
                "offset_ms": offset_seconds * 1000,
                "server": ntp_server,
            }
        else:
            ntp_servers = ["pool.ntp.org", "time.google.com", "time.cloudflare.com"]
            for server in ntp_servers:
                try:
                    client = ntplib.NTPClient()
                    response = client.request(server, version=3, timeout=3)
                    ntp_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
                    local_time = datetime.now(timezone.utc)
                    offset_seconds = (local_time - ntp_time).total_seconds()
                    return {
                        "success": True,
                        "ntp_time": ntp_time,
                        "local_time": local_time,
                        "offset_seconds": offset_seconds,
                        "offset_ms": offset_seconds * 1000,
                        "server": server,
                    }
                except Exception:
                    continue
            return {"success": False, "error": "ntplib not available and NTP query failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


class SpeedTestSession:
    """Holds all measurements and logging for a single speedtest run series."""

    def __init__(self, log_file: str, computer_name: str, time_offset=None, run_name=None, visualizations_dir=None):
        self.log_file = log_file
        self.log_path = Path(log_file)
        self.computer_name = computer_name
        self.time_offset = time_offset  # seconds, may be None
        self.run_name = run_name  # Run name for chart headers
        self.visualizations_dir = Path(visualizations_dir) if visualizations_dir else Path('logs/visualizations')

        self.measurements = []  # list of dicts

    def get_synchronized_time(self, local_time=None):
        if local_time is None:
            local_time = datetime.now()
        if self.time_offset is not None:
            return local_time - timedelta(seconds=self.time_offset)
        return local_time

    def write_header(self, time_sync_info=None):
        start_time = self.get_synchronized_time().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        time_sync_text = ""
        if time_sync_info:
            if time_sync_info.get("offset_seconds") is not None:
                offset_ms = time_sync_info.get("offset_ms", 0)
                offset_sec = time_sync_info.get("offset_seconds", 0)
                ntp_server = time_sync_info.get("server", "NTP")

                if abs(offset_ms) < 10:
                    time_sync_text = (
                        f"Time Sync: Synchronized with {ntp_server} "
                        f"(offset: {offset_ms:.2f}ms)\n"
                        "All timestamps are adjusted to NTP time for cross-computer accuracy.\n"
                    )
                else:
                    time_sync_text = (
                        f"Time Sync: Adjusted to {ntp_server} "
                        f"(offset: {offset_ms:.2f}ms / {offset_sec:.3f}s)\n"
                        "All timestamps are adjusted to NTP time for cross-computer accuracy.\n"
                    )
            else:
                time_sync_text = (
                    "Time Sync: NTP query failed - using local time\n"
                    "WARNING: Timestamps may not be synchronized across multiple computers!\n"
                )

        run_name_line = f"Run Name: {self.run_name}\n" if self.run_name else ""
        header = f"""
{'='*80}
Speed Test Diagnostic Log
{'='*80}
{run_name_line}Computer Name: {self.computer_name}
Start Time (NTP-adjusted): {start_time}
{time_sync_text}Log File: {self.log_path.absolute()}
{'='*80}

"""
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(header)

    def log_result(self, timestamp_str: str, result: dict):
        status = result.get("status", "UNKNOWN")
        down = result.get("download_mbps")
        up = result.get("upload_mbps")
        ping_ms = result.get("ping_ms")
        error = result.get("error")

        status_icon = "✓" if status == "OK" else "✗"

        line = (
            f"[{timestamp_str}] {status_icon} Computer: {self.computer_name} | "
            f"Download: {down:.2f} Mbps | Upload: {up:.2f} Mbps | "
            f"Ping: {ping_ms:.1f} ms | Status: {status}"
        )
        if error:
            line += f" | Error: {error}"
        line += "\n"

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)

        print(line.strip())

        # Store for later analysis / visualization
        self.measurements.append(
            {
                "timestamp": result.get("timestamp"),
                "download_mbps": down,
                "upload_mbps": up,
                "ping_ms": ping_ms,
                "status": status,
                "error": error,
            }
        )

    def write_footer(self, low_speed_threshold_mbps: float = 10.0):
        if not self.measurements:
            return

        downloads = [m["download_mbps"] for m in self.measurements if m["status"] == "OK"]
        uploads = [m["upload_mbps"] for m in self.measurements if m["status"] == "OK"]

        def safe_stats(values):
            if not values:
                return {"avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
            return {
                "avg": statistics.mean(values),
                "median": statistics.median(values),
                "min": min(values),
                "max": max(values),
            }

        dl_stats = safe_stats(downloads)
        ul_stats = safe_stats(uploads)

        low_downloads = [v for v in downloads if v < low_speed_threshold_mbps]
        low_uploads = [v for v in uploads if v < low_speed_threshold_mbps]
        total_ok = len(downloads)

        def pct(count):
            if total_ok == 0:
                return 0.0
            return (count / total_ok) * 100.0

        end_time = self.get_synchronized_time().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        footer = f"""
{'='*80}
Summary Statistics
{'='*80}
Computer Name: {self.computer_name}
End Time (NTP-adjusted): {end_time}
Total Tests (successful): {total_ok}

Download (Mbps):
  Avg:    {dl_stats['avg']:.2f}
  Median: {dl_stats['median']:.2f}
  Min:    {dl_stats['min']:.2f}
  Max:    {dl_stats['max']:.2f}

Upload (Mbps):
  Avg:    {ul_stats['avg']:.2f}
  Median: {ul_stats['median']:.2f}
  Min:    {ul_stats['min']:.2f}
  Max:    {ul_stats['max']:.2f}

Low-speed occurrences (<{low_speed_threshold_mbps:.1f} Mbps):
  Download: {len(low_downloads)} tests ({pct(len(low_downloads)):.1f}% of successful tests)
  Upload:   {len(low_uploads)} tests ({pct(len(low_uploads)):.1f}% of successful tests)
{'='*80}
"""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(footer)

        insights = self.generate_insights(dl_stats, ul_stats, low_speed_threshold_mbps)
        if insights:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write("\nInsights & Guidance\n" + "=" * 80 + "\n")
                for line in insights:
                    f.write(f"- {line}\n")

    def generate_insights(self, dl_stats, ul_stats, threshold):
        insights = []

        if dl_stats["avg"] < threshold or ul_stats["avg"] < threshold:
            insights.append(
                f"Average throughput is below {threshold:.1f} Mbps, indicating under-performing service."
            )
        else:
            insights.append("Average throughput is above the low-speed threshold.")

        if dl_stats["min"] < threshold / 2 or ul_stats["min"] < threshold / 2:
            insights.append(
                "There are very low-speed tests (below half the threshold), suggesting intermittent severe slowdowns."
            )

        if dl_stats["max"] > 2 * threshold or ul_stats["max"] > 2 * threshold:
            insights.append(
                "Throughput varies significantly between tests; some runs are much faster than others."
            )

        return insights

    def generate_visualization(self):
        if not HAS_MATPLOTLIB or not self.measurements or len(self.measurements) < 2:
            return None

        timestamps = [m["timestamp"] for m in self.measurements]
        downloads = [m["download_mbps"] for m in self.measurements]
        uploads = [m["upload_mbps"] for m in self.measurements]
        statuses = [m["status"] for m in self.measurements]

        fig, ax = plt.subplots(figsize=(12, 6))

        ax.plot(timestamps, downloads, "-o", color="#1f77b4", label="Download (Mbps)")
        ax.plot(timestamps, uploads, "-o", color="#ff7f0e", label="Upload (Mbps)")

        # Mark failed tests if any
        for ts, dl, up, st in zip(timestamps, downloads, uploads, statuses):
            if st != "OK":
                ax.axvline(ts, color="red", alpha=0.3, linestyle="--")

        # Build title with run name if available
        title_parts = ["Speed Test Results Over Time"]
        if self.run_name:
            title_parts.insert(0, f"Run: {self.run_name}")
        title_parts.append(f"Computer: {self.computer_name}")
        
        ax.set_xlabel("Time")
        ax.set_ylabel("Speed (Mbps)")
        ax.set_title("\n".join(title_parts))
        ax.grid(True, alpha=0.3)
        ax.legend()

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        plt.tight_layout()

        viz_file = self.visualizations_dir / f"{self.log_path.stem}_speedtest_visualization.png"
        fig.savefig(viz_file, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return str(viz_file)


class SpeedTestDiagnostic:
    def __init__(self, log_prefix=None, interval_minutes=15.0, run_name=None):
        self.running = True
        self.interval_minutes = interval_minutes
        self.run_name = run_name
        self.computer_name = self.get_computer_name()
        
        # Create directories if they don't exist
        self.logs_dir = Path('logs/speedtest')
        self.visualizations_dir = Path('logs/visualizations')
        self.data_dir = Path('data')
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.visualizations_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Store JSON file path for cleanup
        self.json_file_path = None
        
        # Build log prefix: use provided prefix, or generate from run_name + timestamp, or just timestamp
        if log_prefix:
            self.log_prefix = log_prefix
        elif run_name:
            camel_run = to_camel_case(run_name)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.log_prefix = f"{camel_run}_speedtest_{timestamp}"
        else:
            self.log_prefix = f"speedtest_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.time_sync_info = self.query_ntp_offset()
        time_offset = (
            self.time_sync_info.get("offset_seconds")
            if self.time_sync_info.get("success")
            else None
        )

        log_file = self.logs_dir / f"{self.log_prefix}.txt"
        self.session = SpeedTestSession(str(log_file), self.computer_name, time_offset=time_offset, run_name=run_name, visualizations_dir=self.visualizations_dir)

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def query_ntp_offset(self):
        print("\n" + "=" * 80)
        print("Time Synchronization (Script-Level) - Speed Test")
        print("=" * 80)

        ntp_result = query_ntp_time()

        if ntp_result.get("success"):
            offset_ms = ntp_result.get("offset_ms", 0)
            offset_sec = ntp_result.get("offset_seconds", 0)
            ntp_server = ntp_result.get("server", "pool.ntp.org")

            print(f"✓ NTP Server: {ntp_server}")
            print(f"✓ Time Offset: {offset_ms:.2f}ms ({offset_sec:.3f}s)")
            print("✓ All timestamps will be adjusted to NTP time")
            print("  This ensures accurate correlation across multiple computers")

            if abs(offset_ms) > 1000:
                print(f"\n⚠️  Note: Large time offset detected ({offset_ms:.2f}ms)")
                print("   Your system clock may be significantly off from NTP time")

            return {
                "success": True,
                "offset_seconds": offset_sec,
                "offset_ms": offset_ms,
                "server": ntp_server,
            }

        error_msg = ntp_result.get("error", "Unknown error")
        print(f"✗ Could not query NTP server: {error_msg}")

        if not HAS_NTPLIB:
            print("\n⚠️  WARNING: ntplib not installed!")
            print("   Install it for time synchronization:")
            print("   python -m pip install ntplib")
            print("\n   Without ntplib, timestamps will use local system time")
            print("   and may not be synchronized across multiple computers.")
        else:
            print("\n⚠️  WARNING: NTP query failed!")
            print("   Timestamps will use local system time")
            print("   and may not be synchronized across multiple computers.")

        return {
            "success": False,
            "error": error_msg,
            "offset_seconds": None,
            "offset_ms": None,
        }

    def get_computer_name(self):
        computer_name = os.environ.get("COMPUTERNAME") or os.environ.get("COMPUTER_NAME")
        if computer_name:
            return computer_name
        try:
            return socket.gethostname()
        except Exception:
            return "UNKNOWN"

    def signal_handler(self, signum, frame):
        print("\n\nStopping speed test diagnostic...")
        self.running = False
    
    def export_json_data(self):
        """Export current speedtest data to JSON file for dashboard"""
        try:
            # Serialize measurements for JSON
            measurements_serialized = []
            for m in self.session.measurements:
                measurements_serialized.append({
                    'timestamp': m['timestamp'].isoformat() if isinstance(m['timestamp'], datetime) else m['timestamp'],
                    'download_mbps': m['download_mbps'],
                    'upload_mbps': m['upload_mbps'],
                    'ping_ms': m['ping_ms'],
                    'status': m['status'],
                    'error': m.get('error')
                })
            
            json_data = {
                'run_name': self.run_name,
                'computer_name': self.computer_name,
                'start_time': self.session.get_synchronized_time().isoformat() if self.session.measurements else None,
                'time_sync_info': self.time_sync_info,
                'interval_minutes': self.interval_minutes,
                'measurements': measurements_serialized
            }
            
            # Write JSON file to data directory for dashboard
            json_file = f"{self.log_prefix}.json"
            json_path = self.data_dir / json_file
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            # Store path for cleanup
            self.json_file_path = json_path
            
            return json_path
        except Exception as e:
            print(f"Error exporting JSON data: {e}")
            return None

    def run_speedtest_once(self):
        if not HAS_SPEEDTEST:
            return {
                "timestamp": self.session.get_synchronized_time(),
                "download_mbps": 0.0,
                "upload_mbps": 0.0,
                "ping_ms": 0.0,
                "status": "ERROR",
                "error": "speedtest-cli module not available",
            }

        try:
            # Use secure=True to enable HTTPS and reduce 403 Forbidden errors
            st = speedtest.Speedtest(secure=True)
            st.get_best_server()
            download_bps = st.download()
            upload_bps = st.upload()
            ping_ms = st.results.ping

            download_mbps = download_bps / 1_000_000.0
            upload_mbps = upload_bps / 1_000_000.0

            ts = self.session.get_synchronized_time()

            return {
                "timestamp": ts,
                "download_mbps": download_mbps,
                "upload_mbps": upload_mbps,
                "ping_ms": float(ping_ms),
                "status": "OK",
                "error": None,
            }
        except Exception as e:
            ts = self.session.get_synchronized_time()
            error_msg = str(e)
            
            # Provide helpful message for 403 errors (rate limiting)
            if "403" in error_msg or "Forbidden" in error_msg:
                error_msg = (
                    f"HTTP 403 Forbidden - Speedtest.net rate limit reached. "
                    f"Current interval: {self.interval_minutes} minutes. "
                    f"Consider increasing interval with --interval <minutes> or wait longer between tests."
                )
            
            return {
                "timestamp": ts,
                "download_mbps": 0.0,
                "upload_mbps": 0.0,
                "ping_ms": 0.0,
                "status": "ERROR",
                "error": error_msg,
            }

    def run(self):
        self.session.write_header(self.time_sync_info)

        print("=" * 80)
        print("Speed Test Diagnostic Tool")
        print("=" * 80)
        print(f"Computer Name: {self.computer_name}")
        print(f"Log File: {self.session.log_path.name}")
        print(f"Test interval: {self.interval_minutes} minute(s)")
        print("\nPress Ctrl+C to stop\n")

        try:
            while self.running:
                sync_time = self.session.get_synchronized_time()
                timestamp_str = sync_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                result = self.run_speedtest_once()
                # Ensure result timestamp is synchronized object
                result["timestamp"] = sync_time
                self.session.log_result(timestamp_str, result)
                
                # Export JSON data for dashboard
                self.export_json_data()

                if not self.running:
                    break

                sleep_seconds = max(0.0, self.interval_minutes * 60.0)
                for _ in range(int(sleep_seconds)):
                    if not self.running:
                        break
                    _time.sleep(1)
                if self.running and sleep_seconds - int(sleep_seconds) > 0:
                    _time.sleep(sleep_seconds - int(sleep_seconds))

        except KeyboardInterrupt:
            pass
        finally:
            print("\n" + "=" * 80)
            print("Generating speed test summary...")
            self.session.write_footer()
            print(f"Log saved: {self.session.log_path.absolute()}")

            if HAS_MATPLOTLIB:
                print("\nGenerating speed test visualization...")
                viz_file = self.session.generate_visualization()
                if viz_file:
                    print(f"Visualization saved: {Path(viz_file).absolute()}")
            
            # Clean up JSON file after generating PNG
            self.cleanup_json_file()

            print(
                "\nYou can now attach this speed test log and visualization alongside your "
                "ping diagnostics when contacting Eero support."
            )
    
    def cleanup_json_file(self):
        """Remove JSON file used for dashboard after PNG is generated"""
        if self.json_file_path and self.json_file_path.exists():
            try:
                self.json_file_path.unlink()
                print(f"Cleaned up JSON file: {self.json_file_path.name}")
            except Exception as e:
                print(f"Error cleaning up JSON file: {e}")


def parse_args(argv):
    log_prefix = None
    interval_minutes = 15.0  # Increased from 5.0 to reduce rate limiting issues

    args = [a for a in argv[1:] if not a.startswith("-")]

    if len(args) >= 1:
        log_prefix = args[0]

    if len(args) >= 2:
        try:
            interval_minutes = float(args[1])
        except ValueError:
            print(f"Warning: Invalid interval '{args[1]}', using default 15 minutes")

    if "--interval" in argv:
        try:
            idx = argv.index("--interval")
            if idx + 1 < len(argv):
                interval_minutes = float(argv[idx + 1])
        except (ValueError, IndexError):
            print("Warning: Invalid value for --interval, using default 15 minutes")
    elif "-i" in argv:
        try:
            idx = argv.index("-i")
            if idx + 1 < len(argv):
                interval_minutes = float(argv[idx + 1])
        except (ValueError, IndexError):
            print("Warning: Invalid value for -i, using default 15 minutes")

    return log_prefix, interval_minutes


def main():
    print("=" * 80)
    print("Speed Test Diagnostic Tool")
    print("=" * 80)
    print()
    
    # Prompt for run name
    run_name = input("Enter a name for this test run (e.g., 'wifi new position', 'node swap', 'after router restart'): ").strip()
    if not run_name:
        run_name = None
        print("No run name provided. Using default naming.\n")
    else:
        print(f"Run name: '{run_name}' (will be used as prefix for log files and charts)\n")

    log_prefix, interval_minutes = parse_args(sys.argv)

    print(f"Test interval: {interval_minutes} minute(s) between speed tests")
    print("  (Use --interval <minutes> or -i <minutes> to change)")
    print("  Note: Default interval is 15 minutes to reduce rate limiting issues.\n")

    diagnostic = SpeedTestDiagnostic(log_prefix=log_prefix, interval_minutes=interval_minutes, run_name=run_name)
    diagnostic.run()


if __name__ == "__main__":
    main()



