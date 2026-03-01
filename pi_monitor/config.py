#!/usr/bin/env python3
"""
Configuration for pi_monitor daemon.
Loads from JSON config file or environment variables.
"""

import json
import os
from pathlib import Path
from typing import List, Optional


def get_config_path() -> Path:
    """Get config file path. Checks PING_DIAGNOSTIC_CONFIG env first."""
    env_path = os.environ.get("PING_DIAGNOSTIC_CONFIG")
    if env_path:
        return Path(env_path)
    base = Path(__file__).resolve().parent.parent
    return base / "pi_monitor" / "config.json"


def load_config() -> dict:
    """Load configuration from file or use defaults."""
    defaults = {
        "ping_targets": ["192.168.1.1", "8.8.8.8"],
        "ping_interval_seconds": 1,
        "ping_timeout_seconds": 2.0,
        "outage_min_consecutive_timeouts": 10,
        "speedtest_interval_minutes": 15,
        "computer_name": None,
        "data_dir": None,
        "db_path": None,
        "retention_days": 30,
        "vacuum_after_cleanup": True,
        "api_enabled": True,
        "api_port": 5001,
        "api_host": "0.0.0.0",
    }

    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config from {config_path}: {e}")

    # Override with env vars
    if os.environ.get("PING_TARGETS"):
        defaults["ping_targets"] = [t.strip() for t in os.environ["PING_TARGETS"].split(",")]
    if os.environ.get("PING_INTERVAL"):
        try:
            defaults["ping_interval_seconds"] = float(os.environ["PING_INTERVAL"])
        except ValueError:
            pass
    if os.environ.get("SPEEDTEST_INTERVAL"):
        try:
            defaults["speedtest_interval_minutes"] = float(os.environ["SPEEDTEST_INTERVAL"])
        except ValueError:
            pass
    if os.environ.get("RETENTION_DAYS"):
        try:
            defaults["retention_days"] = int(os.environ["RETENTION_DAYS"])
        except ValueError:
            pass

    return defaults
