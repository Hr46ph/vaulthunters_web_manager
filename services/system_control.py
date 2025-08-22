import subprocess
import psutil
import time
import re
import os
import signal
import threading
from datetime import datetime, timedelta
from flask import current_app
import logging
from .server_properties import ServerPropertiesParser

# Global cache for status data
_status_cache = {}
_cache_duration = 5  # Cache for 5 seconds

# Global process tracking
_minecraft_process = None
_process_lock = threading.Lock()

class SystemControlService:
    """Service for managing Minecraft server process directly"""
    
    def __init__(self, server_name=None):
        self.server_name = server_name or "minecraft"
        self.logger = logging.getLogger(__name__)
        self.server_path = None
        self.java_executable = None
        self.server_jar = None
        self._initialize_server_config()
    
    def _initialize_server_config(self):
        """Initialize server configuration from Flask config"""
        try:
            self.server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
            self.java_executable = current_app.config.get('JAVA_EXECUTABLE', 'java')
            self.forge_startup_command = current_app.config.get('FORGE_STARTUP_COMMAND', [
                '@user_jvm_args.txt',
                '@libraries/net/minecraftforge/forge/1.18.2-40.2.9/unix_args.txt'
            ])
            
            self.logger.info(f"Server config - Path: {self.server_path}")
            self.logger.info(f"Forge startup command: {self.java_executable} {' '.join(self.forge_startup_command)}")
            
        except Exception as e:
            self.logger.error(f"Error initializing server config: {e}")
            # Fallback defaults
            self.server_path = '/home/minecraft/vaulthunters'
            self.java_executable = 'java'
            self.forge_startup_command = [
                '@user_jvm_args.txt',
                '@libraries/net/minecraftforge/forge/1.18.2-40.2.9/unix_args.txt'
            ]
    
    def get_server_status(self):
        """Get detailed server status with startup detection and caching"""
        # Check cache first
        cache_key = f"status_{self.server_name}"
        now = time.time()
        
        if cache_key in _status_cache:
            cached_data, cache_time = _status_cache[cache_key]
            if now - cache_time < _cache_duration:
                self.logger.debug("Returning cached status")
                return cached_data
        
        try:
            status_info = {
                'running': False,
                'status': 'stopped',  # stopped, starting, running
                'uptime': '0 minutes',
                'players': 0,
                'max_players': 20,
                'last_update': datetime.now().isoformat(),
                'memory_usage': 0,
                'cpu_usage': 0.0,
                'pid': None,
                'server_ready': False
            }
            
            # Check if Minecraft process is running
            minecraft_proc = self._get_minecraft_process()
            
            if minecraft_proc and minecraft_proc.is_running():
                status_info['running'] = True
                status_info['pid'] = minecraft_proc.pid
                
                try:
                    # Get process info
                    proc_info = minecraft_proc.as_dict(attrs=['pid', 'create_time', 'memory_info', 'cpu_percent'])
                    
                    # Calculate uptime
                    create_time = datetime.fromtimestamp(proc_info['create_time'])
                    uptime_seconds = (datetime.now() - create_time).total_seconds()
                    status_info['uptime'] = self._format_uptime(uptime_seconds)
                    
                    # Get memory usage (in MB)
                    if proc_info['memory_info']:
                        status_info['memory_usage'] = round(proc_info['memory_info'].rss / 1024 / 1024)
                    
                    # Get CPU usage
                    cpu_percent = proc_info.get('cpu_percent', 0)
                    if cpu_percent is not None:
                        status_info['cpu_usage'] = cpu_percent
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    self.logger.warning(f"Error getting process info: {e}")
                
                # Check if server is ready for connections using mcstatus
                server_ready = False
                last_error = None
                
                try:
                    from mcstatus import JavaServer
                    server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
                    server_port = current_app.config.get('MINECRAFT_SERVER_PORT', 25565)
                    
                    
                    server = JavaServer(server_host, server_port)
                    query_status = server.status()
                    
                    if query_status:
                        server_ready = True
                        status_info['players'] = query_status.players.online
                        status_info['max_players'] = query_status.players.max
                        
                        # Collect player names from mcstatus
                        player_names = []
                        if query_status.players.sample:
                            for player in query_status.players.sample:
                                player_names.append(player.name)
                        
                        # Try query method for more complete player list (if available)
                        try:
                            query_result = server.query()
                            if hasattr(query_result.players, 'names') and query_result.players.names:
                                player_names = query_result.players.names  # More complete list
                        except:
                            pass  # Query not available, use sample
                        
                        status_info['player_names'] = player_names
                        status_info['server_ready'] = True
                        status_info['status'] = 'running'
                        
                        player_list_str = ", ".join(player_names) if player_names else "none"
                        self.logger.info(f"mcstatus connected successfully - {query_status.players.online}/{query_status.players.max} players ({player_list_str})")
                        
                except Exception as e:
                    last_error = e
                    self.logger.warning(f"mcstatus connection to {server_host}:{server_port} failed: {type(e).__name__}: {e}")
                
                if not server_ready and last_error:
                    self.logger.warning(f"mcstatus connection failed: {type(last_error).__name__}: {last_error}")
                    
                    # Check process uptime to distinguish between starting vs connection issues
                    proc_info = minecraft_proc.as_dict(attrs=['create_time'])
                    create_time = datetime.fromtimestamp(proc_info['create_time'])
                    uptime_seconds = (datetime.now() - create_time).total_seconds()
                    
                    # If server has been running for more than 5 minutes, it's likely a connection issue, not startup
                    if uptime_seconds > 300:  # 5 minutes
                        self.logger.warning(f"Server process running for {uptime_seconds:.1f}s but mcstatus failed - assuming running with connection issues")
                        status_info['server_ready'] = False
                        status_info['status'] = 'running'  # Assume running but with connection problems
                    else:
                        # Server process exists but can't connect and hasn't been running long - it's starting up
                        status_info['server_ready'] = False
                        status_info['status'] = 'starting'
                    
                    # Try to get max_players from server.properties as fallback
                    try:
                        server_props = ServerPropertiesParser()
                        if server_props.load_properties():
                            max_players = server_props.get_property('max-players', '20')
                            status_info['max_players'] = int(max_players) if max_players.isdigit() else 20
                    except Exception:
                        pass
            else:
                # No process running
                status_info['status'] = 'stopped'
            
            # Cache the result
            _status_cache[cache_key] = (status_info, now)
            return status_info
            
        except Exception as e:
            self.logger.error(f"Error getting server status: {e}")
            return {
                'running': False,
                'status': 'stopped',
                'uptime': 'Unknown',
                'players': 0,
                'max_players': 20,
                'last_update': datetime.now().isoformat(),
                'memory_usage': 0,
                'cpu_usage': 0.0,
                'pid': None,
                'server_ready': False,
                'error': str(e)
            }
    
    def _get_minecraft_process(self):
        """Find the running Minecraft server process"""
        global _minecraft_process
        
        with _process_lock:
            # Check if we have a cached process and it's still running
            if _minecraft_process and _minecraft_process.is_running():
                return _minecraft_process
            
            # Search for Minecraft process - prioritize actual Java process over bash wrapper
            java_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    name = proc.info['name']
                    if not cmdline:
                        continue
                    
                    # Look for Java process with Forge arguments
                    if (any('java' in arg.lower() for arg in cmdline) and
                        (any('user_jvm_args.txt' in arg for arg in cmdline) or
                         any('unix_args.txt' in arg for arg in cmdline) or
                         any('forge' in arg.lower() for arg in cmdline))):
                        
                        # Prioritize actual java processes over bash wrappers
                        if name == 'java':
                            _minecraft_process = proc
                            self.logger.info(f"Found Java Minecraft process: PID {proc.pid}")
                            return _minecraft_process
                        else:
                            java_processes.append(proc)
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # If no direct java process found, use any qualifying process
            if java_processes:
                _minecraft_process = java_processes[0]
                self.logger.info(f"Found Minecraft wrapper process: PID {_minecraft_process.pid}")
                return _minecraft_process
            
            _minecraft_process = None
            return None
    
    def start_server(self):
        """Start the Minecraft server process"""
        try:
            # Check if server is already running
            if self._get_minecraft_process():
                return {'success': False, 'error': 'Server is already running'}
            
            # Start the startup monitor
            try:
                from .startup_monitor import get_startup_monitor
                startup_monitor = get_startup_monitor()
                startup_monitor.start_monitoring()
                self.logger.info("Started startup monitoring")
            except Exception as e:
                self.logger.warning(f"Could not start startup monitor: {e}")
            
            # Verify required files exist
            user_jvm_args_path = os.path.join(self.server_path, 'user_jvm_args.txt')
            unix_args_path = os.path.join(self.server_path, 'libraries/net/minecraftforge/forge/1.18.2-40.2.9/unix_args.txt')
            
            if not os.path.exists(user_jvm_args_path):
                return {'success': False, 'error': f'user_jvm_args.txt not found: {user_jvm_args_path}'}
            
            if not os.path.exists(unix_args_path):
                return {'success': False, 'error': f'unix_args.txt not found: {unix_args_path}'}
            
            # Prepare the command using Forge launcher format
            cmd = [self.java_executable] + self.forge_startup_command
            
            self.logger.info(f"Starting Minecraft server in {self.server_path}")
            self.logger.info(f"Command: {' '.join(cmd)}")
            
            # Prepare log file paths
            log_file = os.path.join(self.server_path, 'logs', 'latest.log')
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            
            # Build the command string for shell execution
            cmd_str = ' '.join([f'"{arg}"' if ' ' in arg else arg for arg in ([self.java_executable] + self.forge_startup_command)])
            
            # Use bash to execute a completely detached process
            detach_cmd = f'bash -c "cd \\"{self.server_path}\\" && setsid nohup {cmd_str} >>logs/latest.log 2>&1 </dev/null & disown"'
            
            self.logger.info(f"Starting detached server: {detach_cmd}")
            
            # Execute with minimal connection to parent
            process = subprocess.Popen(
                detach_cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd='/'  # Change to root to avoid any path dependencies
            )
            
            # Don't wait for the subprocess - it should exit immediately after forking
            
            # Wait for the actual minecraft server to start
            time.sleep(5)
            
            # Find the newly started Minecraft process
            minecraft_proc = self._get_minecraft_process()
            
            if minecraft_proc:
                self.logger.info(f"Minecraft server started successfully with PID {minecraft_proc.pid}")
                
                # Clear the status cache
                _status_cache.clear()
                
                return {'success': True, 'message': f'Server started with PID {minecraft_proc.pid}'}
            else:
                # Check if there were any startup errors in the log
                try:
                    with open(log_file, 'r') as f:
                        recent_logs = f.read()[-1000:]  # Last 1000 chars
                        if 'Error' in recent_logs or 'Exception' in recent_logs:
                            error_msg = f"Server failed to start. Check logs: {recent_logs[-200:]}"
                        else:
                            error_msg = "Server process not found after startup attempt"
                except:
                    error_msg = "Server failed to start - unable to read startup logs"
                
                self.logger.error(error_msg)
                return {'success': False, 'error': error_msg}
                
        except FileNotFoundError as e:
            error_msg = f"Java executable not found: {self.java_executable}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Failed to start server: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {'success': False, 'error': error_msg}
    
    def stop_server(self):
        """Stop the Minecraft server process gracefully using RCON commands"""
        try:
            minecraft_proc = self._get_minecraft_process()
            
            if not minecraft_proc:
                return {'success': False, 'error': 'Server is not running'}
            
            pid = minecraft_proc.pid
            self.logger.info(f"Stopping Minecraft server (PID {pid}) using RCON")
            
            # Try to stop using RCON commands first
            try:
                from .rcon_client import RconClient
                from .server_properties import ServerPropertiesParser
                
                # Get RCON configuration
                server_props = ServerPropertiesParser()
                if server_props.load_properties():
                    rcon_port = int(server_props.get_property('rcon.port', '25575'))
                    rcon_password = server_props.get_property('rcon.password', '')
                    server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
                    
                    if rcon_password:
                        # Execute RCON stop sequence
                        with RconClient(server_host, rcon_port, rcon_password) as rcon:
                            self.logger.info("Executing RCON stop sequence")
                            rcon.command("save-off")
                            time.sleep(1)
                            rcon.command("save-all flush")
                            time.sleep(2)
                            rcon.command("stop")
                            
                        # Wait up to 30 seconds for graceful shutdown
                        for i in range(30):
                            if not minecraft_proc.is_running():
                                self.logger.info("Server stopped gracefully via RCON")
                                break
                            time.sleep(1)
                        else:
                            self.logger.warning("RCON stop timed out, falling back to SIGTERM")
                            minecraft_proc.terminate()
                            minecraft_proc.wait(timeout=10)
                    else:
                        self.logger.warning("No RCON password configured, using SIGTERM")
                        minecraft_proc.terminate()
                        minecraft_proc.wait(timeout=30)
                else:
                    self.logger.warning("Cannot read server.properties, using SIGTERM")
                    minecraft_proc.terminate()
                    minecraft_proc.wait(timeout=30)
                    
            except Exception as rcon_error:
                self.logger.warning(f"RCON stop failed: {rcon_error}, falling back to SIGTERM")
                minecraft_proc.terminate()
                
                # Wait up to 30 seconds for graceful shutdown
                try:
                    minecraft_proc.wait(timeout=30)
                    self.logger.info(f"Server stopped gracefully")
                except psutil.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    self.logger.warning("Graceful shutdown timed out, force killing")
                    minecraft_proc.kill()
                    minecraft_proc.wait(timeout=10)  # Wait for force kill
                    self.logger.info("Server force killed")
            
            # Clear cached process
            global _minecraft_process
            with _process_lock:
                _minecraft_process = None
            
            # Stop startup monitoring
            try:
                from .startup_monitor import get_startup_monitor
                startup_monitor = get_startup_monitor()
                startup_monitor.stop_monitoring()
                self.logger.info("Stopped startup monitoring")
            except Exception as e:
                self.logger.warning(f"Could not stop startup monitor: {e}")
            
            # Clear status cache
            _status_cache.clear()
            
            return {'success': True, 'message': f'Server stopped (was PID {pid})'}
            
        except psutil.NoSuchProcess:
            return {'success': False, 'error': 'Server process not found'}
        except Exception as e:
            error_msg = f"Failed to stop server: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {'success': False, 'error': error_msg}
    
    def restart_server(self):
        """Restart the Minecraft server"""
        try:
            # Stop the server first
            stop_result = self.stop_server()
            if not stop_result['success'] and 'not running' not in stop_result['error']:
                return stop_result
            
            # Wait a moment before starting
            time.sleep(3)
            
            # Start the server
            start_result = self.start_server()
            
            if start_result['success']:
                return {'success': True, 'message': 'Server restarted successfully'}
            else:
                return start_result
                
        except Exception as e:
            error_msg = f"Failed to restart server: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {'success': False, 'error': error_msg}
    
    def _format_uptime(self, seconds):
        """Format uptime in human readable format"""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            days = int(seconds / 86400)
            hours = int((seconds % 86400) / 3600)
            return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"

    # Compatibility methods for existing code
    def get_service_status(self):
        """Compatibility method - redirects to get_server_status"""
        return self.get_server_status()
    
    def control_service(self, action):
        """Compatibility method for service control"""
        if action == 'start':
            return self.start_server()
        elif action == 'stop':
            return self.stop_server()
        elif action == 'restart':
            return self.restart_server()
        else:
            return {'success': False, 'error': f'Unknown action: {action}'}