# Ping Diagnostic Tool

A Python tool for continuous network ping diagnostics with detailed timestamped logging. Perfect for diagnosing WiFi mesh network issues and providing logs to support teams.

## Features

- ✅ **Dual Target Monitoring**: Automatically pings both your Eero gateway and Google DNS (8.8.8.8)
- ✅ **Separate Log Files**: Creates individual log files for each target for easy analysis
- ✅ **Computer Name Tracking**: Includes computer name in logs (useful when running on multiple devices)
- ✅ **Continuous ping monitoring** with precise timestamps (millisecond precision)
- ✅ **Logs IP address, TTL, timeout status, and response time**
- ✅ **Saves logs to text files** for easy email attachment
- ✅ **Graceful shutdown** with Ctrl+C
- ✅ **Summary statistics** at the end of each session
- ✅ **Auto-detects default gateway** (Eero router)
- ✅ **Easy to use command-line interface**

## Requirements

- Python 3.6 or higher
- Windows (uses Windows ping command)

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
```

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

## Exporting Logs

Simply attach **both log files** to your email to Eero support. The log files are plain text and can be opened in any text editor or email client.

**Pro Tip**: When running on multiple computers, the computer name in each log helps identify which device had issues.

## Tips for Eero Support

1. **Run on multiple devices**: The computer name in logs helps identify which device had connectivity issues
2. **Compare gateway vs internet**: 
   - If gateway pings fail → local network issue
   - If gateway succeeds but 8.8.8.8 fails → internet connectivity issue
3. **Run for several minutes**: Capture enough data to show the pattern of issues
4. **Note the time of issues**: The timestamps will help correlate with your experience
5. **Common Eero gateway IPs**: `192.168.1.1`, `192.168.4.1`, or auto-detected

## Troubleshooting

- **Permission errors**: Make sure you have write permissions in the directory
- **Ping not working**: Verify you have network connectivity and the IP address is correct
- **Script won't stop**: Use Ctrl+C, or close the terminal window
- **Gateway not detected**: The script will use `192.168.1.1` as default, but you can specify your Eero gateway IP manually
