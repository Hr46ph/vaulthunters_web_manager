import subprocess
import logging
import os
import glob
from datetime import datetime
from flask import current_app

class LogService:
    """Service for reading various log files and systemd journal"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_service_journal(self, service_name, lines=100):
        """Get systemd journal logs for a service"""
        # Try with sudo first
        try:
            result = subprocess.run(
                ['sudo', '/bin/journalctl', '-u', f'{service_name}.service', '-n', str(lines), '--no-pager'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'logs': result.stdout,
                    'service': service_name
                }
            else:
                # If sudo fails, try without sudo (user might have access)
                return self._get_journal_without_sudo(service_name, lines)
                
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout reading service journal")
            return {
                'success': False,
                'error': 'Timeout reading service logs',
                'service': service_name
            }
        except Exception as e:
            self.logger.error(f"Error reading service journal with sudo: {e}")
            # Try without sudo as fallback
            return self._get_journal_without_sudo(service_name, lines)
    
    def _get_journal_without_sudo(self, service_name, lines=100):
        """Fallback method to read journal without sudo"""
        try:
            result = subprocess.run(
                ['/bin/journalctl', '-u', f'{service_name}.service', '-n', str(lines), '--no-pager'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'logs': result.stdout,
                    'service': service_name
                }
            else:
                error_msg = result.stderr.strip() or 'Failed to read journal (check permissions)'
                self.logger.error(f"Journal read failed without sudo: {error_msg}")
                return {
                    'success': False,
                    'error': f'Permission denied. Add journalctl commands to sudoers: {error_msg}',
                    'service': service_name
                }
                
        except Exception as e:
            self.logger.error(f"Error reading service journal without sudo: {e}")
            return {
                'success': False,
                'error': f'Cannot read journal. Please add journalctl permissions to sudoers: {str(e)}',
                'service': service_name
            }
    
    def get_web_manager_journal(self, lines=50):
        """Get journal logs for the web manager service itself"""
        web_service_name = 'vaulthunter_web_manager'
        return self.get_service_journal(web_service_name, lines)
    
    def get_minecraft_server_logs(self, log_type='latest', lines=100):
        """Get Minecraft server log files"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {
                    'success': False,
                    'error': 'Server path not configured',
                    'logs': ''
                }
            
            log_file_map = {
                'latest': f'{server_path}/logs/latest.log',
                'debug': f'{server_path}/logs/debug.log',
                'crash': f'{server_path}/crash-reports'
            }
            
            if log_type == 'crash':
                return self._get_crash_reports(server_path)
            
            log_file = log_file_map.get(log_type)
            if not log_file:
                return {
                    'success': False,
                    'error': f'Unknown log type: {log_type}',
                    'logs': ''
                }
            
            if not os.path.exists(log_file):
                return {
                    'success': False,
                    'error': f'Log file not found: {log_file}',
                    'logs': ''
                }
            
            result = subprocess.run(
                ['tail', '-n', str(lines), log_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'logs': result.stdout,
                    'log_type': log_type,
                    'log_file': log_file
                }
            else:
                return {
                    'success': False,
                    'error': f'Could not read {log_file}',
                    'logs': ''
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Timeout reading log file',
                'logs': ''
            }
        except Exception as e:
            self.logger.error(f"Error reading log file: {e}")
            return {
                'success': False,
                'error': str(e),
                'logs': ''
            }
    
    def _get_crash_reports(self, server_path):
        """Get list and content of crash reports"""
        try:
            crash_dir = f'{server_path}/crash-reports'
            if not os.path.exists(crash_dir):
                return {
                    'success': True,
                    'logs': 'No crash reports found',
                    'log_type': 'crash',
                    'crash_files': []
                }
            
            crash_files = glob.glob(f'{crash_dir}/crash-*.txt')
            crash_files.sort(key=os.path.getmtime, reverse=True)
            
            if not crash_files:
                return {
                    'success': True,
                    'logs': 'No crash reports found',
                    'log_type': 'crash',
                    'crash_files': []
                }
            
            # Get the most recent crash report
            latest_crash = crash_files[0]
            with open(latest_crash, 'r') as f:
                crash_content = f.read()
            
            crash_file_info = []
            for crash_file in crash_files[:10]:  # Limit to 10 most recent
                stat = os.stat(crash_file)
                crash_file_info.append({
                    'filename': os.path.basename(crash_file),
                    'path': crash_file,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            
            return {
                'success': True,
                'logs': crash_content,
                'log_type': 'crash',
                'crash_files': crash_file_info,
                'latest_crash': os.path.basename(latest_crash)
            }
            
        except Exception as e:
            self.logger.error(f"Error reading crash reports: {e}")
            return {
                'success': False,
                'error': str(e),
                'logs': '',
                'crash_files': []
            }
    
    def get_available_log_files(self):
        """Get list of available log files"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return []
            
            log_files = []
            
            # Main log files
            main_logs = ['latest.log', 'debug.log']
            logs_dir = f'{server_path}/logs'
            
            if os.path.exists(logs_dir):
                for log_name in main_logs:
                    log_path = f'{logs_dir}/{log_name}'
                    if os.path.exists(log_path):
                        stat = os.stat(log_path)
                        log_files.append({
                            'name': log_name,
                            'type': log_name.replace('.log', ''),
                            'path': log_path,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
                
                # Historical log files
                historical_logs = glob.glob(f'{logs_dir}/*.log.gz')
                for log_path in sorted(historical_logs, key=os.path.getmtime, reverse=True)[:5]:
                    stat = os.stat(log_path)
                    log_files.append({
                        'name': os.path.basename(log_path),
                        'type': 'historical',
                        'path': log_path,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
            
            # Crash reports
            crash_dir = f'{server_path}/crash-reports'
            if os.path.exists(crash_dir):
                crash_count = len(glob.glob(f'{crash_dir}/crash-*.txt'))
                if crash_count > 0:
                    log_files.append({
                        'name': f'Crash Reports ({crash_count})',
                        'type': 'crash',
                        'path': crash_dir,
                        'size': 0,
                        'modified': datetime.now().isoformat()
                    })
            
            return log_files
            
        except Exception as e:
            self.logger.error(f"Error getting available log files: {e}")
            return []
    
    def tail_log_file(self, log_type, lines=50, follow=False):
        """Tail a log file with optional follow mode for real-time updates"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH')
            if not server_path:
                return {'success': False, 'error': 'Server path not configured'}
            
            log_file_map = {
                'latest': f'{server_path}/logs/latest.log',
                'debug': f'{server_path}/logs/debug.log'
            }
            
            log_file = log_file_map.get(log_type)
            if not log_file or not os.path.exists(log_file):
                return {'success': False, 'error': f'Log file not found: {log_type}'}
            
            cmd = ['tail', '-n', str(lines)]
            if follow:
                cmd.append('-f')
            cmd.append(log_file)
            
            if follow:
                # For real-time following, we need a different approach
                # This would typically be used with WebSocket or Server-Sent Events
                return {'success': False, 'error': 'Real-time following not implemented yet'}
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return {
                        'success': True,
                        'logs': result.stdout,
                        'log_type': log_type
                    }
                else:
                    return {'success': False, 'error': f'Failed to read {log_file}'}
            
        except Exception as e:
            self.logger.error(f"Error tailing log file: {e}")
            return {'success': False, 'error': str(e)}