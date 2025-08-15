import subprocess
import psutil
import time
import re
from datetime import datetime, timedelta
from flask import current_app
import logging
from .server_properties import ServerPropertiesParser

# Global cache for status data
_status_cache = {}
_cache_duration = 5  # Cache for 5 seconds

class SystemControlService:
    """Service for managing systemd service and system operations"""
    
    def __init__(self, service_name):
        self.service_name = service_name
        self.logger = logging.getLogger(__name__)
    
    def get_service_status(self):
        """Get detailed service status from systemd with caching"""
        # Check cache first
        cache_key = f"status_{self.service_name}"
        now = time.time()
        
        if cache_key in _status_cache:
            cached_data, cache_time = _status_cache[cache_key]
            if now - cache_time < _cache_duration:
                self.logger.debug("Returning cached status")
                return cached_data
        
        try:
            # Get service status with reduced timeout
            result = subprocess.run(
                ['sudo', '/bin/systemctl', 'status', f'{self.service_name}.service'],
                capture_output=True,
                text=True,
                timeout=5  # Reduced from 10 to 5 seconds
            )
            
            status_info = {
                'running': False,
                'uptime': '0 minutes',
                'players': 0,
                'max_players': 20,
                'last_update': datetime.now().isoformat(),
                'memory_usage': 0,
                'cpu_usage': 0.0
            }
            
            # Parse systemctl status output
            if result.returncode == 0:
                output = result.stdout
                
                # Check if service is active
                if 'Active: active (running)' in output:
                    status_info['running'] = True
                    
                    # Extract uptime
                    uptime_match = re.search(r'Active: active \(running\) since (.+?);', output)
                    if uptime_match:
                        start_time_str = uptime_match.group(1).strip()
                        try:
                            # Parse the start time (format may vary)
                            start_time = datetime.strptime(start_time_str, '%a %Y-%m-%d %H:%M:%S %Z')
                            uptime_delta = datetime.now() - start_time
                            status_info['uptime'] = self._format_uptime(uptime_delta)
                        except ValueError:
                            # Try alternative format
                            try:
                                start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
                                uptime_delta = datetime.now() - start_time
                                status_info['uptime'] = self._format_uptime(uptime_delta)
                            except ValueError:
                                status_info['uptime'] = 'Unknown'
                    
                    # Extract PID and get process info
                    pid_match = re.search(r'Main PID: (\d+)', output)
                    if pid_match:
                        main_pid = int(pid_match.group(1))
                        try:
                            # Get memory and CPU usage (optimized)
                            process = psutil.Process(main_pid)
                            memory_info = process.memory_info()
                            status_info['memory_usage'] = memory_info.rss // (1024 * 1024)  # MB
                            status_info['cpu_usage'] = process.cpu_percent(interval=0.1)  # Quick sample
                            
                            # Get child processes (for Java process) - limit recursion
                            try:
                                children = process.children(recursive=False)  # Only direct children
                                for child in children[:5]:  # Limit to 5 children max
                                    if 'java' in child.name().lower():
                                        child_memory = child.memory_info()
                                        status_info['memory_usage'] += child_memory.rss // (1024 * 1024)
                                        status_info['cpu_usage'] += child.cpu_percent(interval=0.1)
                                        break  # Only check first Java process
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    
                    # Try to get player count from server logs if available
                    try:
                        player_info = self._get_player_count()
                        status_info.update(player_info)
                    except Exception as e:
                        self.logger.debug(f"Could not get player count: {e}")
            
            # Cache the result
            _status_cache[cache_key] = (status_info, now)
            return status_info
            
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout getting service status")
            # Get max players from server.properties
            try:
                server_props = ServerPropertiesParser()
                max_players = server_props.get_max_players()
            except Exception:
                max_players = 20
            return {'running': False, 'uptime': 'Unknown', 'players': 0, 'max_players': max_players}
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            # Get max players from server.properties
            try:
                server_props = ServerPropertiesParser()
                max_players = server_props.get_max_players()
            except Exception:
                max_players = 20
            return {'running': False, 'uptime': 'Error', 'players': 0, 'max_players': max_players}
    
    def start_service(self):
        """Start the systemd service"""
        try:
            result = subprocess.run(
                ['sudo', '/bin/systemctl', 'start', f'{self.service_name}.service'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.logger.info(f"Service {self.service_name} started successfully")
                return {'success': True, 'message': f'Service {self.service_name} started'}
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                self.logger.error(f"Failed to start service: {error_msg}")
                return {'success': False, 'error': f'Failed to start service: {error_msg}'}
                
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout starting service")
            return {'success': False, 'error': 'Service start timeout'}
        except Exception as e:
            self.logger.error(f"Error starting service: {e}")
            return {'success': False, 'error': str(e)}
    
    def stop_service(self):
        """Stop the systemd service"""
        try:
            result = subprocess.run(
                ['sudo', '/bin/systemctl', 'stop', f'{self.service_name}.service'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.logger.info(f"Service {self.service_name} stopped successfully")
                return {'success': True, 'message': f'Service {self.service_name} stopped'}
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                self.logger.error(f"Failed to stop service: {error_msg}")
                return {'success': False, 'error': f'Failed to stop service: {error_msg}'}
                
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout stopping service")
            return {'success': False, 'error': 'Service stop timeout'}
        except Exception as e:
            self.logger.error(f"Error stopping service: {e}")
            return {'success': False, 'error': str(e)}
    
    def restart_service(self):
        """Restart the systemd service"""
        try:
            result = subprocess.run(
                ['sudo', '/bin/systemctl', 'restart', f'{self.service_name}.service'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.logger.info(f"Service {self.service_name} restarted successfully")
                return {'success': True, 'message': f'Service {self.service_name} restarted'}
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                self.logger.error(f"Failed to restart service: {error_msg}")
                return {'success': False, 'error': f'Failed to restart service: {error_msg}'}
                
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout restarting service")
            return {'success': False, 'error': 'Service restart timeout'}
        except Exception as e:
            self.logger.error(f"Error restarting service: {e}")
            return {'success': False, 'error': str(e)}
    
    def _format_uptime(self, uptime_delta):
        """Format uptime delta to human readable string"""
        total_seconds = int(uptime_delta.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        if days > 0:
            return f"{days} days, {hours} hours"
        elif hours > 0:
            return f"{hours} hours, {minutes} minutes"
        else:
            return f"{minutes} minutes"
    
    def _get_player_count(self):
        """Get player count using mcstatus server query"""
        try:
            from mcstatus.server import JavaServer
            
            # Get server connection details from server.properties and config
            server_props = ServerPropertiesParser()
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            server_port = server_props.get_server_port()
            query_port = server_props.get_query_port()
            
            # Try server query first (most reliable)
            try:
                server = JavaServer.lookup(f"{server_host}:{query_port}")
                query = server.query()
                return {
                    'players': query.players.online,
                    'max_players': query.players.max,
                    'player_names': query.players.names if hasattr(query.players, 'names') else []
                }
            except Exception as query_error:
                self.logger.debug(f"Query failed, trying status ping: {query_error}")
                
                # Fallback to status ping
                server = JavaServer.lookup(f"{server_host}:{server_port}")
                status = server.status()
                return {
                    'players': status.players.online,
                    'max_players': status.players.max,
                    'player_names': []
                }
                
        except Exception as e:
            self.logger.debug(f"Could not get player count via mcstatus: {e}")
            # Final fallback - try old method
            return self._get_player_count_fallback()
    
    def _get_player_count_fallback(self):
        """Fallback method using server.properties"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {'players': 0, 'max_players': 20, 'player_names': []}
            
            max_players = 20
            # Try to find server.properties for max players
            try:
                props_result = subprocess.run(
                    ['grep', 'max-players', f"{server_path}/server.properties"],
                    capture_output=True,
                    text=True,
                    timeout=2  # Reduced timeout for file operation
                )
                if props_result.returncode == 0:
                    match = re.search(r'max-players=(\d+)', props_result.stdout)
                    if match:
                        max_players = int(match.group(1))
            except:
                pass
            
            return {'players': 0, 'max_players': max_players, 'player_names': []}
            
        except Exception as e:
            self.logger.debug(f"Fallback player count failed: {e}")
        
        return {'players': 0, 'max_players': 20, 'player_names': []}