---
name: pi-network-monitor
description: Query persistent ping and speedtest diagnostics from a Raspberry Pi. Use when the user asks about network outages, speed stability, latency, or weekly reports.
---

# Pi Network Monitor Skill

Query long-term network diagnostics (ping outages, speedtests, latency) collected by the pi_monitor daemon on a Raspberry Pi.

## When to Use

- User asks about network outages, connectivity issues, or uptime
- User wants speedtest history, download/upload stability, or latency trends
- User requests a weekly or multi-day network report

## MCP Tools (preferred)

If the MCP server is configured, use these tools:

| Tool | Purpose |
|------|---------|
| `ping_outage_report` | Outage count, success rate, uptime %, outages per day |
| `speedtest_summary` | Download/upload stats, stability over N days |
| `latency_summary` | Ping latency (avg, min, max) for successful pings |
| `weekly_network_report` | Combined human-readable report |
| `storage_stats` | Row counts and DB path (for monitoring retention) |

Example: "What were the network outages last week?" → use `ping_outage_report(days=7)` or `weekly_network_report(days=7)`.

## Exec Fallback

If MCP is not configured, run the report CLI to get a printed report:

| Action | Command |
|--------|---------|
| Weekly report (7 days) | `python -m pi_monitor.report_cli --days 7` |
| 30-day report | `python -m pi_monitor.report_cli --days 30` |

On the Pi, use the venv Python:
```bash
/home/pi/nanobot-venv/bin/python -m pi_monitor.report_cli --days 7
```

To start collecting data (daemon):
```bash
python -m pi_monitor.daemon
```

## Prerequisites

- The pi_monitor daemon must be running (as a systemd service) to collect data
- Database at `data/pi_monitor.db` (or path in config)
- Nanobot v0.1.4+ for MCP support
