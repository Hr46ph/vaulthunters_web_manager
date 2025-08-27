#!/usr/bin/env python3

import subprocess
import logging
from typing import Dict, Any, Optional, List
from enum import Enum

from .platform_abstraction import platform_abstraction

class ExecutionPolicy(Enum):
    """PowerShell execution policy levels"""
    RESTRICTED = "Restricted"
    ALL_SIGNED = "AllSigned"
    REMOTE_SIGNED = "RemoteSigned"
    UNRESTRICTED = "Unrestricted"
    BYPASS = "Bypass"
    UNDEFINED = "Undefined"

class PowerShellPolicyManager:
    """Manages PowerShell execution policies for VaultHunters Web Manager"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.is_windows = platform_abstraction.is_windows
        
        if not self.is_windows:
            self.logger.info("PowerShell policy management not needed on non-Windows platforms")
    
    def is_available(self) -> bool:
        """Check if PowerShell is available and execution policy management is possible"""
        if not self.is_windows:
            return False
        
        try:
            result = subprocess.run(
                ['powershell.exe', '-Command', 'Get-ExecutionPolicy'],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_current_policy(self, scope: str = None) -> Dict[str, Any]:
        """Get current PowerShell execution policy"""
        if not self.is_windows:
            return {"available": False, "reason": "Not Windows"}
        
        try:
            # Get policy for specific scope or all scopes
            if scope:
                cmd = ['powershell.exe', '-Command', f'Get-ExecutionPolicy -Scope {scope}']
            else:
                cmd = ['powershell.exe', '-Command', 'Get-ExecutionPolicy -List | Format-Table -AutoSize']
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                policy_info = {
                    "available": True,
                    "current_policy": result.stdout.strip(),
                    "restrictive": self._is_policy_restrictive(result.stdout.strip()),
                    "scope": scope or "all",
                    "raw_output": result.stdout
                }
                
                # Add recommendation if policy is restrictive
                if policy_info["restrictive"]:
                    policy_info["recommendation"] = {
                        "policy": ExecutionPolicy.REMOTE_SIGNED.value,
                        "reason": "RemoteSigned allows local scripts while maintaining security for remote scripts"
                    }
                
                return policy_info
            else:
                return {
                    "available": False,
                    "error": result.stderr.strip(),
                    "reason": "Failed to query execution policy"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "available": False,
                "reason": "PowerShell command timed out"
            }
        except Exception as e:
            self.logger.error(f"Error getting PowerShell execution policy: {e}")
            return {
                "available": False,
                "error": str(e),
                "reason": "Exception occurred"
            }
    
    def _is_policy_restrictive(self, policy: str) -> bool:
        """Check if the execution policy is restrictive for VaultHunters Web Manager"""
        restrictive_policies = [
            ExecutionPolicy.RESTRICTED.value,
            ExecutionPolicy.ALL_SIGNED.value
        ]
        
        # Check if any line contains a restrictive policy
        for line in policy.split('\n'):
            for restrictive in restrictive_policies:
                if restrictive in line:
                    return True
        
        return False
    
    def check_compatibility(self) -> Dict[str, Any]:
        """Check PowerShell execution policy compatibility for VaultHunters Web Manager"""
        if not self.is_windows:
            return {
                "compatible": True,
                "reason": "PowerShell not required on non-Windows platforms"
            }
        
        policy_info = self.get_current_policy()
        
        if not policy_info.get("available"):
            return {
                "compatible": False,
                "issue": "PowerShell not available or accessible",
                "details": policy_info
            }
        
        if policy_info.get("restrictive"):
            return {
                "compatible": False,
                "issue": "Restrictive execution policy detected",
                "current_policy": policy_info.get("current_policy"),
                "recommendation": policy_info.get("recommendation"),
                "details": "VaultHunters Web Manager may need to execute PowerShell scripts for log management and system operations"
            }
        
        return {
            "compatible": True,
            "current_policy": policy_info.get("current_policy"),
            "details": "PowerShell execution policy is compatible"
        }
    
    def set_execution_policy(self, policy: ExecutionPolicy, scope: str = "CurrentUser", force: bool = False) -> Dict[str, Any]:
        """Set PowerShell execution policy"""
        if not self.is_windows:
            return {
                "success": False,
                "reason": "Not available on non-Windows platforms"
            }
        
        try:
            # Build command
            cmd = ['powershell.exe', '-Command', f'Set-ExecutionPolicy -ExecutionPolicy {policy.value} -Scope {scope}']
            
            if force:
                cmd[-1] += ' -Force'
            
            # Execute command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                self.logger.info(f"PowerShell execution policy set to {policy.value} for scope {scope}")
                
                # Verify the change
                verification = self.get_current_policy(scope)
                
                return {
                    "success": True,
                    "policy": policy.value,
                    "scope": scope,
                    "verification": verification,
                    "message": f"Execution policy successfully set to {policy.value}"
                }
            else:
                error_msg = result.stderr.strip()
                self.logger.error(f"Failed to set execution policy: {error_msg}")
                
                return {
                    "success": False,
                    "error": error_msg,
                    "policy": policy.value,
                    "scope": scope,
                    "message": "Failed to set execution policy. This usually requires administrator privileges."
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "reason": "Command timed out",
                "message": "PowerShell command timed out. This may indicate a permission prompt."
            }
        except Exception as e:
            self.logger.error(f"Error setting PowerShell execution policy: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "An error occurred while setting the execution policy"
            }
    
    def recommend_policy_fix(self) -> Dict[str, Any]:
        """Provide recommendations for fixing PowerShell execution policy issues"""
        compatibility = self.check_compatibility()
        
        if compatibility.get("compatible"):
            return {
                "fix_needed": False,
                "message": "PowerShell execution policy is already compatible"
            }
        
        recommendations = {
            "fix_needed": True,
            "issue": compatibility.get("issue"),
            "recommendations": []
        }
        
        if "Restrictive" in compatibility.get("issue", ""):
            recommendations["recommendations"].extend([
                {
                    "method": "user_scope",
                    "title": "Set Policy for Current User (Recommended)",
                    "description": "Set execution policy to RemoteSigned for current user only",
                    "command": "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser",
                    "admin_required": False,
                    "risk": "Low"
                },
                {
                    "method": "local_machine",
                    "title": "Set Policy for Local Machine",
                    "description": "Set execution policy to RemoteSigned for all users",
                    "command": "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine",
                    "admin_required": True,
                    "risk": "Medium"
                },
                {
                    "method": "bypass",
                    "title": "Bypass Policy (Advanced)",
                    "description": "Bypass execution policy entirely (not recommended for production)",
                    "command": "Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser",
                    "admin_required": False,
                    "risk": "High"
                }
            ])
        
        if not self.is_available():
            recommendations["recommendations"].append({
                "method": "install_powershell",
                "title": "Install PowerShell",
                "description": "Install or repair PowerShell installation",
                "admin_required": True,
                "risk": "Low"
            })
        
        return recommendations
    
    def test_script_execution(self) -> Dict[str, Any]:
        """Test if PowerShell scripts can be executed with current policy"""
        if not self.is_windows:
            return {
                "can_execute": True,
                "reason": "PowerShell not required on non-Windows platforms"
            }
        
        try:
            # Try to execute a simple test script
            test_script = "Write-Output 'PowerShell execution test successful'"
            
            result = subprocess.run(
                ['powershell.exe', '-Command', test_script],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0 and "successful" in result.stdout:
                return {
                    "can_execute": True,
                    "test_output": result.stdout.strip(),
                    "message": "PowerShell script execution is working correctly"
                }
            else:
                return {
                    "can_execute": False,
                    "error": result.stderr.strip(),
                    "test_output": result.stdout.strip(),
                    "message": "PowerShell script execution failed"
                }
                
        except Exception as e:
            return {
                "can_execute": False,
                "error": str(e),
                "message": "Failed to test PowerShell script execution"
            }
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get comprehensive PowerShell execution policy status"""
        status = {
            "platform": "Windows" if self.is_windows else "Non-Windows",
            "powershell_available": self.is_available(),
            "timestamp": subprocess.run(['powershell.exe', '-Command', 'Get-Date'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip() if self.is_windows else None
        }
        
        if self.is_windows and status["powershell_available"]:
            status.update({
                "current_policy": self.get_current_policy(),
                "compatibility": self.check_compatibility(),
                "script_execution_test": self.test_script_execution(),
                "recommendations": self.recommend_policy_fix()
            })
        
        return status

# Global PowerShell policy manager instance
powershell_policy_manager = PowerShellPolicyManager()