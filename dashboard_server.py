#!/usr/bin/env python3
"""
Dashboard Web Server for Ping and Speedtest Diagnostics
Serves a real-time dashboard showing active test results.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for local development

# Directory where JSON data files are stored
DATA_DIR = Path('data')
DATA_DIR.mkdir(parents=True, exist_ok=True)


def find_latest_json_files():
    """Find the most recent ping and speedtest JSON files"""
    # Look for ping JSON files: ping_log_*.json or *_ping_*.json
    ping_files = list(DATA_DIR.glob('ping_log_*.json')) + list(DATA_DIR.glob('*_ping_*.json'))
    ping_files = sorted(ping_files, key=os.path.getmtime, reverse=True)
    
    # Look for speedtest JSON files: *_speedtest_*.json
    speedtest_files = sorted(DATA_DIR.glob('*_speedtest_*.json'), key=os.path.getmtime, reverse=True)
    
    return {
        'ping': ping_files[0] if ping_files else None,
        'speedtest': speedtest_files[0] if speedtest_files else None
    }


def load_json_file(filepath):
    """Load JSON data from file"""
    if filepath and filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading {filepath}: {e}")
            return None
    return None


@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/data')
def get_data():
    """API endpoint to get current test data"""
    files = find_latest_json_files()
    
    ping_data = load_json_file(files['ping'])
    speedtest_data = load_json_file(files['speedtest'])
    
    return jsonify({
        'ping': ping_data,
        'speedtest': speedtest_data,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/ping')
def get_ping_data():
    """API endpoint to get ping data only"""
    files = find_latest_json_files()
    ping_data = load_json_file(files['ping'])
    return jsonify(ping_data or {})


@app.route('/api/speedtest')
def get_speedtest_data():
    """API endpoint to get speedtest data only"""
    files = find_latest_json_files()
    speedtest_data = load_json_file(files['speedtest'])
    return jsonify(speedtest_data or {})


if __name__ == '__main__':
    print("=" * 80)
    print("Dashboard Server Starting")
    print("=" * 80)
    print("\nDashboard will be available at: http://localhost:5000")
    print("API endpoints:")
    print("  - http://localhost:5000/api/data (combined data)")
    print("  - http://localhost:5000/api/ping (ping data only)")
    print("  - http://localhost:5000/api/speedtest (speedtest data only)")
    print("\nPress Ctrl+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

