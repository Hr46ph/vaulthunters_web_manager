from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, session
from flask_wtf.csrf import validate_csrf
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, BooleanField
from wtforms.validators import DataRequired, Length, EqualTo
from werkzeug.exceptions import BadRequest
from services.system_control import SystemControlService
from services.log_service import LogService
from services.config_manager import ConfigManager
from services.backup_manager import BackupManager
from services.server_properties import ServerPropertiesParser
from services.log_watcher import get_log_watcher
from services.rcon_client import RconClient
from services.system_info import SystemInfoService
from services.auth_manager import AuthManager, login_required, admin_required
import os
import logging
import subprocess
import json
import time
from datetime import datetime

def get_base_url():
    """Generate proper absolute URL for redirects behind reverse proxy"""
    scheme = request.environ.get('REAL_SCHEME', request.environ.get('wsgi.url_scheme', 'http'))
    host = request.environ.get('REAL_HOST', request.host)
    return f"{scheme}://{host}"

def validate_csrf_token():
    """Validate CSRF token for the current request if CSRF is enabled"""
    if not current_app.config.get('CSRF_ENABLED', True):
        return True
    
    try:
        # For JSON requests, check X-CSRFToken header
        if request.is_json:
            token = request.headers.get('X-CSRFToken')
            if token:
                validate_csrf(token)
                return True
        
        # For form requests, check csrf_token field
        token = request.form.get('csrf_token')
        if token:
            validate_csrf(token)
            return True
            
        # If no token found, raise CSRF error
        current_app.logger.warning(f'CSRF token missing in {request.method} request to {request.endpoint}')
        raise BadRequest('CSRF token missing')
        
    except Exception as e:
        current_app.logger.warning(f'CSRF validation failed: {str(e)}')
        if 'CSRF' in str(e) or 'expired' in str(e).lower():
            raise BadRequest('CSRF token validation failed')
        raise BadRequest('Security validation failed')

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
        
        
        if action == 'stop':
            # Use direct process control for reliable stop
            try:
                current_app.logger.info('Stopping server using direct process control')
                system_control = SystemControlService()
                result = system_control.stop_server()
                
                current_app.logger.info(f'Process stop result: {result}')
                return result
            except Exception as e:
                current_app.logger.error(f'Process stop failed: {e}')
                return {
                    'success': False,
                    'error': f'Server stop failed: {str(e)}'
                }
                
        elif action == 'restart':
            # Use direct process control for reliable restart
            try:
                current_app.logger.info('Restarting server using direct process control')
                system_control = SystemControlService()
                
                # First stop the server
                current_app.logger.info('Stopping server for restart...')
                stop_result = system_control.stop_server()
                current_app.logger.info(f'Stop result: {stop_result}')
                
                if stop_result['success']:
                    # Wait a moment for cleanup
                    time.sleep(2.0)
                    
                    # Then start the server
                    current_app.logger.info('Starting server after stop...')
                    start_result = system_control.start_server()
                    current_app.logger.info(f'Start result: {start_result}')
                    
                    return {
                        'success': start_result['success'],
                        'message': f"Server restart: Stop {'successful' if stop_result['success'] else 'failed'}, Start {'successful' if start_result['success'] else 'failed'}",
                        'stop_result': stop_result,
                        'start_result': start_result
                    }
                else:
                    return {
                        'success': False,
                        'error': f"Restart failed during stop phase: {stop_result.get('error', 'Unknown error')}"
                    }
                    
            except Exception as e:
                current_app.logger.error(f'Process restart failed: {e}')
                return {
                    'success': False,
                    'error': f'Server restart failed: {str(e)}'
                }
                
        elif action == 'save':
            # Execute save-all flush command via RCON
            try:
                with RconClient(server_host, rcon_port, rcon_password, timeout=20.0) as rcon:
                    current_app.logger.info(f'Executing save command via RCON')
                    response = rcon.command('save-all flush')
                    current_app.logger.info(f'save-all flush result: {response}')
                    
                    return {
                        'success': True,
                        'message': 'World save command sent via RCON',
                        'rcon_command': 'save-all flush',
                        'rcon_response': response
                    }
            except Exception as e:
                current_app.logger.error(f'RCON save command failed: {e}')
                return {
                    'success': False,
                    'error': f'RCON save command failed: {str(e)}'
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

# Login form class
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=1, max=50)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# Password change form
class PasswordChangeForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password', 
                                   validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')

# Add user form (admin only)
class AddUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', 
                                   validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Role', choices=[('user', 'User'), ('admin', 'Administrator')], 
                      validators=[DataRequired()])
    submit = SubmitField('Add User')

# Edit user form (admin only)
class EditUserForm(FlaskForm):
    role = SelectField('Role', choices=[('user', 'User'), ('admin', 'Administrator')], 
                      validators=[DataRequired()])
    active = BooleanField('Active')
    submit = SubmitField('Update User')

# 2FA Forms
class TwoFactorLoginForm(FlaskForm):
    totp_token = StringField('Authentication Code', 
                           validators=[DataRequired(), Length(min=6, max=8)],
                           render_kw={'placeholder': '6-digit code or backup code'})
    submit = SubmitField('Verify')

class Setup2FAForm(FlaskForm):
    totp_token = StringField('Authentication Code', 
                           validators=[DataRequired(), Length(min=6, max=6)],
                           render_kw={'placeholder': '6-digit code from authenticator app'})
    submit = SubmitField('Enable 2FA')



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

# Authentication routes
@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication"""
    if AuthManager.is_authenticated():
        return redirect(get_base_url() + url_for('main.index'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        if AuthManager.authenticate_user(username, password):
            # Check if user has 2FA enabled
            if AuthManager.has_2fa_enabled(username):
                # Store username in session temporarily for 2FA verification
                session['2fa_username'] = username
                session['2fa_next'] = request.args.get('next')
                return redirect(get_base_url() + url_for('main.verify_2fa'))
            else:
                # No 2FA, log in directly
                AuthManager.login_user(username)
                flash(f'Welcome, {username}!', 'success')
                
                # Redirect to next page or dashboard
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('auth/login.html', 
                         form=form, 
                         show_emergency_reset=AuthManager.is_emergency_reset_available())

@main_bp.route('/logout')
def logout():
    """Logout and redirect to login page"""
    AuthManager.logout_user()
    flash('You have been logged out.', 'info')
    return redirect(get_base_url() + url_for('main.login'))

@main_bp.route('/emergency-reset-admin', methods=['POST'])
def emergency_reset_admin():
    """Emergency admin password reset - only available when there's only one user"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
        # Check if emergency reset is available
        if not AuthManager.is_emergency_reset_available():
            flash('Emergency reset is not available. This feature is only available when there is exactly one user (admin).', 'error')
            return redirect(get_base_url() + url_for('main.login'))
        
        # Perform the reset
        if AuthManager.emergency_reset_admin_password():
            flash('Emergency password reset successful! Check the service logs for the new password: journalctl --user -u vaulthunters_web_manager | grep "EMERGENCY ADMIN PASSWORD RESET"', 'success')
        else:
            flash('Emergency password reset failed. Please check the application logs.', 'error')
    
    except Exception as e:
        current_app.logger.error(f"Error during emergency reset: {e}")
        flash('An error occurred during password reset.', 'error')
    
    return redirect(get_base_url() + url_for('main.login'))

# 2FA Routes

@main_bp.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    """2FA verification page"""
    # Check if we have a pending 2FA login
    username = session.get('2fa_username')
    if not username:
        flash('Invalid access. Please log in again.', 'error')
        return redirect(get_base_url() + url_for('main.login'))
    
    form = TwoFactorLoginForm()
    
    if form.validate_on_submit():
        totp_token = form.totp_token.data.strip()
        
        if AuthManager.verify_2fa(username, totp_token):
            # 2FA verified, complete login
            AuthManager.login_user(username)
            
            # Clear 2FA session data
            next_page = session.pop('2fa_next', None)
            session.pop('2fa_username', None)
            
            flash(f'Welcome, {username}!', 'success')
            
            # Redirect to next page or dashboard
            if next_page and next_page.startswith('/'):
                return redirect(get_base_url() + next_page)
            return redirect(get_base_url() + url_for('main.index'))
        else:
            flash('Invalid authentication code. Please try again.', 'error')
    
    return render_template('auth/verify_2fa.html', form=form, username=username)

@main_bp.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    """2FA setup page"""
    username = AuthManager.get_current_user()
    
    # Check if 2FA is already enabled
    if AuthManager.has_2fa_enabled(username):
        flash('2FA is already enabled for your account.', 'info')
        return redirect(url_for('main.profile'))
    
    # Check if we're in setup process (have setup data in session)
    setup_data = session.get('2fa_setup_data')
    
    if request.method == 'GET':
        # Start 2FA setup process
        setup_result = AuthManager.setup_2fa(username)
        if not setup_result:
            flash('Failed to set up 2FA. Please try again.', 'error')
            return redirect(url_for('main.profile'))
        
        # Store setup data in session temporarily
        session['2fa_setup_data'] = {
            'secret': setup_result['secret'],
            'qr_code': setup_result['qr_code'],
            'backup_codes': setup_result['backup_codes']
        }
        setup_data = session['2fa_setup_data']
    
    form = Setup2FAForm()
    
    if form.validate_on_submit():
        totp_token = form.totp_token.data.strip()
        
        if AuthManager.enable_2fa(username, totp_token):
            # Clear setup data from session
            session.pop('2fa_setup_data', None)
            
            # Log out user for security - they need to log in again with 2FA
            AuthManager.logout_user()
            
            flash('2FA has been successfully enabled! Please log in again with your new 2FA setup.', 'success')
            return redirect(get_base_url() + url_for('main.login'))
        else:
            flash('Invalid authentication code. Please scan the QR code again and try again.', 'error')
    
    if not setup_data:
        flash('2FA setup session expired. Please try again.', 'error')
        return redirect(url_for('main.profile'))
    
    return render_template('auth/setup_2fa.html', 
                         form=form, 
                         qr_code=setup_data['qr_code'],
                         backup_codes=setup_data['backup_codes'])

@main_bp.route('/disable-2fa', methods=['POST'])
@login_required
def disable_2fa():
    """Disable 2FA for current user"""
    username = AuthManager.get_current_user()
    
    if not AuthManager.has_2fa_enabled(username):
        flash('2FA is not enabled for your account.', 'info')
        return redirect(url_for('main.profile'))
    
    if AuthManager.disable_2fa(username):
        flash('2FA has been disabled for your account.', 'warning')
    else:
        flash('Failed to disable 2FA. Please try again.', 'error')
    
    return redirect(url_for('main.profile'))

@main_bp.route('/regenerate-backup-codes', methods=['POST'])
@login_required
def regenerate_backup_codes():
    """Regenerate backup codes for current user"""
    username = AuthManager.get_current_user()
    
    if not AuthManager.has_2fa_enabled(username):
        flash('2FA is not enabled for your account.', 'error')
        return redirect(url_for('main.profile'))
    
    backup_codes = AuthManager.regenerate_backup_codes(username)
    if backup_codes:
        session['new_backup_codes'] = backup_codes
        flash('New backup codes generated. Please save them in a safe place.', 'success')
        return redirect(url_for('main.show_backup_codes'))
    else:
        flash('Failed to regenerate backup codes. Please try again.', 'error')
        return redirect(url_for('main.profile'))

@main_bp.route('/backup-codes')
@login_required
def show_backup_codes():
    """Show newly generated backup codes"""
    backup_codes = session.pop('new_backup_codes', None)
    if not backup_codes:
        flash('No backup codes to display.', 'error')
        return redirect(url_for('main.profile'))
    
    return render_template('auth/backup_codes.html', backup_codes=backup_codes)

# User Management Routes

@main_bp.route('/users')
@admin_required
def users():
    """User management page (admin only)"""
    try:
        users = AuthManager.list_users()
        current_user = AuthManager.get_current_user()
        return render_template('auth/users.html', users=users, current_user=current_user)
    except Exception as e:
        current_app.logger.error(f'Users page error: {e}')
        flash('Error loading user management page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Add new user page (admin only)"""
    form = AddUserForm()
    
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        role = form.role.data
        
        if AuthManager.add_user(username, password, role):
            flash(f'User {username} added successfully with {role} role.', 'success')
            return redirect(url_for('main.users'))
        else:
            flash('Failed to add user. Username may already exist.', 'error')
    
    return render_template('auth/add_user.html', form=form)

@main_bp.route('/users/<username>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(username):
    """Edit user page (admin only)"""
    user_info = AuthManager.get_user_info(username)
    if not user_info:
        flash('User not found.', 'error')
        return redirect(url_for('main.users'))
    
    form = EditUserForm()
    
    if form.validate_on_submit():
        role = form.role.data
        active = form.active.data
        
        if AuthManager.update_user(username, role=role, active=active):
            flash(f'User {username} updated successfully.', 'success')
            return redirect(url_for('main.users'))
        else:
            flash('Failed to update user.', 'error')
    
    # Pre-populate form
    form.role.data = user_info['role']
    form.active.data = user_info['active']
    
    return render_template('auth/edit_user.html', form=form, user=user_info)

@main_bp.route('/users/<username>/delete', methods=['POST'])
@admin_required
def delete_user(username):
    """Delete user (admin only)"""
    try:
        validate_csrf_token()
        
        current_user = AuthManager.get_current_user()
        if username == current_user:
            flash('You cannot delete your own account.', 'error')
            return redirect(url_for('main.users'))
        
        if AuthManager.delete_user(username):
            flash(f'User {username} deleted successfully.', 'success')
        else:
            flash('Failed to delete user. Cannot delete the last admin user.', 'error')
        
        return redirect(url_for('main.users'))
        
    except Exception as e:
        current_app.logger.error(f'Delete user error: {e}')
        flash('Error deleting user.', 'error')
        return redirect(url_for('main.users'))

@main_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    try:
        user_info = AuthManager.get_user_info()
        if not user_info:
            flash('Error loading user information.', 'error')
            return redirect(url_for('main.index'))
        return render_template('auth/profile.html', user=user_info)
    except Exception as e:
        current_app.logger.error(f'Profile page error: {e}', exc_info=True)
        flash('Error loading profile page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/profile/password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password page"""
    form = PasswordChangeForm()
    
    if form.validate_on_submit():
        current_user = AuthManager.get_current_user()
        current_password = form.current_password.data
        new_password = form.new_password.data
        
        if AuthManager.change_password(current_user, current_password, new_password):
            flash('Password changed successfully.', 'success')
            return redirect(url_for('main.profile'))
        else:
            flash('Current password is incorrect.', 'error')
    
    return render_template('auth/change_password.html', form=form)

@main_bp.route('/')
@login_required
def index():
    """Main dashboard - lightweight initial load"""
    try:
        return render_template('index.html')
    except Exception as e:
        current_app.logger.error(f'Dashboard error: {e}')
        flash('Error loading dashboard', 'error')
        return render_template('index.html')

@main_bp.route('/server/status')
@login_required
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
@login_required
def system_info():
    """API endpoint for system version information"""
    try:
        system_info_service = SystemInfoService()
        return jsonify(system_info_service.get_all_versions())
    except Exception as e:
        current_app.logger.error(f'System info error: {e}')
        return jsonify({'error': 'Failed to get system info'}), 500





@main_bp.route('/server/control', methods=['POST'])
@login_required
def server_control():
    """Handle server control actions (start/stop/restart)"""
    try:
        current_app.logger.info(f'Server control request received - Method: {request.method}')
        
        # Validate CSRF token
        validate_csrf_token()
        
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
@login_required
def logs():
    """Enhanced log viewer page with 3 separate content windows"""
    try:
        return render_template('logs.html')
    except Exception as e:
        current_app.logger.error(f'Logs page error: {e}')
        flash('Error loading logs page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/logs/content/<log_type>')
@login_required
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
@login_required
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
@login_required
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
@login_required
def log_stream(log_type):
    """Server-Sent Events endpoint for real-time log streaming"""
    if log_type not in ['latest', 'debug']:
        return jsonify({'error': 'Invalid log type for streaming'}), 400
    
    # Check server status first - disable SSE streaming if server is restarting
    try:
        system_control = SystemControlService()
        server_status = system_control.get_server_status()
        
        # Disable streaming during restart or when server is starting/stopping to prevent hanging
        if server_status.get('status') == 'starting':
            from flask import Response
            def generate_disabled():
                yield f"data: {json.dumps({'type': 'disabled', 'message': 'Log streaming disabled during server startup to prevent hanging', 'server_status': 'starting'})}\n\n"
            
            return Response(
                generate_disabled(),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'
                }
            )
    except Exception as e:
        current_app.logger.warning(f'Failed to check server status for log streaming: {e}')
    
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
            
            # Check if server is starting up to adjust behavior
            server_startup_mode = False
            try:
                from services.system_control import SystemControlService
                system_control = SystemControlService()
                status = system_control.get_server_status()
                server_startup_mode = status.get('status') == 'starting'
            except Exception:
                pass
            
            # Send initial content using simple tail with startup-aware timeout
            try:
                initial_timeout = 10 if server_startup_mode else 5
                result = subprocess.run(['tail', '-n', '500', log_path], capture_output=True, text=True, timeout=initial_timeout)
                if result.returncode == 0 and result.stdout:
                    yield f"data: {json.dumps({'type': 'initial', 'content': result.stdout, 'log_type': log_type, 'startup_mode': server_startup_mode})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'initial', 'content': f'No {log_type} log data available', 'log_type': log_type, 'startup_mode': server_startup_mode})}\n\n"
            except subprocess.TimeoutExpired:
                yield f"data: {json.dumps({'type': 'error', 'error': f'Initial content read timed out - server may be starting up', 'log_type': log_type})}\n\n"
                return
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
                connection_start = time.time()
                file_stat = None
                max_connection_time = 300  # 5 minutes max connection time during startup
                
                # Get initial file stats
                try:
                    file_stat = os.stat(log_path)
                except OSError:
                    file_stat = None
                
                yield f"data: {json.dumps({'type': 'connected', 'log_type': log_type, 'startup_mode': server_startup_mode})}\n\n"
                
                def start_tail_process():
                    """Start a new tail process with startup-aware configuration"""
                    # Use shorter buffer and more responsive settings during startup
                    bufsize = 0 if server_startup_mode else 1
                    
                    process = subprocess.Popen(
                        ['tail', '-f', log_path],  # Use -f instead of -F for better control
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        bufsize=bufsize
                    )
                    
                    # Make stdout non-blocking
                    try:
                        fd = process.stdout.fileno()
                        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os_module.O_NONBLOCK)
                    except Exception as e:
                        current_app.logger.warning(f"Failed to set non-blocking mode for {log_type}: {e}")
                    
                    return process
                
                tail_process = start_tail_process()
                
                # Stream with file rotation detection
                while True:
                    current_time = time.time()
                    
                    # Check for connection timeout during startup to prevent indefinite hanging
                    if server_startup_mode and (current_time - connection_start > max_connection_time):
                        yield f"data: {json.dumps({'type': 'timeout', 'message': 'Connection timed out during server startup - please refresh page', 'log_type': log_type})}\n\n"
                        break
                    
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
                    
                    # Use startup-aware timeout for select() to prevent hanging
                    select_timeout = 0.5 if server_startup_mode else 1.0
                    
                    try:
                        # Use shorter timeout during startup to be more responsive
                        ready, _, _ = select.select([tail_process.stdout], [], [], select_timeout)
                        
                        if ready:
                            try:
                                line = tail_process.stdout.readline()
                                if line:
                                    line = line.rstrip()
                                    if line:
                                        yield f"data: {json.dumps({'type': 'line', 'line': line, 'timestamp': datetime.now().isoformat(), 'log_type': log_type})}\n\n"
                                        last_activity = current_time
                            except (IOError, OSError):
                                # No data available or process died, continue
                                pass
                        else:
                            # Send keepalive more frequently during startup
                            keepalive_interval = 15 if server_startup_mode else 30
                            if current_time - last_activity > keepalive_interval:
                                yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': datetime.now().isoformat(), 'log_type': log_type, 'startup_mode': server_startup_mode})}\n\n"
                                last_activity = current_time
                    except (OSError, IOError) as e:
                        current_app.logger.warning(f"Select error for {log_type} stream: {e}")
                        # Break out of loop to restart process
                        break
                    
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
@login_required
def rotate_log(log_type):
    """API endpoint for rotating (clearing) log files"""
    try:
        current_app.logger.info(f'Request method: {request.method}')
        current_app.logger.info(f'Request headers: {dict(request.headers)}')
        current_app.logger.info(f'Request form data: {dict(request.form)}')
        
        # Validate CSRF token
        validate_csrf_token()
        
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
@login_required
def journal_content():
    """API endpoint for system journal content"""
    try:
        # Get service name from query parameter, default to web manager
        service_name = request.args.get('service', 'vaulthunters_web_manager')
        
        # Validate service name for security
        allowed_services = ['vaulthunters_web_manager', 'caddy']
        if service_name not in allowed_services:
            return jsonify({
                'success': False,
                'error': f'Invalid service name. Allowed: {", ".join(allowed_services)}'
            }), 400
        
        result = subprocess.run(
            ['/bin/journalctl', '--user', '-xeu', f'{service_name}.service', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'content': result.stdout,
                'service': service_name
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Journal command failed: {result.stderr}',
                'service': service_name
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'Journal content error: {e}')
        return jsonify({'error': 'Failed to read journal'}), 500

@main_bp.route('/logs/journal/stream')
@login_required
def journal_stream():
    """Server-Sent Events endpoint for real-time journal streaming"""
    try:
        # Get service name from query parameter, default to web manager
        service_name = request.args.get('service', 'vaulthunters_web_manager')
        
        # Validate service name for security
        allowed_services = ['vaulthunters_web_manager', 'caddy']
        if service_name not in allowed_services:
            return jsonify({
                'success': False,
                'error': f'Invalid service name. Allowed: {", ".join(allowed_services)}'
            }), 400
        
        from flask import Response
        import subprocess
        import threading
        import queue
        
        def generate():
            try:
                # Start with recent journal entries
                initial_result = subprocess.run(
                    ['/bin/journalctl', '--user', '-xeu', f'{service_name}.service', '--no-pager'],
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
                    ['/bin/journalctl', '--user', '-u', f'{service_name}.service', '--follow'],
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
@login_required
def config_editor():
    """Configuration editor page"""
    try:
        return render_template('config.html')
    except Exception as e:
        current_app.logger.error(f'Config editor error: {e}')
        flash('Error loading configuration editor', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/config/files/list')
@login_required
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
@login_required
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
@login_required
def save_config():
    """Save configuration file"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
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
@login_required
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
@login_required
def save_jvm_config():
    """Save JVM configuration file"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
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
@login_required
def apply_aikars_flags():
    """Generate Aikar's flags content (without saving)"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
        config_manager = ConfigManager()
        result = config_manager.generate_aikars_flags_content()
        
        if result['success']:
            current_app.logger.info('Aikar\'s flags content generated successfully')
            return jsonify({
                'success': True,
                'message': 'Aikar\'s flags generated (not saved - click Save to apply)',
                'content': result['content']
            })
        else:
            current_app.logger.error(f'Failed to generate Aikar\'s flags: {result["error"]}')
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        current_app.logger.error(f'Generate Aikar\'s flags error: {e}')
        return jsonify({'error': 'Failed to generate Aikar\'s flags'}), 500

@main_bp.route('/backups')
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
def console():
    """Console page with RCON interface"""
    try:
        return render_template('console.html')
    except Exception as e:
        current_app.logger.error(f'Console page error: {e}')
        flash('Error loading console page', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/console/status')
@login_required
def console_status():
    """Check RCON connection status"""
    from services.rcon_status import RconStatusService
    
    rcon_service = RconStatusService()
    status = rcon_service.get_rcon_status()
    return jsonify(status)

@main_bp.route('/console/execute', methods=['POST'])
@login_required
def console_execute():
    """Execute RCON command"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
        data = request.get_json()
        command = data.get('command', '').strip()
        
        from services.rcon_status import RconStatusService
        
        rcon_service = RconStatusService()
        result = rcon_service.execute_command(command)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400 if 'No command provided' in result.get('error', '') else 500
        
    except Exception as e:
        current_app.logger.error(f'RCON command execution failed: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/console/connect', methods=['POST'])
@login_required
def console_connect():
    """Force RCON reconnection"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
        from services.rcon_status import RconStatusService
        
        rcon_service = RconStatusService()
        result = rcon_service.force_reconnect()
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except Exception as e:
        current_app.logger.error(f'RCON connect failed: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/console/disconnect', methods=['POST'])
@login_required
def console_disconnect():
    """Disconnect RCON connection"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
        from services.rcon_status import RconStatusService
        
        rcon_service = RconStatusService()
        result = rcon_service.disconnect()
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
        
    except Exception as e:
        current_app.logger.error(f'RCON disconnect failed: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/api/players/online')
@login_required
def get_online_players():
    """API endpoint to get current online players (simplified)"""
    try:
        from services.system_control import SystemControlService
        
        # Get current online players directly from mcstatus
        system_control = SystemControlService()
        online_players = system_control.get_current_online_players()
        
        return jsonify({
            'success': True,
            'players': online_players,
            'count': len(online_players)
        })
        
    except Exception as e:
        current_app.logger.error(f'Failed to get online players: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve online players',
            'players': [],
            'count': 0
        }), 500

@main_bp.route('/api/server-properties/validate')
@login_required
def validate_server_properties():
    """API endpoint to validate server.properties configuration"""
    try:
        from services.server_properties_validator import ServerPropertiesValidator
        validator = ServerPropertiesValidator()
        result = validator.validate_properties()
        
        return jsonify({
            'success': True,
            'validation': result
        })
        
    except Exception as e:
        current_app.logger.error(f'Failed to validate server properties: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/api/server-properties/apply', methods=['POST'])
@login_required
def apply_server_properties():
    """API endpoint to auto-configure server.properties"""
    try:
        # Validate CSRF token
        validate_csrf_token()
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        restart_server = data.get('restart_server', False)
        custom_password = data.get('custom_rcon_password', None)
        keep_existing_password = data.get('keep_existing_password', False)
        
        # Validate custom password if provided
        if custom_password and len(custom_password.strip()) < 8:
            return jsonify({
                'success': False,
                'error': 'Custom RCON password must be at least 8 characters long'
            }), 400
        
        current_app.logger.info(f'Server properties apply request: restart={restart_server}, custom_password_provided={bool(custom_password)}')
        
        from services.server_properties_validator import ServerPropertiesValidator
        validator = ServerPropertiesValidator()
        result = validator.auto_configure_properties(
            restart_server=restart_server,
            custom_rcon_password=custom_password,
            keep_existing_password=keep_existing_password
        )
        
        current_app.logger.info(f'Server properties apply result: {result}')
        
        if result['success']:
            return jsonify(result)
        else:
            current_app.logger.error(f'Server properties apply failed: {result}')
            return jsonify(result), 400
        
    except Exception as e:
        current_app.logger.error(f'Failed to apply server properties: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main_bp.route('/favicon.ico')
def favicon():
    """Favicon endpoint"""
    return '', 204

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': 'placeholder',
        'version': '1.0.0-dev'
    })