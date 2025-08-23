from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, session
from flask_wtf import FlaskForm
import secrets
import hmac
import hashlib
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length
from services.system_control import SystemControlService
from services.log_service import LogService
from services.config_manager import ConfigManager
from services.backup_manager import BackupManager
from services.server_properties import ServerPropertiesParser
from services.log_watcher import get_log_watcher
import os
import logging
import subprocess
import json
import time
import sqlite3
from datetime import datetime

def _execute_rcon_server_control(action):
    """Execute server control via RCON commands"""
    try:
        # Get server connection details from server.properties
        server_props = ServerPropertiesParser()
        
        if not server_props.load_properties():
            return {
                'success': False,
                'error': 'Could not load server.properties file'
            }
        
        if not server_props.is_rcon_enabled():
            return {
                'success': False,
                'error': 'RCON is not enabled in server.properties (enable-rcon=true required)'
            }
        
        server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
        rcon_port = server_props.get_rcon_port()
        rcon_password = server_props.get_rcon_password()
        
        if not rcon_password:
            return {
                'success': False,
                'error': 'RCON password not set in server.properties'
            }
        
        from services.rcon_client import execute_rcon_command
        
        if action == 'stop':
            # Execute safe shutdown sequence via RCON (save first, then stop)
            try:
                # Step 1: Disable auto-save
                success1, response1 = execute_rcon_command(server_host, rcon_port, rcon_password, 'save-off')
                if not success1:
                    current_app.logger.warning(f'save-off command failed: {response1}')
                
                # Step 2: Force save all chunks  
                import time
                time.sleep(1)
                success2, response2 = execute_rcon_command(server_host, rcon_port, rcon_password, 'save-all flush')
                if not success2:
                    current_app.logger.warning(f'save-all flush command failed: {response2}')
                
                # Step 3: Stop the server
                time.sleep(2)
                success3, response3 = execute_rcon_command(server_host, rcon_port, rcon_password, 'stop')
                
                if success3:
                    return {
                        'success': True,
                        'message': 'Server shutdown sequence completed (save-off → save-all flush → stop)',
                        'rcon_command': 'save-off; save-all flush; stop',
                        'rcon_response': f'save-off: {response1 or "OK"} | save-all: {response2 or "OK"} | stop: {response3 or "OK"}'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'RCON stop command failed: {response3}'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'RCON shutdown sequence failed: {str(e)}'
                }
                
        elif action == 'restart':
            # Execute safe shutdown sequence via RCON, then start
            try:
                # Step 1: Disable auto-save
                success1, response1 = execute_rcon_command(server_host, rcon_port, rcon_password, 'save-off')
                if not success1:
                    current_app.logger.warning(f'save-off command failed during restart: {response1}')
                
                # Step 2: Force save all chunks  
                import time
                time.sleep(1)
                success2, response2 = execute_rcon_command(server_host, rcon_port, rcon_password, 'save-all flush')
                if not success2:
                    current_app.logger.warning(f'save-all flush command failed during restart: {response2}')
                
                # Step 3: Stop the server
                time.sleep(2)
                success3, response3 = execute_rcon_command(server_host, rcon_port, rcon_password, 'stop')
                
                if success3:
                    # Wait a moment for server to shut down
                    time.sleep(3)
                    
                    # Then start using system control
                    system_control = SystemControlService()
                    start_result = system_control.start_server()
                    
                    return {
                        'success': start_result['success'],
                        'message': f"Server restart: Safe shutdown completed (save-off → save-all flush → stop), start {'successful' if start_result['success'] else 'failed'}",
                        'rcon_command': 'save-off; save-all flush; stop',
                        'rcon_response': f'save-off: {response1 or "OK"} | save-all: {response2 or "OK"} | stop: {response3 or "OK"}',
                        'start_result': start_result
                    }
                else:
                    return {
                        'success': False,
                        'error': f'RCON stop command failed during restart: {response3}'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'RCON restart sequence failed: {str(e)}'
                }
                
        elif action == 'save':
            # Execute save-all flush command via RCON
            success, response = execute_rcon_command(server_host, rcon_port, rcon_password, 'save-all flush')
            if success:
                return {
                    'success': True,
                    'message': 'World save command sent via RCON',
                    'rcon_command': 'save-all flush',
                    'rcon_response': response
                }
            else:
                return {
                    'success': False,
                    'error': f'RCON save command failed: {response}'
                }
        
        return {'success': False, 'error': 'Unknown action'}
        
    except Exception as e:
        current_app.logger.error(f'RCON server control failed: {e}')
        return {
            'success': False,
            'error': str(e)
        }

# Create blueprint
main_bp = Blueprint('main', __name__)

# Simple CSRF token functions
def generate_csrf_token():
    """Generate a simple CSRF token"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']

def validate_csrf_token(token):
    """Validate CSRF token"""
    if not token:
        return False
    session_token = session.get('csrf_token')
    if not session_token:
        return False
    return hmac.compare_digest(session_token, token)

class ServerControlForm(FlaskForm):
    action = StringField('Action', validators=[DataRequired()])
    submit = SubmitField('Execute')

class ConfigEditForm(FlaskForm):
    config_file = SelectField('Configuration File', choices=[])
    content = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Save Configuration')

# Monitoring helper functions
def get_tps_data():
    """Get TPS data via RCON command"""
    try:
        from services.rcon_client import execute_rcon_command
        from services.server_properties import ServerPropertiesParser
        
        # Get RCON configuration
        server_props = ServerPropertiesParser()
        if not server_props.load_properties() or not server_props.is_rcon_enabled():
            return {'tps': None, 'error': 'RCON not available'}
        
        server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
        rcon_port = server_props.get_rcon_port()
        rcon_password = server_props.get_rcon_password()
        
        if not rcon_password:
            return {'tps': None, 'error': 'RCON password not set'}
        
        # Execute forge tps command
        success, response = execute_rcon_command(server_host, rcon_port, rcon_password, 'forge tps')
        
        if success and response:
            # Parse TPS from response like "Overall: Mean tick time: 45.123 ms. Mean TPS: 20.0"
            import re
            tps_match = re.search(r'Mean TPS:\s*([0-9.]+)', response)
            if tps_match:
                tps = float(tps_match.group(1))
                return {'tps': tps, 'response': response}
        
        return {'tps': None, 'error': f'Failed to parse TPS: {response}'}
        
    except Exception as e:
        current_app.logger.error(f'TPS monitoring error: {e}')
        return {'tps': None, 'error': str(e)}

def get_recent_performance_events():
    """Get recent performance events from system monitoring"""
    try:
        events = []
        
        # Check server status for events
        try:
            system_control = SystemControlService()
            status = system_control.get_server_status()
            
            # Add server status events
            if status.get('running'):
                if status.get('status') == 'starting':
                    events.append({
                        'type': 'Server Status',
                        'message': 'Server is starting up',
                        'timestamp': datetime.now().isoformat(),
                        'severity': 'info'
                    })
                elif status.get('server_ready'):
                    uptime_minutes = 0
                    uptime_str = status.get('uptime', '0 minutes')
                    if 'minute' in uptime_str:
                        uptime_minutes = int(uptime_str.split()[0]) if uptime_str.split()[0].isdigit() else 0
                    
                    if uptime_minutes < 5:
                        events.append({
                            'type': 'Server Start',
                            'message': f'Server started successfully (uptime: {uptime_str})',
                            'timestamp': datetime.now().isoformat(),
                            'severity': 'success'
                        })
                
                # Memory usage events
                memory_mb = status.get('memory_usage', 0)
                if memory_mb > 20000:  # > 20GB
                    events.append({
                        'type': 'High Memory Usage',
                        'message': f'Memory usage: {memory_mb/1024:.1f}GB',
                        'timestamp': datetime.now().isoformat(),
                        'severity': 'warning'
                    })
                
                # CPU usage events
                cpu_usage = status.get('cpu_usage', 0)
                if cpu_usage > 80:
                    events.append({
                        'type': 'High CPU Usage',
                        'message': f'CPU usage: {cpu_usage:.1f}%',
                        'timestamp': datetime.now().isoformat(),
                        'severity': 'warning'
                    })
            else:
                events.append({
                    'type': 'Server Status',
                    'message': 'Server is offline',
                    'timestamp': datetime.now().isoformat(),
                    'severity': 'error'
                })
        except Exception as e:
            current_app.logger.warning(f'Status check failed: {e}')
        
        # Get TPS events
        try:
            tps_data = get_tps_data()
            if tps_data.get('tps') is not None:
                tps = tps_data['tps']
                if tps < 15:
                    events.append({
                        'type': 'Poor Performance',
                        'message': f'TPS dropped to {tps:.1f}',
                        'timestamp': datetime.now().isoformat(),
                        'severity': 'warning'
                    })
                elif tps < 18:
                    events.append({
                        'type': 'TPS Monitoring',
                        'message': f'TPS slightly low: {tps:.1f}',
                        'timestamp': datetime.now().isoformat(),
                        'severity': 'info'
                    })
                else:
                    events.append({
                        'type': 'Performance',
                        'message': f'TPS healthy: {tps:.1f}',
                        'timestamp': datetime.now().isoformat(),
                        'severity': 'success'
                    })
        except Exception as e:
            current_app.logger.warning(f'TPS check failed: {e}')
        
        # If no events, add a default monitoring message
        if not events:
            events.append({
                'type': 'Monitoring',
                'message': 'System monitoring active',
                'timestamp': datetime.now().isoformat(),
                'severity': 'info'
            })
        
        return events[:5]  # Return last 5 events
    except Exception as e:
        current_app.logger.error(f'Performance events error: {e}')
        return [{
            'type': 'Error',
            'message': 'Failed to get performance events',
            'timestamp': datetime.now().isoformat(),
            'severity': 'error'
        }]

@main_bp.route('/')
def index():
    """Main dashboard - lightweight initial load"""
    try:
        # Generate CSRF token for the session
        csrf_token = generate_csrf_token()
        return render_template('index.html', csrf_token=csrf_token)
    except Exception as e:
        current_app.logger.error(f'Dashboard error: {e}')
        flash('Error loading dashboard', 'error')
        return render_template('index.html')

@main_bp.route('/server/status')
def server_status():
    """API endpoint for server status"""
    try:
        # Use new direct process management (service_name parameter is optional now)
        system_control = SystemControlService()
        status = system_control.get_service_status()
        return jsonify(status)
    except Exception as e:
        current_app.logger.error(f'Server status error: {e}')
        return jsonify({'error': 'Failed to get server status'}), 500

@main_bp.route('/system/info')
def system_info():
    """API endpoint for system version information"""
    try:
        versions = {}
        
        # Get Java version
        try:
            java_cmd = current_app.config.get('JAVA_EXECUTABLE', 'java')
            result = subprocess.run([java_cmd, '-version'], 
                                 capture_output=True, text=True, timeout=10)
            java_output = result.stderr  # Java version goes to stderr
            if java_output:
                # Parse Java version from output
                lines = java_output.strip().split('\n')
                if lines:
                    # Extract version from first line (e.g., "openjdk version "17.0.2" 2022-01-18")
                    first_line = lines[0]
                    if 'openjdk version' in first_line.lower():
                        versions['java'] = 'OpenJDK ' + first_line.split('"')[1] if '"' in first_line else 'OpenJDK (version unknown)'
                    elif 'java version' in first_line.lower():
                        versions['java'] = 'Oracle JDK ' + first_line.split('"')[1] if '"' in first_line else 'Oracle JDK (version unknown)'
                    else:
                        versions['java'] = first_line.strip()
                else:
                    versions['java'] = 'Unknown'
            else:
                versions['java'] = 'Unknown'
        except Exception as e:
            current_app.logger.warning(f'Failed to get Java version: {e}')
            versions['java'] = 'Unknown'
        
        # Get VaultHunters version from server data
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
            data_json_path = os.path.join(server_path, 'data', 'the_vault', 'data.json')
            if os.path.exists(data_json_path):
                with open(data_json_path, 'r') as f:
                    data = json.load(f)
                    versions['vaulthunters'] = data.get('version', 'Unknown')
            else:
                versions['vaulthunters'] = 'Not found'
        except Exception as e:
            current_app.logger.warning(f'Failed to get VaultHunters version: {e}')
            versions['vaulthunters'] = 'Unknown'
        
        # Get Linux kernel version
        try:
            result = subprocess.run(['uname', '-r'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                versions['kernel'] = result.stdout.strip()
            else:
                versions['kernel'] = 'Unknown'
        except Exception as e:
            current_app.logger.warning(f'Failed to get kernel version: {e}')
            versions['kernel'] = 'Unknown'
        
        # Get Python version
        try:
            result = subprocess.run(['python3', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                versions['python'] = result.stdout.strip().replace('Python ', '')
            else:
                versions['python'] = 'Unknown'
        except Exception as e:
            current_app.logger.warning(f'Failed to get Python version: {e}')
            versions['python'] = 'Unknown'
        
        return jsonify(versions)
    except Exception as e:
        current_app.logger.error(f'System info error: {e}')
        return jsonify({'error': 'Failed to get system info'}), 500

@main_bp.route('/monitoring')
def monitoring():
    """Monitoring page with charts and metrics"""
    try:
        csrf_token = generate_csrf_token()
        return render_template('monitoring.html', csrf_token=csrf_token)
    except Exception as e:
        current_app.logger.error(f'Monitoring page error: {e}')
        flash('Error loading monitoring page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/api/monitoring/metrics')
def monitoring_metrics():
    """API endpoint for monitoring metrics"""
    # Simple test to verify the route works
    current_app.logger.info('=== MONITORING METRICS API CALLED ===')
    
    # Get system memory data (not just Minecraft process)
    system_memory = {'used_gb': 0, 'total_gb': 0, 'percent': 0}
    try:
        import psutil
        memory = psutil.virtual_memory()
        system_memory = {
            'used_gb': round(memory.used / (1024**3), 1),
            'total_gb': round(memory.total / (1024**3), 1),
            'percent': memory.percent
        }
        current_app.logger.info(f'System memory: {system_memory["used_gb"]}GB / {system_memory["total_gb"]}GB ({system_memory["percent"]}%)')
    except Exception as e:
        current_app.logger.warning(f'Failed to get system memory: {e}')
    
    # Get real CPU data (carefully, non-blocking)
    cpu_system_avg = 15.5  # Default
    cpu_count = 4  # Safe default if detection fails
    cpu_per_core = []  # Will be populated based on actual detection
    
    try:
        import psutil
        # Always get actual core count first
        cpu_count = psutil.cpu_count()
        
        # Non-blocking calls (interval=None means use cached data from previous call)
        cpu_system_avg = psutil.cpu_percent(interval=None)
        cpu_per_core = psutil.cpu_percent(percpu=True, interval=None)
        
        # Ensure per-core list matches actual core count
        if len(cpu_per_core) != cpu_count:
            current_app.logger.warning(f'Core count mismatch: detected {cpu_count} but got {len(cpu_per_core)} usage values')
            cpu_per_core = [cpu_system_avg] * cpu_count  # Use average for all cores as fallback
        
        current_app.logger.info(f'Real CPU: {cpu_count} cores, avg: {cpu_system_avg}%, per-core samples: {len(cpu_per_core)}')
    except Exception as e:
        current_app.logger.warning(f'CPU monitoring failed, using defaults: {e}')
        # Create default per-core data based on detected or fallback core count
        cpu_per_core = [cpu_system_avg] * cpu_count
    
    # Get performance events (simplified to avoid blocking)
    events = [{
        'type': 'Monitoring',
        'message': 'System monitoring active',
        'timestamp': datetime.now().isoformat(),
        'severity': 'info'
    }]
    
    # Get system load average
    system_load = 0.5  # Default
    try:
        load_avg = os.getloadavg()
        system_load = load_avg[0]  # 1-minute load average
        current_app.logger.info(f'System load: {system_load} (1min: {load_avg[0]}, 5min: {load_avg[1]}, 15min: {load_avg[2]})')
    except Exception as e:
        current_app.logger.warning(f'Failed to get system load: {e}')
    
    # Get detailed memory information
    detailed_memory = {}
    try:
        import psutil
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        detailed_memory = {
            'used_mb': round(memory.used / (1024**2)),
            'buffers_mb': round(memory.buffers / (1024**2)) if hasattr(memory, 'buffers') else 0,
            'cache_mb': round(memory.cached / (1024**2)) if hasattr(memory, 'cached') else 0,
            'swap_used_mb': round(swap.used / (1024**2)),
            'swap_free_mb': round(swap.free / (1024**2)),
            'total_mb': round(memory.total / (1024**2)),
            'used_gb': round(memory.used / (1024**3), 1),
            'total_gb': round(memory.total / (1024**3), 1),
            'percent': memory.percent
        }
    except Exception as e:
        current_app.logger.warning(f'Failed to get detailed memory: {e}')
        detailed_memory = system_memory  # Fallback to basic memory
    
    # Get Java process memory and player data from our 3-second metrics collection (super fast)
    java_memory_mb = 0
    player_data = {'count': 0, 'max': 20, 'names': []}
    try:
        system_control = SystemControlService()
        minecraft_proc = system_control._get_minecraft_process()
        
        if minecraft_proc and minecraft_proc.is_running():
            # Get process memory
            try:
                proc_info = minecraft_proc.as_dict(attrs=['memory_info'])
                if proc_info['memory_info']:
                    java_memory_mb = round(proc_info['memory_info'].rss / 1024 / 1024)
            except Exception:
                pass
            
            # Get player data from our fast 3-second metrics collection (no mcstatus call needed)
            try:
                from services.metrics_storage import metrics_storage
                import sqlite3
                
                with sqlite3.connect(metrics_storage.db_path) as conn:
                    cursor = conn.cursor()
                    # Get latest player count metric
                    cursor.execute('''
                        SELECT value, metadata FROM metrics 
                        WHERE metric_type = 'player_count' 
                        ORDER BY timestamp DESC LIMIT 1
                    ''')
                    row = cursor.fetchone()
                    if row:
                        import json
                        player_count, metadata_json = row
                        metadata = json.loads(metadata_json or '{}')
                        
                        player_data['count'] = int(player_count)
                        player_data['max'] = metadata.get('max_players', 20)
                        player_data['names'] = metadata.get('player_names', [])
                        
            except Exception as e:
                current_app.logger.warning(f'Failed to get player data from metrics: {e}')
                # Fallback to empty data
                
        current_app.logger.info(f'Java memory: {java_memory_mb}MB, Players: {player_data["count"]}/{player_data["max"]}')
    except Exception as e:
        current_app.logger.warning(f'Failed to get server status: {e}')
    
    # Get simplified player status (optimized for API performance)
    player_status_data = {'online_players': [], 'offline_players': [], 'unique_players': [], 'total_online': 0}
    try:
        from services.metrics_storage import metrics_storage
        import sqlite3
        
        # Optimized query to get only unique players with their latest session
        with sqlite3.connect(metrics_storage.db_path) as conn:
            cursor = conn.cursor()
            # Get latest session for each unique player (handles ties properly)
            cursor.execute('''
                SELECT username, login_time, logout_time, is_online
                FROM (
                    SELECT username, login_time, logout_time, is_online,
                           ROW_NUMBER() OVER (PARTITION BY username ORDER BY login_time DESC, id DESC) as rn
                    FROM players
                ) ranked
                WHERE rn = 1
                ORDER BY login_time DESC
                LIMIT 50
            ''')
            
            unique_players = []
            total_online = 0
            for row in cursor.fetchall():
                username, login_time_str, logout_time_str, is_online = row
                player_info = {
                    'username': username,
                    'login_time': login_time_str,
                    'logout_time': logout_time_str,
                    'is_online': bool(is_online)
                }
                unique_players.append(player_info)
                if is_online:
                    total_online += 1
            
            player_status_data = {
                'online_players': [p for p in unique_players if p['is_online']],
                'offline_players': [p for p in unique_players if not p['is_online']],
                'unique_players': unique_players,
                'total_online': total_online
            }
        
        current_app.logger.info(f'Player status (optimized): {player_status_data["total_online"]} online, {len(player_status_data["unique_players"])} unique players')
    except Exception as e:
        current_app.logger.warning(f'Failed to get player status: {e}')
    
    # Get hardware temperature data
    temperature_data = {}
    try:
        from services.temperature_monitor import get_temperature_monitor
        temp_monitor = get_temperature_monitor()
        temperature_data = temp_monitor.get_temperature_summary()
        current_app.logger.info(f'Temperature readings: CPU={temperature_data.get("temperatures", {}).get("cpu", "N/A")}°C, '
                              f'GPU={temperature_data.get("temperatures", {}).get("gpu", "N/A")}°C, '
                              f'NVMe={temperature_data.get("temperatures", {}).get("nvme", "N/A")}°C')
    except Exception as e:
        current_app.logger.warning(f'Failed to get temperature data: {e}')
        temperature_data = {
            'temperatures': {},
            'alerts': [],
            'status': 'error',
            'error': str(e)
        }
    
    # Get real TPS and tick time data from metrics storage
    current_tps = 20.0  # Default fallback
    current_tick_time = 50.0  # Default fallback (50ms = 20 TPS)
    try:
        from services.metrics_storage import metrics_storage
        latest_tps = metrics_storage.get_latest_metric('server_tps')
        latest_tick_time = metrics_storage.get_latest_metric('server_tick_time')
        
        if latest_tps and latest_tps.get('value') is not None:
            # Only use real data if it's not a placeholder
            metadata = latest_tps.get('metadata', {})
            if metadata.get('source') != 'placeholder_rcon_failed' and metadata.get('source') != 'placeholder_rcon_error':
                current_tps = latest_tps['value']
                # Try to get tick time from TPS metadata first
                if metadata.get('overall_tick_time') is not None:
                    current_tick_time = metadata['overall_tick_time']
                current_app.logger.info(f'Using real TPS data: {current_tps} TPS, {current_tick_time}ms (source: {metadata.get("source", "unknown")})')
            else:
                current_app.logger.info(f'Ignoring placeholder TPS data, using fallback: {current_tps}')
        
        # Use separate tick time metric if available
        if latest_tick_time and latest_tick_time.get('value') is not None:
            tick_metadata = latest_tick_time.get('metadata', {})
            if tick_metadata.get('source') != 'placeholder_rcon_failed':
                current_tick_time = latest_tick_time['value']
        
        if latest_tps is None and latest_tick_time is None:
            current_app.logger.info(f'No TPS/tick time data available, using fallback: {current_tps} TPS, {current_tick_time}ms')
    except Exception as e:
        current_app.logger.warning(f'Failed to get real TPS/tick time data: {e}')
    
    # Get dimension-specific TPS data (dynamic discovery with optimized query)
    dimension_tps_data = {}
    dimension_tick_time_data = {}
    try:
        from services.metrics_storage import metrics_storage
        import sqlite3
        
        # Get all available dimensions from database (optimized with indexes)
        query = """
        SELECT DISTINCT 
            REPLACE(metric_type, 'server_tps_', '') as dimension_name
        FROM metrics 
        WHERE metric_type LIKE 'server_tps_%' 
          AND json_extract(metadata, '$.source') = 'rcon_forge_tps'
        ORDER BY dimension_name
        """
        
        dimensions = []
        with sqlite3.connect(metrics_storage.db_path) as conn:
            cursor = conn.execute(query)
            for row in cursor.fetchall():
                dimensions.append(row[0])
        
        current_app.logger.info(f'Found dimensions for API: {dimensions}')
        
        for dimension in dimensions:
            # Get latest TPS for this dimension
            latest_dim_tps = metrics_storage.get_latest_metric(f'server_tps_{dimension}')
            if latest_dim_tps and latest_dim_tps.get('value') is not None:
                metadata = latest_dim_tps.get('metadata', {})
                if metadata.get('source') == 'rcon_forge_tps':
                    dimension_tps_data[f'current_tps_{dimension}'] = latest_dim_tps['value']
                    # Get tick time from metadata
                    if metadata.get('mean_tick_time') is not None:
                        dimension_tick_time_data[f'current_tick_time_{dimension}'] = metadata['mean_tick_time']
        
        current_app.logger.info(f'Retrieved dimension data: {len(dimension_tps_data)} dimensions with TPS data')
    except Exception as e:
        current_app.logger.warning(f'Failed to get dimension TPS data: {e}')
    
    # Get RCON status (with actual connection test)
    rcon_status = 'unknown'
    try:
        from services.server_properties import ServerPropertiesParser
        
        # Get RCON details from server.properties
        server_props = ServerPropertiesParser()
        if server_props.load_properties() and server_props.is_rcon_enabled():
            # RCON is configured, now test actual connection
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            rcon_port = server_props.get_rcon_port()
            rcon_password = server_props.get_rcon_password()
            
            if rcon_password:
                try:
                    from services.rcon_client import test_rcon_connection
                    connected, error = test_rcon_connection(server_host, rcon_port, rcon_password)
                    if connected:
                        rcon_status = 'connected'
                    else:
                        rcon_status = 'error'  # RCON configured but not connected
                        current_app.logger.warning(f'RCON connection failed: {error}')
                except Exception as e:
                    rcon_status = 'error'
                    current_app.logger.warning(f'RCON connection test failed: {e}')
            else:
                rcon_status = 'error'  # RCON enabled but no password
        else:
            rcon_status = 'disabled'  # RCON not enabled
        current_app.logger.info(f'RCON status: {rcon_status}')
    except Exception as e:
        current_app.logger.warning(f'Failed to check RCON status: {e}')
        rcon_status = 'error'
    
    # Get disk space information
    disk_data = {}
    try:
        import shutil
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
        
        # Get disk usage for the server directory
        total, used, free = shutil.disk_usage(server_path)
        
        # Convert to GB
        total_gb = round(total / (1024**3), 1)
        used_gb = round(used / (1024**3), 1)
        free_gb = round(free / (1024**3), 1)
        used_percent = round((used / total) * 100, 1)
        
        # Determine disk status based on free space
        if free_gb >= 10:
            disk_status = 'good'
        elif free_gb >= 1:
            disk_status = 'warning'
        else:
            disk_status = 'danger'
        
        disk_data = {
            'total_gb': total_gb,
            'used_gb': used_gb,
            'free_gb': free_gb,
            'used_percent': used_percent,
            'status': disk_status
        }
        
        current_app.logger.info(f'Disk space: {free_gb}GB free / {total_gb}GB total ({used_percent}% used) - Status: {disk_status}')
    except Exception as e:
        current_app.logger.warning(f'Failed to get disk space: {e}')
        disk_data = {
            'total_gb': 0,
            'used_gb': 0,
            'free_gb': 0,
            'used_percent': 0,
            'status': 'error'
        }
    
    # Return mixed real and test data
    test_metrics = {
        'current_tps': current_tps,  # Now using real TPS data when available
        'current_tick_time': current_tick_time,  # Real tick time data
        'lag_spikes_5min': 0,
        'system_memory': detailed_memory,  # Enhanced memory data
        'system_load': system_load,  # Real system load
        'java_memory_mb': java_memory_mb,  # Real Java memory
        'players': player_data['count'],  # Player count for status
        'max_players': player_data['max'],  # Max players
        'player_names': player_data['names'],  # List of player names
        'player_status': player_status_data,  # Detailed player login/logout data
        'recent_lag_spikes': [],
        'events': events,  # Real events
        'rcon_status': rcon_status,  # Real RCON status
        'cpu_system_avg': cpu_system_avg,  # Real CPU average
        'cpu_count': cpu_count,  # Real CPU count
        'cpu_per_core': cpu_per_core,  # Real per-core data
        'temperatures': temperature_data,  # Real temperature data
        'disk_space': disk_data  # Real disk space data
    }
    
    # Add dimension-specific TPS and tick time data
    test_metrics.update(dimension_tps_data)
    test_metrics.update(dimension_tick_time_data)
    
    return jsonify(test_metrics)

@main_bp.route('/api/monitoring/dimensions')
def get_available_dimensions():
    """Get list of available dimensions from database"""
    try:
        from services.metrics_storage import metrics_storage
        
        # Query database for all dimension TPS metrics
        query = """
        SELECT DISTINCT 
            REPLACE(metric_type, 'server_tps_', '') as dimension_name
        FROM metrics 
        WHERE metric_type LIKE 'server_tps_%' 
          AND json_extract(metadata, '$.source') = 'rcon_forge_tps'
        ORDER BY dimension_name
        """
        
        import sqlite3
        dimensions = []
        with sqlite3.connect(metrics_storage.db_path) as conn:
            cursor = conn.execute(query)
            for row in cursor.fetchall():
                dimensions.append(row[0])
        
        current_app.logger.info(f'Found {len(dimensions)} dimensions in database: {dimensions}')
        
        return jsonify({
            'dimensions': dimensions,
            'count': len(dimensions)
        })
        
    except Exception as e:
        current_app.logger.error(f'Failed to get dimensions from database: {e}')
        return jsonify({
            'error': str(e),
            'dimensions': [],
            'count': 0
        }), 500

@main_bp.route('/api/monitoring/history/<metric_type>')
def get_metric_history(metric_type):
    """Get historical data for a specific metric type"""
    try:
        from services.metrics_storage import metrics_storage
        
        # Get time range parameter (default to 1 hour)
        hours = request.args.get('hours', 1, type=float)
        if hours <= 0 or hours > 72:  # Limit to 3 days max
            hours = 1
        
        # Get historical data
        history = metrics_storage.get_metrics(metric_type, hours=hours)
        
        current_app.logger.info(f'Retrieved {len(history)} data points for {metric_type} over {hours} hours')
        
        return jsonify({
            'metric_type': metric_type,
            'hours': hours,
            'data_points': len(history),
            'data': history
        })
        
    except Exception as e:
        current_app.logger.error(f'Failed to get metric history for {metric_type}: {e}')
        return jsonify({
            'error': 'Failed to retrieve metric history',
            'metric_type': metric_type,
            'data': []
        }), 500

@main_bp.route('/api/monitoring/history/bulk')
def get_bulk_metric_history():
    """Get historical data for all metrics in a single query"""
    try:
        from services.metrics_storage import metrics_storage
        
        # Get time range parameter (default to 1 hour)
        hours = request.args.get('hours', 1, type=float)
        if hours <= 0 or hours > 72:  # Limit to 3 days max
            hours = 1
        
        # Get all historical data in one query
        bulk_history = metrics_storage.get_bulk_metrics(hours=hours)
        
        # Count total data points and analyze sampling efficiency
        total_points = sum(len(metric_data) for metric_data in bulk_history.values())
        avg_points_per_metric = total_points / len(bulk_history) if bulk_history else 0
        current_app.logger.info(f'Retrieved {total_points} total points ({avg_points_per_metric:.0f} avg/metric) across {len(bulk_history)} metrics over {hours}h - 300-sample optimization active')
        
        return jsonify({
            'hours': hours,
            'metric_count': len(bulk_history),
            'total_data_points': total_points,
            'data': bulk_history
        })
        
    except Exception as e:
        current_app.logger.error(f'Failed to get bulk metric history: {e}')
        return jsonify({
            'error': 'Failed to retrieve bulk metric history',
            'data': {}
        }), 500

@main_bp.route('/api/monitoring/config', methods=['GET', 'POST'])
def monitoring_config():
    """Get or update monitoring configuration"""
    try:
        from services.metrics_storage import metrics_storage
        
        if request.method == 'GET':
            # Return current configuration (collection_interval is read-only from config.toml)
            config_interval = current_app.config.get('METRICS_COLLECTION_INTERVAL', 5)
            actual_interval = max(3, min(10, config_interval))  # Apply same bounds as metrics collection
            config = {
                'collection_interval': actual_interval,
                'collection_interval_source': 'config.toml (read-only)',
                'retention_days': current_app.config.get('METRICS_RETENTION_DAYS', 7),
                'enabled': current_app.config.get('METRICS_ENABLED', True),
                'collect_system_memory': current_app.config.get('METRICS_COLLECT_SYSTEM_MEMORY', True),
                'collect_system_cpu': current_app.config.get('METRICS_COLLECT_SYSTEM_CPU', True),
                'collect_system_load': current_app.config.get('METRICS_COLLECT_SYSTEM_LOAD', True),
                'collect_java_process': current_app.config.get('METRICS_COLLECT_JAVA_PROCESS', True),
                'collect_server_tps': current_app.config.get('METRICS_COLLECT_SERVER_TPS', True),
                'collect_player_count': current_app.config.get('METRICS_COLLECT_PLAYER_COUNT', True)
            }
            return jsonify(config)
        
        elif request.method == 'POST':
            # Update configuration (stored in database for runtime changes)
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            # Validate and store configuration (collection_interval is read-only from config.toml)
            valid_keys = ['retention_days', 'enabled']  # Removed collection_interval
            updated_keys = []
            
            # Warn if someone tries to change collection_interval
            if 'collection_interval' in data:
                current_app.logger.warning('Attempt to change collection_interval via API ignored - use config.toml instead')
            
            for key in valid_keys:
                if key in data:
                    metrics_storage.set_config_value(key, data[key])
                    updated_keys.append(f"{key}={data[key]}")
            
            current_app.logger.info(f'Metrics configuration updated: {", ".join(updated_keys)}')
            
            return jsonify({
                'success': True, 
                'message': 'Configuration updated',
                'updated': updated_keys
            })
            
    except Exception as e:
        current_app.logger.error(f'Failed to handle monitoring config: {e}')
        return jsonify({'error': 'Configuration operation failed'}), 500

@main_bp.route('/server/control', methods=['POST'])
def server_control():
    """Handle server control actions (start/stop/restart)"""
    try:
        current_app.logger.info(f'Server control request received - Method: {request.method}')
        current_app.logger.info(f'Form data: {dict(request.form)}')
        current_app.logger.info(f'Request cookies: {dict(request.cookies)}')
        current_app.logger.info(f'Headers: {dict(request.headers)}')
        
        # Skip CSRF validation for server control route
        current_app.logger.info('CSRF validation skipped for server control')
        
        # Get and validate action
        action = request.form.get('action', '').strip()
        current_app.logger.info(f'Action requested: {action}')
        
        if not action:
            return jsonify({'success': False, 'error': 'Action parameter required'}), 400
        
        if action not in ['start', 'stop', 'restart', 'kill', 'save']:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
        
        current_app.logger.info(f'Executing server {action} action')
        
        # Use new direct process management
        system_control = SystemControlService()
        
        # Execute the requested action
        if action == 'start':
            result = system_control.start_server()
        elif action == 'stop':
            # Use RCON stop command for graceful shutdown
            result = _execute_rcon_server_control('stop')
        elif action == 'restart':
            # Use RCON stop followed by system start
            result = _execute_rcon_server_control('restart')
        elif action == 'kill':
            # Force kill server process (emergency use)
            result = system_control.stop_server()
        elif action == 'save':
            # Save world via RCON
            result = _execute_rcon_server_control('save')
        
        current_app.logger.info(f'Server control result: {result}')
        
        if result['success']:
            current_app.logger.info(f'Server control action {action} successful')
            response_data = {'success': True, 'message': result['message']}
            
            # Include RCON command data if available (for console display)
            if 'rcon_command' in result:
                response_data['rcon_command'] = result['rcon_command']
            if 'rcon_response' in result:
                response_data['rcon_response'] = result['rcon_response']
            
            # For start action, include PID if available
            if action == 'start':
                # Try to get the PID from the system control service
                try:
                    status = system_control.get_server_status()
                    if status.get('pid'):
                        response_data['pid'] = status['pid']
                except Exception as e:
                    current_app.logger.warning(f'Could not get PID for start response: {e}')
            
            return jsonify(response_data)
        else:
            current_app.logger.error(f'Server control action {action} failed: {result["error"]}')
            return jsonify({'success': False, 'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'Server control error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'Server control failed: {str(e)}'}), 500

@main_bp.route('/logs')
def logs():
    """Enhanced log viewer page with 3 separate content windows"""
    try:
        csrf_token = generate_csrf_token()
        return render_template('logs.html', csrf_token=csrf_token)
    except Exception as e:
        current_app.logger.error(f'Logs page error: {e}')
        flash('Error loading logs page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/logs/content/<log_type>')
def log_content(log_type):
    """API endpoint for log content"""
    try:
        if log_type not in ['latest', 'debug', 'crash']:
            return jsonify({'error': 'Invalid log type'}), 400
        
        log_service = LogService()
        result = log_service.get_minecraft_server_logs(log_type, lines=500)
        
        if result['success']:
            return jsonify({
                'content': result['logs'],
                'log_type': result.get('log_type', log_type),
                'log_file': result.get('log_file', 'N/A')
            })
        else:
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'Log content error: {e}')
        return jsonify({'error': 'Failed to read log file'}), 500

@main_bp.route('/logs/crash/list')
def crash_reports_list():
    """API endpoint to list available crash reports"""
    try:
        log_service = LogService()
        crash_reports = log_service.get_crash_reports_list()
        
        return jsonify({
            'success': True,
            'crash_reports': crash_reports
        })
        
    except Exception as e:
        current_app.logger.error(f'Error getting crash reports list: {e}')
        return jsonify({'success': False, 'error': 'Failed to get crash reports list'}), 500

@main_bp.route('/logs/crash/content/<path:filename>')
def crash_report_content(filename):
    """API endpoint to get specific crash report content"""
    try:
        log_service = LogService()
        result = log_service.get_crash_report_content(filename)
        
        if result['success']:
            return jsonify({
                'success': True,
                'content': result['content'],
                'filename': filename,
                'size': result.get('size', 0),
                'modified': result.get('modified', '')
            })
        else:
            return jsonify({'success': False, 'error': result['error']}), 404
            
    except Exception as e:
        current_app.logger.error(f'Error reading crash report: {e}')
        return jsonify({'success': False, 'error': 'Failed to read crash report'}), 500

@main_bp.route('/logs/stream/<log_type>')
def log_stream(log_type):
    """Server-Sent Events endpoint for real-time log streaming"""
    if log_type not in ['latest', 'debug']:
        return jsonify({'error': 'Invalid log type for streaming'}), 400
    
    # Capture Flask config values in request context (before generator starts)
    server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/natie/VaultHunters')
    log_files = current_app.config.get('LOG_FILES', {
        'latest': 'logs/latest.log',
        'debug': 'logs/debug.log'
    })
    
    log_path = os.path.join(server_path, log_files.get(log_type, f'logs/{log_type}.log'))
    
    # Log the attempt
    
    def generate():
        tail_process = None
        try:
            # Check if log file exists
            if not os.path.exists(log_path):
                yield f"data: {json.dumps({'type': 'error', 'error': f'Log file not found: {log_path}'})}\n\n"
                return
            
            # Send initial content using simple tail
            try:
                result = subprocess.run(['tail', '-n', '500', log_path], capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and result.stdout:
                    yield f"data: {json.dumps({'type': 'initial', 'content': result.stdout, 'log_type': log_type})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'initial', 'content': f'No {log_type} log data available', 'log_type': log_type})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': f'Failed to read initial content: {str(e)}'})}\n\n"
                return
            
            # Start streaming with robust log rotation handling
            try:
                import select
                import fcntl
                import os as os_module
                
                last_activity = time.time()
                last_file_check = time.time()
                file_stat = None
                
                # Get initial file stats
                try:
                    file_stat = os.stat(log_path)
                except OSError:
                    file_stat = None
                
                yield f"data: {json.dumps({'type': 'connected', 'log_type': log_type})}\n\n"
                
                def start_tail_process():
                    """Start a new tail process"""
                    process = subprocess.Popen(
                        ['tail', '-f', log_path],  # Use -f instead of -F for better control
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        bufsize=0
                    )
                    
                    # Make stdout non-blocking
                    fd = process.stdout.fileno()
                    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os_module.O_NONBLOCK)
                    
                    return process
                
                tail_process = start_tail_process()
                
                # Stream with file rotation detection
                while True:
                    current_time = time.time()
                    
                    # Check if process is still running
                    if tail_process.poll() is not None:
                        current_app.logger.warning(f"Tail process for {log_type} terminated, restarting...")
                        try:
                            tail_process = start_tail_process()
                            yield f"data: {json.dumps({'type': 'reconnected', 'message': 'Restarted tail process', 'log_type': log_type})}\n\n"
                        except Exception as e:
                            current_app.logger.error(f"Failed to restart tail process: {e}")
                            break
                    
                    # Check for file rotation every 5 seconds
                    if current_time - last_file_check > 5:
                        try:
                            new_stat = os.stat(log_path)
                            # Check if file was recreated (inode changed) or truncated (size decreased significantly)
                            if (file_stat is None or 
                                new_stat.st_ino != file_stat.st_ino or 
                                (new_stat.st_size < file_stat.st_size - 1000)):  # File truncated by more than 1KB
                                
                                
                                # Kill old tail process
                                tail_process.terminate()
                                try:
                                    tail_process.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    tail_process.kill()
                                
                                # Start new tail process
                                tail_process = start_tail_process()
                                file_stat = new_stat
                                
                                yield f"data: {json.dumps({'type': 'rotation', 'message': f'Log file rotated - following new file', 'timestamp': datetime.now().isoformat(), 'log_type': log_type})}\n\n"
                            else:
                                file_stat = new_stat
                                
                        except OSError:
                            # File doesn't exist, wait for it to be created
                            if file_stat is not None:
                                current_app.logger.info(f"Log file {log_type} disappeared, waiting for recreation")
                                file_stat = None
                        
                        last_file_check = current_time
                    
                    # Use select to check for data availability with timeout
                    ready, _, _ = select.select([tail_process.stdout], [], [], 1.0)
                    
                    if ready:
                        try:
                            line = tail_process.stdout.readline()
                            if line:
                                line = line.rstrip()
                                if line:
                                    yield f"data: {json.dumps({'type': 'line', 'line': line, 'timestamp': datetime.now().isoformat(), 'log_type': log_type})}\n\n"
                                    last_activity = current_time
                        except IOError:
                            # No data available, continue
                            pass
                    else:
                        # Send keepalive every 30 seconds
                        if current_time - last_activity > 30:
                            yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': datetime.now().isoformat(), 'log_type': log_type})}\n\n"
                            last_activity = current_time
                    
                    # Check for client disconnect
                    try:
                        yield ""
                    except GeneratorExit:
                        current_app.logger.info(f"Client disconnected from {log_type} stream")
                        break
                    
            except GeneratorExit:
                pass
            except Exception as e:
                current_app.logger.error(f"Tail process error for {log_type}: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': f'Tail process error: {str(e)}'})}\n\n"
                
        except GeneratorExit:
            pass
        except Exception as e:
            current_app.logger.error(f"SSE setup error for {log_type}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': f'SSE setup error: {str(e)}'})}\n\n"
        finally:
            # Always clean up the tail process
            if tail_process:
                try:
                    tail_process.terminate()
                    # Give it a moment to terminate gracefully
                    try:
                        tail_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        tail_process.kill()
                        tail_process.wait()
                except Exception as e:
                    current_app.logger.error(f"Error cleaning up tail process for {log_type}: {e}")
    
    from flask import Response
    response = Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )
    return response

@main_bp.route('/logs/rotate/<log_type>', methods=['POST'])
def rotate_log(log_type):
    """API endpoint for rotating (clearing) log files"""
    try:
        current_app.logger.info(f'Request method: {request.method}')
        current_app.logger.info(f'Request headers: {dict(request.headers)}')
        current_app.logger.info(f'Request form data: {dict(request.form)}')
        
        # Skip CSRF validation for now to isolate the issue
        csrf_token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
        
        # TODO: Re-enable CSRF validation after fixing the core issue
        # from flask_wtf.csrf import validate_csrf
        # try:
        #     if csrf_token:
        #         validate_csrf(csrf_token)
        #         current_app.logger.info('CSRF token validation successful')
        #     else:
        #         current_app.logger.warning('No CSRF token provided in headers or form')
        #         return jsonify({'success': False, 'error': 'CSRF token required'}), 400
        # except Exception as e:
        #     current_app.logger.error(f'CSRF validation failed: {e}', exc_info=True)
        #     return jsonify({'success': False, 'error': f'CSRF token validation failed: {str(e)}'}), 400
        
        if log_type not in ['latest', 'debug']:  # Removed 'crash' from rotation
            current_app.logger.error(f'Invalid log type requested: {log_type}')
            return jsonify({'success': False, 'error': 'Invalid log type - crash logs cannot be rotated'}), 400
        
        try:
            log_service = LogService()
            current_app.logger.info('LogService created successfully')
        except Exception as e:
            current_app.logger.error(f'Failed to create LogService: {e}', exc_info=True)
            return jsonify({'success': False, 'error': f'Service initialization failed: {str(e)}'}), 500
        
        try:
            result = log_service.rotate_log_file(log_type)
        except Exception as e:
            current_app.logger.error(f'rotate_log_file threw exception: {e}', exc_info=True)
            return jsonify({'success': False, 'error': f'Log rotation service error: {str(e)}'}), 500
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': result['message'],
                'rotated_file': result.get('rotated_file', 'N/A')
            })
        else:
            current_app.logger.error(f'Log rotation failed for {log_type}: {result.get("error", "Unknown error")}')
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 200
            
    except ImportError as e:
        current_app.logger.error(f'Import error in log rotation: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'Service unavailable: {str(e)}'}), 500
    except Exception as e:
        current_app.logger.error(f'Unexpected error in log rotation: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'Failed to rotate log file: {str(e)}'}), 500

@main_bp.route('/logs/journal')
def journal_content():
    """API endpoint for system journal content"""
    try:
        result = subprocess.run(
            ['sudo', '/bin/journalctl', '-xeu', 'vaulthunters-web.service', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'content': result.stdout
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Journal command failed: {result.stderr}'
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'Journal content error: {e}')
        return jsonify({'error': 'Failed to read journal'}), 500

@main_bp.route('/logs/journal/stream')
def journal_stream():
    """Server-Sent Events endpoint for real-time journal streaming"""
    try:
        from flask import Response
        import subprocess
        import threading
        import queue
        
        def generate():
            try:
                # Start with recent journal entries
                initial_result = subprocess.run(
                    ['sudo', '/bin/journalctl', '-xeu', 'vaulthunters-web.service', '--no-pager'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if initial_result.returncode == 0:
                    data = json.dumps({'type': 'initial', 'content': initial_result.stdout})
                    yield f"data: {data}\n\n"
                else:
                    data = json.dumps({'type': 'error', 'error': f'Failed to read initial journal: {initial_result.stderr}'})
                    yield f"data: {data}\n\n"
                
                # Start following the journal (use -u without -xe for cleaner follow output)
                process = subprocess.Popen(
                    ['sudo', '/bin/journalctl', '-u', 'vaulthunters-web.service', '--follow'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            line = line.rstrip('\n\r')
                            if line.strip():  # Only send non-empty lines
                                data = json.dumps({'type': 'line', 'line': line})
                                yield f"data: {data}\n\n"
                except Exception as e:
                    data = json.dumps({'type': 'error', 'error': str(e)})
                    yield f"data: {data}\n\n"
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )
    except Exception as e:
        current_app.logger.error(f'Journal stream error: {e}')
        return jsonify({'error': 'Failed to start journal stream'}), 500

@main_bp.route('/config')
def config_editor():
    """Configuration editor page"""
    try:
        return render_template('config.html')
    except Exception as e:
        current_app.logger.error(f'Config editor error: {e}')
        flash('Error loading configuration editor', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/config/files/list')
def config_files_list():
    """API endpoint for config files list"""
    try:
        config_manager = ConfigManager()
        available_configs = config_manager.get_available_config_files()
        
        # Filter to only config directory files for the file browser
        config_dir_files = []
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
        config_dir_path = f"{server_path}/config/"
        
        for config in available_configs:
            # Only include files from the config/ directory
            if config['path'].startswith(config_dir_path):
                config_dir_files.append({
                    'name': config['name'].replace('config/', ''),  # Remove config/ prefix
                    'path': config['path'],
                    'size': config['size'],
                    'type': config['type']
                })
        
        return jsonify({
            'success': True,
            'files': config_dir_files
        })
        
    except Exception as e:
        current_app.logger.error(f'Config files list error: {e}')
        return jsonify({'error': 'Failed to get config files list'}), 500

@main_bp.route('/config/content/<path:config_file>')
def config_content(config_file):
    """API endpoint for config file content"""
    try:
        config_manager = ConfigManager()
        
        # Get server path and construct full config path
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
        
        # Handle different file locations
        if config_file in ['server.properties', 'banned-ips.json', 'banned-players.json', 'whitelist.json']:
            # Root server files
            config_path = os.path.join(server_path, config_file)
        else:
            # Config directory files
            config_path = os.path.join(server_path, 'config', config_file)
        
        result = config_manager.read_config_file(config_path)
        
        if result['success']:
            return jsonify({
                'content': result['content'],
                'filename': config_file,
                'size': result.get('size', 0),
                'type': result.get('type', 'text')
            })
        else:
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'Config content error: {e}')
        return jsonify({'error': 'Failed to read config file'}), 500

@main_bp.route('/config/save', methods=['POST'])
def save_config():
    """Save configuration file"""
    try:
        config_file = request.form.get('config_file')
        content = request.form.get('content')
        
        if not config_file or content is None:
            return jsonify({'error': 'Missing config_file or content'}), 400
        
        config_manager = ConfigManager()
        
        # Get server path and construct full config path
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
        
        # Handle different file locations
        if config_file in ['server.properties', 'banned-ips.json', 'banned-players.json', 'whitelist.json']:
            # Root server files
            config_path = os.path.join(server_path, config_file)
        else:
            # Config directory files
            config_path = os.path.join(server_path, 'config', config_file)
        
        result = config_manager.write_config_file(config_path, content, create_backup=True)
        
        if result['success']:
            current_app.logger.info(f'Config save successful for: {config_file}')
            return jsonify({
                'success': True, 
                'message': result['message'],
                'backup_created': result.get('backup_created', False)
            })
        else:
            current_app.logger.error(f'Config save failed for {config_file}: {result["error"]}')
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'Config save error: {e}')
        return jsonify({'error': 'Failed to save configuration'}), 500

@main_bp.route('/config/jvm/<file_type>')
def get_jvm_config(file_type):
    """Get JVM configuration file content"""
    try:
        if file_type not in ['user_jvm_args', 'unix_args']:
            return jsonify({'error': 'Invalid file type'}), 400
        
        config_manager = ConfigManager()
        result = config_manager.read_jvm_args_file(file_type)
        
        if result['success']:
            return jsonify({'content': result['content']})
        else:
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'JVM config read error: {e}')
        return jsonify({'error': 'Failed to read JVM configuration'}), 500

@main_bp.route('/config/jvm/save', methods=['POST'])
def save_jvm_config():
    """Save JVM configuration file"""
    try:
        file_type = request.form.get('file_type')
        content = request.form.get('content')
        
        if not file_type or content is None:
            return jsonify({'error': 'Missing file_type or content'}), 400
        
        if file_type not in ['user_jvm_args', 'unix_args']:
            return jsonify({'error': 'Invalid file type'}), 400
        
        config_manager = ConfigManager()
        result = config_manager.write_jvm_args_file(file_type, content)
        
        if result['success']:
            current_app.logger.info(f'JVM config save successful for: {file_type}')
            return jsonify({
                'success': True,
                'message': result['message'],
                'backup_created': result.get('backup_created', False)
            })
        else:
            current_app.logger.error(f'JVM config save failed for {file_type}: {result["error"]}')
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'JVM config save error: {e}')
        return jsonify({'error': 'Failed to save JVM configuration'}), 500

@main_bp.route('/config/jvm/apply_aikars_flags', methods=['POST'])
def apply_aikars_flags():
    """Apply Aikar's flags to user_jvm_args.txt"""
    try:
        config_manager = ConfigManager()
        result = config_manager.apply_aikars_flags()
        
        if result['success']:
            current_app.logger.info('Aikar\'s flags applied successfully')
            return jsonify({
                'success': True,
                'message': result['message'],
                'backup_created': result.get('backup_created', False)
            })
        else:
            current_app.logger.error(f'Failed to apply Aikar\'s flags: {result["error"]}')
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'Apply Aikar\'s flags error: {e}')
        return jsonify({'error': 'Failed to apply Aikar\'s flags'}), 500

@main_bp.route('/backups')
def backups():
    """Backup manager page"""
    try:
        backup_manager = BackupManager()
        available_backups = backup_manager.get_available_backups()
        
        # Format backup data for template
        backups = []
        for backup in available_backups:
            backups.append({
                'name': backup['filename'],
                'size': backup['size_human'],
                'date': backup['modified']
            })
        
        return render_template('backups.html', backups=backups)
    except Exception as e:
        current_app.logger.error(f'Backups page error: {e}')
        flash('Error loading backups page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/backups/download/<filename>')
def download_backup(filename):
    """Download backup file"""
    try:
        backup_manager = BackupManager()
        return backup_manager.download_backup(filename)
    except Exception as e:
        current_app.logger.error(f'Backup download error: {e}')
        flash('Error downloading backup', 'error')
        return redirect(url_for('main.backups'))

@main_bp.route('/server/journal')
def server_journal():
    """Get systemd journal logs for the VaultHunters service"""
    try:
        service_name = current_app.config.get('SERVICE_NAME', 'vaulthunters')
        lines = request.args.get('lines', 100, type=int)
        
        log_service = LogService()
        result = log_service.get_service_journal(service_name, lines)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f'Server journal error: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to read service journal',
            'service': service_name
        }), 500

@main_bp.route('/webmanager/journal')
def webmanager_journal():
    """Get systemd journal logs for the web manager service"""
    try:
        lines = request.args.get('lines', 50, type=int)
        
        log_service = LogService()
        result = log_service.get_web_manager_journal(lines)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f'Web manager journal error: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to read web manager journal'
        }), 500

@main_bp.route('/console')
def console():
    """Console page with RCON interface"""
    try:
        return render_template('console.html')
    except Exception as e:
        current_app.logger.error(f'Console page error: {e}')
        flash('Error loading console page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/console/status')
def console_status():
    """Check RCON connection status"""
    try:
        from mcrcon import MCRcon
        import os
        
        # Get server connection details from server.properties
        server_props = ServerPropertiesParser()
        
        # Check if server.properties file exists
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
        props_file = os.path.join(server_path, 'server.properties')
        current_app.logger.info(f'Looking for server.properties at: {props_file}')
        current_app.logger.info(f'File exists: {os.path.exists(props_file)}')
        
        if os.path.exists(props_file):
            current_app.logger.info(f'File size: {os.path.getsize(props_file)} bytes')
            # Read first few lines for debugging
            try:
                with open(props_file, 'r') as f:
                    first_lines = [f.readline().strip() for _ in range(5)]
                current_app.logger.info(f'First 5 lines: {first_lines}')
            except Exception as e:
                current_app.logger.error(f'Could not read server.properties: {e}')
        
        # Load properties first
        if not server_props.load_properties():
            return jsonify({
                'connected': False,
                'error': f'Could not load server.properties file at {props_file}'
            })
        
        all_props = server_props.get_all_properties()
        current_app.logger.info(f'Loaded server.properties with {len(all_props)} properties')
        current_app.logger.info(f'Sample properties: {dict(list(all_props.items())[:5]) if all_props else "None"}')
        
        # Check specific RCON properties
        enable_rcon = server_props.get_property('enable-rcon')
        rcon_port_prop = server_props.get_property('rcon.port')
        rcon_password_prop = server_props.get_property('rcon.password')
        
        current_app.logger.info(f'Raw properties - enable-rcon: {enable_rcon}, rcon.port: {rcon_port_prop}, rcon.password: {"SET" if rcon_password_prop else "EMPTY"}')
        
        if not server_props.is_rcon_enabled():
            return jsonify({
                'connected': False,
                'error': f'RCON is not enabled in server.properties (enable-rcon={enable_rcon}, need enable-rcon=true)'
            })
        
        server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
        rcon_port = server_props.get_rcon_port()
        rcon_password = server_props.get_rcon_password()
        
        current_app.logger.info(f'RCON config - Host: {server_host}, Port: {rcon_port}, Password: {"SET" if rcon_password else "EMPTY"}')
        
        if not rcon_password:
            return jsonify({
                'connected': False,
                'error': f'RCON password not set in server.properties (rcon.password="{rcon_password_prop}")'
            })
        
        current_app.logger.info(f'RCON status check: attempting connection to {server_host}:{rcon_port}')
        
        # Test basic network connectivity first
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((server_host, rcon_port))
            sock.close()
            
            if result != 0:
                return jsonify({
                    'connected': False,
                    'error': f'Cannot connect to {server_host}:{rcon_port} - server may not be running or RCON port blocked'
                })
            
            current_app.logger.info(f'Socket connection to {server_host}:{rcon_port} successful')
        except Exception as socket_error:
            current_app.logger.error(f'Socket test failed: {socket_error}')
            return jsonify({
                'connected': False,
                'error': f'Network connectivity test failed: {str(socket_error)}'
            })
        
        # Test RCON connection using custom client to avoid signal issues
        try:
            
            from services.rcon_client import get_rcon_connection_status, test_rcon_connection
            # First check if we have an existing connection
            connected, error = get_rcon_connection_status(server_host, rcon_port, rcon_password)
            
            # If not connected, try to test connection
            if not connected:
                connected, error = test_rcon_connection(server_host, rcon_port, rcon_password)
            
            if not connected:
                raise Exception(error)
            
            current_app.logger.info(f'RCON connection successful with custom client')
                
        except Exception as rcon_error:
            current_app.logger.error(f'RCON connection failed: {type(rcon_error).__name__}: {rcon_error}', exc_info=True)
            
            error_message = str(rcon_error).lower()
            if 'refused' in error_message or 'timeout' in error_message:
                return jsonify({
                    'connected': False,
                    'error': f'RCON server not responding on {server_host}:{rcon_port}. Check if Minecraft server is running and RCON is enabled.'
                })
            elif 'auth' in error_message or 'password' in error_message:
                return jsonify({
                    'connected': False,
                    'error': f'RCON authentication failed. Check rcon.password in server.properties.'
                })
            else:
                return jsonify({
                    'connected': False,
                    'error': f'RCON connection error: {str(rcon_error)}'
                })
            
        current_app.logger.info(f'RCON status check: connection successful')
        return jsonify({
            'connected': True,
            'host': server_host,
            'port': rcon_port
        })
        
    except Exception as e:
        current_app.logger.error(f'RCON status check failed: {str(e)} (type: {type(e).__name__})')
        return jsonify({
            'connected': False,
            'error': str(e)
        })

@main_bp.route('/console/execute', methods=['POST'])
def console_execute():
    """Execute RCON command"""
    try:
        # Skip CSRF validation for console commands (consistent with server control)
        current_app.logger.info('CSRF validation skipped for console execute')
        
        data = request.get_json()
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({
                'success': False,
                'error': 'No command provided'
            }), 400
        
        from mcrcon import MCRcon
        
        # Get server connection details from server.properties
        server_props = ServerPropertiesParser()
        
        # Load properties first
        if not server_props.load_properties():
            return jsonify({
                'success': False,
                'error': 'Could not load server.properties file'
            }), 500
        
        if not server_props.is_rcon_enabled():
            return jsonify({
                'success': False,
                'error': 'RCON is not enabled in server.properties (enable-rcon=true required)'
            }), 500
        
        server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
        rcon_port = server_props.get_rcon_port()
        rcon_password = server_props.get_rcon_password()
        
        current_app.logger.info(f'RCON execute - Host: {server_host}, Port: {rcon_port}, Command: {command}')
        
        if not rcon_password:
            return jsonify({
                'success': False,
                'error': 'RCON password not set in server.properties'
            }), 500
        
        # Execute command via RCON using custom client to avoid signal issues
        try:
            current_app.logger.info(f'Executing RCON command: {command}')
            
            from services.rcon_client import execute_rcon_command
            success, response = execute_rcon_command(server_host, rcon_port, rcon_password, command)
            
            if not success:
                raise Exception(response)
            
            current_app.logger.info(f'RCON command successful with custom client')
                
        except Exception as rcon_error:
            current_app.logger.error(f'RCON command execution failed: {rcon_error}')
            
            error_message = str(rcon_error).lower()
            if 'refused' in error_message or 'timeout' in error_message:
                return jsonify({
                    'success': False,
                    'error': 'RCON server not responding. Check if Minecraft server is running.'
                }), 500
            elif 'auth' in error_message or 'password' in error_message:
                return jsonify({
                    'success': False,
                    'error': 'RCON authentication failed. Check server password.'
                }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': f'Command execution failed: {str(rcon_error)}'
                }), 500
            
        current_app.logger.info(f'RCON command executed: {command}')
        
        return jsonify({
            'success': True,
            'command': command,
            'response': response if response else 'Command executed successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f'RCON command execution failed: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/console/connect', methods=['POST'])
def console_connect():
    """Force RCON reconnection"""
    try:
        from services.rcon_client import force_rcon_reconnect
        
        # Get server connection details from server.properties
        server_props = ServerPropertiesParser()
        
        if not server_props.load_properties():
            return jsonify({
                'success': False,
                'error': 'Could not load server.properties file'
            }), 500
        
        if not server_props.is_rcon_enabled():
            return jsonify({
                'success': False,
                'error': 'RCON is not enabled in server.properties'
            }), 500
        
        server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
        rcon_port = server_props.get_rcon_port()
        rcon_password = server_props.get_rcon_password()
        
        if not rcon_password:
            return jsonify({
                'success': False,
                'error': 'RCON password not set in server.properties'
            }), 500
        
        # Force reconnection
        success, error = force_rcon_reconnect(server_host, rcon_port, rcon_password)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'RCON reconnected successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': error or 'Failed to reconnect'
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'RCON connect failed: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/console/disconnect', methods=['POST'])
def console_disconnect():
    """Disconnect RCON connection"""
    try:
        from services.rcon_client import RconConnectionManager
        
        # Get server connection details
        server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
        server_props = ServerPropertiesParser()
        
        if server_props.load_properties():
            rcon_port = server_props.get_rcon_port()
            # Disconnect the specific connection
            connection_key = f"{server_host}:{rcon_port}"
            RconConnectionManager.disconnect_all()  # For simplicity, disconnect all
        
        return jsonify({
            'success': True,
            'message': 'RCON disconnected successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f'RCON disconnect failed: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/api/player/<username>/history')
def get_player_history(username):
    """Get detailed login/logout history for a specific player"""
    try:
        from services.metrics_storage import metrics_storage
        
        # Get all sessions for this player
        with sqlite3.connect(metrics_storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT login_time, logout_time, is_online
                FROM players 
                WHERE username = ?
                ORDER BY login_time DESC
            ''', (username,))
            
            sessions = []
            total_playtime_seconds = 0
            
            for row in cursor.fetchall():
                login_time_str, logout_time_str, is_online = row
                
                login_time = datetime.fromisoformat(login_time_str) if login_time_str else None
                logout_time = datetime.fromisoformat(logout_time_str) if logout_time_str else None
                
                # Calculate session duration
                session_duration = 0
                if login_time:
                    if logout_time:
                        # Completed session
                        session_duration = (logout_time - login_time).total_seconds()
                    elif is_online:
                        # Currently online session
                        session_duration = (datetime.now() - login_time).total_seconds()
                
                total_playtime_seconds += session_duration
                
                # Format times for display
                login_display = login_time.strftime('%Y-%m-%d %H:%M:%S') if login_time else 'Unknown'
                logout_display = logout_time.strftime('%Y-%m-%d %H:%M:%S') if logout_time else ('Still online' if is_online else 'Unknown')
                
                # Format session duration
                hours = int(session_duration // 3600)
                minutes = int((session_duration % 3600) // 60)
                seconds = int(session_duration % 60)
                
                if hours > 0:
                    duration_display = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    duration_display = f"{minutes}m {seconds}s"
                else:
                    duration_display = f"{seconds}s"
                
                sessions.append({
                    'login_time': login_display,
                    'logout_time': logout_display,
                    'is_online': bool(is_online),
                    'duration': duration_display,
                    'duration_seconds': session_duration
                })
            
            # Format total playtime
            total_hours = int(total_playtime_seconds // 3600)
            total_minutes = int((total_playtime_seconds % 3600) // 60)
            total_seconds = int(total_playtime_seconds % 60)
            
            if total_hours > 0:
                total_playtime_display = f"{total_hours}h {total_minutes}m {total_seconds}s"
            elif total_minutes > 0:
                total_playtime_display = f"{total_minutes}m {total_seconds}s"
            else:
                total_playtime_display = f"{total_seconds}s"
            
            return jsonify({
                'username': username,
                'total_sessions': len(sessions),
                'total_playtime': total_playtime_display,
                'total_playtime_seconds': total_playtime_seconds,
                'sessions': sessions
            })
            
    except Exception as e:
        current_app.logger.error(f'Failed to get player history for {username}: {e}')
        return jsonify({
            'error': 'Failed to retrieve player history',
            'username': username,
            'sessions': []
        }), 500

# Death tracking removed - only tracking player sessions now

@main_bp.route('/admin/cleanup-duplicate-sessions', methods=['POST'])
def cleanup_duplicate_sessions():
    """Admin endpoint to clean up duplicate player sessions"""
    try:
        from services.metrics_storage import metrics_storage
        removed_count = metrics_storage.remove_duplicate_sessions()
        
        return jsonify({
            'success': True,
            'message': f'Successfully removed {removed_count} duplicate sessions',
            'removed_count': removed_count
        })
        
    except Exception as e:
        current_app.logger.error(f'Failed to cleanup duplicate sessions: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to cleanup duplicate sessions'
        }), 500

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': 'placeholder',
        'version': '1.0.0-dev'
    })