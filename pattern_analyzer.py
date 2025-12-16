#!/usr/bin/env python3
"""
Pattern Analyzer for Ping Diagnostic Logs
Analyzes timeout patterns across multiple test runs by abstracting dates
and focusing on time-of-day patterns.
"""

import re
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
import argparse

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.dates import date2num
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed. Visualization features will be disabled.")
    print("Install with: pip install matplotlib")


def parse_log_file(filepath):
    """
    Parse a ping diagnostic log file and extract timeout information.
    
    Returns:
        dict with keys:
            - 'timeouts': list of datetime objects for each timeout
            - 'all_pings': list of tuples (datetime, status) for all pings
            - 'filename': name of the log file
            - 'run_name': name of the test run
            - 'target_ip': target IP address
    """
    timeouts = []
    all_pings = []
    run_name = None
    target_ip = None
    
    # Pattern to match log entries: [YYYY-MM-DD HH:MM:SS.mmm] ...
    timestamp_pattern = re.compile(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}\.\d{3})\]')
    # Pattern to match timeout entries
    timeout_pattern = re.compile(r'Status:\s+TIMEOUT')
    # Pattern to match run name
    run_name_pattern = re.compile(r'Run Name:\s+(.+)')
    # Pattern to match target IP
    target_ip_pattern = re.compile(r'Target IP:\s+([\d.]+)')
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # Extract run name
                run_match = run_name_pattern.search(line)
                if run_match:
                    run_name = run_match.group(1).strip()
                
                # Extract target IP
                ip_match = target_ip_pattern.search(line)
                if ip_match:
                    target_ip = ip_match.group(1).strip()
                
                # Check if line contains a timestamp
                ts_match = timestamp_pattern.search(line)
                if ts_match:
                    date_str = ts_match.group(1)
                    time_str = ts_match.group(2)
                    full_timestamp = f"{date_str} {time_str}"
                    
                    try:
                        dt = datetime.strptime(full_timestamp, "%Y-%m-%d %H:%M:%S.%f")
                        
                        # Check if this is a timeout
                        if timeout_pattern.search(line):
                            timeouts.append(dt)
                            all_pings.append((dt, 'timeout'))
                        else:
                            # Check for success or other status
                            if 'Status: SUCCESS' in line:
                                all_pings.append((dt, 'success'))
                            elif 'Status: UNREACHABLE' in line:
                                all_pings.append((dt, 'unreachable'))
                            else:
                                all_pings.append((dt, 'unknown'))
                    except ValueError as e:
                        # Skip lines with invalid timestamps
                        continue
        
        return {
            'timeouts': timeouts,
            'all_pings': all_pings,
            'filename': Path(filepath).name,
            'run_name': run_name or Path(filepath).stem,
            'target_ip': target_ip or 'unknown'
        }
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return None


def abstract_time_of_day(datetime_obj):
    """
    Abstract the date, keeping only the time of day.
    Returns a datetime object with today's date but the original time.
    """
    # Use a reference date (e.g., 2000-01-01) to normalize all times
    reference_date = datetime(2000, 1, 1)
    return datetime.combine(reference_date, datetime_obj.time())


def group_by_hour(timeouts):
    """
    Group timeout timestamps by hour of day.
    
    Returns:
        dict mapping hour (0-23) to list of timeout datetimes
    """
    hourly_groups = defaultdict(list)
    for timeout in timeouts:
        hour = timeout.hour
        hourly_groups[hour].append(timeout)
    return hourly_groups


def calculate_timeouts_per_hour(timeouts):
    """
    Calculate timeouts per hour for each hour of the day.
    Since we abstract dates, we need to count how many timeouts occurred
    at each hour across all days.
    
    Returns:
        dict mapping hour (0-23) to count of timeouts
    """
    hourly_counts = defaultdict(int)
    for timeout in timeouts:
        hour = timeout.hour
        hourly_counts[hour] += 1
    return hourly_counts


def calculate_average_interval_by_hour(timeouts):
    """
    Calculate average interval between timeouts grouped by hour.
    Only calculates intervals between timeouts that occur on the same day
    to avoid misleading cross-day intervals.
    
    Returns:
        dict mapping hour (0-23) to average interval in seconds
    """
    # Group timeouts by hour
    hourly_groups = group_by_hour(timeouts)
    
    hourly_intervals = {}
    for hour, hour_timeouts in hourly_groups.items():
        if len(hour_timeouts) < 2:
            # Need at least 2 timeouts to calculate interval
            hourly_intervals[hour] = None
        else:
            # Sort timeouts by time
            sorted_timeouts = sorted(hour_timeouts)
            intervals = []
            
            # Only calculate intervals between timeouts on the same day
            # to avoid misleading cross-day intervals (e.g., 14:50 Day 1 to 14:10 Day 2)
            for i in range(1, len(sorted_timeouts)):
                prev_timeout = sorted_timeouts[i-1]
                curr_timeout = sorted_timeouts[i]
                
                # Calculate interval in seconds
                interval = (curr_timeout - prev_timeout).total_seconds()
                
                # Only include intervals that are within the same day (less than 2 hours)
                # This filters out cross-day intervals while allowing same-day intervals
                # that might span slightly into the next hour
                if interval < 2 * 3600:  # Less than 2 hours
                    intervals.append(interval)
            
            if intervals:
                hourly_intervals[hour] = statistics.mean(intervals)
            else:
                hourly_intervals[hour] = None
    
    return hourly_intervals


def find_ping_log_files(directory='.'):
    """
    Find all ping diagnostic log files in the directory.
    Looks for files matching pattern: *_ping_*.txt
    
    Returns:
        list of Path objects for matching log files
    
    Raises:
        FileNotFoundError: if the directory doesn't exist
        NotADirectoryError: if the path exists but is not a directory
        PermissionError: if permission is denied accessing the directory
    """
    directory_path = Path(directory)
    
    # Check if directory exists
    if not directory_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    
    # Check if it's actually a directory
    if not directory_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")
    
    log_files = []
    
    # Pattern: anything_ping_anything.txt
    pattern = re.compile(r'.*_ping_.*\.txt$', re.IGNORECASE)
    
    # Wrap iterdir() in try-except to handle potential race conditions
    # (directory could be deleted between exists() check and iterdir() call)
    # and other OS-level errors
    try:
        for file in directory_path.iterdir():
            if file.is_file() and pattern.match(file.name):
                log_files.append(file)
    except FileNotFoundError as e:
        # Handle race condition: directory deleted between check and iterdir()
        raise FileNotFoundError(f"Directory not found or was deleted: {directory}") from e
    except PermissionError as e:
        raise PermissionError(f"Permission denied accessing directory: {directory}") from e
    except OSError as e:
        # Catch other OS-level errors (e.g., network drive disconnected, etc.)
        raise OSError(f"Error accessing directory {directory}: {e}") from e
    
    return sorted(log_files)


def create_timeouts_per_hour_plot(parsed_logs, output_file='pattern_analysis_timeouts_per_hour.png'):
    """
    Create a time series plot showing timeouts per hour for each log file.
    X-axis: Time of day (hours)
    Y-axis: Number of timeouts per hour (aggregated across all days)
    One line per log file.
    """
    if not HAS_MATPLOTLIB:
        print("matplotlib not available, skipping visualization")
        return
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Create hours list (0-23) for x-axis
    hours = list(range(24))
    
    # Plot a line for each log file
    for log_data in parsed_logs:
        if log_data is None:
            continue
        
        timeouts = log_data['timeouts']
        if not timeouts:
            continue
        
        # Calculate timeouts per hour (aggregated across all days)
        hourly_counts = calculate_timeouts_per_hour(timeouts)
        
        # Create data points for all hours
        counts = [hourly_counts.get(hour, 0) for hour in hours]
        
        # Create label from filename and run name
        label = f"{log_data['run_name']} ({log_data['target_ip']})"
        if len(label) > 50:
            label = label[:47] + "..."
        
        ax.plot(hours, counts, marker='o', label=label, linewidth=2, markersize=5, alpha=0.8)
    
    ax.set_xlabel('Hour of Day', fontsize=12, fontweight='bold')
    ax.set_ylabel('Total Timeouts per Hour (Aggregated Across All Days)', fontsize=12, fontweight='bold')
    ax.set_title('Timeout Frequency Pattern by Hour of Day', fontsize=14, fontweight='bold')
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}:00" for h in hours], rotation=45, ha='right')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    ax.set_xlim(-0.5, 23.5)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved timeouts per hour plot: {output_file}")
    plt.close()


def create_interval_plot(parsed_logs, output_file='pattern_analysis_intervals.png'):
    """
    Create a plot showing average interval between timeouts grouped by hour.
    X-axis: Hour of day
    Y-axis: Average interval between timeouts (seconds)
    One line per log file.
    """
    if not HAS_MATPLOTLIB:
        print("matplotlib not available, skipping visualization")
        return
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    hours = list(range(24))
    
    for log_data in parsed_logs:
        if log_data is None:
            continue
        
        timeouts = log_data['timeouts']
        if not timeouts:
            continue
        
        # Calculate average intervals by hour
        hourly_intervals = calculate_average_interval_by_hour(timeouts)
        
        # Create data points for all hours
        intervals = [hourly_intervals.get(hour) for hour in hours]
        
        # Create label
        label = f"{log_data['run_name']} ({log_data['target_ip']})"
        if len(label) > 50:
            label = label[:47] + "..."
        
        # Plot only hours that have data
        valid_hours = [h for h, iv in zip(hours, intervals) if iv is not None]
        valid_intervals = [iv for iv in intervals if iv is not None]
        
        if valid_hours:
            ax.plot(valid_hours, valid_intervals, marker='o', label=label, linewidth=2, markersize=4)
    
    ax.set_xlabel('Hour of Day', fontsize=12, fontweight='bold')
    ax.set_ylabel('Average Interval Between Timeouts (seconds)', fontsize=12, fontweight='bold')
    ax.set_title('Average Timeout Interval by Hour of Day', fontsize=14, fontweight='bold')
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}:00" for h in hours], rotation=45, ha='right')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    ax.set_xlim(-0.5, 23.5)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved interval plot: {output_file}")
    plt.close()


def create_hourly_frequency_plot(parsed_logs, output_file='pattern_analysis_hourly_frequency.png'):
    """
    Create a plot showing hourly frequency of timeouts for each log file.
    This shows the count of timeout events at each hour across all days.
    X-axis: Hour of day
    Y-axis: Count of timeout events at that hour
    One line per log file.
    """
    if not HAS_MATPLOTLIB:
        print("matplotlib not available, skipping visualization")
        return
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    hours = list(range(24))
    
    for log_data in parsed_logs:
        if log_data is None:
            continue
        
        timeouts = log_data['timeouts']
        if not timeouts:
            continue
        
        # Group by hour and count occurrences
        hourly_groups = group_by_hour(timeouts)
        
        # Count how many timeouts occurred at each hour
        frequencies = [len(hourly_groups.get(hour, [])) for hour in hours]
        
        # Create label
        label = f"{log_data['run_name']} ({log_data['target_ip']})"
        if len(label) > 50:
            label = label[:47] + "..."
        
        ax.plot(hours, frequencies, marker='o', label=label, linewidth=2, markersize=5, alpha=0.8)
    
    ax.set_xlabel('Hour of Day', fontsize=12, fontweight='bold')
    ax.set_ylabel('Count of Timeout Events', fontsize=12, fontweight='bold')
    ax.set_title('Hourly Frequency of Timeout Events (Aggregated Across All Days)', fontsize=14, fontweight='bold')
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}:00" for h in hours], rotation=45, ha='right')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    ax.set_xlim(-0.5, 23.5)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved hourly frequency plot: {output_file}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description='Analyze timeout patterns across multiple ping diagnostic log files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pattern_analyzer.py
  python pattern_analyzer.py --directory ./logs
  python pattern_analyzer.py --output-prefix my_analysis
        """
    )
    parser.add_argument(
        '--directory', '-d',
        type=str,
        default='.',
        help='Directory containing ping log files (default: current directory)'
    )
    parser.add_argument(
        '--output-prefix', '-o',
        type=str,
        default='pattern_analysis',
        help='Prefix for output visualization files (default: pattern_analysis)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Pattern Analyzer for Ping Diagnostic Logs")
    print("=" * 80)
    print()
    
    # Find all ping log files
    try:
        log_files = find_ping_log_files(args.directory)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print(f"Please check that the directory exists: {args.directory}")
        return
    except NotADirectoryError as e:
        print(f"Error: {e}")
        print(f"Please provide a valid directory path: {args.directory}")
        return
    except PermissionError as e:
        print(f"Error: {e}")
        print(f"Please check that you have permission to access: {args.directory}")
        return
    except OSError as e:
        print(f"Error: {e}")
        print(f"Please check that the directory is accessible: {args.directory}")
        return
    
    if not log_files:
        print(f"No ping log files found in {args.directory}")
        print("Looking for files matching pattern: *_ping_*.txt")
        return
    
    print(f"Found {len(log_files)} log file(s):")
    for log_file in log_files:
        print(f"  - {log_file.name}")
    print()
    
    # Parse all log files
    print("Parsing log files...")
    parsed_logs = []
    for log_file in log_files:
        print(f"  Parsing {log_file.name}...", end=' ')
        log_data = parse_log_file(log_file)
        if log_data:
            timeout_count = len(log_data['timeouts'])
            print(f"OK - Found {timeout_count} timeout(s)")
            parsed_logs.append(log_data)
        else:
            print("FAILED - Could not parse")
    
    if not parsed_logs:
        print("\nNo valid log files could be parsed.")
        return
    
    # Filter out logs with no timeouts
    parsed_logs = [log for log in parsed_logs if log['timeouts']]
    
    if not parsed_logs:
        print("\nNo timeouts found in any log files.")
        return
    
    print(f"\nAnalyzing {len(parsed_logs)} log file(s) with timeouts...")
    print()
    
    # Generate visualizations
    if HAS_MATPLOTLIB:
        print("Generating visualizations...")
        create_timeouts_per_hour_plot(parsed_logs, f"{args.output_prefix}_timeouts_per_hour.png")
        create_interval_plot(parsed_logs, f"{args.output_prefix}_intervals.png")
        create_hourly_frequency_plot(parsed_logs, f"{args.output_prefix}_hourly_frequency.png")
        print()
        print("Analysis complete! Generated visualization files:")
        print(f"  - {args.output_prefix}_timeouts_per_hour.png")
        print(f"  - {args.output_prefix}_intervals.png")
        print(f"  - {args.output_prefix}_hourly_frequency.png")
    else:
        print("matplotlib not available. Install with: pip install matplotlib")
        print("Skipping visualization generation.")
    
    # Print summary statistics
    print()
    print("=" * 80)
    print("Summary Statistics")
    print("=" * 80)
    for log_data in parsed_logs:
        print(f"\n{log_data['run_name']} ({log_data['target_ip']}):")
        print(f"  Total timeouts: {len(log_data['timeouts'])}")
        hourly_counts = calculate_timeouts_per_hour(log_data['timeouts'])
        if hourly_counts:
            max_hour = max(hourly_counts.items(), key=lambda x: x[1])
            print(f"  Peak hour: {max_hour[0]:02d}:00 with {max_hour[1]} timeout(s)")
            total_hours = sum(hourly_counts.values())
            print(f"  Total timeout events: {total_hours}")


if __name__ == '__main__':
    main()

