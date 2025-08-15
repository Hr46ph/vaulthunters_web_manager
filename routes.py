from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, session
from flask_wtf import FlaskForm
from flask_wtf.csrf import validate_csrf
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length
from services.system_control import SystemControlService
from services.log_service import LogService
from services.config_manager import ConfigManager
from services.backup_manager import BackupManager
from services.server_properties import ServerPropertiesParser
import os
import logging

# Create blueprint
main_bp = Blueprint('main', __name__)

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
        # Return minimal page - status will be loaded via AJAX
        return render_template('index.html')
    except Exception as e:
        current_app.logger.error(f'Dashboard error: {e}')
        flash('Error loading dashboard', 'error')
        return render_template('index.html')

@main_bp.route('/server/status')
def server_status():
    """API endpoint for server status"""
    try:
        service_name = current_app.config.get('SERVICE_NAME', 'vaulthunters')
        system_control = SystemControlService(service_name)
        status = system_control.get_service_status()
        return jsonify(status)
    except Exception as e:
        current_app.logger.error(f'Server status error: {e}')
        return jsonify({'error': 'Failed to get server status'}), 500

@main_bp.route('/server/control', methods=['POST'])
def server_control():
    """Handle server control actions (start/stop/restart)"""
    form = ServerControlForm()
    
    if form.validate_on_submit():
        action = form.action.data
        
        if action not in ['start', 'stop', 'restart']:
            return jsonify({'error': 'Invalid action'}), 400
        
        try:
            service_name = current_app.config.get('SERVICE_NAME', 'vaulthunters')
            system_control = SystemControlService(service_name)
            
            # Execute the requested action
            if action == 'start':
                result = system_control.start_service()
            elif action == 'stop':
                result = system_control.stop_service()
            elif action == 'restart':
                result = system_control.restart_service()
            
            if result['success']:
                current_app.logger.info(f'Server control action {action} successful')
                flash(result['message'], 'success')
                return jsonify({'success': True, 'message': result['message']})
            else:
                current_app.logger.error(f'Server control action {action} failed: {result["error"]}')
                return jsonify({'success': False, 'error': result['error']}), 500
                
        except Exception as e:
            current_app.logger.error(f'Server control error: {e}')
            return jsonify({'error': f'Failed to {action} server: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid request'}), 400

@main_bp.route('/logs')
def logs():
    """Enhanced log viewer page with 3 separate content windows"""
    try:
        return render_template('logs.html')
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
        result = log_service.get_minecraft_server_logs(log_type, lines=200)
        
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
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunter')
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
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunter')
        
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
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunter')
        
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
            flash(f'Configuration {config_file} saved successfully', 'success')
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
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunter')
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
        
        # Test RCON connection using mcrcon with timeout
        try:
            current_app.logger.info('Creating MCRcon instance')
            mcr = MCRcon(server_host, rcon_password, port=rcon_port, timeout=5)
            current_app.logger.info('Attempting RCON connect')
            mcr.connect()
            current_app.logger.info('RCON connected, sending help command')
            # Simple test command
            response = mcr.command("help")
            current_app.logger.info(f'RCON command successful, response length: {len(response) if response else 0}')
            mcr.disconnect()
            current_app.logger.info('RCON disconnected successfully')
        except Exception as rcon_error:
            current_app.logger.error(f'RCON connection failed: {type(rcon_error).__name__}: {rcon_error}', exc_info=True)
            return jsonify({
                'connected': False,
                'error': f'RCON authentication/command failed: {str(rcon_error)}'
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
        validate_csrf(request.form.get('csrf_token') or request.headers.get('X-CSRFToken'))
        
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
        
        # Execute command via RCON with proper connection handling
        try:
            mcr = MCRcon(server_host, rcon_password, port=rcon_port, timeout=10)
            mcr.connect()
            response = mcr.command(command)
            mcr.disconnect()
        except Exception as rcon_error:
            current_app.logger.error(f'RCON command execution failed: {rcon_error}')
            raise rcon_error
            
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

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': 'placeholder',
        'version': '1.0.0-dev'
    })