from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_wtf import FlaskForm
from flask_wtf.csrf import validate_csrf
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length
from services.system_control import SystemControlService
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
    """Main dashboard"""
    try:
        service_name = current_app.config.get('SERVICE_NAME', 'vaulthunters')
        system_control = SystemControlService(service_name)
        server_status = system_control.get_service_status()
        
        return render_template('index.html', server_status=server_status)
    except Exception as e:
        current_app.logger.error(f'Dashboard error: {e}')
        flash('Error loading dashboard', 'error')
        return render_template('index.html', server_status={'running': False})

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
    """Log viewer page"""
    try:
        # TODO: Get available log files
        log_files = ['server', 'debug', 'crash']
        selected_log = request.args.get('log', 'server')
        
        return render_template('logs.html', 
                             log_files=log_files, 
                             selected_log=selected_log)
    except Exception as e:
        current_app.logger.error(f'Logs page error: {e}')
        flash('Error loading logs page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/logs/content/<log_type>')
def log_content(log_type):
    """API endpoint for log content"""
    try:
        # TODO: Implement actual log reading
        if log_type not in ['server', 'debug', 'crash']:
            return jsonify({'error': 'Invalid log type'}), 400
        
        # Placeholder log content
        log_content = f"[INFO] This is a placeholder for {log_type} log content\n"
        log_content += "[INFO] Log reading functionality not yet implemented\n"
        
        return jsonify({
            'content': log_content,
            'last_modified': 'Unknown',
            'size': len(log_content)
        })
    except Exception as e:
        current_app.logger.error(f'Log content error: {e}')
        return jsonify({'error': 'Failed to read log file'}), 500

@main_bp.route('/config')
def config_editor():
    """Configuration editor page"""
    try:
        # TODO: Get available config files
        config_files = ['server.properties', 'bukkit.yml', 'spigot.yml']
        selected_config = request.args.get('config', 'server.properties')
        
        form = ConfigEditForm()
        form.config_file.choices = [(f, f) for f in config_files]
        
        return render_template('config.html', 
                             form=form, 
                             config_files=config_files,
                             selected_config=selected_config)
    except Exception as e:
        current_app.logger.error(f'Config editor error: {e}')
        flash('Error loading configuration editor', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/config/content/<config_file>')
def config_content(config_file):
    """API endpoint for config file content"""
    try:
        # TODO: Implement actual config file reading
        if config_file not in current_app.config.get('EDITABLE_CONFIGS', []):
            return jsonify({'error': 'Config file not allowed'}), 403
        
        # Placeholder config content
        content = f"# Placeholder content for {config_file}\n"
        content += "# Configuration file reading not yet implemented\n"
        
        return jsonify({
            'content': content,
            'filename': config_file
        })
    except Exception as e:
        current_app.logger.error(f'Config content error: {e}')
        return jsonify({'error': 'Failed to read config file'}), 500

@main_bp.route('/config/save', methods=['POST'])
def save_config():
    """Save configuration file"""
    form = ConfigEditForm()
    
    if form.validate_on_submit():
        config_file = form.config_file.data
        content = form.content.data
        
        try:
            # TODO: Implement actual config file saving
            current_app.logger.info(f'Config save request for: {config_file}')
            flash(f'Configuration {config_file} saved successfully', 'success')
            return jsonify({'success': True, 'message': 'Configuration saved'})
        except Exception as e:
            current_app.logger.error(f'Config save error: {e}')
            return jsonify({'error': 'Failed to save configuration'}), 500
    
    return jsonify({'error': 'Invalid form data'}), 400

@main_bp.route('/backups')
def backups():
    """Backup manager page"""
    try:
        # TODO: Get available backups
        backups = [
            {'name': 'backup_2024_01_01.zip', 'size': '125 MB', 'date': '2024-01-01 12:00:00'},
            {'name': 'backup_2024_01_02.zip', 'size': '128 MB', 'date': '2024-01-02 12:00:00'},
        ]
        
        return render_template('backups.html', backups=backups)
    except Exception as e:
        current_app.logger.error(f'Backups page error: {e}')
        flash('Error loading backups page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/backups/download/<filename>')
def download_backup(filename):
    """Download backup file"""
    try:
        # TODO: Implement actual backup download
        current_app.logger.info(f'Backup download request: {filename}')
        flash('Backup download functionality not yet implemented', 'info')
        return redirect(url_for('main.backups'))
    except Exception as e:
        current_app.logger.error(f'Backup download error: {e}')
        flash('Error downloading backup', 'error')
        return redirect(url_for('main.backups'))

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': 'placeholder',
        'version': '1.0.0-dev'
    })