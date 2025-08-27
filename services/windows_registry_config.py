#!/usr/bin/env python3

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
from datetime import datetime

# Conditional import for Windows registry
try:
    import winreg
except ImportError:
    winreg = None

class WindowsRegistryConfig:
    """Windows registry-based configuration management"""
    
    # Registry paths
    BASE_KEY = winreg.HKEY_LOCAL_MACHINE if winreg else None
    SOFTWARE_KEY = r"SOFTWARE\VaultHunters\WebManager"
    SERVICE_KEY = r"SYSTEM\CurrentControlSet\Services\VaultHuntersWebManager"
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.is_available = winreg is not None
        
        if not self.is_available:
            self.logger.warning("Windows registry not available on this platform")
    
    def is_registry_available(self) -> bool:
        """Check if Windows registry is available"""
        return self.is_available
    
    def create_registry_structure(self) -> bool:
        """Create the registry structure for VaultHunters Web Manager"""
        if not self.is_available:
            return False
        
        try:
            # Create main software key
            software_key = winreg.CreateKey(self.BASE_KEY, self.SOFTWARE_KEY)
            winreg.CloseKey(software_key)
            
            # Create configuration subkeys
            config_keys = [
                "Installation",
                "Server",
                "Web",
                "Paths",
                "Service"
            ]
            
            for subkey in config_keys:
                key_path = f"{self.SOFTWARE_KEY}\\{subkey}"
                key = winreg.CreateKey(self.BASE_KEY, key_path)
                winreg.CloseKey(key)
            
            self.logger.info("Registry structure created successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create registry structure: {e}")
            return False
    
    def set_installation_info(self, working_dir: str, python_exe: str, version: str = "1.0.0") -> bool:
        """Store installation information in registry"""
        if not self.is_available:
            return False
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Installation"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_WRITE)
            
            # Store installation details
            winreg.SetValueEx(key, "WorkingDirectory", 0, winreg.REG_SZ, working_dir)
            winreg.SetValueEx(key, "PythonExecutable", 0, winreg.REG_SZ, python_exe)
            winreg.SetValueEx(key, "Version", 0, winreg.REG_SZ, version)
            winreg.SetValueEx(key, "InstallDate", 0, winreg.REG_SZ, datetime.now().isoformat())
            winreg.SetValueEx(key, "Platform", 0, winreg.REG_SZ, "Windows")
            
            winreg.CloseKey(key)
            self.logger.info("Installation info stored in registry")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store installation info: {e}")
            return False
    
    def get_installation_info(self) -> Dict[str, str]:
        """Get installation information from registry"""
        if not self.is_available:
            return {}
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Installation"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_READ)
            
            info = {}
            try:
                info['working_directory'] = winreg.QueryValueEx(key, "WorkingDirectory")[0]
                info['python_executable'] = winreg.QueryValueEx(key, "PythonExecutable")[0]
                info['version'] = winreg.QueryValueEx(key, "Version")[0]
                info['install_date'] = winreg.QueryValueEx(key, "InstallDate")[0]
                info['platform'] = winreg.QueryValueEx(key, "Platform")[0]
            except FileNotFoundError:
                pass
            
            winreg.CloseKey(key)
            return info
            
        except Exception as e:
            self.logger.error(f"Failed to get installation info: {e}")
            return {}
    
    def set_server_config(self, server_config: Dict[str, Any]) -> bool:
        """Store server configuration in registry"""
        if not self.is_available:
            return False
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Server"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_WRITE)
            
            # Store server configuration
            if 'minecraft_path' in server_config:
                winreg.SetValueEx(key, "MinecraftPath", 0, winreg.REG_SZ, str(server_config['minecraft_path']))
            
            if 'java_executable' in server_config:
                winreg.SetValueEx(key, "JavaExecutable", 0, winreg.REG_SZ, str(server_config['java_executable']))
            
            if 'server_jar' in server_config:
                winreg.SetValueEx(key, "ServerJar", 0, winreg.REG_SZ, str(server_config['server_jar']))
            
            if 'jvm_args' in server_config:
                winreg.SetValueEx(key, "JvmArgs", 0, winreg.REG_SZ, str(server_config['jvm_args']))
            
            if 'backup_path' in server_config:
                winreg.SetValueEx(key, "BackupPath", 0, winreg.REG_SZ, str(server_config['backup_path']))
            
            winreg.CloseKey(key)
            self.logger.info("Server config stored in registry")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store server config: {e}")
            return False
    
    def get_server_config(self) -> Dict[str, str]:
        """Get server configuration from registry"""
        if not self.is_available:
            return {}
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Server"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_READ)
            
            config = {}
            try:
                config['minecraft_path'] = winreg.QueryValueEx(key, "MinecraftPath")[0]
                config['java_executable'] = winreg.QueryValueEx(key, "JavaExecutable")[0]
                config['server_jar'] = winreg.QueryValueEx(key, "ServerJar")[0]
                config['jvm_args'] = winreg.QueryValueEx(key, "JvmArgs")[0]
                config['backup_path'] = winreg.QueryValueEx(key, "BackupPath")[0]
            except FileNotFoundError:
                pass
            
            winreg.CloseKey(key)
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to get server config: {e}")
            return {}
    
    def set_web_config(self, web_config: Dict[str, Any]) -> bool:
        """Store web configuration in registry"""
        if not self.is_available:
            return False
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Web"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_WRITE)
            
            # Store web configuration
            if 'host' in web_config:
                winreg.SetValueEx(key, "Host", 0, winreg.REG_SZ, str(web_config['host']))
            
            if 'port' in web_config:
                winreg.SetValueEx(key, "Port", 0, winreg.REG_DWORD, int(web_config['port']))
            
            if 'debug' in web_config:
                winreg.SetValueEx(key, "Debug", 0, winreg.REG_DWORD, int(bool(web_config['debug'])))
            
            if 'secret_key' in web_config:
                winreg.SetValueEx(key, "SecretKey", 0, winreg.REG_SZ, str(web_config['secret_key']))
            
            winreg.CloseKey(key)
            self.logger.info("Web config stored in registry")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store web config: {e}")
            return False
    
    def get_web_config(self) -> Dict[str, Union[str, int, bool]]:
        """Get web configuration from registry"""
        if not self.is_available:
            return {}
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Web"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_READ)
            
            config = {}
            try:
                config['host'] = winreg.QueryValueEx(key, "Host")[0]
                config['port'] = winreg.QueryValueEx(key, "Port")[0]
                config['debug'] = bool(winreg.QueryValueEx(key, "Debug")[0])
                config['secret_key'] = winreg.QueryValueEx(key, "SecretKey")[0]
            except FileNotFoundError:
                pass
            
            winreg.CloseKey(key)
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to get web config: {e}")
            return {}
    
    def set_service_config(self, service_config: Dict[str, Any]) -> bool:
        """Store service configuration in registry"""
        if not self.is_available:
            return False
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Service"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_WRITE)
            
            # Store service configuration
            if 'auto_start' in service_config:
                winreg.SetValueEx(key, "AutoStart", 0, winreg.REG_DWORD, int(bool(service_config['auto_start'])))
            
            if 'restart_on_failure' in service_config:
                winreg.SetValueEx(key, "RestartOnFailure", 0, winreg.REG_DWORD, int(bool(service_config['restart_on_failure'])))
            
            if 'log_level' in service_config:
                winreg.SetValueEx(key, "LogLevel", 0, winreg.REG_SZ, str(service_config['log_level']))
            
            winreg.CloseKey(key)
            self.logger.info("Service config stored in registry")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store service config: {e}")
            return False
    
    def get_service_config(self) -> Dict[str, Union[str, bool]]:
        """Get service configuration from registry"""
        if not self.is_available:
            return {}
        
        try:
            key_path = f"{self.SOFTWARE_KEY}\\Service"
            key = winreg.OpenKey(self.BASE_KEY, key_path, 0, winreg.KEY_READ)
            
            config = {}
            try:
                config['auto_start'] = bool(winreg.QueryValueEx(key, "AutoStart")[0])
                config['restart_on_failure'] = bool(winreg.QueryValueEx(key, "RestartOnFailure")[0])
                config['log_level'] = winreg.QueryValueEx(key, "LogLevel")[0]
            except FileNotFoundError:
                pass
            
            winreg.CloseKey(key)
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to get service config: {e}")
            return {}
    
    def export_config_to_file(self, file_path: str) -> bool:
        """Export all registry configuration to a JSON file"""
        if not self.is_available:
            return False
        
        try:
            config = {
                'installation': self.get_installation_info(),
                'server': self.get_server_config(),
                'web': self.get_web_config(),
                'service': self.get_service_config(),
                'export_timestamp': datetime.now().isoformat()
            }
            
            with open(file_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.logger.info(f"Configuration exported to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export config: {e}")
            return False
    
    def import_config_from_file(self, file_path: str) -> bool:
        """Import configuration from JSON file to registry"""
        if not self.is_available:
            return False
        
        try:
            with open(file_path, 'r') as f:
                config = json.load(f)
            
            # Create registry structure first
            self.create_registry_structure()
            
            # Import each section
            success = True
            
            if 'installation' in config and config['installation']:
                success &= self.set_installation_info(
                    config['installation'].get('working_directory', ''),
                    config['installation'].get('python_executable', ''),
                    config['installation'].get('version', '1.0.0')
                )
            
            if 'server' in config and config['server']:
                success &= self.set_server_config(config['server'])
            
            if 'web' in config and config['web']:
                success &= self.set_web_config(config['web'])
            
            if 'service' in config and config['service']:
                success &= self.set_service_config(config['service'])
            
            if success:
                self.logger.info(f"Configuration imported from {file_path}")
            else:
                self.logger.warning("Some configuration sections failed to import")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to import config: {e}")
            return False
    
    def remove_all_registry_data(self) -> bool:
        """Remove all VaultHunters registry data"""
        if not self.is_available:
            return False
        
        try:
            # Remove the entire VaultHunters key tree
            winreg.DeleteKey(self.BASE_KEY, self.SOFTWARE_KEY)
            self.logger.info("All registry data removed")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove registry data: {e}")
            return False
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration from registry"""
        return {
            'installation': self.get_installation_info(),
            'server': self.get_server_config(),
            'web': self.get_web_config(),
            'service': self.get_service_config(),
            'registry_available': self.is_available
        }

# Global registry config instance
windows_registry_config = WindowsRegistryConfig()