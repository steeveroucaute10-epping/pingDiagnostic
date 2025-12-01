# Ping Diagnostic Tool

A Python tool for continuous network ping diagnostics with detailed timestamped logging. Perfect for diagnosing WiFi mesh network issues and providing logs to support teams.

## Quick Install Dependencies

To install all optional dependencies at once:
```bash
python -m pip install -r requirements.txt
```

Or install individually:
```bash
python -m pip install matplotlib  # For visualizations
python -m pip install ntplib      # For accurate time sync checking
python -m pip install speedtest-cli  # For periodic speed tests
```

## Features

- ✅ **Dual Target Monitoring**: Automatically pings both your Eero gateway and Google DNS (8.8.8.8)
- ✅ **Separate Log Files**: Creates individual log files for each target for easy analysis
- ✅ **Computer Name Tracking**: Includes computer name in logs (useful when running on multiple devices)
- ✅ **Continuous ping monitoring** with precise timestamps (millisecond precision)
- ✅ **Logs IP address, TTL, timeout status, and response time**
- ✅ **Saves logs to text files** for easy email attachment
- ✅ **Visualization Charts**: Automatically generates 4-panel visualization charts showing:
  - Timeout events over time
  - Average ping duration over time (with rolling average)
  - Distribution of time between timeout events
  - Percentage breakdown of ping status (success/timeout/other)
- ✅ **Graceful shutdown** with Ctrl+C
- ✅ **Summary statistics** at the end of each session
- ✅ **Auto-detects default gateway** (Eero router)
- ✅ **Script-Level Time Synchronization**: Automatically adjusts all timestamps to NTP time (no root privileges required)
- ✅ **Network Stability Analytics**: Median uptime between outages, disruption frequency, and timeout duration histograms
- ✅ **Easy to use command-line interface**

## Requirements

- Python 3.6 or higher
- **Cross-platform support**: Windows, macOS, and Linux
- **matplotlib** (optional, for visualizations): `python -m pip install matplotlib`
- **ntplib** (optional, for accurate time offset checking): `python -m pip install ntplib`

## Usage

### Basic Usage (Recommended)

```bash
python ping_diagnostic.py
```

The script will:
1. **Auto-detect your default gateway** (Eero router IP)
2. **Automatically ping both** the gateway and Google DNS (8.8.8.8)
3. **Create separate log files** for each target
4. **Include your computer name** in all logs

Just press Enter to start with the defaults, or type custom IPs if needed.

### Advanced Usage

```bash
# Specify custom targets (comma-separated)
python ping_diagnostic.py 192.168.1.1,8.8.8.8

# Specify targets and custom log file prefix
python ping_diagnostic.py 192.168.1.1,8.8.8.8 my_network_test

# Specify targets, log prefix, and ping interval (in seconds)
python ping_diagnostic.py 192.168.1.1,8.8.8.8 my_network_test 2

# Configure ping frequency (interval between ping cycles)
python ping_diagnostic.py --interval 0.5  # Ping every 0.5 seconds
python ping_diagnostic.py -i 2            # Ping every 2 seconds

# With debug mode
python ping_diagnostic.py --debug
```

### Speed Test Diagnostic (Separate Script)

You can run a periodic internet speed test (download & upload) using a separate script
so it does not interfere with the ping diagnostic:

```bash
python speedtest_diagnostic.py
```

This will:

1. Perform script-level NTP time synchronization (same approach as the ping tool).
2. Run a speed test approximately every 5 minutes by default.
3. Log each test to `speedtest_log_YYYYMMDD_HHMMSS.txt`.
4. Include computer name, download/upload Mbps, ping latency, and status for each run.

To change the interval between tests:

```bash
# Every 10 minutes
python speedtest_diagnostic.py --interval 10

# Every 2 minutes
python speedtest_diagnostic.py -i 2

# Custom log prefix and interval (minutes)
python speedtest_diagnostic.py my_speed_session 3
```

When you stop the script with `Ctrl+C`, it will:

- Append summary statistics (average/median/min/max download and upload).
- Note how often speeds fall below a low-speed threshold.
- Generate a line chart PNG showing download and upload over time, aligned to NTP timestamps.

### Examples

```bash
# Use defaults (auto-detected gateway + 8.8.8.8)
python ping_diagnostic.py

# Ping specific Eero gateway and Google DNS
python ping_diagnostic.py 192.168.4.1,8.8.8.8

# Custom targets with 2 second intervals
python ping_diagnostic.py 192.168.1.1,8.8.8.8,1.1.1.1 network_test 2
```

## Log Files

The script creates **separate log files** for each target:

- `ping_log_YYYYMMDD_HHMMSS_192_168_1_1.txt` (for gateway)
- `ping_log_YYYYMMDD_HHMMSS_8_8_8_8.txt` (for Google DNS)

Each log file contains:
- Computer name (so you can identify which device generated the log)
- Target IP address
- All ping results with timestamps
- Summary statistics

## Log Format

Each log entry includes:
- **Timestamp**: Precise timestamp with millisecond precision
- **Computer Name**: The computer that generated this log entry
- **Status Icon**: ✓ for success, ✗ for failure
- **IP Address**: The target being pinged
- **Status**: SUCCESS, TIMEOUT, UNREACHABLE, or ERROR
- **TTL**: Time To Live value from the ping response
- **Time**: Response time in milliseconds

Example log entry:
```
[2024-01-15 14:23:45.123] ✓ Computer: DESKTOP-ABC123 | IP: 8.8.8.8 | Status: SUCCESS | TTL: 64 | Time: 15ms
[2024-01-15 14:23:46.456] ✗ Computer: DESKTOP-ABC123 | IP: 192.168.1.1 | Status: TIMEOUT | TTL: N/A | Time: N/A
```

## Console Output

The console shows results from all targets simultaneously:
```
[192.168.1.1   ] [2024-01-15 14:23:45.123] ✓ Computer: DESKTOP-ABC123 | IP: 192.168.1.1 | Status: SUCCESS | TTL: 64 | Time: 2ms
[8.8.8.8       ] [2024-01-15 14:23:45.234] ✓ Computer: DESKTOP-ABC123 | IP: 8.8.8.8 | Status: SUCCESS | TTL: 64 | Time: 15ms
```

## Stopping the Diagnostic

Press `Ctrl+C` to stop the ping diagnostic. The script will:
- Stop pinging immediately
- Write summary statistics to each log file
- Display the location of all log files
- Show you're ready to attach files to email

## Visualization

The tool automatically generates comprehensive visualization charts when you stop the diagnostic (Ctrl+C). Each target gets its own visualization PNG file with 4 panels:

1. **Timeout Events Over Time**: Shows when timeouts occurred as a timeline
2. **Ping Duration Over Time**: Individual ping durations and rolling average
3. **Time Between Timeout Events**: Histogram showing the distribution of intervals between timeouts
4. **Ping Status Distribution**: Pie chart showing percentage of successful vs timeout pings

Visualization files are saved as: `ping_log_YYYYMMDD_HHMMSS_IP_visualization.png`

**Note**: Visualizations require matplotlib. Install with:
```bash
python -m pip install matplotlib
```

If matplotlib is not installed, the tool will still work but skip visualization generation.

**📖 Need help interpreting the charts?** See [CHART_INTERPRETATION_GUIDE.md](CHART_INTERPRETATION_GUIDE.md) for a comprehensive guide on reading and understanding all visualization panels.

## Exporting Logs

Simply attach **both ping and speed test log files and visualization images** to your email to Eero support. The log files are plain text and can be opened in any text editor or email client. The visualization PNG files provide a quick visual summary of connectivity stability and throughput over time.

**Pro Tip**: When running on multiple computers, the computer name in each log helps identify which device had issues.

## Time Synchronization (Script-Level)

When running the script on multiple computers, accurate timestamps are crucial for correlating events. The script automatically performs **script-level time synchronization** - no root/administrator privileges required!

### How It Works

1. **Queries NTP server** - On startup, the script queries an NTP server (e.g., pool.ntp.org) to get accurate time
2. **Calculates time offset** - Measures the difference between local system time and NTP time
3. **Applies offset to all timestamps** - All timestamps in logs are automatically adjusted to NTP time
4. **No system changes** - The system clock is not modified; only the logged timestamps are adjusted

### Benefits

- ✅ **No root/administrator privileges required** - Works for all users
- ✅ **Automatic** - Happens automatically when the script starts
- ✅ **Cross-computer accuracy** - All computers using the script will have synchronized timestamps
- ✅ **Transparent** - Log headers show the offset being applied

### Installing ntplib

For accurate time synchronization, install `ntplib`:

```bash
python -m pip install ntplib
```

**Note**: If `ntplib` is not installed, the script will use local system time and warn you that timestamps may not be synchronized across computers.

## Network Stability Metrics

The visualization suite and log summary now include advanced stability analytics:

- **Median stable time between disruptions** – how long the network stays healthy between timeout clusters
- **Disruptions per hour** – frequency of outage clusters normalized per hour of monitoring
- **Median timeout duration** – typical length of an outage (clusters consider consecutive timeouts as one disruption)
- **Timeout duration histogram** – visual breakdown of short spikes vs lengthy outages
- **Total timeout time** – aggregate downtime observed during the session

Timeout clusters are derived from consecutive timeout events, so bursts of failures appear as one disruption with a specific duration. This helps characterize the severity and frequency of outages when sharing data with support teams.

## Interpreting the Visualizations & Insights

Each visualization panel highlights a specific aspect of stability:

1. **Timeout Timeline** – Red bands mark each disruption. Closer bands indicate frequent outages.
2. **Ping Duration Trend** – Shows whether latency drifts upward before failures. Sudden spikes often precede dropouts.
3. **Stable Time Between Disruptions** – Bar chart of uptime between clusters. Short bars mean the network rarely recovers.
4. **Timeout Duration Distribution** – Histogram of outage lengths, useful to show if issues are quick blips or lengthy drops.

Under the chart, a text summary highlights median uptime/downtime and disruptions per hour.  
The log file also contains an **“Insights & Guidance”** section with human-readable conclusions (e.g., “Frequent disruptions detected” or “Outages are brief”). Share this section with support to describe how often and how long the network fails.

## Tips for Eero Support

1. **Run on multiple devices**: The computer name in logs helps identify which device had connectivity issues
2. **Time is automatically synchronized**: The script adjusts all timestamps to NTP time automatically - no setup needed!
3. **Compare gateway vs internet**: 
   - If gateway pings fail → local network issue
   - If gateway succeeds but 8.8.8.8 fails → internet connectivity issue
4. **Run for several minutes**: Capture enough data to show the pattern of issues
5. **Note the time of issues**: The timestamps (NTP-adjusted) will help correlate with your experience across multiple computers
6. **Common Eero gateway IPs**: `192.168.1.1`, `192.168.4.1`, or auto-detected

## Troubleshooting

- **Permission errors**: Make sure you have write permissions in the directory
- **Ping not working**: Verify you have network connectivity and the IP address is correct
- **Script won't stop**: Use Ctrl+C, or close the terminal window
- **Gateway not detected**: The script will use `192.168.1.1` as default, but you can specify your Eero gateway IP manually
