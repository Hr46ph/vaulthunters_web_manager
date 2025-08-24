"""
Server properties validation service for VaultHunters Web Manager.

Validates required server.properties settings and provides auto-configuration.
"""

import os
import logging
import tempfile
import shutil
from typing import Dict, List, Tuple, Optional
from flask import current_app
from services.server_properties import ServerPropertiesParser
from services.config_manager import ConfigManager

class ServerPropertiesValidator:
    """Validator for required server.properties settings."""
    
    # Required settings for web manager functionality
    REQUIRED_SETTINGS = {
        'enable-query': {
            'required_value': 'true',
            'default_value': 'false',
            'name': 'Query Protocol',
            'description': 'Enables GameSpy4 protocol for server queries. Required for player count and server status checks.',
            'security_note': 'Security Risk: When exposing server to internet, only forward TCP traffic to query port, NOT UDP to prevent DDoS amplification attacks.',
            'technical_details': 'Used by the web manager to get real-time player counts and server information via mcstatus library.'
        },
        'enable-rcon': {
            'required_value': 'true', 
            'default_value': 'false',
            'name': 'RCON (Remote Console)',
            'description': 'Enables remote console access for server administration. Required for integrated console and server control.',
            'security_note': 'Ensure RCON password is strong and RCON port is not exposed to internet.',
            'technical_details': 'Used by the web manager for server commands, graceful shutdowns, and the integrated console interface.'
        },
        'enable-status': {
            'required_value': 'true',
            'default_value': 'true', 
            'name': 'Server List Status',
            'description': 'Enables server list ping responses. Required for server status monitoring.',
            'security_note': 'Generally safe to expose. Provides basic server information to client server browsers.',
            'technical_details': 'Used by the web manager to monitor server availability and basic status information.'
        },
        'rcon.password': {
            'required_value': None,  # Any non-empty value
            'default_value': '',
            'name': 'RCON Password',
            'description': 'Password for RCON access. Must be set when RCON is enabled.',
            'security_note': 'Use a strong, unique password. Never share this password or expose RCON port to internet.',
            'technical_details': 'Authentication credential for the web manager\'s RCON client connections.',
            'validation_type': 'non_empty'
        }
    }
    
    def __init__(self, server_path: Optional[str] = None):
        """Initialize validator with optional server path."""
        self.server_path = server_path or current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
        self.properties_file = os.path.join(self.server_path, 'server.properties')
        self.parser = ServerPropertiesParser(server_path)
        self.config_manager = ConfigManager()
        self.logger = current_app.logger
        
    def validate_properties(self) -> Dict:
        """Validate all required properties and return detailed results."""
        try:
            # Load properties
            if not self.parser.load_properties():
                return {
                    'valid': False,
                    'error': f'Could not load server.properties from {self.properties_file}',
                    'file_exists': os.path.exists(self.properties_file),
                    'issues': [],
                    'missing_settings': list(self.REQUIRED_SETTINGS.keys())
                }
            
            issues = []
            missing_settings = []
            all_properties = self.parser.get_all_properties()
            
            # Check each required setting
            for setting_key, setting_info in self.REQUIRED_SETTINGS.items():
                current_value = all_properties.get(setting_key, setting_info['default_value'])
                
                # Validate based on setting type
                if setting_info.get('validation_type') == 'non_empty':
                    # For password fields, just check if non-empty
                    if not current_value or current_value.strip() == '':
                        issues.append({
                            'setting': setting_key,
                            'current_value': current_value or '(not set)',
                            'required_value': '(non-empty password)',
                            'name': setting_info['name'],
                            'description': setting_info['description'],
                            'security_note': setting_info['security_note'],
                            'technical_details': setting_info['technical_details'],
                            'severity': 'critical' if setting_key == 'rcon.password' else 'warning'
                        })
                        missing_settings.append(setting_key)
                else:
                    # For boolean/exact value settings
                    required_value = setting_info['required_value']
                    if current_value != required_value:
                        issues.append({
                            'setting': setting_key,
                            'current_value': current_value,
                            'required_value': required_value,
                            'name': setting_info['name'],
                            'description': setting_info['description'],
                            'security_note': setting_info['security_note'],
                            'technical_details': setting_info['technical_details'],
                            'severity': 'critical'
                        })
                        missing_settings.append(setting_key)
            
            # Check if RCON password already exists (for UI logic)
            current_password = all_properties.get('rcon.password', '').strip()
            has_rcon_password = bool(current_password)
            
            return {
                'valid': len(issues) == 0,
                'file_exists': True,
                'issues': issues,
                'missing_settings': missing_settings,
                'total_issues': len(issues),
                'critical_issues': len([i for i in issues if i['severity'] == 'critical']),
                'warning_issues': len([i for i in issues if i['severity'] == 'warning']),
                'has_rcon_password': has_rcon_password
            }
            
        except Exception as e:
            self.logger.error(f'Error validating server.properties: {e}')
            return {
                'valid': False,
                'error': str(e),
                'file_exists': os.path.exists(self.properties_file),
                'issues': [],
                'missing_settings': list(self.REQUIRED_SETTINGS.keys())
            }
    
    def auto_configure_properties(self, restart_server: bool = False, custom_rcon_password: Optional[str] = None, keep_existing_password: bool = False) -> Dict:
        """Auto-configure required properties with optional server restart."""
        try:
            validation_result = self.validate_properties()
            
            if validation_result['valid']:
                return {
                    'success': True,
                    'message': 'Server properties already properly configured',
                    'changes_made': [],
                    'restart_required': False
                }
            
            if not validation_result['file_exists']:
                return {
                    'success': False,
                    'error': 'server.properties file does not exist'
                }
            
            # Read current properties file
            config_result = self.config_manager.read_config_file(self.properties_file)
            if not config_result['success']:
                return {
                    'success': False,
                    'error': f'Could not read server.properties: {config_result["error"]}'
                }
            
            current_content = config_result['content']
            modified_content = current_content
            changes_made = []
            
            # Process each missing setting
            for issue in validation_result['issues']:
                setting_key = issue['setting']
                required_value = issue['required_value']
                current_value = issue['current_value']
                
                # Special handling for RCON password
                if setting_key == 'rcon.password':
                    # Check if user wants to keep existing password
                    if keep_existing_password:
                        # Skip password update entirely
                        continue
                    
                    # Only update password if it's actually empty/unset
                    # The issue is only added when password is empty, so we should update it
                    if custom_rcon_password:
                        new_value = custom_rcon_password
                    else:
                        # Check current RCON state to determine if we need to generate a password
                        all_properties = self.parser.get_all_properties()
                        enable_rcon = all_properties.get('enable-rcon', 'false')
                        current_password = all_properties.get('rcon.password', '').strip()
                        
                        # Only generate password if:
                        # 1. RCON is being enabled (enable-rcon=true in issues) OR already enabled
                        # 2. AND password is actually empty
                        if not current_password:
                            # Generate secure random password
                            import secrets
                            import string
                            chars = string.ascii_letters + string.digits
                            new_value = ''.join(secrets.choice(chars) for _ in range(16))
                        else:
                            # Password already exists, skip this update
                            continue
                    
                    changes_made.append({
                        'setting': setting_key,
                        'old_value': current_value,
                        'new_value': '(hidden for security)',
                        'display_name': issue['name']
                    })
                else:
                    new_value = required_value
                    changes_made.append({
                        'setting': setting_key,
                        'old_value': current_value,
                        'new_value': new_value,
                        'display_name': issue['name']
                    })
                
                # Update content
                modified_content = self._update_property_in_content(
                    modified_content, setting_key, new_value, current_value
                )
            
            # Write updated properties file
            write_result = self.config_manager.write_config_file(
                self.properties_file, 
                modified_content, 
                create_backup=True
            )
            
            if not write_result['success']:
                return {
                    'success': False,
                    'error': f'Failed to update server.properties: {write_result["error"]}'
                }
            
            # Force reload of properties to ensure validation reflects the changes
            self.parser.reload()
            
            # Handle server restart if requested
            restart_performed = False
            if restart_server:
                restart_result = self._restart_server_if_running()
                restart_performed = restart_result['restarted']
            
            return {
                'success': True,
                'message': f'Successfully configured {len(changes_made)} server properties',
                'changes_made': changes_made,
                'backup_created': write_result.get('backup_created', False),
                'backup_path': write_result.get('backup_path'),
                'restart_required': not restart_performed,
                'restart_performed': restart_performed
            }
            
        except Exception as e:
            self.logger.error(f'Error auto-configuring server.properties: {e}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def _update_property_in_content(self, content: str, key: str, new_value: str, current_value: str) -> str:
        """Update a property in the content string."""
        lines = content.split('\n')
        updated_lines = []
        property_found = False
        
        for line in lines:
            stripped_line = line.strip()
            
            # Skip comments and empty lines
            if not stripped_line or stripped_line.startswith('#'):
                updated_lines.append(line)
                continue
            
            # Check if this is the property we're looking for
            if '=' in stripped_line:
                prop_key = stripped_line.split('=', 1)[0].strip()
                if prop_key == key:
                    # Replace the property
                    updated_lines.append(f'{key}={new_value}')
                    property_found = True
                    continue
            
            updated_lines.append(line)
        
        # If property wasn't found, add it at the end
        if not property_found:
            updated_lines.append(f'{key}={new_value}')
        
        return '\n'.join(updated_lines)
    
    def _restart_server_if_running(self) -> Dict:
        """Restart the server if it's currently running."""
        try:
            from services.system_control import SystemControlService
            system_control = SystemControlService()
            
            # Check if server is running
            status = system_control.get_server_status()
            self.logger.info(f'Server status check for restart: {status}')
            
            if not status.get('running', False):
                self.logger.info('Server is not running, skipping restart')
                return {
                    'restarted': False,
                    'message': 'Server was not running, no restart needed'
                }
            
            self.logger.info('Attempting to stop server for restart...')
            # Stop the server
            stop_result = system_control.stop_server()
            self.logger.info(f'Server stop result: {stop_result}')
            
            if not stop_result.get('success', False):
                self.logger.error(f'Failed to stop server: {stop_result.get("error", "Unknown error")}')
                return {
                    'restarted': False,
                    'error': f'Failed to stop server: {stop_result.get("error", "Unknown error")}'
                }
            
            # Wait a moment for graceful shutdown
            import time
            self.logger.info('Waiting 3 seconds for graceful shutdown...')
            time.sleep(3)
            
            self.logger.info('Attempting to start server...')
            # Start the server
            start_result = system_control.start_server()
            self.logger.info(f'Server start result: {start_result}')
            
            if not start_result.get('success', False):
                self.logger.error(f'Failed to start server: {start_result.get("error", "Unknown error")}')
                return {
                    'restarted': False,
                    'error': f'Failed to start server: {start_result.get("error", "Unknown error")}'
                }
            
            self.logger.info('Server restart completed successfully')
            return {
                'restarted': True,
                'message': 'Server successfully restarted with new configuration'
            }
            
        except Exception as e:
            self.logger.error(f'Error restarting server: {e}', exc_info=True)
            return {
                'restarted': False,
                'error': str(e)
            }
    
    def get_validation_summary(self) -> Dict:
        """Get a summary of validation status for dashboard display."""
        try:
            result = self.validate_properties()
            
            if not result['file_exists']:
                return {
                    'status': 'error',
                    'message': 'server.properties file not found',
                    'details': 'Configuration file is missing'
                }
            
            if result['valid']:
                return {
                    'status': 'success',
                    'message': 'All required settings properly configured',
                    'details': 'Web manager functionality fully enabled'
                }
            
            critical_count = result.get('critical_issues', 0)
            warning_count = result.get('warning_issues', 0)
            
            if critical_count > 0:
                return {
                    'status': 'critical',
                    'message': f'{critical_count} critical issues found',
                    'details': f'{result["total_issues"]} total configuration issues require attention'
                }
            else:
                return {
                    'status': 'warning',
                    'message': f'{warning_count} warnings found',
                    'details': 'Non-critical issues that should be addressed'
                }
                
        except Exception as e:
            self.logger.error(f'Error getting validation summary: {e}')
            return {
                'status': 'error',
                'message': 'Validation check failed',
                'details': str(e)
            }
    
    def generate_rcon_password(self) -> str:
        """Generate a secure RCON password."""
        import secrets
        import string
        
        # Use a mix of uppercase, lowercase letters, and numbers
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(16))