#!/usr/bin/env python3
"""
Ping Diagnostic Tool
Continuously pings multiple target IP addresses and logs results with timestamps.
Useful for diagnosing network connectivity issues.
"""

import subprocess
import re
import sys
import signal
import os
import socket
import time
import platform
from datetime import datetime, timezone, timedelta
from pathlib import Path
try:
    import ntplib
    HAS_NTPLIB = True
except ImportError:
    HAS_NTPLIB = False
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed. Visualization features will be disabled.")
    print("Install with: pip install matplotlib")

def get_platform_type():
    """Detect the operating system platform"""
    system = platform.system().lower()
    if system == 'windows':
        return 'windows'
    elif system == 'darwin':  # macOS
        return 'mac'
    elif system == 'linux':
        return 'linux'
    else:
        return 'unix'  # Generic Unix-like


def query_ntp_time(ntp_server='pool.ntp.org'):
    """Query NTP server to get accurate time and calculate offset (script-level sync)"""
    try:
        if HAS_NTPLIB:
            # Use ntplib if available (more accurate)
            client = ntplib.NTPClient()
            response = client.request(ntp_server, version=3, timeout=5)
            ntp_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
            local_time = datetime.now(timezone.utc)
            offset_seconds = (local_time - ntp_time).total_seconds()
            return {
                'success': True,
                'ntp_time': ntp_time,
                'local_time': local_time,
                'offset_seconds': offset_seconds,
                'offset_ms': offset_seconds * 1000,
                'server': ntp_server
            }
        else:
            # Try multiple NTP servers as fallback
            ntp_servers = ['pool.ntp.org', 'time.google.com', 'time.cloudflare.com']
            for server in ntp_servers:
                try:
                    client = ntplib.NTPClient()
                    response = client.request(server, version=3, timeout=3)
                    ntp_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
                    local_time = datetime.now(timezone.utc)
                    offset_seconds = (local_time - ntp_time).total_seconds()
                    return {
                        'success': True,
                        'ntp_time': ntp_time,
                        'local_time': local_time,
                        'offset_seconds': offset_seconds,
                        'offset_ms': offset_seconds * 1000,
                        'server': server
                    }
                except:
                    continue
            return {'success': False, 'error': 'ntplib not available and NTP query failed'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


class PingTarget:
    """Represents a single ping target with its own logging"""
    def __init__(self, target_ip, log_file, computer_name, debug=False, time_offset=None):
        self.target_ip = target_ip
        self.log_file = log_file
        self.log_path = Path(log_file)
        self.computer_name = computer_name
        self.ping_count = 0
        self.success_count = 0
        self.timeout_count = 0
        self.debug = debug
        self.platform = get_platform_type()
        self.time_offset = time_offset  # Offset in seconds to apply to timestamps
        
        # Data storage for visualization
        self.ping_data = []  # List of dicts: {'timestamp': datetime, 'duration': float, 'status': str}
        self.start_time = None
    
    def get_synchronized_time(self, local_time=None):
        """Get synchronized timestamp by applying NTP offset"""
        if local_time is None:
            local_time = datetime.now()
        
        if self.time_offset is not None:
            return local_time - timedelta(seconds=self.time_offset)
        return local_time
        
    def parse_ping_output(self, output):
        """Parse ping output to extract TTL and status (supports Windows, Mac, and Linux)"""
        lines = output.strip().split('\n')
        
        # Look for reply line - different formats for different OS
        # Windows: "Reply from 192.168.1.1: bytes=32 time=1ms TTL=64"
        # Mac/Linux: "64 bytes from 192.168.1.1: icmp_seq=0 ttl=64 time=1.234 ms"
        for line in lines:
            line_lower = line.lower()
            
            # Check for successful reply - Windows format
            if 'reply from' in line_lower or ('bytes=' in line_lower and 'time' in line_lower and self.platform == 'windows'):
                # Extract TTL - try multiple patterns
                ttl_match = re.search(r'TTL[=:](\d+)', line, re.IGNORECASE)
                if not ttl_match:
                    ttl_match = re.search(r'ttl\s*(\d+)', line, re.IGNORECASE)
                ttl = ttl_match.group(1) if ttl_match else 'N/A'
                
                # Extract time - try multiple patterns
                time_match = re.search(r'time[<=:](\d+)', line, re.IGNORECASE)
                if not time_match:
                    time_match = re.search(r'(\d+)\s*ms', line, re.IGNORECASE)
                time_ms = time_match.group(1) if time_match else 'N/A'
                
                return {
                    'status': 'success',
                    'ttl': ttl,
                    'time_ms': time_ms
                }
            
            # Check for successful reply - Mac/Linux format
            # Format: "64 bytes from 192.168.1.1: icmp_seq=0 ttl=64 time=1.234 ms"
            if 'bytes from' in line_lower and 'icmp_seq' in line_lower and self.platform != 'windows':
                # Extract TTL
                ttl_match = re.search(r'ttl[=:](\d+)', line, re.IGNORECASE)
                ttl = ttl_match.group(1) if ttl_match else 'N/A'
                
                # Extract time (can be decimal like 1.234 ms)
                time_match = re.search(r'time[=:](\d+\.?\d*)\s*ms', line, re.IGNORECASE)
                if time_match:
                    # Round to integer for consistency
                    time_ms = str(int(float(time_match.group(1))))
                else:
                    time_match = re.search(r'time[=:](\d+)', line, re.IGNORECASE)
                    time_ms = time_match.group(1) if time_match else 'N/A'
                
                return {
                    'status': 'success',
                    'ttl': ttl,
                    'time_ms': time_ms
                }
            
            # Check for timeout - multiple patterns
            # Windows: "Request timed out"
            # Mac/Linux: "Request timeout for icmp_seq X" or "no answer yet"
            if ('request timed out' in line_lower or 
                'timed out' in line_lower or 
                'request timeout' in line_lower or
                'no answer yet' in line_lower or
                '100% packet loss' in line_lower):
                return {
                    'status': 'timeout',
                    'ttl': 'N/A',
                    'time_ms': 'N/A'
                }
            
            # Check for destination host unreachable
            if 'destination host unreachable' in line_lower or 'host unreachable' in line_lower:
                return {
                    'status': 'unreachable',
                    'ttl': 'N/A',
                    'time_ms': 'N/A'
                }
            
            # Mac/Linux: Check for "no route to host" or "network is unreachable"
            if 'no route to host' in line_lower or 'network is unreachable' in line_lower:
                return {
                    'status': 'unreachable',
                    'ttl': 'N/A',
                    'time_ms': 'N/A'
                }
        
        return {
            'status': 'unknown',
            'ttl': 'N/A',
            'time_ms': 'N/A'
        }
    
    def ping(self, timestamp):
        """Perform a single ping and log the result"""
        # Record start time if first ping
        if self.start_time is None:
            self.start_time = datetime.now()
        
        ping_datetime = datetime.now()
        # Get synchronized timestamp (timestamp parameter is already synchronized from run loop)
        # But we also need it for storing in ping_data
        sync_datetime = self.get_synchronized_time(ping_datetime)
        
        try:
            # Build ping command based on platform
            if self.platform == 'windows':
                # Windows: ping -n 1 -w 1000 <target>
                # -n 1 = count 1 packet, -w 1000 = timeout 1000ms
                ping_cmd = f'ping -n 1 -w 1000 {self.target_ip}'
                use_shell = True
            elif self.platform == 'mac':
                # Mac: ping -c 1 -W 1000 <target>
                # -c 1 = count 1 packet, -W 1000 = timeout 1000ms
                ping_cmd = ['ping', '-c', '1', '-W', '1000', self.target_ip]
                use_shell = False
            else:
                # Linux: ping -c 1 -W 1 <target>
                # -c 1 = count 1 packet, -W 1 = timeout 1 second (Linux uses seconds)
                ping_cmd = ['ping', '-c', '1', '-W', '1', self.target_ip]
                use_shell = False
            
            result = subprocess.run(
                ping_cmd,
                shell=use_shell,
                capture_output=True,
                text=True,
                timeout=10  # Increased timeout to allow ping to complete
            )
            
            # Combine stdout and stderr (ping output can go to either)
            output = result.stdout + result.stderr
            
            # Debug output
            if self.debug:
                print(f"\n[DEBUG] Ping command return code: {result.returncode}")
                print(f"[DEBUG] stdout length: {len(result.stdout)}, stderr length: {len(result.stderr)}")
                print(f"[DEBUG] Output preview (first 500 chars):\n{output[:500]}")
            
            # Parse output
            ping_result = self.parse_ping_output(output)
            
            # Mac/Linux: Check return code for timeout detection FIRST
            # On Mac/Linux, ping returns non-zero exit code on timeout
            # Return code 0 = success, 1 = no reply/timeout, 2 = other error
            if self.platform != 'windows' and result.returncode != 0:
                # Mac/Linux ping returns 1 on timeout (no reply), 2 on other errors
                if result.returncode == 1:
                    # No reply received - this is a timeout
                    # Override parsing result if we got success or unknown
                    if ping_result['status'] in ['success', 'unknown']:
                        ping_result = {
                            'status': 'timeout',
                            'ttl': 'N/A',
                            'time_ms': 'N/A'
                        }
                elif result.returncode == 2:
                    # Other error - only treat as timeout if not unreachable
                    if ping_result['status'] in ['success', 'unknown']:
                        if 'unreachable' not in output.lower() and 'no route' not in output.lower():
                            ping_result = {
                                'status': 'timeout',
                                'ttl': 'N/A',
                                'time_ms': 'N/A'
                            }
            
            # If parsing failed and we got unknown, check return code
            if ping_result['status'] == 'unknown':
                # Return code 0 usually means success, non-zero means failure
                if result.returncode == 0:
                    # Try to parse again with more lenient matching
                    ping_result = self.parse_ping_output_verbose(output)
                elif self.platform == 'windows':
                    # Windows: Check for common error patterns
                    if 'timed out' in output.lower() or 'request timed out' in output.lower():
                        ping_result = {
                            'status': 'timeout',
                            'ttl': 'N/A',
                            'time_ms': 'N/A'
                        }
            
        except subprocess.TimeoutExpired:
            # Ping command itself timed out
            ping_result = {
                'status': 'timeout',
                'ttl': 'N/A',
                'time_ms': 'N/A'
            }
        
        except Exception as e:
            # Other errors - log the error for debugging
            ping_result = {
                'status': f'error: {str(e)}',
                'ttl': 'N/A',
                'time_ms': 'N/A'
            }
        
        # Store data for visualization (use synchronized time)
        duration = float(ping_result['time_ms']) if ping_result['time_ms'] != 'N/A' else None
        self.ping_data.append({
            'timestamp': sync_datetime,  # Store synchronized time
            'duration': duration,
            'status': ping_result['status']
        })
        
        # Log the result (timestamp parameter is already synchronized from run loop)
        self.log_result(timestamp, ping_result)
        return ping_result
    
    def parse_ping_output_verbose(self, output):
        """More verbose parsing that tries multiple patterns (cross-platform)"""
        lines = output.strip().split('\n')
        
        # Try multiple patterns for successful ping
        for line in lines:
            line_lower = line.lower()
            
            # Windows pattern: "Reply from 192.168.1.1: bytes=32 time=1ms TTL=64"
            if 'reply from' in line_lower:
                # Extract TTL
                ttl_match = re.search(r'TTL[=:](\d+)', line, re.IGNORECASE)
                ttl = ttl_match.group(1) if ttl_match else 'N/A'
                
                # Extract time - try multiple patterns
                time_match = re.search(r'time[<=:](\d+)', line, re.IGNORECASE)
                if not time_match:
                    time_match = re.search(r'(\d+)\s*ms', line, re.IGNORECASE)
                time_ms = time_match.group(1) if time_match else 'N/A'
                
                return {
                    'status': 'success',
                    'ttl': ttl,
                    'time_ms': time_ms
                }
            
            # Mac/Linux pattern: "64 bytes from 192.168.1.1: icmp_seq=0 ttl=64 time=1.234 ms"
            if 'bytes from' in line_lower and 'icmp_seq' in line_lower:
                # Extract TTL
                ttl_match = re.search(r'ttl[=:](\d+)', line, re.IGNORECASE)
                ttl = ttl_match.group(1) if ttl_match else 'N/A'
                
                # Extract time (can be decimal)
                time_match = re.search(r'time[=:](\d+\.?\d*)\s*ms', line, re.IGNORECASE)
                if time_match:
                    time_ms = str(int(float(time_match.group(1))))
                else:
                    time_match = re.search(r'time[=:](\d+)', line, re.IGNORECASE)
                    time_ms = time_match.group(1) if time_match else 'N/A'
                
                return {
                    'status': 'success',
                    'ttl': ttl,
                    'time_ms': time_ms
                }
            
            # Check for timeout
            if 'timed out' in line_lower or 'timeout' in line_lower:
                return {
                    'status': 'timeout',
                    'ttl': 'N/A',
                    'time_ms': 'N/A'
                }
            
            # Check for destination host unreachable
            if 'unreachable' in line_lower or 'no route to host' in line_lower:
                return {
                    'status': 'unreachable',
                    'ttl': 'N/A',
                    'time_ms': 'N/A'
                }
        
        return {
            'status': 'unknown',
            'ttl': 'N/A',
            'time_ms': 'N/A'
        }
    
    def log_result(self, timestamp, result):
        """Log ping result to file (timestamp is already synchronized)"""
        status_icon = '✓' if result['status'] == 'success' else '✗'
        log_line = f"[{timestamp}] {status_icon} Computer: {self.computer_name} | IP: {self.target_ip} | Status: {result['status'].upper()} | TTL: {result['ttl']} | Time: {result['time_ms']}ms\n"
        
        # Write to file
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(log_line)
        
        # Also print to console with target identifier
        target_label = f"[{self.target_ip:15}]"
        print(f"{target_label} {log_line.strip()}")
        
        # Update statistics
        self.ping_count += 1
        if result['status'] == 'success':
            self.success_count += 1
        elif result['status'] == 'timeout':
            self.timeout_count += 1
    
    def write_header(self, time_sync_info=None):
        """Write header information to log file"""
        # Use synchronized time for start time
        start_time = self.get_synchronized_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Add time sync information if available
        time_sync_text = ""
        if time_sync_info:
            if time_sync_info.get('offset_seconds') is not None:
                offset_ms = time_sync_info.get('offset_ms', 0)
                offset_sec = time_sync_info.get('offset_seconds', 0)
                ntp_server = time_sync_info.get('server', 'NTP')
                
                if abs(offset_ms) < 10:
                    time_sync_text = f"Time Sync: Synchronized with {ntp_server} (offset: {offset_ms:.2f}ms)\n"
                    time_sync_text += "All timestamps are adjusted to NTP time for cross-computer accuracy.\n"
                else:
                    time_sync_text = f"Time Sync: Adjusted to {ntp_server} (offset: {offset_ms:.2f}ms / {offset_sec:.3f}s)\n"
                    time_sync_text += "All timestamps are adjusted to NTP time for cross-computer accuracy.\n"
            else:
                time_sync_text = "Time Sync: NTP query failed - using local time\n"
                time_sync_text += "WARNING: Timestamps may not be synchronized across multiple computers!\n"
        
        header = f"""
{'='*80}
Ping Diagnostic Log
{'='*80}
Computer Name: {self.computer_name}
Target IP: {self.target_ip}
Start Time (NTP-adjusted): {start_time}
{time_sync_text}Log File: {self.log_path.absolute()}
{'='*80}

"""
        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(header)
    
    def write_footer(self):
        """Write summary statistics to log file"""
        success_pct = (self.success_count/self.ping_count*100) if self.ping_count > 0 else 0.0
        timeout_pct = (self.timeout_count/self.ping_count*100) if self.ping_count > 0 else 0.0
        
        # Calculate average duration for successful pings
        successful_durations = [d['duration'] for d in self.ping_data if d['duration'] is not None]
        avg_duration = sum(successful_durations) / len(successful_durations) if successful_durations else 0.0
        
        # Use synchronized time for end time
        end_time = self.get_synchronized_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        footer = f"""
{'='*80}
Summary Statistics
{'='*80}
Computer Name: {self.computer_name}
Target IP: {self.target_ip}
End Time (NTP-adjusted): {end_time}
Total Pings: {self.ping_count}
Successful: {self.success_count} ({success_pct:.2f}%)
Timeouts: {self.timeout_count} ({timeout_pct:.2f}%)
Average Duration: {avg_duration:.2f}ms
{'='*80}
"""
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(footer)
    
    def generate_visualizations(self):
        """Generate visualization charts for this target"""
        if not HAS_MATPLOTLIB:
            return None
        
        if len(self.ping_data) < 2:
            print(f"Not enough data to generate visualizations for {self.target_ip}")
            return None
        
        safe_ip = self.target_ip.replace('.', '_')
        viz_prefix = str(self.log_path).replace('.txt', '')
        
        # Prepare data
        timestamps = [d['timestamp'] for d in self.ping_data]
        durations = [d['duration'] if d['duration'] is not None else 0 for d in self.ping_data]
        is_timeout = [1 if d['status'] == 'timeout' else 0 for d in self.ping_data]
        
        # Create figure with subplots
        fig = plt.figure(figsize=(16, 12))
        fig.suptitle(f'Ping Diagnostic Visualization - {self.target_ip}\nComputer: {self.computer_name}', 
                     fontsize=16, fontweight='bold')
        
        # 1. Timeout Volume Over Time
        ax1 = plt.subplot(2, 2, 1)
        ax1.plot(timestamps, is_timeout, 'r-', linewidth=1, alpha=0.7, label='Timeout Events')
        ax1.fill_between(timestamps, 0, is_timeout, alpha=0.3, color='red')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Timeout (1=Yes, 0=No)')
        ax1.set_title('Timeout Events Over Time')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax1.legend()
        
        # 2. Average Duration Over Time (rolling average)
        ax2 = plt.subplot(2, 2, 2)
        window_size = min(10, len(durations) // 10 + 1)  # Adaptive window size
        rolling_avg = []
        for i in range(len(durations)):
            start_idx = max(0, i - window_size + 1)
            window_durs = [d for d in durations[start_idx:i+1] if d > 0]
            if window_durs:
                rolling_avg.append(sum(window_durs) / len(window_durs))
            else:
                rolling_avg.append(0)
        
        ax2.plot(timestamps, durations, 'b.', markersize=2, alpha=0.3, label='Individual Pings')
        ax2.plot(timestamps, rolling_avg, 'g-', linewidth=2, label=f'Rolling Average ({window_size} pings)')
        ax2.set_xlabel('Time')
        ax2.set_ylabel('Duration (ms)')
        ax2.set_title('Ping Duration Over Time')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax2.legend()
        
        # 3. Time Between Timeout Events
        ax3 = plt.subplot(2, 2, 3)
        timeout_times = [timestamps[i] for i, is_to in enumerate(is_timeout) if is_to == 1]
        if len(timeout_times) > 1:
            time_between = []
            for i in range(1, len(timeout_times)):
                delta = (timeout_times[i] - timeout_times[i-1]).total_seconds()
                time_between.append(delta)
            
            if time_between:
                ax3.hist(time_between, bins=min(20, len(time_between)), edgecolor='black', alpha=0.7, color='orange')
                ax3.axvline(sum(time_between) / len(time_between), color='red', linestyle='--', 
                           linewidth=2, label=f'Average: {sum(time_between) / len(time_between):.1f}s')
                ax3.set_xlabel('Time Between Timeouts (seconds)')
                ax3.set_ylabel('Frequency')
                ax3.set_title('Distribution of Time Between Timeout Events')
                ax3.grid(True, alpha=0.3, axis='y')
                ax3.legend()
            else:
                ax3.text(0.5, 0.5, 'Only one timeout event\n(no intervals to calculate)', 
                        ha='center', va='center', transform=ax3.transAxes, fontsize=12)
                ax3.set_title('Time Between Timeout Events')
        else:
            ax3.text(0.5, 0.5, f'No timeout events\n({self.timeout_count} timeouts total)', 
                    ha='center', va='center', transform=ax3.transAxes, fontsize=12)
            ax3.set_title('Time Between Timeout Events')
        
        # 4. Percentage of Timeouts (Pie Chart)
        ax4 = plt.subplot(2, 2, 4)
        success_count = self.success_count
        timeout_count = self.timeout_count
        other_count = self.ping_count - success_count - timeout_count
        
        if self.ping_count > 0:
            sizes = [success_count, timeout_count, other_count]
            labels = [f'Successful\n{success_count} ({success_count/self.ping_count*100:.1f}%)',
                     f'Timeout\n{timeout_count} ({timeout_count/self.ping_count*100:.1f}%)',
                     f'Other\n{other_count} ({other_count/self.ping_count*100:.1f}%)']
            colors = ['#2ecc71', '#e74c3c', '#95a5a6']
            explode = (0, 0.1 if timeout_count > 0 else 0, 0)  # Explode timeout slice if present
            
            ax4.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='',
                   shadow=True, startangle=90)
            ax4.set_title('Ping Status Distribution')
        else:
            ax4.text(0.5, 0.5, 'No data available', ha='center', va='center', 
                    transform=ax4.transAxes, fontsize=12)
            ax4.set_title('Ping Status Distribution')
        
        plt.tight_layout()
        
        # Save the figure
        viz_file = f"{viz_prefix}_visualization.png"
        fig.savefig(viz_file, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        return viz_file


class PingDiagnostic:
    def __init__(self, targets, log_prefix=None, computer_name=None, debug=False):
        self.running = True
        self.computer_name = computer_name or self.get_computer_name()
        self.log_prefix = log_prefix or f"ping_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.debug = debug
        self.platform = get_platform_type()
        
        # Query NTP server to get time offset (script-level synchronization)
        self.time_sync_info = self.query_ntp_offset()
        
        # Extract offset for passing to targets
        time_offset = self.time_sync_info.get('offset_seconds') if self.time_sync_info.get('success') else None
        
        # Create ping targets with time offset
        self.targets = []
        for target_ip in targets:
            # Create log file name based on target IP (sanitize IP for filename)
            safe_ip = target_ip.replace('.', '_')
            log_file = f"{self.log_prefix}_{safe_ip}.txt"
            target = PingTarget(target_ip, log_file, self.computer_name, debug=debug, time_offset=time_offset)
            self.targets.append(target)
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def query_ntp_offset(self):
        """Query NTP server to get time offset for script-level synchronization"""
        print("\n" + "="*80)
        print("Time Synchronization (Script-Level)")
        print("="*80)
        
        # Query NTP server
        ntp_result = query_ntp_time()
        
        if ntp_result.get('success'):
            offset_ms = ntp_result.get('offset_ms', 0)
            offset_sec = ntp_result.get('offset_seconds', 0)
            ntp_server = ntp_result.get('server', 'pool.ntp.org')
            
            print(f"✓ NTP Server: {ntp_server}")
            print(f"✓ Time Offset: {offset_ms:.2f}ms ({offset_sec:.3f}s)")
            print(f"✓ All timestamps will be adjusted to NTP time")
            print(f"  This ensures accurate correlation across multiple computers")
            
            if abs(offset_ms) > 1000:  # More than 1 second
                print(f"\n⚠️  Note: Large time offset detected ({offset_ms:.2f}ms)")
                print("   Your system clock may be significantly off from NTP time")
            
            return {
                'success': True,
                'offset_seconds': offset_sec,
                'offset_ms': offset_ms,
                'server': ntp_server
            }
        else:
            error_msg = ntp_result.get('error', 'Unknown error')
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
                'success': False,
                'error': error_msg,
                'offset_seconds': None,
                'offset_ms': None
            }
        
        print("="*80 + "\n")
    
    def get_computer_name(self):
        """Get the computer name"""
        # Try Windows environment variable first
        computer_name = os.environ.get('COMPUTERNAME') or os.environ.get('COMPUTER_NAME')
        if computer_name:
            return computer_name
        # Fallback to socket hostname
        try:
            return socket.gethostname()
        except:
            return 'UNKNOWN'
    
    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\nStopping ping diagnostic...")
        self.running = False
    
    def run(self, interval=1):
        """Run continuous ping diagnostic for all targets"""
        # Write headers for all targets (with time sync info)
        for target in self.targets:
            target.write_header(self.time_sync_info)
        
        print("="*80)
        print("Ping Diagnostic Tool")
        print("="*80)
        print(f"Computer Name: {self.computer_name}")
        print(f"Monitoring {len(self.targets)} target(s):")
        for target in self.targets:
            print(f"  - {target.target_ip} -> {target.log_path.name}")
        print(f"\nPress Ctrl+C to stop\n")
        
        try:
            while self.running:
                # Get synchronized timestamp (same for all targets in this cycle)
                # Use the first target's synchronized time method
                sync_time = self.targets[0].get_synchronized_time() if self.targets else datetime.now()
                timestamp = sync_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                
                # Ping all targets sequentially
                for target in self.targets:
                    if not self.running:
                        break
                    target.ping(timestamp)
                
                # Wait before next cycle (if still running)
                if self.running:
                    import time
                    time.sleep(interval)
                    
        except KeyboardInterrupt:
            pass
        finally:
            # Write footers for all targets
            print("\n" + "="*80)
            print("Generating summary statistics...")
            for target in self.targets:
                target.write_footer()
                print(f"Log saved: {target.log_path.absolute()}")
            
            # Generate visualizations
            if HAS_MATPLOTLIB:
                print("\nGenerating visualizations...")
                for target in self.targets:
                    viz_file = target.generate_visualizations()
                    if viz_file:
                        print(f"Visualization saved: {Path(viz_file).absolute()}")
            
            print("\nYou can now attach these log files and visualizations to your email to Eero support.")


def get_default_gateway():
    """Try to detect the default gateway IP (cross-platform)"""
    platform_type = get_platform_type()
    
    try:
        if platform_type == 'windows':
            # Windows: route print 0.0.0.0
            result = subprocess.run(
                ['route', 'print', '0.0.0.0'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Look for default gateway in output
            lines = result.stdout.split('\n')
            for line in lines:
                if '0.0.0.0' in line and 'On-link' not in line:
                    parts = line.split()
                    # Gateway is usually in the third column
                    for i, part in enumerate(parts):
                        if part == '0.0.0.0' and i + 2 < len(parts):
                            gateway = parts[i + 2]
                            # Validate it looks like an IP
                            if re.match(r'^\d+\.\d+\.\d+\.\d+$', gateway):
                                return gateway
        else:
            # Mac/Linux: route -n get default or netstat -rn | grep default
            # Try route first (Mac)
            try:
                result = subprocess.run(
                    ['route', '-n', 'get', 'default'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                # Look for "gateway: x.x.x.x" in output
                for line in result.stdout.split('\n'):
                    if 'gateway:' in line.lower():
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.lower() == 'gateway:' and i + 1 < len(parts):
                                gateway = parts[i + 1]
                                if re.match(r'^\d+\.\d+\.\d+\.\d+$', gateway):
                                    return gateway
            except:
                pass
            
            # Fallback: netstat -rn (works on both Mac and Linux)
            try:
                result = subprocess.run(
                    ['netstat', '-rn'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                # Look for default route line
                for line in result.stdout.split('\n'):
                    if 'default' in line.lower() or line.startswith('0.0.0.0'):
                        parts = line.split()
                        # Gateway is usually the second field
                        if len(parts) >= 2:
                            gateway = parts[1]
                            if re.match(r'^\d+\.\d+\.\d+\.\d+$', gateway):
                                return gateway
            except:
                pass
    except:
        pass
    
    return None


def main():
    """Main entry point"""
    print("="*80)
    print("Ping Diagnostic Tool")
    print("="*80)
    print()
    
    # Default targets: Eero gateway (to be detected) and Google DNS
    default_gateway = get_default_gateway()
    
    targets = []
    
    # Check command line arguments (filter out flags)
    args = [arg for arg in sys.argv[1:] if not arg.startswith('--') and not arg.startswith('-')]
    
    if len(args) > 0:
        # User provided targets
        targets = args[0].split(',')
        targets = [t.strip() for t in targets]
    else:
        # Use defaults: Eero gateway and Google DNS
        if default_gateway:
            print(f"Detected default gateway: {default_gateway}")
            targets = [default_gateway, '8.8.8.8']
        else:
            print("Could not auto-detect gateway. Using defaults: 192.168.1.1 and 8.8.8.8")
            targets = ['192.168.1.1', '8.8.8.8']
        
        print(f"\nWill ping: {', '.join(targets)}")
        response = input("Press Enter to continue, or type custom IPs (comma-separated): ").strip()
        
        if response:
            targets = [t.strip() for t in response.split(',')]
    
    if not targets:
        print("Error: At least one target IP is required")
        sys.exit(1)
    
    # Optional: custom log file prefix
    log_prefix = None
    if len(args) > 1:
        log_prefix = args[1]
    
    # Optional: ping interval (frequency)
    interval = 1  # Default: 1 second between ping cycles
    # Check for --interval or -i flag
    if '--interval' in sys.argv:
        idx = sys.argv.index('--interval')
        if idx + 1 < len(sys.argv):
            try:
                interval = float(sys.argv[idx + 1])
            except (ValueError, IndexError):
                print(f"Warning: Invalid interval value, using default 1 second")
    elif '-i' in sys.argv:
        idx = sys.argv.index('-i')
        if idx + 1 < len(sys.argv):
            try:
                interval = float(sys.argv[idx + 1])
            except (ValueError, IndexError):
                print(f"Warning: Invalid interval value, using default 1 second")
    elif len(args) > 2:
        # Legacy: interval as positional argument
        try:
            interval = float(args[2])
        except ValueError:
            print(f"Warning: Invalid interval '{args[2]}', using default 1 second")
    
    # Optional: debug mode
    debug = '--debug' in sys.argv or '-d' in sys.argv
    
    # Display ping frequency
    print(f"\nPing frequency: {interval} second(s) between ping cycles")
    print(f"  (Use --interval <seconds> or -i <seconds> to change)\n")
    
    # Create and run diagnostic
    # Note: Time synchronization is now automatic at script level (no root required)
    diagnostic = PingDiagnostic(targets, log_prefix, debug=debug)
    diagnostic.run(interval)


if __name__ == '__main__':
    main()
