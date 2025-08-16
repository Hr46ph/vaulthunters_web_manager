import os
import shutil
import logging
import tempfile
from datetime import datetime
from flask import current_app
import re

class ConfigManager:
    """Service for managing configuration file operations"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def get_available_config_files(self):
        """Get list of available configuration files"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return []
            
            config_files = []
            
            # Common Minecraft server config files
            common_configs = [
                'server.properties',
                'ops.json',
                'whitelist.json',
                'banned-players.json',
                'banned-ips.json',
                'usercache.json'
            ]
            
            for config_name in common_configs:
                config_path = f'{server_path}/{config_name}'
                if os.path.exists(config_path):
                    stat = os.stat(config_path)
                    config_files.append({
                        'name': config_name,
                        'path': config_path,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'type': self._get_config_type(config_name)
                    })
            
            # Look for mod configs in config directory
            config_dir = f'{server_path}/config'
            if os.path.exists(config_dir):
                for root, dirs, files in os.walk(config_dir):
                    for file in files:
                        if file.endswith(('.cfg', '.conf', '.properties', '.json', '.yaml', '.yml', '.toml')):
                            config_path = os.path.join(root, file)
                            rel_path = os.path.relpath(config_path, server_path)
                            stat = os.stat(config_path)
                            config_files.append({
                                'name': rel_path,
                                'path': config_path,
                                'size': stat.st_size,
                                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                'type': self._get_config_type(file)
                            })
            
            return sorted(config_files, key=lambda x: x['name'])
            
        except Exception as e:
            self.logger.error(f"Error getting config files: {e}")
            return []
    
    def _get_config_type(self, filename):
        """Determine config file type based on filename"""
        if filename.endswith('.properties'):
            return 'properties'
        elif filename.endswith('.json'):
            return 'json'
        elif filename.endswith(('.yaml', '.yml')):
            return 'yaml'
        elif filename.endswith('.toml'):
            return 'toml'
        elif filename.endswith(('.cfg', '.conf')):
            return 'config'
        else:
            return 'text'
    
    def read_config_file(self, config_path):
        """Read and return config file content"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {'success': False, 'error': 'Server path not configured'}
            
            # Security check - ensure path is within server directory
            real_server_path = os.path.realpath(server_path)
            real_config_path = os.path.realpath(config_path)
            
            if not real_config_path.startswith(real_server_path):
                return {'success': False, 'error': 'Access denied: Path outside server directory'}
            
            if not os.path.exists(config_path):
                return {'success': False, 'error': f'Config file not found: {config_path}'}
            
            # Check if file is too large (limit to 1MB for web editing)
            file_size = os.path.getsize(config_path)
            if file_size > 1024 * 1024:
                return {'success': False, 'error': 'File too large for web editing (max 1MB)'}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                'success': True,
                'content': content,
                'path': config_path,
                'size': file_size,
                'type': self._get_config_type(os.path.basename(config_path))
            }
            
        except UnicodeDecodeError:
            return {'success': False, 'error': 'File contains non-UTF8 content'}
        except PermissionError:
            return {'success': False, 'error': 'Permission denied reading file'}
        except Exception as e:
            self.logger.error(f"Error reading config file: {e}")
            return {'success': False, 'error': str(e)}
    
    def write_config_file(self, config_path, content, create_backup=True):
        """Write content to config file with optional backup"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {'success': False, 'error': 'Server path not configured'}
            
            # Security check - ensure path is within server directory
            real_server_path = os.path.realpath(server_path)
            real_config_path = os.path.realpath(config_path)
            
            if not real_config_path.startswith(real_server_path):
                return {'success': False, 'error': 'Access denied: Path outside server directory'}
            
            if not os.path.exists(config_path):
                return {'success': False, 'error': f'Config file not found: {config_path}'}
            
            # Validate content based on file type
            validation_result = self._validate_config_content(config_path, content)
            if not validation_result['valid']:
                return {'success': False, 'error': f'Invalid content: {validation_result["error"]}'}
            
            # Create backup if requested
            backup_path = None
            if create_backup:
                backup_result = self._create_config_backup(config_path)
                if not backup_result['success']:
                    return backup_result
                backup_path = backup_result['backup_path']
            
            # Write to temporary file first
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, 
                                           dir=os.path.dirname(config_path)) as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name
            
            # Replace original file atomically
            shutil.move(temp_path, config_path)
            
            # Preserve original file permissions
            if backup_path:
                backup_stat = os.stat(backup_path)
                os.chmod(config_path, backup_stat.st_mode)
            
            return {
                'success': True,
                'message': 'Configuration file updated successfully',
                'backup_created': backup_path is not None,
                'backup_path': backup_path
            }
            
        except PermissionError:
            return {'success': False, 'error': 'Permission denied writing file'}
        except Exception as e:
            self.logger.error(f"Error writing config file: {e}")
            # Clean up temp file if it exists
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            return {'success': False, 'error': str(e)}
    
    def _validate_config_content(self, config_path, content):
        """Validate config file content based on file type"""
        try:
            filename = os.path.basename(config_path)
            file_type = self._get_config_type(filename)
            
            if file_type == 'json':
                import json
                json.loads(content)
            elif file_type == 'yaml':
                try:
                    import yaml
                    yaml.safe_load(content)
                except ImportError:
                    pass  # Skip YAML validation if PyYAML not installed
            elif file_type == 'properties':
                # Basic properties file validation
                for line_num, line in enumerate(content.split('\n'), 1):
                    line = line.strip()
                    if line and not line.startswith('#') and '=' not in line:
                        return {'valid': False, 'error': f'Invalid properties format at line {line_num}'}
            
            return {'valid': True}
            
        except json.JSONDecodeError as e:
            return {'valid': False, 'error': f'Invalid JSON: {str(e)}'}
        except yaml.YAMLError as e:
            return {'valid': False, 'error': f'Invalid YAML: {str(e)}'}
        except Exception as e:
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    def _create_config_backup(self, config_path):
        """Create a timestamped backup of the config file"""
        try:
            if not os.path.exists(config_path):
                return {'success': False, 'error': 'Original file not found'}
            
            # Create backups directory
            backups_dir = f'{os.path.dirname(config_path)}/config_backups'
            os.makedirs(backups_dir, exist_ok=True)
            
            # Generate backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.basename(config_path)
            backup_filename = f'{filename}.{timestamp}.backup'
            backup_path = f'{backups_dir}/{backup_filename}'
            
            # Copy file
            shutil.copy2(config_path, backup_path)
            
            return {'success': True, 'backup_path': backup_path}
            
        except Exception as e:
            self.logger.error(f"Error creating backup: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_config_backups(self, config_path):
        """Get list of available backups for a config file"""
        try:
            filename = os.path.basename(config_path)
            backups_dir = f'{os.path.dirname(config_path)}/config_backups'
            
            if not os.path.exists(backups_dir):
                return []
            
            backups = []
            backup_pattern = f'{filename}.*.backup'
            
            for backup_file in os.listdir(backups_dir):
                if re.match(backup_pattern.replace('*', r'\d{8}_\d{6}'), backup_file):
                    backup_path = f'{backups_dir}/{backup_file}'
                    stat = os.stat(backup_path)
                    
                    # Extract timestamp from filename
                    timestamp_match = re.search(r'\.(\d{8}_\d{6})\.backup$', backup_file)
                    if timestamp_match:
                        timestamp_str = timestamp_match.group(1)
                        created = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                        
                        backups.append({
                            'filename': backup_file,
                            'path': backup_path,
                            'size': stat.st_size,
                            'created': created.isoformat()
                        })
            
            return sorted(backups, key=lambda x: x['created'], reverse=True)
            
        except Exception as e:
            self.logger.error(f"Error getting config backups: {e}")
            return []
    
    def restore_config_backup(self, config_path, backup_path):
        """Restore a config file from backup"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {'success': False, 'error': 'Server path not configured'}
            
            # Security checks
            real_server_path = os.path.realpath(server_path)
            real_config_path = os.path.realpath(config_path)
            real_backup_path = os.path.realpath(backup_path)
            
            if not real_config_path.startswith(real_server_path):
                return {'success': False, 'error': 'Access denied: Config path outside server directory'}
            
            if not real_backup_path.startswith(real_server_path):
                return {'success': False, 'error': 'Access denied: Backup path outside server directory'}
            
            if not os.path.exists(backup_path):
                return {'success': False, 'error': 'Backup file not found'}
            
            # Create current backup before restore
            current_backup = self._create_config_backup(config_path)
            if not current_backup['success']:
                return {'success': False, 'error': f'Failed to backup current config: {current_backup["error"]}'}
            
            # Restore from backup
            shutil.copy2(backup_path, config_path)
            
            return {
                'success': True,
                'message': 'Configuration restored from backup',
                'current_backup': current_backup['backup_path']
            }
            
        except Exception as e:
            self.logger.error(f"Error restoring config backup: {e}")
            return {'success': False, 'error': str(e)}
    
    def read_jvm_args_file(self, file_type):
        """Read JVM args file (user_jvm_args.txt or unix_args.txt)"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {'success': False, 'error': 'Server path not configured'}
            
            if file_type == 'user_jvm_args':
                file_path = os.path.join(server_path, 'user_jvm_args.txt')
            elif file_type == 'unix_args':
                file_path = os.path.join(server_path, 'libraries/net/minecraftforge/forge/1.18.2-40.2.9/unix_args.txt')
            else:
                return {'success': False, 'error': 'Invalid file type'}
            
            if not os.path.exists(file_path):
                # Create user_jvm_args.txt if it doesn't exist
                if file_type == 'user_jvm_args':
                    with open(file_path, 'w') as f:
                        f.write('# JVM Arguments\n# Add your JVM arguments here, one per line\n')
                    return {'success': True, 'content': '# JVM Arguments\n# Add your JVM arguments here, one per line\n'}
                else:
                    return {'success': False, 'error': f'File not found: {file_path}'}
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {'success': True, 'content': content}
            
        except UnicodeDecodeError:
            return {'success': False, 'error': 'File contains non-UTF8 content'}
        except PermissionError:
            return {'success': False, 'error': 'Permission denied reading file'}
        except Exception as e:
            self.logger.error(f"Error reading JVM args file: {e}")
            return {'success': False, 'error': str(e)}
    
    def write_jvm_args_file(self, file_type, content):
        """Write JVM args file"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {'success': False, 'error': 'Server path not configured'}
            
            if file_type == 'user_jvm_args':
                file_path = os.path.join(server_path, 'user_jvm_args.txt')
            elif file_type == 'unix_args':
                file_path = os.path.join(server_path, 'libraries/net/minecraftforge/forge/1.18.2-40.2.9/unix_args.txt')
            else:
                return {'success': False, 'error': 'Invalid file type'}
            
            # Create backup if file exists
            backup_path = None
            if os.path.exists(file_path):
                backup_result = self._create_config_backup(file_path)
                if backup_result['success']:
                    backup_path = backup_result['backup_path']
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write to temporary file first
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, 
                                           dir=os.path.dirname(file_path)) as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name
            
            # Replace original file atomically
            shutil.move(temp_path, file_path)
            
            return {
                'success': True,
                'message': f'{file_type}.txt updated successfully',
                'backup_created': backup_path is not None,
                'backup_path': backup_path
            }
            
        except PermissionError:
            return {'success': False, 'error': 'Permission denied writing file'}
        except Exception as e:
            self.logger.error(f"Error writing JVM args file: {e}")
            # Clean up temp file if it exists
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            return {'success': False, 'error': str(e)}
    
    def apply_aikars_flags(self):
        """Apply Aikar's flags to user_jvm_args.txt"""
        try:
            # Get Aikar's flags from config.toml
            aikars_flags = self._get_aikars_flags_from_config()
            if not aikars_flags:
                return {'success': False, 'error': 'Could not load Aikar\'s flags from configuration'}
            
            # Build JVM args content
            content_lines = [
                '# Aikar\'s Flags - Optimized JVM arguments for Minecraft servers',
                '# Source: https://docs.papermc.io/paper/aikars-flags/',
                '# Applied on: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                '',
                '# Memory allocation (adjust -Xms and -Xmx based on your system)',
                '-Xms4G',
                '-Xmx8G',
                '',
                '# Aikar\'s optimization flags',
            ]
            
            # Add each flag
            for flag in aikars_flags:
                content_lines.append(f'-{flag}')
            
            content = '\n'.join(content_lines) + '\n'
            
            # Write to user_jvm_args.txt
            result = self.write_jvm_args_file('user_jvm_args', content)
            
            if result['success']:
                result['message'] = 'Aikar\'s flags applied successfully'
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error applying Aikar's flags: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_aikars_flags_from_config(self):
        """Get Aikar's flags from config.toml"""
        try:
            # Try to read from config.toml
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return None
            
            # Look for config.toml in the project root (parent of server path)
            project_root = os.path.dirname(os.path.dirname(server_path))
            config_toml_path = os.path.join(project_root, 'config.toml')
            
            if not os.path.exists(config_toml_path):
                # Fallback to hardcoded Aikar's flags
                return self._get_default_aikars_flags()
            
            try:
                import toml
                with open(config_toml_path, 'r') as f:
                    config_data = toml.load(f)
                
                jvm_config = config_data.get('jvm', {})
                optimization_flags = jvm_config.get('optimization_flags', [])
                system_properties = jvm_config.get('system_properties', [])
                
                # Combine optimization flags and system properties
                all_flags = []
                all_flags.extend(optimization_flags)
                
                # Add system properties with -D prefix
                for prop in system_properties:
                    all_flags.append(f'D{prop}')
                
                return all_flags if all_flags else self._get_default_aikars_flags()
                
            except ImportError:
                # toml library not available, use defaults
                return self._get_default_aikars_flags()
            
        except Exception as e:
            self.logger.warning(f"Could not read config.toml: {e}")
            return self._get_default_aikars_flags()
    
    def _get_default_aikars_flags(self):
        """Get default Aikar's flags if config.toml is not available"""
        return [
            'UseG1GC',
            'ParallelRefProcEnabled',
            'MaxGCPauseMillis=200',
            'UnlockExperimentalVMOptions',
            'DisableExplicitGC',
            'AlwaysPreTouch',
            'G1NewSizePercent=30',
            'G1MaxNewSizePercent=40',
            'G1HeapRegionSize=8M',
            'G1ReservePercent=20',
            'G1HeapWastePercent=5',
            'G1MixedGCCountTarget=4',
            'InitiatingHeapOccupancyPercent=15',
            'G1MixedGCLiveThresholdPercent=90',
            'G1RSetUpdatingPauseTimePercent=5',
            'SurvivorRatio=32',
            'PerfDisableSharedMem',
            'MaxTenuringThreshold=1',
            'Dusing.aikars.flags=https://mcflags.emc.gs',
            'Daikars.new.flags=true'
        ]