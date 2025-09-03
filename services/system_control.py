import subprocess
import psutil
import time
import re
import os
import signal
import threading
from datetime import datetime, timedelta
from flask import current_app, has_app_context
import logging
from .server_properties import ServerPropertiesParser

# Global cache for status data
_status_cache = {}
_cache_duration = 5  # Cache for 5 seconds

# Global process tracking and background monitoring
_minecraft_process = None
_minecraft_pid = None
_cached_cpu_usage = 0.0
_cached_memory_usage = 0
_last_cpu_update = 0
_cpu_monitor_thread = None
_monitor_running = False
_process_lock = threading.Lock()

def start_cpu_monitoring():
    """Start background thread for CPU monitoring with 5-second interval"""
    global _cpu_monitor_thread, _monitor_running
    
    if _monitor_running:
        return  # Already running
    
    def monitor_loop():
        global _minecraft_pid, _cached_cpu_usage, _cached_memory_usage, _last_cpu_update, _monitor_running
        
        logger = logging.getLogger(__name__)
        logger.info("Starting CPU monitoring thread with 5-second interval")
        _monitor_running = True
        
        while _monitor_running:
            try:
                if _minecraft_pid:
                    try:
                        proc = psutil.Process(_minecraft_pid)
                        if proc.is_running():
                            # 5-second blocking measurement - this happens in background
                            _cached_cpu_usage = proc.cpu_percent(interval=5.0)
                            _cached_memory_usage = round(proc.memory_info().rss / 1024 / 1024)  # MB
                            _last_cpu_update = time.time()
                            logger.debug(f"Updated CPU: {_cached_cpu_usage:.1f}%, Memory: {_cached_memory_usage}MB")
                        else:
                            # Process died, clear cache
                            logger.info(f"Minecraft process PID {_minecraft_pid} no longer running")
                            _minecraft_pid = None
                            _cached_cpu_usage = 0.0
                            _cached_memory_usage = 0
                    except psutil.NoSuchProcess:
                        logger.info(f"Minecraft process PID {_minecraft_pid} not found")
                        _minecraft_pid = None
                        _cached_cpu_usage = 0.0
                        _cached_memory_usage = 0
                else:
                    # Search for new process
                    new_pid = _find_minecraft_pid_lightweight()
                    if new_pid:
                        logger.info(f"Found new Minecraft process: PID {new_pid}")
                        _minecraft_pid = new_pid
                        # Prime the CPU measurement (first call returns 0)
                        try:
                            proc = psutil.Process(_minecraft_pid)
                            proc.cpu_percent()  # Prime for next measurement
                        except:
                            pass
                    else:
                        # No process found, sleep and continue
                        time.sleep(5.0)
                        
            except Exception as e:
                logger.error(f"CPU monitoring error: {e}")
                time.sleep(5.0)
    
    _cpu_monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="CPUMonitor")
    _cpu_monitor_thread.start()

def stop_cpu_monitoring():
    """Stop the background CPU monitoring thread"""
    global _monitor_running, _cpu_monitor_thread
    _monitor_running = False
    if _cpu_monitor_thread:
        _cpu_monitor_thread = None

def _find_minecraft_pid_lightweight():
    """Lightweight PID search - returns PID only"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.debug("Starting process search for Minecraft server")
        java_procs_found = 0
        minecraft_candidates = []
        
        # Use pids() for faster iteration than process_iter()
        for pid in psutil.pids():
            try:
                proc = psutil.Process(pid)
                cmdline = proc.cmdline()
                name = proc.name()
                
                if not cmdline:
                    continue
                
                # Count all java processes for debugging
                if name == 'java':
                    java_procs_found += 1
                    logger.debug(f"Found Java process PID {pid}: {' '.join(cmdline[:3])}...")
                
                # Look for Java process with Forge arguments
                if (any('java' in arg.lower() for arg in cmdline) and
                    (any('user_jvm_args.txt' in arg for arg in cmdline) or
                     any('unix_args.txt' in arg for arg in cmdline) or
                     any('forge' in arg.lower() for arg in cmdline))):
                    
                    minecraft_candidates.append(pid)
                    logger.debug(f"Minecraft candidate found: PID {pid}, name={name}")
                    
                    # Prioritize actual java processes
                    if name == 'java':
                        logger.info(f"Found Minecraft server: PID {pid}")
                        return pid
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        logger.warning(f"Process search complete: {java_procs_found} Java processes found, {len(minecraft_candidates)} candidates, no match")
        return None
        
    except Exception as e:
        logger.error(f"Exception in process search: {e}")
        return None

class SystemControlService:
    """Service for managing Minecraft server process directly"""
    
    def __init__(self, server_name=None):
        self.server_name = server_name or "minecraft"
        self.logger = logging.getLogger(__name__)
        self.server_path = None
        self.java_executable = None
        self.server_jar = None
        # Player name cache for normalization
        self.player_name_cache = {}
        self._initialize_server_config()
        
        # Start CPU monitoring if not already running
        start_cpu_monitoring()
    
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
        """Get detailed server status using cached CPU/memory data"""
        global _minecraft_pid, _cached_cpu_usage, _cached_memory_usage, _last_cpu_update
        
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
                'max_players': "?",
                'last_update': datetime.now().isoformat(),
                'memory_usage': 0,
                'cpu_usage': 0.0,
                'pid': None,
                'server_ready': False
            }
            
            # Use cached PID instead of expensive process search
            if _minecraft_pid:
                try:
                    proc = psutil.Process(_minecraft_pid)
                    if proc.is_running():
                        status_info['running'] = True
                        status_info['pid'] = _minecraft_pid
                        
                        # Use cached CPU and memory values from background thread
                        status_info['cpu_usage'] = _cached_cpu_usage
                        status_info['memory_usage'] = _cached_memory_usage
                        
                        # Calculate uptime (this is lightweight)
                        create_time = datetime.fromtimestamp(proc.create_time())
                        uptime_seconds = (datetime.now() - create_time).total_seconds()
                        status_info['uptime'] = self._format_uptime(uptime_seconds)
                        
                    else:
                        # Process died, clear cached PID
                        _minecraft_pid = None
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process died, clear cached PID
                    _minecraft_pid = None
                
                # Always get max_players from server.properties first
                try:
                    server_props = ServerPropertiesParser()
                    if server_props.load_properties():
                        status_info['max_players'] = server_props.get_max_players()
                    else:
                        status_info['max_players'] = "?"  # Show ? if server.properties can't be read
                except Exception:
                    status_info['max_players'] = "?"  # Show ? if server.properties can't be read
                
                # Check if server is ready for connections using mcstatus
                server_ready = False
                
                try:
                    from mcstatus import JavaServer
                    import concurrent.futures
                    
                    server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
                    server_port = current_app.config.get('MINECRAFT_SERVER_PORT', 25565)
                    
                    server = JavaServer(server_host, server_port)
                    
                    # Use ThreadPoolExecutor with timeout to prevent hanging
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(server.status)
                        query_status = future.result(timeout=3)  # 3 second timeout
                    
                    if query_status:
                        server_ready = True
                        status_info['players'] = query_status.players.online
                        
                        # Collect player names from mcstatus
                        player_names = []
                        if query_status.players.sample:
                            for player in query_status.players.sample:
                                player_names.append(player.name)
                        
                        status_info['player_names'] = player_names
                        status_info['server_ready'] = True
                        status_info['status'] = 'running'
                        
                        player_list_str = ", ".join(player_names) if player_names else "none"
                        self.logger.info(f"mcstatus connected successfully - {query_status.players.online}/{status_info['max_players']} players ({player_list_str})")
                        
                except (Exception, concurrent.futures.TimeoutError) as e:
                    self.logger.warning(f"mcstatus connection to {server_host}:{server_port} failed: {type(e).__name__}: {e}")
                
                if not server_ready and status_info['running']:
                    # Show "?" for online players when mcstatus fails
                    status_info['players'] = "?"
                    status_info['player_names'] = []
                    
                    # Check process uptime to distinguish between starting vs connection issues
                    try:
                        proc = psutil.Process(_minecraft_pid)
                        create_time = datetime.fromtimestamp(proc.create_time())
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
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # Process check failed, assume stopped
                        status_info['running'] = False
                        status_info['status'] = 'stopped'
            
            # Set status based on process state
            if not status_info['running']:
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
                'max_players': "?",
                'last_update': datetime.now().isoformat(),
                'memory_usage': 0,
                'cpu_usage': 0.0,
                'pid': None,
                'server_ready': False,
                'error': str(e)
            }
    
    def _get_minecraft_process(self):
        """Get Minecraft process using cached PID (legacy compatibility)"""
        global _minecraft_pid, _minecraft_process
        
        with _process_lock:
            if _minecraft_pid:
                try:
                    proc = psutil.Process(_minecraft_pid)
                    if proc.is_running():
                        _minecraft_process = proc
                        return proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Fallback to process search if no cached PID
            new_pid = _find_minecraft_pid_lightweight()
            if new_pid:
                _minecraft_pid = new_pid
                _minecraft_process = psutil.Process(new_pid)
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
                server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
                server_port = current_app.config.get('MINECRAFT_SERVER_PORT', 25565)
                startup_monitor = get_startup_monitor()
                startup_monitor.server_host = server_host
                startup_monitor.server_port = server_port
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
            
            # Use systemd-run for proper process isolation from web manager service
            detach_cmd = f'systemd-run --user --scope --slice=minecraft.slice --property=KillMode=none -- bash -c "cd \\"{self.server_path}\\" && {cmd_str} >>logs/latest.log 2>&1"'
            
            self.logger.info(f"Starting detached server with systemd-run: {detach_cmd}")
            
            # Execute with complete isolation from web manager service
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
                global _minecraft_pid
                _minecraft_pid = minecraft_proc.pid
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
            
            # Clear cached process and PID
            global _minecraft_process, _minecraft_pid
            with _process_lock:
                _minecraft_process = None
                _minecraft_pid = None
            
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

    def _normalize_player_name(self, display_name: str) -> str:
        """Normalize player names to handle achievement titles (cached version)"""
        if display_name in self.player_name_cache:
            return self.player_name_cache[display_name]
        
        # Simple normalization - remove common title patterns
        # "Slayer MadSavage69 of the Ancients" -> "MadSavage69"
        title_patterns = [
            r'^[A-Za-z\s]+ ([A-Za-z0-9_]+) of the .+$',  # "Title Name of the Something"
            r'^[A-Za-z\s]+ ([A-Za-z0-9_]+)$',            # "Title Name"
        ]
        
        for pattern in title_patterns:
            match = re.match(pattern, display_name)
            if match:
                base_name = match.group(1)
                self.player_name_cache[display_name] = base_name
                return base_name
        
        # If no pattern matches, assume it's already a base name
        self.player_name_cache[display_name] = display_name
        return display_name
    
    def get_current_online_players(self):
        """Get current online players from the server (simplified for display only)"""
        try:
            player_status = self._collect_player_status_via_mcstatus()
            if player_status['success']:
                return player_status.get('players', [])
            else:
                return []
        except Exception as e:
            self.logger.warning(f'Failed to get current online players: {e}')
            return []
    
    def _collect_player_status_via_mcstatus(self):
        """Collect current player status using mcstatus (simplified - no database updates)"""
        # Always get max_players from server.properties first
        try:
            server_props = ServerPropertiesParser()
            if server_props.load_properties():
                max_players = server_props.get_max_players()
            else:
                max_players = "?"  # Show ? if server.properties can't be read
        except Exception:
            max_players = "?"  # Show ? if server.properties can't be read
        
        try:
            from mcstatus import JavaServer
            import concurrent.futures
            
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            server_port = current_app.config.get('MINECRAFT_SERVER_PORT', 25565)
            
            server = JavaServer(server_host, server_port)
            
            # Use ThreadPoolExecutor with timeout to prevent hanging
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(server.status)
                status_result = future.result(timeout=3)  # 3 second timeout
            
            # Get current online players from status (sample)
            current_players = []
            if status_result and status_result.players.sample:
                current_players = [player.name for player in status_result.players.sample]
            
            normalized_players = [self._normalize_player_name(name) for name in current_players]
            
            return {
                'success': True,
                'player_count': status_result.players.online if status_result else "?",
                'max_players': max_players,
                'players': normalized_players
            }
            
        except (Exception, concurrent.futures.TimeoutError) as e:
            self.logger.warning(f'Failed to collect player status via mcstatus: {e}')
            return {
                'success': False,
                'error': str(e),
                'player_count': "?",
                'max_players': max_players,
                'players': []
            }
    
    def _get_rcon_port(self) -> int:
        """Get RCON port from server.properties or config"""
        try:
            # Try config first
            config_rcon_port = current_app.config.get('RCON_PORT')
            if config_rcon_port:
                return int(config_rcon_port)
            
            # Try reading from server.properties
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if server_path:
                props_file = os.path.join(server_path, 'server.properties')
                if os.path.exists(props_file):
                    with open(props_file, 'r') as f:
                        for line in f:
                            if line.startswith('rcon.port='):
                                return int(line.split('=')[1].strip())
            
            return 25575  # Default RCON port
        except Exception:
            return 25575  # Default RCON port
    
    def _get_rcon_password(self) -> str:
        """Get RCON password from server.properties"""
        try:
            # Try config first (though it's usually not stored there for security)
            config_password = current_app.config.get('RCON_PASSWORD')
            if config_password:
                return config_password
            
            # Read from server.properties
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if server_path:
                props_file = os.path.join(server_path, 'server.properties')
                if os.path.exists(props_file):
                    with open(props_file, 'r') as f:
                        for line in f:
                            if line.startswith('rcon.password='):
                                password = line.split('=', 1)[1].strip()
                                return password if password else ''
            
            return ''
        except Exception:
            return ''

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