#!/usr/bin/env python3

import os
import sys
import subprocess
import json
import time
import platform
from pathlib import Path
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import logging

# Conditional import for Windows registry
try:
    import winreg
except ImportError:
    winreg = None

from .platform_abstraction import platform_abstraction

class ServiceManagerBase(ABC):
    """Abstract base class for service management"""
    
    def __init__(self, service_name: str = "VaultHunters Web Manager"):
        self.service_name = service_name
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def is_installed(self) -> bool:
        """Check if service is installed"""
        pass
    
    @abstractmethod
    def install_service(self, executable_path: str, working_dir: str, description: str = None) -> bool:
        """Install service"""
        pass
    
    @abstractmethod
    def uninstall_service(self) -> bool:
        """Uninstall service"""
        pass
    
    @abstractmethod
    def start_service(self) -> bool:
        """Start service"""
        pass
    
    @abstractmethod
    def stop_service(self) -> bool:
        """Stop service"""
        pass
    
    @abstractmethod
    def restart_service(self) -> bool:
        """Restart service"""
        pass
    
    @abstractmethod
    def get_service_status(self) -> Dict[str, Any]:
        """Get service status information"""
        pass
    
    @abstractmethod
    def enable_service(self) -> bool:
        """Enable service to start on boot"""
        pass
    
    @abstractmethod
    def disable_service(self) -> bool:
        """Disable service from starting on boot"""
        pass

class WindowsServiceManager(ServiceManagerBase):
    """Windows service management using sc.exe and registry"""
    
    def __init__(self, service_name: str = "VaultHuntersWebManager"):
        super().__init__(service_name)
        self.service_key = f"SYSTEM\\CurrentControlSet\\Services\\{self.service_name}"
        self.config_key = f"SOFTWARE\\VaultHunters\\WebManager"
    
    def is_installed(self) -> bool:
        """Check if Windows service is installed"""
        try:
            result = subprocess.run(
                ['sc', 'query', self.service_name],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Error checking service installation: {e}")
            return False
    
    def install_service(self, executable_path: str, working_dir: str, description: str = None) -> bool:
        """Install Windows service using sc.exe"""
        try:
            # Prepare service command - use Python to run the Flask app
            python_exe = sys.executable
            app_script = Path(working_dir) / "app.py"
            
            service_cmd = f'"{python_exe}" "{app_script}"'
            
            # Install service
            install_cmd = [
                'sc', 'create', self.service_name,
                'binPath=', service_cmd,
                'DisplayName=', 'VaultHunters Web Manager',
                'start=', 'auto',
                'type=', 'own'
            ]
            
            if description:
                install_cmd.extend(['description=', description])
            
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                # Store configuration in registry
                self._store_config_in_registry(working_dir)
                self.logger.info(f"Service {self.service_name} installed successfully")
                return True
            else:
                self.logger.error(f"Failed to install service: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error installing service: {e}")
            return False
    
    def _store_config_in_registry(self, working_dir: str) -> bool:
        """Store service configuration in Windows registry"""
        try:
            import winreg
            
            # Create registry key
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, self.config_key)
            
            # Store configuration
            winreg.SetValueEx(key, "WorkingDirectory", 0, winreg.REG_SZ, working_dir)
            winreg.SetValueEx(key, "PythonExecutable", 0, winreg.REG_SZ, sys.executable)
            winreg.SetValueEx(key, "InstallDate", 0, winreg.REG_SZ, str(int(time.time())))
            
            winreg.CloseKey(key)
            return True
        except Exception as e:
            self.logger.error(f"Error storing config in registry: {e}")
            return False
    
    def _get_config_from_registry(self) -> Dict[str, str]:
        """Get service configuration from Windows registry"""
        try:
            import winreg
            
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.config_key)
            config = {}
            
            try:
                config['working_directory'] = winreg.QueryValueEx(key, "WorkingDirectory")[0]
                config['python_executable'] = winreg.QueryValueEx(key, "PythonExecutable")[0]
                config['install_date'] = winreg.QueryValueEx(key, "InstallDate")[0]
            except FileNotFoundError:
                pass
            
            winreg.CloseKey(key)
            return config
        except Exception:
            return {}
    
    def uninstall_service(self) -> bool:
        """Uninstall Windows service"""
        try:
            # Stop service first if running
            self.stop_service()
            
            # Delete service
            result = subprocess.run(
                ['sc', 'delete', self.service_name],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                # Clean up registry
                self._cleanup_registry()
                self.logger.info(f"Service {self.service_name} uninstalled successfully")
                return True
            else:
                self.logger.error(f"Failed to uninstall service: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error uninstalling service: {e}")
            return False
    
    def _cleanup_registry(self) -> bool:
        """Clean up registry entries"""
        try:
            import winreg
            
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, self.config_key)
            return True
        except Exception as e:
            self.logger.error(f"Error cleaning up registry: {e}")
            return False
    
    def start_service(self) -> bool:
        """Start Windows service"""
        try:
            result = subprocess.run(
                ['sc', 'start', self.service_name],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} started successfully")
            else:
                self.logger.error(f"Failed to start service: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error starting service: {e}")
            return False
    
    def stop_service(self) -> bool:
        """Stop Windows service"""
        try:
            result = subprocess.run(
                ['sc', 'stop', self.service_name],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Service might not be running, check for specific error codes
            if result.returncode == 0 or "1062" in result.stderr:  # 1062 = service not started
                self.logger.info(f"Service {self.service_name} stopped successfully")
                return True
            else:
                self.logger.error(f"Failed to stop service: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error stopping service: {e}")
            return False
    
    def restart_service(self) -> bool:
        """Restart Windows service"""
        return self.stop_service() and self.start_service()
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get Windows service status"""
        try:
            result = subprocess.run(
                ['sc', 'query', self.service_name],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode != 0:
                return {"installed": False, "status": "not_installed", "enabled": False}
            
            output = result.stdout
            
            # Parse sc query output
            status = "unknown"
            if "RUNNING" in output:
                status = "running"
            elif "STOPPED" in output:
                status = "stopped"
            elif "START_PENDING" in output:
                status = "starting"
            elif "STOP_PENDING" in output:
                status = "stopping"
            
            # Check if service is set to auto-start
            config_result = subprocess.run(
                ['sc', 'qc', self.service_name],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            enabled = "AUTO_START" in config_result.stdout if config_result.returncode == 0 else False
            
            # Get additional config from registry
            registry_config = self._get_config_from_registry()
            
            return {
                "installed": True,
                "status": status,
                "enabled": enabled,
                "registry_config": registry_config
            }
            
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            return {"installed": False, "status": "error", "enabled": False}
    
    def enable_service(self) -> bool:
        """Enable Windows service for auto-start"""
        try:
            result = subprocess.run(
                ['sc', 'config', self.service_name, 'start=', 'auto'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} enabled for auto-start")
            else:
                self.logger.error(f"Failed to enable service: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error enabling service: {e}")
            return False
    
    def disable_service(self) -> bool:
        """Disable Windows service from auto-start"""
        try:
            result = subprocess.run(
                ['sc', 'config', self.service_name, 'start=', 'demand'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} disabled from auto-start")
            else:
                self.logger.error(f"Failed to disable service: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error disabling service: {e}")
            return False
    
    def check_powershell_execution_policy(self) -> Dict[str, Any]:
        """Check PowerShell execution policy"""
        try:
            result = subprocess.run(
                ['powershell.exe', '-Command', 'Get-ExecutionPolicy'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                policy = result.stdout.strip()
                return {
                    "policy": policy,
                    "restricted": policy.lower() in ["restricted", "allsigned"],
                    "recommendation": "RemoteSigned" if policy.lower() == "restricted" else None
                }
            else:
                return {"policy": "unknown", "restricted": True}
                
        except Exception as e:
            self.logger.error(f"Error checking PowerShell execution policy: {e}")
            return {"policy": "error", "restricted": True}
    
    def set_powershell_execution_policy(self, policy: str = "RemoteSigned") -> bool:
        """Set PowerShell execution policy (requires admin privileges)"""
        try:
            result = subprocess.run(
                ['powershell.exe', '-Command', f'Set-ExecutionPolicy -ExecutionPolicy {policy} -Force'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"PowerShell execution policy set to {policy}")
            else:
                self.logger.error(f"Failed to set execution policy: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error setting PowerShell execution policy: {e}")
            return False

class LinuxServiceManager(ServiceManagerBase):
    """Linux systemd service management"""
    
    def __init__(self, service_name: str = "vaulthunters-web-manager"):
        super().__init__(service_name)
        self.service_file = f"{service_name}.service"
        self.systemd_path = Path("/etc/systemd/system") / self.service_file
        self.user_systemd_path = Path.home() / ".config/systemd/user" / self.service_file
    
    def is_installed(self) -> bool:
        """Check if systemd service is installed"""
        return self.systemd_path.exists() or self.user_systemd_path.exists()
    
    def install_service(self, executable_path: str, working_dir: str, description: str = None) -> bool:
        """Install systemd service"""
        try:
            python_exe = sys.executable
            app_script = Path(working_dir) / "app.py"
            
            service_content = f"""[Unit]
Description={description or 'VaultHunters Web Manager'}
After=network.target
Wants=network.target

[Service]
Type=simple
User=minecraft
WorkingDirectory={working_dir}
Environment=PATH={os.environ.get('PATH', '')}
Environment=PYTHONPATH={working_dir}
ExecStart={python_exe} {app_script}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
            
            # Try to install as system service first, fall back to user service
            try:
                with open(self.systemd_path, 'w') as f:
                    f.write(service_content)
                
                # Reload systemd
                result = subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
                if result.returncode == 0:
                    self.logger.info(f"System service {self.service_name} installed successfully")
                    return True
                    
            except PermissionError:
                # Fall back to user service
                self.user_systemd_path.parent.mkdir(parents=True, exist_ok=True)
                
                user_service_content = service_content.replace("WantedBy=multi-user.target", "WantedBy=default.target")
                
                with open(self.user_systemd_path, 'w') as f:
                    f.write(user_service_content)
                
                # Reload user systemd
                result = subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
                if result.returncode == 0:
                    self.logger.info(f"User service {self.service_name} installed successfully")
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error installing service: {e}")
            return False
    
    def uninstall_service(self) -> bool:
        """Uninstall systemd service"""
        try:
            success = True
            
            # Stop services first
            self.stop_service()
            self.disable_service()
            
            # Remove system service
            if self.systemd_path.exists():
                try:
                    self.systemd_path.unlink()
                    subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
                except PermissionError:
                    self.logger.warning("Could not remove system service file (permission denied)")
                    success = False
            
            # Remove user service
            if self.user_systemd_path.exists():
                self.user_systemd_path.unlink()
                subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
            
            if success:
                self.logger.info(f"Service {self.service_name} uninstalled successfully")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error uninstalling service: {e}")
            return False
    
    def _run_systemctl(self, command: List[str], user_service: bool = None) -> subprocess.CompletedProcess:
        """Run systemctl command, trying both system and user services"""
        if user_service is None:
            # Auto-detect: try system first, fall back to user
            system_cmd = ['systemctl'] + command
            result = subprocess.run(system_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return result
            
            # Try user service
            user_cmd = ['systemctl', '--user'] + command
            return subprocess.run(user_cmd, capture_output=True, text=True)
        
        elif user_service:
            user_cmd = ['systemctl', '--user'] + command
            return subprocess.run(user_cmd, capture_output=True, text=True)
        else:
            system_cmd = ['systemctl'] + command
            return subprocess.run(system_cmd, capture_output=True, text=True)
    
    def start_service(self) -> bool:
        """Start systemd service"""
        try:
            result = self._run_systemctl(['start', self.service_name])
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} started successfully")
            else:
                self.logger.error(f"Failed to start service: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error starting service: {e}")
            return False
    
    def stop_service(self) -> bool:
        """Stop systemd service"""
        try:
            result = self._run_systemctl(['stop', self.service_name])
            
            # Service might not be running
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} stopped successfully")
            else:
                self.logger.warning(f"Service stop returned non-zero: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error stopping service: {e}")
            return False
    
    def restart_service(self) -> bool:
        """Restart systemd service"""
        try:
            result = self._run_systemctl(['restart', self.service_name])
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} restarted successfully")
            else:
                self.logger.error(f"Failed to restart service: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error restarting service: {e}")
            return False
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get systemd service status"""
        try:
            if not self.is_installed():
                return {"installed": False, "status": "not_installed", "enabled": False}
            
            # Get service status
            status_result = self._run_systemctl(['is-active', self.service_name])
            status = status_result.stdout.strip()
            
            # Get enabled status
            enabled_result = self._run_systemctl(['is-enabled', self.service_name])
            enabled = enabled_result.stdout.strip() == "enabled"
            
            # Get detailed status
            detailed_result = self._run_systemctl(['status', self.service_name])
            
            return {
                "installed": True,
                "status": status,
                "enabled": enabled,
                "detailed_status": detailed_result.stdout if detailed_result.returncode == 0 else None,
                "service_file": str(self.systemd_path if self.systemd_path.exists() else self.user_systemd_path)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            return {"installed": False, "status": "error", "enabled": False}
    
    def enable_service(self) -> bool:
        """Enable systemd service"""
        try:
            result = self._run_systemctl(['enable', self.service_name])
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} enabled successfully")
            else:
                self.logger.error(f"Failed to enable service: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error enabling service: {e}")
            return False
    
    def disable_service(self) -> bool:
        """Disable systemd service"""
        try:
            result = self._run_systemctl(['disable', self.service_name])
            
            success = result.returncode == 0
            if success:
                self.logger.info(f"Service {self.service_name} disabled successfully")
            else:
                self.logger.warning(f"Service disable returned non-zero: {result.stderr}")
            
            return success
        except Exception as e:
            self.logger.error(f"Error disabling service: {e}")
            return False

class ServiceManager:
    """Unified cross-platform service manager"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        if platform_abstraction.is_windows:
            self.manager = WindowsServiceManager()
        elif platform_abstraction.is_linux:
            self.manager = LinuxServiceManager()
        else:
            raise NotImplementedError(f"Service management not implemented for {platform_abstraction.get_platform_info()['system']}")
    
    def get_platform_manager(self) -> ServiceManagerBase:
        """Get the platform-specific service manager"""
        return self.manager
    
    def is_installed(self) -> bool:
        """Check if service is installed"""
        return self.manager.is_installed()
    
    def install_service(self, executable_path: str = None, working_dir: str = None, description: str = None) -> bool:
        """Install service with platform-appropriate defaults"""
        if working_dir is None:
            working_dir = os.getcwd()
        
        if executable_path is None:
            executable_path = sys.executable
        
        if description is None:
            description = "VaultHunters Web Manager - Minecraft server management interface"
        
        return self.manager.install_service(executable_path, working_dir, description)
    
    def uninstall_service(self) -> bool:
        """Uninstall service"""
        return self.manager.uninstall_service()
    
    def start_service(self) -> bool:
        """Start service"""
        return self.manager.start_service()
    
    def stop_service(self) -> bool:
        """Stop service"""
        return self.manager.stop_service()
    
    def restart_service(self) -> bool:
        """Restart service"""
        return self.manager.restart_service()
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get service status with platform information"""
        status = self.manager.get_service_status()
        status['platform'] = platform_abstraction.get_platform_info()['system']
        status['service_manager_type'] = type(self.manager).__name__
        return status
    
    def enable_service(self) -> bool:
        """Enable service"""
        return self.manager.enable_service()
    
    def disable_service(self) -> bool:
        """Disable service"""
        return self.manager.disable_service()
    
    def get_platform_specific_info(self) -> Dict[str, Any]:
        """Get platform-specific service information"""
        info = {
            "platform": platform_abstraction.get_platform_info()['system'],
            "service_manager": type(self.manager).__name__
        }
        
        # Add Windows-specific information
        if platform_abstraction.is_windows and isinstance(self.manager, WindowsServiceManager):
            info['powershell_policy'] = self.manager.check_powershell_execution_policy()
        
        return info

# Global service manager instance
service_manager = ServiceManager()