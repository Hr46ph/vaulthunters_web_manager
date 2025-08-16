import os
import time
import threading
import queue
import select
import subprocess
from datetime import datetime
import logging

class LogWatcher:
    """Real-time log file watcher using tail -f approach"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.watchers = {}  # {log_type: {'process': subprocess, 'queue': queue, 'clients': set}}
        self.lock = threading.Lock()
    
    def start_watching(self, log_type, log_path):
        """Start watching a log file for changes"""
        with self.lock:
            if log_type in self.watchers:
                return  # Already watching
            
            if not os.path.exists(log_path):
                self.logger.warning(f"Log file does not exist: {log_path}")
                return
            
            try:
                
                # Use tail -f to follow the log file
                process = subprocess.Popen(
                    ['tail', '-f', log_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1
                )
                
                # Create queue for new lines
                line_queue = queue.Queue()
                clients = set()
                
                # Start thread to read from tail and put into queue
                def reader_thread():
                    try:
                        while True:
                            # Use select to check if data is available
                            ready, _, _ = select.select([process.stdout], [], [], 1.0)
                            if ready:
                                line = process.stdout.readline()
                                if line:
                                    timestamp = datetime.now().isoformat()
                                    line_queue.put({
                                        'line': line.rstrip('\n\r'),
                                        'timestamp': timestamp,
                                        'log_type': log_type
                                    })
                                elif process.poll() is not None:
                                    # Process has ended
                                    break
                            elif process.poll() is not None:
                                # Process has ended and no more data
                                break
                    except Exception as e:
                        self.logger.error(f"Error in reader thread for {log_type}: {e}")
                    finally:
                        self.logger.info(f"Reader thread for {log_type} ended")
                
                thread = threading.Thread(target=reader_thread, daemon=True)
                thread.start()
                
                self.watchers[log_type] = {
                    'process': process,
                    'queue': line_queue,
                    'clients': clients,
                    'thread': thread,
                    'log_path': log_path
                }
                
                self.logger.info(f"Started watching {log_type} log: {log_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to start watching {log_type}: {e}")
    
    def stop_watching(self, log_type):
        """Stop watching a log file"""
        with self.lock:
            if log_type not in self.watchers:
                return
            
            watcher = self.watchers[log_type]
            
            # Terminate the tail process
            if watcher['process']:
                watcher['process'].terminate()
                try:
                    watcher['process'].wait(timeout=5)
                except subprocess.TimeoutExpired:
                    watcher['process'].kill()
            
            # Clear clients
            watcher['clients'].clear()
            
            del self.watchers[log_type]
            self.logger.info(f"Stopped watching {log_type} log")
    
    def add_client(self, log_type, client_id):
        """Add a client to receive updates for a log type"""
        with self.lock:
            if log_type in self.watchers:
                self.watchers[log_type]['clients'].add(client_id)
                return True
            return False
    
    def remove_client(self, log_type, client_id):
        """Remove a client from receiving updates"""
        with self.lock:
            if log_type in self.watchers:
                self.watchers[log_type]['clients'].discard(client_id)
                
                # If no more clients, stop watching to save resources
                if not self.watchers[log_type]['clients']:
                    self.stop_watching(log_type)
    
    def get_new_lines(self, log_type, client_id, timeout=30):
        """Get new lines for a specific client (blocking call for SSE)"""
        if log_type not in self.watchers:
            return None
        
        watcher = self.watchers[log_type]
        
        # Add client if not already added
        self.add_client(log_type, client_id)
        
        try:
            # Wait for new line with timeout
            line_data = watcher['queue'].get(timeout=timeout)
            return line_data
        except queue.Empty:
            # Timeout - send keepalive
            return {'keepalive': True, 'timestamp': datetime.now().isoformat()}
        except Exception as e:
            self.logger.error(f"Error getting new lines for {log_type}: {e}")
            return None
    
    def get_recent_lines(self, log_path, lines=50):
        """Get recent lines from a log file (for initial load)"""
        try:
            result = subprocess.run(
                ['tail', '-n', str(lines), log_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error reading log: {result.stderr}"
        except subprocess.TimeoutExpired:
            return "Error: timeout reading log file"
        except FileNotFoundError:
            return "Log file not found"
        except Exception as e:
            return f"Error reading log: {str(e)}"

# Global log watcher instance
_log_watcher = LogWatcher()

def get_log_watcher():
    """Get the global log watcher instance"""
    return _log_watcher