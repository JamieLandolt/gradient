#!/usr/bin/env python3
"""
Debug Server for TRAE-debugger skill.
Collects runtime logs via HTTP API for debugging sessions.
"""

import argparse
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)

# Store logs in memory and optionally write to file
logs = []
log_file = None
session_id = None
start_time = time.time()
idle_timeout = 1200  # 20 minutes default


def write_log_to_file(log_entry):
    """Write log entry to NDJSON file."""
    if log_file:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'session_id': session_id,
        'uptime': time.time() - start_time,
        'log_count': len(logs)
    })


@app.route('/logs', methods=['GET'])
def get_logs():
    """Get all logs or filter by query parameters."""
    filtered_logs = logs.copy()
    
    # Filter by level if specified
    level = request.args.get('level')
    if level:
        filtered_logs = [log for log in filtered_logs if log.get('level') == level]
    
    # Filter by hypothesis if specified
    hypothesis = request.args.get('hypothesis')
    if hypothesis:
        filtered_logs = [log for log in filtered_logs if log.get('hypothesis') == hypothesis]
    
    # Limit number of logs
    limit = request.args.get('limit', 100, type=int)
    filtered_logs = filtered_logs[-limit:]
    
    return jsonify({
        'logs': filtered_logs,
        'total': len(logs),
        'filtered': len(filtered_logs)
    })


@app.route('/logs', methods=['POST'])
def add_log():
    """Add a new log entry."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    # Add metadata
    log_entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'session_id': session_id,
        **data
    }
    
    logs.append(log_entry)
    write_log_to_file(log_entry)
    
    # Print to console for immediate visibility
    level = log_entry.get('level', 'INFO')
    message = log_entry.get('message', 'No message')
    print(f"[{level}] {message}")
    
    return jsonify({'status': 'logged', 'id': len(logs) - 1}), 201


@app.route('/logs', methods=['DELETE'])
def clear_logs():
    """Clear all logs."""
    logs.clear()
    if log_file and Path(log_file).exists():
        Path(log_file).unlink()
    return jsonify({'status': 'cleared'})


@app.route('/session', methods=['GET'])
def get_session_info():
    """Get current session information."""
    return jsonify({
        'session_id': session_id,
        'start_time': start_time,
        'uptime': time.time() - start_time,
        'log_count': len(logs),
        'idle_timeout': idle_timeout
    })


def check_idle_timeout():
    """Check for idle timeout and shutdown if exceeded."""
    while True:
        time.sleep(60)  # Check every minute
        if time.time() - start_time > idle_timeout:
            print(f"Idle timeout ({idle_timeout}s) exceeded. Shutting down...")
            # In a real implementation, you'd gracefully shut down the server
            break


def main():
    global session_id, log_file, idle_timeout
    
    parser = argparse.ArgumentParser(description='TRAE Debug Server')
    parser.add_argument('--session', required=True, help='Debug session ID')
    parser.add_argument('--port', type=int, default=8080, help='Server port (default: 8080)')
    parser.add_argument('--idle', type=int, default=1200, help='Idle timeout in seconds (default: 1200)')
    parser.add_argument('--log-dir', default='.', help='Directory for log files')
    
    args = parser.parse_args()
    
    session_id = args.session
    idle_timeout = args.idle
    log_dir = Path(args.log_dir)
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f'trae-debug-log-{session_id}.ndjson'
    
    # Write environment file for instrumentation
    env_file = log_dir / '.dbg' / f'{session_id}.env'
    env_file.parent.mkdir(exist_ok=True)
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(f'DEBUG_SERVER_URL=http://localhost:{args.port}\n')
        f.write(f'DEBUG_SESSION_ID={session_id}\n')
        f.write(f'DEBUG_LOG_FILE={log_file}\n')
    
    print(f"Starting TRAE Debug Server")
    print(f"Session ID: {session_id}")
    print(f"Port: {args.port}")
    print(f"Log file: {log_file}")
    print(f"Idle timeout: {idle_timeout}s")
    print(f"Environment file: {env_file}")
    print(f"API endpoints:")
    print(f"  GET  /health - Health check")
    print(f"  GET  /logs - Get logs (optional: ?level=ERROR&hypothesis=H1&limit=50)")
    print(f"  POST /logs - Add log entry")
    print(f"  DELETE /logs - Clear logs")
    print(f"  GET  /session - Get session info")
    
    # Start idle timeout checker in background
    timeout_thread = threading.Thread(target=check_idle_timeout, daemon=True)
    timeout_thread.start()
    
    app.run(host='0.0.0.0', port=args.port, debug=False)


if __name__ == '__main__':
    main()