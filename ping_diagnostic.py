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
from datetime import datetime
from pathlib import Path

class PingTarget:
    """Represents a single ping target with its own logging"""
    def __init__(self, target_ip, log_file, computer_name):
        self.target_ip = target_ip
        self.log_file = log_file
        self.log_path = Path(log_file)
        self.computer_name = computer_name
        self.ping_count = 0
        self.success_count = 0
        self.timeout_count = 0
        
    def parse_ping_output(self, output):
        """Parse Windows ping output to extract TTL and status"""
        lines = output.strip().split('\n')
        
        # Look for reply line (e.g., "Reply from 192.168.1.1: bytes=32 time=1ms TTL=64")
        for line in lines:
            if 'Reply from' in line or 'bytes=' in line:
                # Extract TTL
                ttl_match = re.search(r'TTL=(\d+)', line)
                ttl = ttl_match.group(1) if ttl_match else 'N/A'
                
                # Extract time
                time_match = re.search(r'time[<=](\d+)', line)
                time_ms = time_match.group(1) if time_match else 'N/A'
                
                return {
                    'status': 'success',
                    'ttl': ttl,
                    'time_ms': time_ms
                }
            
            # Check for timeout
            if 'Request timed out' in line or 'timed out' in line:
                return {
                    'status': 'timeout',
                    'ttl': 'N/A',
                    'time_ms': 'N/A'
                }
            
            # Check for destination host unreachable
            if 'Destination host unreachable' in line:
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
        try:
            # Windows ping command: ping -n 1 -w 1000 <target>
            result = subprocess.run(
                ['ping', '-n', '1', '-w', '1000', self.target_ip],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Parse output
            ping_result = self.parse_ping_output(result.stdout)
            
        except subprocess.TimeoutExpired:
            # Ping command itself timed out
            ping_result = {
                'status': 'timeout',
                'ttl': 'N/A',
                'time_ms': 'N/A'
            }
        
        except Exception as e:
            # Other errors
            ping_result = {
                'status': f'error: {str(e)}',
                'ttl': 'N/A',
                'time_ms': 'N/A'
            }
        
        # Log the result
        self.log_result(timestamp, ping_result)
        return ping_result
    
    def log_result(self, timestamp, result):
        """Log ping result to file"""
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
    
    def write_header(self):
        """Write header information to log file"""
        header = f"""
{'='*80}
Ping Diagnostic Log
{'='*80}
Computer Name: {self.computer_name}
Target IP: {self.target_ip}
Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}
Log File: {self.log_path.absolute()}
{'='*80}

"""
        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(header)
    
    def write_footer(self):
        """Write summary statistics to log file"""
        success_pct = (self.success_count/self.ping_count*100) if self.ping_count > 0 else 0.0
        timeout_pct = (self.timeout_count/self.ping_count*100) if self.ping_count > 0 else 0.0
        footer = f"""
{'='*80}
Summary Statistics
{'='*80}
Computer Name: {self.computer_name}
Target IP: {self.target_ip}
End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}
Total Pings: {self.ping_count}
Successful: {self.success_count} ({success_pct:.2f}%)
Timeouts: {self.timeout_count} ({timeout_pct:.2f}%)
{'='*80}
"""
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(footer)


class PingDiagnostic:
    def __init__(self, targets, log_prefix=None, computer_name=None):
        self.running = True
        self.computer_name = computer_name or self.get_computer_name()
        self.log_prefix = log_prefix or f"ping_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create ping targets
        self.targets = []
        for target_ip in targets:
            # Create log file name based on target IP (sanitize IP for filename)
            safe_ip = target_ip.replace('.', '_')
            log_file = f"{self.log_prefix}_{safe_ip}.txt"
            target = PingTarget(target_ip, log_file, self.computer_name)
            self.targets.append(target)
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
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
        # Write headers for all targets
        for target in self.targets:
            target.write_header()
        
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
                # Get precise timestamp (same for all targets in this cycle)
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                
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
            print("\nYou can now attach these log files to your email to Eero support.")


def get_default_gateway():
    """Try to detect the default gateway IP"""
    try:
        # Use route command to get default gateway
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
    
    # Check command line arguments
    if len(sys.argv) > 1:
        # User provided targets
        targets = sys.argv[1].split(',')
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
    if len(sys.argv) > 2:
        log_prefix = sys.argv[2]
    
    # Optional: ping interval
    interval = 1
    if len(sys.argv) > 3:
        try:
            interval = float(sys.argv[3])
        except ValueError:
            print(f"Warning: Invalid interval '{sys.argv[3]}', using default 1 second")
    
    # Create and run diagnostic
    diagnostic = PingDiagnostic(targets, log_prefix)
    diagnostic.run(interval)


if __name__ == '__main__':
    main()
