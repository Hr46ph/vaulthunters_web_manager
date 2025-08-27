#!/usr/bin/env python3

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from .platform_abstraction import platform_abstraction
from .windows_registry_config import windows_registry_config
from .powershell_policy import powershell_policy_manager

class CrossPlatformConfig:
    """Cross-platform configuration manager that handles platform-specific storage"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.platform = platform_abstraction.get_platform_info()['system']
    
    def get_platform_config_path(self) -> Path:
        """Get the appropriate configuration file path for the current platform"""
        if platform_abstraction.is_windows:
            # Windows: Store in AppData/Roaming
            return Path.home() / "AppData" / "Roaming" / "VaultHunters" / "config.toml"
        else:
            # Linux/Unix: Use current working directory or home
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config.py"
            if config_path.exists():
                return config_path
            return Path.home() / ".vaulthunters" / "config.toml"
    
    def ensure_config_directory(self) -> bool:
        """Ensure configuration directory exists"""
        try:
            config_path = self.get_platform_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to create config directory: {e}")
            return False
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values for current platform"""
        default_config = {
            "server": {
                "minecraft_path": platform_abstraction.get_default_minecraft_path(),
                "backup_path": platform_abstraction.get_default_backup_path(),
                "java_executable": platform_abstraction.find_java_executable(),
                "server_jar": "forge-1.18.2-40.2.21-universal.jar"
            },
            "web": {
                "host": "0.0.0.0",
                "port": 3000 if platform_abstraction.is_windows else 8080,
                "debug": False
            },
            "platform": {
                "system": self.platform,
                "config_method": "registry" if platform_abstraction.is_windows else "file"
            }
        }
        
        # Add Windows-specific defaults
        if platform_abstraction.is_windows:
            default_config["windows"] = {
                "service_name": "VaultHuntersWebManager",
                "auto_start": True,
                "powershell_policy": "RemoteSigned"
            }
        
        # Add Linux-specific defaults
        if platform_abstraction.is_linux:
            default_config["linux"] = {
                "service_name": "vaulthunters-web-manager",
                "systemd_user": False  # Try system service first
            }
        
        return default_config
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from appropriate platform storage"""
        config = self.get_default_config()
        
        # Try to load from Windows registry first if available
        if platform_abstraction.is_windows and windows_registry_config.is_registry_available():
            try:
                registry_config = windows_registry_config.get_all_config()
                
                # Merge registry config with defaults
                if registry_config.get('server'):
                    config['server'].update(registry_config['server'])
                
                if registry_config.get('web'):
                    config['web'].update(registry_config['web'])
                
                if registry_config.get('service'):
                    config.setdefault('windows', {}).update(registry_config['service'])
                
                self.logger.info("Configuration loaded from Windows registry")
                return config
                
            except Exception as e:
                self.logger.warning(f"Failed to load from registry, falling back to file: {e}")
        
        # Fall back to file-based configuration
        config_path = self.get_platform_config_path()
        
        if config_path.exists():
            try:
                if config_path.suffix == '.json':
                    with open(config_path, 'r') as f:
                        file_config = json.load(f)
                elif config_path.suffix == '.toml':
                    try:
                        import toml
                        with open(config_path, 'r') as f:
                            file_config = toml.load(f)
                    except ImportError:
                        self.logger.warning("TOML support not available, using JSON format")
                        return config
                else:
                    # Try to import Python config file
                    self.logger.info(f"Loading Python config from {config_path}")
                    return config
                
                # Merge file config with defaults
                self._deep_merge(config, file_config)
                self.logger.info(f"Configuration loaded from {config_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to load config from {config_path}: {e}")
        
        return config
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to appropriate platform storage"""
        success = False
        
        # Save to Windows registry if available
        if platform_abstraction.is_windows and windows_registry_config.is_registry_available():
            try:
                # Create registry structure
                windows_registry_config.create_registry_structure()
                
                # Store configuration sections
                if 'server' in config:
                    windows_registry_config.set_server_config(config['server'])
                
                if 'web' in config:
                    windows_registry_config.set_web_config(config['web'])
                
                if 'windows' in config:
                    windows_registry_config.set_service_config(config['windows'])
                
                # Store installation info
                working_dir = str(Path(__file__).parent.parent)
                python_exe = os.sys.executable
                windows_registry_config.set_installation_info(working_dir, python_exe)
                
                self.logger.info("Configuration saved to Windows registry")
                success = True
                
            except Exception as e:
                self.logger.error(f"Failed to save to registry: {e}")
        
        # Also save to file as backup/fallback
        try:
            self.ensure_config_directory()
            config_path = self.get_platform_config_path()
            
            # Save as JSON for cross-platform compatibility
            json_path = config_path.with_suffix('.json')
            
            with open(json_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.logger.info(f"Configuration saved to {json_path}")
            success = True
            
        except Exception as e:
            self.logger.error(f"Failed to save config to file: {e}")
        
        return success
    
    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> None:
        """Deep merge update dictionary into base dictionary"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration and return validation results"""
        validation = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "platform_issues": []
        }
        
        # Validate server configuration
        if 'server' in config:
            server_config = config['server']
            
            # Check if Minecraft path exists
            if 'minecraft_path' in server_config:
                minecraft_path = Path(server_config['minecraft_path'])
                if not minecraft_path.exists():
                    validation["warnings"].append(f"Minecraft path does not exist: {minecraft_path}")
            
            # Check Java executable
            if 'java_executable' in server_config:
                java_exe = server_config['java_executable']
                if java_exe != 'java':  # Skip check for default 'java' command
                    java_path = Path(java_exe)
                    if not java_path.exists():
                        validation["warnings"].append(f"Java executable not found: {java_exe}")
        
        # Platform-specific validation
        if platform_abstraction.is_windows:
            # Check PowerShell execution policy
            if powershell_policy_manager.is_available():
                compatibility = powershell_policy_manager.check_compatibility()
                if not compatibility.get("compatible"):
                    validation["platform_issues"].append({
                        "issue": "PowerShell execution policy",
                        "details": compatibility
                    })
        
        # Set overall validation status
        validation["valid"] = len(validation["errors"]) == 0
        
        return validation
    
    def get_platform_status(self) -> Dict[str, Any]:
        """Get comprehensive platform status for configuration management"""
        status = {
            "platform": self.platform,
            "config_path": str(self.get_platform_config_path()),
            "platform_abstraction": {
                "minecraft_path": platform_abstraction.get_default_minecraft_path(),
                "backup_path": platform_abstraction.get_default_backup_path(),
                "java_executable": platform_abstraction.find_java_executable()
            }
        }
        
        # Add Windows-specific status
        if platform_abstraction.is_windows:
            status["windows"] = {
                "registry_available": windows_registry_config.is_registry_available(),
                "powershell_status": powershell_policy_manager.get_detailed_status()
            }
        
        return status

# Global cross-platform config instance
cross_platform_config = CrossPlatformConfig()