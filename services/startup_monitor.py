import time
import threading
import logging
from datetime import datetime
from flask import current_app
from mcstatus import JavaServer
from .system_control import SystemControlService

class StartupMonitor:
    """Monitors Minecraft server startup progress and readiness"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._startup_state = 'stopped'  # stopped, starting, running, ready
        self._startup_start_time = None
        self._startup_callbacks = []
        self._monitor_thread = None
        self._stop_monitoring = False
    
    def get_startup_state(self):
        """Get current startup state"""
        return {
            'state': self._startup_state,
            'start_time': self._startup_start_time.isoformat() if self._startup_start_time else None,
            'duration': self._get_startup_duration()
        }
    
    def _get_startup_duration(self):
        """Get startup duration in seconds"""
        if not self._startup_start_time:
            return 0
        return (datetime.now() - self._startup_start_time).total_seconds()
    
    def register_callback(self, callback):
        """Register callback for state changes: callback(state, data)"""
        self._startup_callbacks.append(callback)
    
    def _notify_callbacks(self, state, data=None):
        """Notify all registered callbacks of state change"""
        for callback in self._startup_callbacks:
            try:
                callback(state, data)
            except Exception as e:
                self.logger.error(f"Startup callback error: {e}")
    
    def start_monitoring(self):
        """Start monitoring server startup process"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            self.logger.warning("Startup monitoring already running")
            return
        
        self._startup_state = 'starting'
        self._startup_start_time = datetime.now()
        self._stop_monitoring = False
        
        self._monitor_thread = threading.Thread(target=self._monitor_startup, daemon=True)
        self._monitor_thread.start()
        
        self._notify_callbacks('starting', {'start_time': self._startup_start_time})
        self.logger.info("Started server startup monitoring")
    
    def stop_monitoring(self):
        """Stop startup monitoring"""
        self._stop_monitoring = True
        self._startup_state = 'stopped'
        self._startup_start_time = None
        self._notify_callbacks('stopped')
        self.logger.info("Stopped server startup monitoring")
    
    def _monitor_startup(self):
        """Monitor startup process in background thread"""
        try:
            system_control = SystemControlService()
            
            # Phase 1: Wait for process to start
            self.logger.info("Phase 1: Waiting for Java process to start...")
            process_start_time = time.time()
            process_found = False
            
            while not self._stop_monitoring and time.time() - process_start_time < 60:  # 60 second timeout
                if system_control._get_minecraft_process():
                    process_found = True
                    self.logger.info("Java process started")
                    self._notify_callbacks('process_started', {
                        'duration': time.time() - process_start_time
                    })
                    break
                time.sleep(1)
            
            if not process_found:
                self._startup_state = 'failed'
                self._notify_callbacks('failed', {'error': 'Process failed to start within 60 seconds'})
                return
            
            # Phase 2: Wait for server to accept connections
            self.logger.info("Phase 2: Waiting for server to accept connections...")
            self._startup_state = 'running'
            self._notify_callbacks('running')
            
            connection_start_time = time.time()
            server_ready = False
            
            # Get server connection details
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            server_port = current_app.config.get('MINECRAFT_SERVER_PORT', 25565)
            
            while not self._stop_monitoring and time.time() - connection_start_time < 300:  # 5 minute timeout
                try:
                    server = JavaServer(server_host, server_port)
                    status = server.status(timeout=5)
                    
                    if status:
                        server_ready = True
                        self._startup_state = 'ready'
                        ready_duration = time.time() - process_start_time
                        
                        self.logger.info(f"Server ready for connections (total startup: {ready_duration:.1f}s)")
                        self._notify_callbacks('ready', {
                            'total_duration': ready_duration,
                            'connection_duration': time.time() - connection_start_time,
                            'players': status.players.online,
                            'max_players': status.players.max
                        })
                        break
                        
                except Exception as e:
                    self.logger.debug(f"Server not ready yet: {e}")
                
                time.sleep(2)  # Check every 2 seconds
            
            if not server_ready:
                self._startup_state = 'timeout'
                self._notify_callbacks('timeout', {
                    'error': 'Server did not become ready within 5 minutes'
                })
        
        except Exception as e:
            self.logger.error(f"Startup monitoring error: {e}")
            self._startup_state = 'error'
            self._notify_callbacks('error', {'error': str(e)})

# Global startup monitor instance
_startup_monitor = None

def get_startup_monitor():
    """Get global startup monitor instance"""
    global _startup_monitor
    if _startup_monitor is None:
        _startup_monitor = StartupMonitor()
    return _startup_monitor