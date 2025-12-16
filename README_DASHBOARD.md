# Network Diagnostic Dashboard

A real-time web dashboard for monitoring active ping and speedtest diagnostics.

## Features

- **Real-time Monitoring**: View active test results as they happen
- **Auto-refresh**: Dashboard updates every minute automatically
- **Multiple Targets**: Monitor multiple ping targets simultaneously
- **Visual Charts**: Interactive charts showing ping duration and speedtest results
- **Statistics**: Real-time statistics including success rates, timeouts, and averages

## Setup

1. Install dependencies:
```bash
python -m pip install -r requirements.txt
```

2. Start the dashboard server:
```bash
python dashboard_server.py
```

3. Open your browser and navigate to:
```
http://localhost:5000
```

## Usage

### Running Tests with Dashboard

1. **Start the dashboard server** (in one terminal):
```bash
python dashboard_server.py
```

2. **Start ping diagnostic** (in another terminal):
```bash
python ping_diagnostic.py
```

3. **Start speedtest diagnostic** (optional, in another terminal):
```bash
python speedtest_diagnostic.py
```

4. **View the dashboard** in your browser at `http://localhost:5000`

The dashboard will automatically:
- Detect the latest JSON data files
- Update every minute with fresh data
- Show charts and statistics for all active tests

## Dashboard Features

### Ping Diagnostics Section
- **Ping Duration Chart**: Shows ping response times over time for each target
- **Statistics**: Total pings, success rate, timeout count, average duration
- **Multi-target Support**: Separate charts for each ping target (gateway, DNS, etc.)

### Speed Test Section
- **Download/Upload Chart**: Shows download and upload speeds over time
- **Statistics**: Tests completed, average download/upload, last ping latency
- **Status Indicators**: Shows test status (OK, ERROR)

## How It Works

1. When you run `ping_diagnostic.py` or `speedtest_diagnostic.py`, they automatically create JSON data files alongside the log files
2. The dashboard server reads these JSON files and serves them via a REST API
3. The web dashboard fetches data every minute and updates the charts
4. PNG visualizations are still generated at the end of tests (for sharing with Eero support)

## File Patterns

The dashboard looks for JSON files matching these patterns:
- Ping: `ping_log_*.json` or `*_ping_*.json`
- Speedtest: `*_speedtest_*.json`

These files are automatically created by the diagnostic scripts during execution.

## Troubleshooting

**Dashboard shows "No data available"**
- Make sure you've started a diagnostic script (`ping_diagnostic.py` or `speedtest_diagnostic.py`)
- Check that JSON files are being created in the same directory
- Verify the dashboard server is running

**Charts not updating**
- Check browser console for errors (F12)
- Verify the dashboard server is accessible
- Ensure JSON files are being written (check file timestamps)

**Port 5000 already in use**
- Change the port in `dashboard_server.py` (last line: `app.run(port=5001)`)
- Update the URL in your browser accordingly

