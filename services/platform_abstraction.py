#!/usr/bin/env python3

import os
import sys
import subprocess
import platform
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

class PlatformAbstraction:
    """Cross-platform abstraction layer for OS-specific operations"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.is_windows = platform.system().lower() == 'windows'
        self.is_linux = platform.system().lower() == 'linux'
        self.is_macos = platform.system().lower() == 'darwin'
        
    def get_platform_info(self) -> Dict[str, Any]:
        """Get platform-specific information"""
        return {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'is_windows': self.is_windows,
            'is_linux': self.is_linux,
            'is_macos': self.is_macos,
            'python_version': platform.python_version()
        }
    
    def normalize_path(self, path: str) -> str:
        """Normalize path for current platform"""
        return str(Path(path).resolve())
    
    def get_default_minecraft_path(self) -> str:
        """Get default Minecraft server path for current platform"""
        if self.is_windows:
            return str(Path.home() / "AppData" / "Roaming" / "VaultHunters")
        else:
            return "/home/minecraft/vaulthunters"
    
    def get_default_backup_path(self) -> str:
        """Get default backup path for current platform"""
        if self.is_windows:
            return str(Path.home() / "AppData" / "Roaming" / "VaultHunters" / "backups")
        else:
            return "/home/minecraft/backups"
    
    def find_java_executable(self) -> Optional[str]:
        """Find Java executable on current platform"""
        java_name = "java.exe" if self.is_windows else "java"
        
        # Check JAVA_HOME first
        java_home = os.environ.get('JAVA_HOME')
        if java_home:
            java_path = Path(java_home) / "bin" / java_name
            if java_path.exists():
                return str(java_path)
        
        # Check PATH
        try:
            if self.is_windows:
                result = subprocess.run(['where', java_name], capture_output=True, text=True)
            else:
                result = subprocess.run(['which', java_name], capture_output=True, text=True)
            
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
        except Exception:
            pass
        
        return java_name  # Fallback to hoping it's in PATH
    
    def start_detached_process(self, command: List[str], cwd: str, log_file: str) -> subprocess.Popen:
        """Start a process detached from parent on current platform"""
        if self.is_windows:
            return self._start_detached_windows(command, cwd, log_file)
        else:
            return self._start_detached_unix(command, cwd, log_file)
    
    def _start_detached_windows(self, command: List[str], cwd: str, log_file: str) -> subprocess.Popen:
        """Start detached process on Windows"""
        log_path = Path(cwd) / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, 'a') as log_handle:
            return subprocess.Popen(
                command,
                cwd=cwd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                close_fds=True
            )
    
    def _start_detached_unix(self, command: List[str], cwd: str, log_file: str) -> subprocess.Popen:
        """Start detached process on Unix-like systems"""
        log_path = Path(cwd) / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, 'a') as log_handle:
            return subprocess.Popen(
                command,
                cwd=cwd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True
            )
    
    def terminate_process_gracefully(self, process, timeout: int = 30) -> bool:
        """Terminate process gracefully with platform-specific signals"""
        try:
            if self.is_windows:
                # Windows: Use terminate() directly
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                    return True
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                    return False
            else:
                # Unix: Try SIGTERM first, then SIGKILL
                process.terminate()  # Sends SIGTERM on Unix
                try:
                    process.wait(timeout=timeout)
                    return True
                except subprocess.TimeoutExpired:
                    process.kill()  # Sends SIGKILL on Unix
                    process.wait(timeout=10)
                    return False
        except Exception as e:
            self.logger.error(f"Error terminating process: {e}")
            return False
    
    def get_log_tail_command(self, log_file: str, lines: int = 100, follow: bool = False) -> List[str]:
        """Get platform-specific command to tail log files"""
        if self.is_windows:
            if follow:
                return [
                    'powershell.exe', '-Command',
                    f'Get-Content -Path "{log_file}" -Tail {lines} -Wait'
                ]
            else:
                return [
                    'powershell.exe', '-Command',
                    f'Get-Content -Path "{log_file}" -Tail {lines}'
                ]
        else:
            cmd = ['tail', '-n', str(lines)]
            if follow:
                cmd.append('-f')
            cmd.append(log_file)
            return cmd
    
    def get_service_logs_command(self, service_name: str, lines: int = 100) -> Optional[List[str]]:
        """Get command to retrieve service logs on current platform"""
        if self.is_windows:
            return [
                'powershell.exe', '-Command',
                f'Get-WinEvent -FilterHashtable @{{LogName="Application"; ProviderName="{service_name}"}} -MaxEvents {lines} | Format-Table -AutoSize'
            ]
        elif self.is_linux:
            return ['journalctl', '-u', f'{service_name}.service', '-n', str(lines), '--no-pager']
        else:
            return None
    
    def supports_signals(self) -> bool:
        """Check if platform supports Unix signals"""
        return not self.is_windows

# Global instance
platform_abstraction = PlatformAbstraction()