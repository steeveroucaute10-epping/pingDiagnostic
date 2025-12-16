# Directory Structure

This document explains the organized directory structure of the Network Diagnostic tools.

## Directory Layout

```
pingDiagnostic/
├── scripts/                    # Main diagnostic scripts (root level)
│   ├── ping_diagnostic.py
│   ├── speedtest_diagnostic.py
│   ├── dashboard_server.py
│   └── pattern_analyzer.py
│
├── logs/                       # All log files and visualizations
│   ├── ping/                   # Ping diagnostic log files (.txt)
│   ├── speedtest/              # Speedtest diagnostic log files (.txt)
│   └── visualizations/         # PNG visualization files
│
├── data/                       # Temporary JSON files for dashboard
│   └── (auto-cleaned on script exit)
│
├── templates/                  # Dashboard HTML template
│   └── dashboard.html
│
└── requirements.txt            # Python dependencies
```

## File Organization

### Log Files
- **Ping logs**: `logs/ping/ping_log_YYYYMMDD_HHMMSS_IP.txt`
- **Speedtest logs**: `logs/speedtest/speedtest_log_YYYYMMDD_HHMMSS.txt`
- **Visualizations**: `logs/visualizations/*_visualization.png`

### Temporary Files
- **JSON files**: `data/*.json` (automatically cleaned up when scripts exit)

## Auto-Cleanup

JSON files in the `data/` directory are automatically deleted when:
1. The diagnostic script exits (Ctrl+C)
2. PNG visualizations are successfully generated

This prevents accumulation of temporary JSON files from previous runs.

## Dashboard

The dashboard server looks for JSON files in the `data/` directory:
- Ping: `data/ping_log_*.json` or `data/*_ping_*.json`
- Speedtest: `data/*_speedtest_*.json`

## Benefits

1. **Organized**: Logs, visualizations, and temporary files are separated
2. **Clean**: JSON files are automatically removed after use
3. **Easy to share**: All visualization PNGs are in one place (`logs/visualizations/`)
4. **Version control friendly**: `data/` directory is ignored by git (see `.gitignore`)


