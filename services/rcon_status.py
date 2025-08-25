"""
RCON Status Service

Handles RCON connection status checking, validation, and error reporting.
Consolidates RCON status logic previously scattered in routes.py.
"""

import socket
import logging
from typing import Dict, Any, Optional, Tuple
from flask import current_app

from services.system_control import SystemControlService
from services.server_properties import ServerPropertiesParser
from services.rcon_client import get_rcon_connection_status, test_rcon_connection, execute_rcon_command, force_rcon_reconnect

logger = logging.getLogger(__name__)


class RconStatusService:
    """Service for checking RCON connection status and validation"""
    
    def __init__(self):
        self.system_control = SystemControlService()
        self.server_props = ServerPropertiesParser()
    
    def get_rcon_status(self) -> Dict[str, Any]:
        """
        Get comprehensive RCON connection status
        Returns dict with 'connected', 'host', 'port', 'error' keys
        """
        try:
            # First check if server is running - NO RCON/mcstatus if server not green
            server_status = self.system_control.get_server_status()
            
            if not server_status.get('running', False) or server_status.get('status') != 'running':
                return {
                    'connected': False,
                    'error': f'Server not running (status: {server_status.get("status", "stopped")})'
                }
            
            # Validate server.properties configuration
            validation_result = self._validate_server_properties()
            if not validation_result['valid']:
                return {
                    'connected': False,
                    'error': validation_result['error']
                }
            
            # Get connection details
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            rcon_port = self.server_props.get_rcon_port()
            rcon_password = self.server_props.get_rcon_password()
            
            logger.info(f'RCON config - Host: {server_host}, Port: {rcon_port}, Password: {"SET" if rcon_password else "EMPTY"}')
            
            # Test basic network connectivity first
            network_result = self._test_network_connectivity(server_host, rcon_port)
            if not network_result['success']:
                return {
                    'connected': False,
                    'error': network_result['error']
                }
            
            # Test RCON connection using custom client
            rcon_result = self._test_rcon_connection(server_host, rcon_port, rcon_password)
            if not rcon_result['success']:
                return {
                    'connected': False,
                    'error': rcon_result['error']
                }
            
            logger.info(f'RCON status check: connection successful')
            return {
                'connected': True,
                'host': server_host,
                'port': rcon_port
            }
            
        except Exception as e:
            logger.error(f'RCON status check failed: {str(e)} (type: {type(e).__name__})')
            return {
                'connected': False,
                'error': str(e)
            }
    
    def _validate_server_properties(self) -> Dict[str, Any]:
        """
        Validate server.properties file and RCON configuration
        Returns dict with 'valid' boolean and 'error' message if invalid
        """
        import os
        
        # Check if server.properties file exists
        server_path = current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
        props_file = os.path.join(server_path, 'server.properties')
        logger.info(f'Looking for server.properties at: {props_file}')
        logger.info(f'File exists: {os.path.exists(props_file)}')
        
        if os.path.exists(props_file):
            logger.info(f'File size: {os.path.getsize(props_file)} bytes')
            # Read first few lines for debugging
            try:
                with open(props_file, 'r') as f:
                    first_lines = [f.readline().strip() for _ in range(5)]
                logger.info(f'First 5 lines: {first_lines}')
            except Exception as e:
                logger.error(f'Could not read server.properties: {e}')
        
        # Load properties first
        if not self.server_props.load_properties():
            return {
                'valid': False,
                'error': f'Could not load server.properties file at {props_file}'
            }
        
        all_props = self.server_props.get_all_properties()
        logger.info(f'Loaded server.properties with {len(all_props)} properties')
        logger.info(f'Sample properties: {dict(list(all_props.items())[:5]) if all_props else "None"}')
        
        # Check specific RCON properties
        enable_rcon = self.server_props.get_property('enable-rcon')
        rcon_port_prop = self.server_props.get_property('rcon.port')
        rcon_password_prop = self.server_props.get_property('rcon.password')
        
        logger.info(f'Raw properties - enable-rcon: {enable_rcon}, rcon.port: {rcon_port_prop}, rcon.password: {"SET" if rcon_password_prop else "EMPTY"}')
        
        if not self.server_props.is_rcon_enabled():
            return {
                'valid': False,
                'error': f'RCON is not enabled in server.properties (enable-rcon={enable_rcon}, need enable-rcon=true)'
            }
        
        rcon_password = self.server_props.get_rcon_password()
        if not rcon_password:
            return {
                'valid': False,
                'error': f'RCON password not set in server.properties (rcon.password="{rcon_password_prop}")'
            }
        
        return {'valid': True}
    
    def _test_network_connectivity(self, host: str, port: int) -> Dict[str, Any]:
        """
        Test basic network connectivity to RCON port
        Returns dict with 'success' boolean and 'error' message if failed
        """
        logger.info(f'RCON status check: attempting connection to {host}:{port}')
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result != 0:
                return {
                    'success': False,
                    'error': f'Cannot connect to {host}:{port} - server may not be running or RCON port blocked'
                }
            
            logger.info(f'Socket connection to {host}:{port} successful')
            return {'success': True}
            
        except Exception as socket_error:
            logger.error(f'Socket test failed: {socket_error}')
            return {
                'success': False,
                'error': f'Network connectivity test failed: {str(socket_error)}'
            }
    
    def _test_rcon_connection(self, host: str, port: int, password: str) -> Dict[str, Any]:
        """
        Test RCON connection using custom client
        Returns dict with 'success' boolean and 'error' message if failed
        """
        try:
            # First check if we have an existing connection
            connected, error = get_rcon_connection_status(host, port, password)
            
            # If not connected, try to test connection
            if not connected:
                connected, error = test_rcon_connection(host, port, password)
            
            if not connected:
                raise Exception(error)
            
            logger.info(f'RCON connection successful with custom client')
            return {'success': True}
            
        except Exception as rcon_error:
            logger.error(f'RCON connection failed: {type(rcon_error).__name__}: {rcon_error}', exc_info=True)
            
            error_message = str(rcon_error).lower()
            if 'refused' in error_message or 'timeout' in error_message:
                return {
                    'success': False,
                    'error': f'RCON server not responding on {host}:{port}. Check if Minecraft server is running and RCON is enabled.'
                }
            elif 'auth' in error_message or 'password' in error_message:
                return {
                    'success': False,
                    'error': f'RCON authentication failed. Check rcon.password in server.properties.'
                }
            else:
                return {
                    'success': False,
                    'error': f'RCON connection error: {str(rcon_error)}'
                }
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """
        Execute RCON command with validation and error handling
        Returns dict with 'success', 'command', 'response', 'error' keys
        """
        try:
            if not command or not command.strip():
                return {
                    'success': False,
                    'error': 'No command provided'
                }
            
            # Validate server.properties configuration
            validation_result = self._validate_server_properties()
            if not validation_result['valid']:
                return {
                    'success': False,
                    'error': validation_result['error']
                }
            
            # Get connection details
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            rcon_port = self.server_props.get_rcon_port()
            rcon_password = self.server_props.get_rcon_password()
            
            logger.info(f'RCON execute - Host: {server_host}, Port: {rcon_port}, Command: {command}')
            
            # Execute command via RCON using custom client
            success, response = execute_rcon_command(server_host, rcon_port, rcon_password, command)
            
            if not success:
                raise Exception(response)
            
            logger.info(f'RCON command successful with custom client')
            logger.info(f'RCON command executed: {command}')
            
            return {
                'success': True,
                'command': command,
                'response': response if response else 'Command executed successfully'
            }
            
        except Exception as rcon_error:
            logger.error(f'RCON command execution failed: {rcon_error}')
            
            error_message = str(rcon_error).lower()
            if 'refused' in error_message or 'timeout' in error_message:
                return {
                    'success': False,
                    'error': 'RCON server not responding. Check if Minecraft server is running.'
                }
            elif 'auth' in error_message or 'password' in error_message:
                return {
                    'success': False,
                    'error': 'RCON authentication failed. Check server password.'
                }
            else:
                return {
                    'success': False,
                    'error': f'Command execution failed: {str(rcon_error)}'
                }
    
    def force_reconnect(self) -> Dict[str, Any]:
        """
        Force RCON reconnection with validation
        Returns dict with 'success', 'message', 'error' keys
        """
        try:
            # Validate server.properties configuration
            validation_result = self._validate_server_properties()
            if not validation_result['valid']:
                return {
                    'success': False,
                    'error': validation_result['error']
                }
            
            # Get connection details
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            rcon_port = self.server_props.get_rcon_port()
            rcon_password = self.server_props.get_rcon_password()
            
            # Force reconnection
            success, error = force_rcon_reconnect(server_host, rcon_port, rcon_password)
            
            if success:
                return {
                    'success': True,
                    'message': 'RCON reconnected successfully'
                }
            else:
                return {
                    'success': False,
                    'error': error or 'Failed to reconnect'
                }
                
        except Exception as e:
            logger.error(f'RCON connect failed: {e}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def disconnect(self) -> Dict[str, Any]:
        """
        Disconnect RCON connection
        Returns dict with 'success', 'message' keys
        """
        try:
            from services.rcon_client import RconConnectionManager
            
            # Get server connection details for targeted disconnect
            server_host = current_app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            
            if self.server_props.load_properties():
                rcon_port = self.server_props.get_rcon_port()
                # For simplicity, disconnect all connections
                RconConnectionManager.disconnect_all()
            else:
                # If can't load properties, still disconnect all
                RconConnectionManager.disconnect_all()
            
            return {
                'success': True,
                'message': 'RCON disconnected successfully'
            }
            
        except Exception as e:
            logger.error(f'RCON disconnect failed: {e}')
            return {
                'success': False,
                'error': str(e)
            }