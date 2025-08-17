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
    current_app.logger.info(f'SSE request for {log_type} log at {log_path}')
    
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
                current_app.logger.info(f"Started tail process for {log_type}")
                
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
                                
                                current_app.logger.info(f"Log file rotation detected for {log_type}, restarting tail")
                                
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
                current_app.logger.info(f"SSE generator exit for {log_type}")
            except Exception as e:
                current_app.logger.error(f"Tail process error for {log_type}: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': f'Tail process error: {str(e)}'})}\n\n"
                
        except GeneratorExit:
            current_app.logger.info(f"SSE outer generator exit for {log_type}")
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
                    current_app.logger.info(f"Cleaned up tail process for {log_type}")
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
        current_app.logger.info(f'Log rotation request: {log_type}')
        current_app.logger.info(f'Request method: {request.method}')
        current_app.logger.info(f'Request headers: {dict(request.headers)}')
        current_app.logger.info(f'Request form data: {dict(request.form)}')
        
        # Skip CSRF validation for now to isolate the issue
        current_app.logger.info('Skipping CSRF validation temporarily for debugging')
        csrf_token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
        current_app.logger.info(f'CSRF token received: {csrf_token[:10] if csrf_token else "None"}...')
        
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
        
        current_app.logger.info(f'Creating LogService for {log_type}')
        try:
            log_service = LogService()
            current_app.logger.info('LogService created successfully')
        except Exception as e:
            current_app.logger.error(f'Failed to create LogService: {e}', exc_info=True)
            return jsonify({'success': False, 'error': f'Service initialization failed: {str(e)}'}), 500
        
        current_app.logger.info(f'Calling rotate_log_file for {log_type}')
        try:
            result = log_service.rotate_log_file(log_type)
            current_app.logger.info(f'rotate_log_file returned: {result}')
        except Exception as e:
            current_app.logger.error(f'rotate_log_file threw exception: {e}', exc_info=True)
            return jsonify({'success': False, 'error': f'Log rotation service error: {str(e)}'}), 500
        
        if result.get('success'):
            current_app.logger.info(f'Log rotation successful for: {log_type}')
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
            current_app.logger.info(f'Testing socket connection to {server_host}:{rcon_port}')
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
            current_app.logger.info('Testing RCON connection with custom client')
            
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

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': 'placeholder',
        'version': '1.0.0-dev'
    })