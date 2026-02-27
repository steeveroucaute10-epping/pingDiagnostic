# Pi Network Monitor - Raspberry Pi Setup

Run ping and speedtest diagnostics permanently on a Raspberry Pi (Debian), persist data, and query via nanobot MCP.

## Prerequisites

- Raspberry Pi with Raspberry Pi OS (Debian-based)
- Python 3.9+ in a venv (e.g. `/home/pi/nanobot-venv/`)
- Nanobot v0.1.4+ (for MCP support)

## 1. Clone the Repository

```bash
cd ~/.nanobot/workspace/skills
git clone https://github.com/YOUR_ORG/pingDiagnostic.git pi-network-monitor
cd pi-network-monitor
```
Replace `YOUR_ORG` with your GitHub user or org (e.g. `steev`).

## 2. Install Dependencies

```bash
/home/pi/nanobot-venv/bin/pip install -r requirements.txt
```

## 3. Configure the Monitor

Copy the example config and edit if needed:

```bash
cp pi_monitor/config.example.json pi_monitor/config.json
# Edit pi_monitor/config.json to set ping_targets, intervals, etc.
```

Default config:
- Ping targets: `192.168.1.1`, `8.8.8.8`
- Ping interval: 1 second
- Speedtest interval: 15 minutes
- **Retention: 30 days** – data older than 30 days is deleted automatically (startup + every 24h)
- `vacuum_after_cleanup: true` – reclaims disk space after deletions

To change retention: set `retention_days` in config (e.g. `14` for 2 weeks) or `RETENTION_DAYS` env var.

To use your gateway, run `ip route | grep default` and use the gateway IP.

## 4. Install systemd Service (Daemon)

```bash
sudo cp pi_monitor/systemd/pi-monitor.service /etc/systemd/system/
# If you cloned to a different path, edit the service file:
# sudo nano /etc/systemd/system/pi-monitor.service
# Update WorkingDirectory and ensure ExecStart uses the venv Python path

sudo systemctl daemon-reload
sudo systemctl enable pi-monitor.service
sudo systemctl start pi-monitor.service
sudo systemctl status pi-monitor.service
```

## 5. Add MCP Server to Nanobot Config

Edit `~/.nanobot/config.json` and add under `tools.mcpServers`:

```json
{
  "tools": {
    "mcpServers": {
      "pi-network-monitor": {
        "command": "/home/pi/nanobot-venv/bin/python",
        "args": ["/home/pi/.nanobot/workspace/skills/pi-network-monitor/pi_monitor/run.py"]
      }
    }
  }
}
```

If you cloned elsewhere, update the `args` path to your `pi_monitor/run.py`.

## 6. Restart Nanobot

```bash
sudo systemctl daemon-reload
sudo systemctl restart nanobot.service
```

## 7. Verify

- **Daemon**: `sudo journalctl -u pi-monitor.service -f`
- **Database**: `ls -la ~/.nanobot/workspace/skills/pi-network-monitor/data/pi_monitor.db`
- **MCP handshake**: 
  ```bash
  echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | /home/pi/nanobot-venv/bin/python /home/pi/.nanobot/workspace/skills/pi-network-monitor/pi_monitor/run.py
  ```
  Should return JSON with `serverInfo`.

- **Session cleanup** (if MCP tools don't appear): 
  ```bash
  rm ~/.nanobot/workspace/sessions/*.json
  sudo systemctl restart nanobot.service
  ```

- **Exec fallback** (report without MCP): 
  ```bash
  /home/pi/nanobot-venv/bin/python -m pi_monitor.report_cli --days 7
  ```

## Dashboard UI (Local Network)

To view stats in a browser from any device on your network:

### Option A: Run dashboard on your PC, connect to Pi API

1. **Start the API on the Pi** (if not running as a service):
   ```bash
   /home/pi/nanobot-venv/bin/python -m pi_monitor.api --host 0.0.0.0 --port 5001
   ```
   Or enable the API service:
   ```bash
   sudo cp pi_monitor/systemd/pi-monitor-api.service /etc/systemd/system/
   sudo systemctl enable pi-monitor-api.service
   sudo systemctl start pi-monitor-api.service
   ```

2. **Start the dashboard on your PC** (or any machine on the network):
   ```bash
   python dashboard_server.py --api-url http://PI_IP:5001
   ```
   Replace `PI_IP` with your Pi's IP (e.g. `192.168.1.10`).

3. Open `http://localhost:5000` in your browser. The dashboard will show data from the Pi.

### Option B: Run dashboard on the Pi

1. Start the API (see above).
2. Start the dashboard on the Pi:
   ```bash
   /home/pi/nanobot-venv/bin/python dashboard_server.py --host 0.0.0.0 --port 5000
   ```
3. From any device on the network, open `http://PI_IP:5000`.

### Environment variable

You can also set `DASHBOARD_API_URL=http://PI_IP:5001` instead of `--api-url`.

## MCP Tools Available to Nanobot

| Tool | Description |
|------|-------------|
| `ping_outage_report` | Outage stats (count, uptime %, outages/day) for last N days |
| `speedtest_summary` | Download/upload stats and stability |
| `latency_summary` | Ping latency (avg, min, max) |
| `weekly_network_report` | Combined human-readable report |

Example questions for nanobot: "What were the network outages last week?", "How stable is my internet speed?", "Give me a weekly network report."

## Troubleshooting

- **No database**: Ensure pi-monitor.service is running. Data appears after a few minutes.
- **MCP tools not showing**: Check nanobot version (`nanobot --version`), clear sessions, verify config JSON syntax.
- **Different clone path**: Update `WorkingDirectory` in pi-monitor.service and `args` in nanobot config.
