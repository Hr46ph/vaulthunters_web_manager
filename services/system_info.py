import subprocess
import os
import json
from flask import current_app


class SystemInfoService:
    """Service for collecting system version information"""
    
    def __init__(self):
        pass
    
    def get_java_version(self):
        """Get Java version information"""
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
                        return 'OpenJDK ' + first_line.split('"')[1] if '"' in first_line else 'OpenJDK (version unknown)'
                    elif 'java version' in first_line.lower():
                        return 'Oracle JDK ' + first_line.split('"')[1] if '"' in first_line else 'Oracle JDK (version unknown)'
                    else:
                        return first_line.strip()
                else:
                    return 'Unknown'
            else:
                return 'Unknown'
        except Exception as e:
            current_app.logger.warning(f'Failed to get Java version: {e}')
            return 'Unknown'
    
    def get_vaulthunters_version(self):
        """Get VaultHunters version from server data"""
        try:
            server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
            data_json_path = os.path.join(server_path, 'data', 'the_vault', 'data.json')
            if os.path.exists(data_json_path):
                with open(data_json_path, 'r') as f:
                    data = json.load(f)
                    return data.get('version', 'Unknown')
            else:
                return 'Not found'
        except Exception as e:
            current_app.logger.warning(f'Failed to get VaultHunters version: {e}')
            return 'Unknown'
    
    def get_kernel_version(self):
        """Get Linux kernel version"""
        try:
            result = subprocess.run(['uname', '-r'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return 'Unknown'
        except Exception as e:
            current_app.logger.warning(f'Failed to get kernel version: {e}')
            return 'Unknown'
    
    def get_python_version(self):
        """Get Python version"""
        try:
            result = subprocess.run(['python3', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip().replace('Python ', '')
            else:
                return 'Unknown'
        except Exception as e:
            current_app.logger.warning(f'Failed to get Python version: {e}')
            return 'Unknown'
    
    def get_all_versions(self):
        """Get all version information as a dictionary"""
        return {
            'java': self.get_java_version(),
            'vaulthunters': self.get_vaulthunters_version(),
            'kernel': self.get_kernel_version(),
            'python': self.get_python_version()
        }