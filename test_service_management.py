#!/usr/bin/env python3

import os
import sys
import json
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.service_manager import service_manager
from services.platform_abstraction import platform_abstraction
from services.powershell_policy import powershell_policy_manager
from services.windows_registry_config import windows_registry_config

def test_platform_detection():
    """Test platform detection"""
    print("=== Platform Detection Test ===")
    
    platform_info = platform_abstraction.get_platform_info()
    print(f"Platform: {platform_info['system']}")
    print(f"Windows: {platform_info['is_windows']}")
    print(f"Linux: {platform_info['is_linux']}")
    print(f"macOS: {platform_info['is_macos']}")
    print(f"Service Manager Type: {type(service_manager.manager).__name__}")
    print()

def test_service_status():
    """Test service status checking"""
    print("=== Service Status Test ===")
    
    try:
        status = service_manager.get_service_status()
        print("Service Status:")
        print(json.dumps(status, indent=2))
        
        print(f"Service Installed: {status.get('installed', False)}")
        print(f"Service Status: {status.get('status', 'unknown')}")
        print(f"Service Enabled: {status.get('enabled', False)}")
    
    except Exception as e:
        print(f"Error getting service status: {e}")
    
    print()

def test_powershell_policy():
    """Test PowerShell execution policy (Windows only)"""
    print("=== PowerShell Policy Test ===")
    
    if not platform_abstraction.is_windows:
        print("PowerShell policy test skipped (not Windows)")
        print()
        return
    
    try:
        # Check if PowerShell is available
        available = powershell_policy_manager.is_available()
        print(f"PowerShell Available: {available}")
        
        if available:
            # Get current policy
            policy_info = powershell_policy_manager.get_current_policy()
            print("Current Execution Policy:")
            print(json.dumps(policy_info, indent=2))
            
            # Check compatibility
            compatibility = powershell_policy_manager.check_compatibility()
            print("Compatibility Check:")
            print(json.dumps(compatibility, indent=2))
            
            # Test script execution
            execution_test = powershell_policy_manager.test_script_execution()
            print("Script Execution Test:")
            print(json.dumps(execution_test, indent=2))
    
    except Exception as e:
        print(f"Error testing PowerShell policy: {e}")
    
    print()

def test_registry_config():
    """Test Windows registry configuration (Windows only)"""
    print("=== Windows Registry Config Test ===")
    
    if not platform_abstraction.is_windows:
        print("Registry config test skipped (not Windows)")
        print()
        return
    
    try:
        available = windows_registry_config.is_registry_available()
        print(f"Registry Available: {available}")
        
        if available:
            # Get current configuration
            config = windows_registry_config.get_all_config()
            print("Current Registry Configuration:")
            print(json.dumps(config, indent=2))
    
    except Exception as e:
        print(f"Error testing registry config: {e}")
    
    print()

def test_service_installation():
    """Test service installation (dry run)"""
    print("=== Service Installation Test (Dry Run) ===")
    
    try:
        working_dir = str(project_root)
        python_exe = sys.executable
        
        print(f"Working Directory: {working_dir}")
        print(f"Python Executable: {python_exe}")
        print(f"Service Manager Type: {type(service_manager.manager).__name__}")
        
        # Check if service is already installed
        installed = service_manager.is_installed()
        print(f"Service Currently Installed: {installed}")
        
        # Get platform-specific info
        platform_info = service_manager.get_platform_specific_info()
        print("Platform-Specific Info:")
        print(json.dumps(platform_info, indent=2))
    
    except Exception as e:
        print(f"Error in service installation test: {e}")
    
    print()

def test_path_abstraction():
    """Test cross-platform path handling"""
    print("=== Path Abstraction Test ===")
    
    try:
        minecraft_path = platform_abstraction.get_default_minecraft_path()
        backup_path = platform_abstraction.get_default_backup_path()
        java_exe = platform_abstraction.find_java_executable()
        
        print(f"Default Minecraft Path: {minecraft_path}")
        print(f"Default Backup Path: {backup_path}")
        print(f"Java Executable: {java_exe}")
        
        # Test path normalization
        test_path = "C:\\temp\\test" if platform_abstraction.is_windows else "/tmp/test"
        normalized = platform_abstraction.normalize_path(test_path)
        print(f"Path Normalization Test: {test_path} -> {normalized}")
    
    except Exception as e:
        print(f"Error in path abstraction test: {e}")
    
    print()

def run_all_tests():
    """Run all service management tests"""
    print("VaultHunters Web Manager - Service Management Tests")
    print("=" * 55)
    print()
    
    test_platform_detection()
    test_path_abstraction()
    test_service_status()
    test_powershell_policy()
    test_registry_config()
    test_service_installation()
    
    print("=== Test Summary ===")
    print("All tests completed. Review output above for any errors.")
    print()
    
    if platform_abstraction.is_windows:
        print("Windows-specific notes:")
        print("- Service installation requires administrator privileges")
        print("- PowerShell execution policy may need adjustment")
        print("- Registry configuration available for persistent settings")
    else:
        print("Linux-specific notes:")
        print("- Service installation may require sudo for system-wide services")
        print("- User services are available as fallback")
        print("- systemd is used for service management")

if __name__ == "__main__":
    run_all_tests()