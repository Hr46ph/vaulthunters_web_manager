#!/usr/bin/env python3

import os
import sys
import socket
import servicemanager
import win32event
import win32service
import win32serviceutil
import logging
from pathlib import Path

class VaultHuntersWebService(win32serviceutil.ServiceFramework):
    """Windows service wrapper for VaultHunters Web Manager"""
    
    _svc_name_ = "VaultHuntersWebManager"
    _svc_display_name_ = "VaultHunters Web Manager"
    _svc_description_ = "Web-based management interface for VaultHunters Minecraft servers"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.flask_app = None
        
        # Set up logging
        self.setup_logging()
        
    def setup_logging(self):
        """Set up Windows service logging"""
        try:
            # Create logs directory
            log_dir = Path.home() / "AppData" / "Roaming" / "VaultHunters" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Configure logging
            log_file = log_dir / "service.log"
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler()
                ]
            )
            
            self.logger = logging.getLogger(__name__)
            
        except Exception as e:
            # Fallback logging
            servicemanager.LogErrorMsg(f"Failed to setup logging: {e}")
            self.logger = logging.getLogger(__name__)
    
    def SvcStop(self):
        """Stop the Windows service"""
        self.logger.info("VaultHunters Web Manager service stopping...")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        
        # Stop the Flask app
        self.running = False
        
        if self.flask_app:
            try:
                # Gracefully shutdown Flask
                self.flask_app.shutdown()
            except Exception as e:
                self.logger.error(f"Error stopping Flask app: {e}")
        
        win32event.SetEvent(self.hWaitStop)
        self.logger.info("VaultHunters Web Manager service stopped")
    
    def SvcDoRun(self):
        """Main service execution"""
        self.logger.info("VaultHunters Web Manager service starting...")
        
        # Log service start
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        try:
            self.main()
        except Exception as e:
            self.logger.error(f"Service error: {e}")
            servicemanager.LogErrorMsg(f"Service error: {e}")
        
        # Log service stop
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, '')
        )
    
    def main(self):
        """Main service logic - run the Flask application"""
        try:
            # Change to the working directory (where app.py is located)
            script_dir = Path(__file__).parent.parent
            os.chdir(script_dir)
            
            # Add to Python path
            if str(script_dir) not in sys.path:
                sys.path.insert(0, str(script_dir))
            
            # Import and run the Flask app
            from app import app
            
            self.logger.info("Starting Flask application...")
            
            # Get configuration
            try:
                from config import Config
                host = getattr(Config, 'HOST', '0.0.0.0')
                port = getattr(Config, 'PORT', 3000)
                debug = False  # Never run in debug mode as a service
            except ImportError:
                host = '0.0.0.0'
                port = 3000
                debug = False
            
            # Store Flask app reference
            self.flask_app = app
            
            # Run Flask app in a way that can be stopped
            self.run_flask_app(app, host, port, debug)
            
        except Exception as e:
            self.logger.error(f"Error in main service loop: {e}")
            raise
    
    def run_flask_app(self, app, host, port, debug):
        """Run Flask app with proper service lifecycle management"""
        try:
            # Use Werkzeug's development server with threading
            from werkzeug.serving import make_server
            
            server = make_server(host, port, app, threaded=True)
            self.logger.info(f"Flask server started on {host}:{port}")
            
            # Store server reference for clean shutdown
            self.flask_server = server
            
            # Run the server
            server.serve_forever()
            
        except Exception as e:
            self.logger.error(f"Error running Flask server: {e}")
            if not self.running:
                # Service is stopping, this is expected
                return
            raise

class WindowsServiceInstaller:
    """Helper class for installing/managing the Windows service"""
    
    @staticmethod
    def install():
        """Install the Windows service"""
        try:
            # Install service
            win32serviceutil.InstallService(
                VaultHuntersWebService._svc_reg_class_,
                VaultHuntersWebService._svc_name_,
                VaultHuntersWebService._svc_display_name_,
                description=VaultHuntersWebService._svc_description_
            )
            
            print(f"Service '{VaultHuntersWebService._svc_display_name_}' installed successfully")
            return True
            
        except Exception as e:
            print(f"Failed to install service: {e}")
            return False
    
    @staticmethod
    def uninstall():
        """Uninstall the Windows service"""
        try:
            # Stop service if running
            WindowsServiceInstaller.stop()
            
            # Remove service
            win32serviceutil.RemoveService(VaultHuntersWebService._svc_name_)
            print(f"Service '{VaultHuntersWebService._svc_display_name_}' uninstalled successfully")
            return True
            
        except Exception as e:
            print(f"Failed to uninstall service: {e}")
            return False
    
    @staticmethod
    def start():
        """Start the Windows service"""
        try:
            win32serviceutil.StartService(VaultHuntersWebService._svc_name_)
            print(f"Service '{VaultHuntersWebService._svc_display_name_}' started successfully")
            return True
            
        except Exception as e:
            print(f"Failed to start service: {e}")
            return False
    
    @staticmethod
    def stop():
        """Stop the Windows service"""
        try:
            win32serviceutil.StopService(VaultHuntersWebService._svc_name_)
            print(f"Service '{VaultHuntersWebService._svc_display_name_}' stopped successfully")
            return True
            
        except Exception as e:
            print(f"Failed to stop service: {e}")
            return False
    
    @staticmethod
    def restart():
        """Restart the Windows service"""
        return WindowsServiceInstaller.stop() and WindowsServiceInstaller.start()
    
    @staticmethod
    def status():
        """Get Windows service status"""
        try:
            status = win32serviceutil.QueryServiceStatus(VaultHuntersWebService._svc_name_)
            status_names = {
                win32service.SERVICE_STOPPED: "Stopped",
                win32service.SERVICE_START_PENDING: "Start Pending",
                win32service.SERVICE_STOP_PENDING: "Stop Pending",
                win32service.SERVICE_RUNNING: "Running",
                win32service.SERVICE_CONTINUE_PENDING: "Continue Pending",
                win32service.SERVICE_PAUSE_PENDING: "Pause Pending",
                win32service.SERVICE_PAUSED: "Paused"
            }
            
            current_state = status[1]
            return {
                "installed": True,
                "status": status_names.get(current_state, f"Unknown ({current_state})"),
                "status_code": current_state
            }
            
        except Exception as e:
            return {
                "installed": False,
                "status": f"Error: {e}",
                "status_code": None
            }

# Service management functions
def install_service():
    """Install the Windows service"""
    return WindowsServiceInstaller.install()

def uninstall_service():
    """Uninstall the Windows service"""
    return WindowsServiceInstaller.uninstall()

def start_service():
    """Start the Windows service"""
    return WindowsServiceInstaller.start()

def stop_service():
    """Stop the Windows service"""
    return WindowsServiceInstaller.stop()

def restart_service():
    """Restart the Windows service"""
    return WindowsServiceInstaller.restart()

def service_status():
    """Get Windows service status"""
    return WindowsServiceInstaller.status()

if __name__ == '__main__':
    # Handle command line arguments
    if len(sys.argv) == 1:
        # Run as service
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(VaultHuntersWebService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Handle install/remove/debug commands
        win32serviceutil.HandleCommandLine(VaultHuntersWebService)