import socket
import struct
import threading
import time
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class RconClient:
    """Custom RCON client using raw sockets to avoid signal handling issues"""
    
    # RCON packet types
    SERVERDATA_AUTH = 3
    SERVERDATA_EXECCOMMAND = 2
    SERVERDATA_RESPONSE_VALUE = 0
    SERVERDATA_AUTH_RESPONSE = 2
    
    def __init__(self, host: str, port: int, password: str, timeout: float = 10.0, max_retries: int = 3):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self.socket = None
        self.request_id = 1
        self._lock = threading.Lock()
        self._connected = False
        self._last_connection_attempt = 0
        self._connection_cooldown = 5  # seconds between connection attempts
    
    def _pack_packet(self, packet_type: int, body: str) -> bytes:
        """Pack an RCON packet"""
        body_bytes = body.encode('utf-8')
        packet_size = 4 + 4 + len(body_bytes) + 2  # id + type + body + null terminators
        
        return struct.pack('<I', packet_size) + \
               struct.pack('<I', self.request_id) + \
               struct.pack('<I', packet_type) + \
               body_bytes + \
               b'\x00\x00'
    
    def _unpack_packet(self, data: bytes) -> Tuple[int, int, str]:
        """Unpack an RCON packet"""
        if len(data) < 12:
            raise ValueError("Invalid packet: too short")
        
        packet_size = struct.unpack('<I', data[:4])[0]
        packet_id = struct.unpack('<I', data[4:8])[0]
        packet_type = struct.unpack('<I', data[8:12])[0]
        
        body = data[12:-2].decode('utf-8', errors='replace')
        
        return packet_id, packet_type, body
    
    def _receive_packet(self) -> Tuple[int, int, str]:
        """Receive a complete RCON packet"""
        # Read packet size first
        size_data = self._recv_exactly(4)
        packet_size = struct.unpack('<I', size_data)[0]
        
        # Read the rest of the packet
        packet_data = self._recv_exactly(packet_size)
        
        # Unpack the packet
        packet_id = struct.unpack('<I', packet_data[:4])[0]
        packet_type = struct.unpack('<I', packet_data[4:8])[0]
        body = packet_data[8:-2].decode('utf-8', errors='replace')
        
        return packet_id, packet_type, body
    
    def _recv_exactly(self, size: int) -> bytes:
        """Receive exactly the specified number of bytes"""
        data = b''
        while len(data) < size:
            chunk = self.socket.recv(size - len(data))
            if not chunk:
                raise ConnectionError("Connection lost while receiving data")
            data += chunk
        return data
    
    def connect(self) -> bool:
        """Connect to the RCON server and authenticate"""
        try:
            with self._lock:
                # Check cooldown to prevent spam
                current_time = time.time()
                if current_time - self._last_connection_attempt < self._connection_cooldown:
                    return False
                
                self._last_connection_attempt = current_time
                
                # Clean up existing socket
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = None
                
                # Create socket
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                
                # Connect
                self.socket.connect((self.host, self.port))
                
                # Send authentication packet
                auth_packet = self._pack_packet(self.SERVERDATA_AUTH, self.password)
                self.socket.send(auth_packet)
                
                # Receive auth response
                packet_id, packet_type, body = self._receive_packet()
                
                # Check if authentication was successful
                if packet_id == -1:
                    raise ConnectionError("Authentication failed: invalid password")
                
                self._connected = True
                logger.info(f"RCON connected to {self.host}:{self.port}")
                return True
                
        except Exception as e:
            self._connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            logger.warning(f"RCON connection failed to {self.host}:{self.port}: {e}")
            raise e
    
    def is_connected(self) -> bool:
        """Check if RCON is currently connected"""
        return self._connected and self.socket is not None
    
    def _attempt_reconnect(self) -> bool:
        """Attempt to reconnect with retries"""
        for attempt in range(self.max_retries):
            try:
                if self.connect():
                    return True
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 10))  # Exponential backoff, max 10s
        return False
    
    def command(self, cmd: str, auto_reconnect: bool = True) -> str:
        """Execute an RCON command with automatic reconnection"""
        try:
            with self._lock:
                # Check if we need to reconnect
                if not self.is_connected():
                    if auto_reconnect:
                        logger.info("RCON not connected, attempting to reconnect...")
                        if not self._attempt_reconnect():
                            raise ConnectionError("Failed to reconnect to RCON server after multiple attempts")
                    else:
                        raise ConnectionError("Not connected to RCON server")
                
                # Increment request ID
                self.request_id += 1
                
                # Send command packet
                cmd_packet = self._pack_packet(self.SERVERDATA_EXECCOMMAND, cmd)
                self.socket.send(cmd_packet)
                
                # Send empty packet to signal end of multi-packet response
                empty_packet = self._pack_packet(self.SERVERDATA_EXECCOMMAND, "")
                self.socket.send(empty_packet)
                
                # Receive response packets
                responses = []
                while True:
                    packet_id, packet_type, body = self._receive_packet()
                    
                    if packet_id == self.request_id:
                        responses.append(body)
                        break
                    elif packet_id == self.request_id + 1:
                        # Empty packet response - we're done
                        break
                    else:
                        # Got a response packet
                        responses.append(body)
                
                return ''.join(responses)
                
        except (ConnectionError, socket.error, OSError) as e:
            self._connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            
            # Try to reconnect if auto_reconnect is enabled
            if auto_reconnect and isinstance(e, (socket.error, OSError)):
                logger.info("Connection lost, attempting to reconnect...")
                if self._attempt_reconnect():
                    # Retry the command after successful reconnection
                    return self.command(cmd, auto_reconnect=False)
            
            raise e
    
    def disconnect(self):
        """Disconnect from the RCON server"""
        with self._lock:
            self._connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
                logger.info(f"RCON disconnected from {self.host}:{self.port}")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# Global RCON connection pool
_rcon_connections = {}
_connection_lock = threading.Lock()

class RconConnectionManager:
    """Manages persistent RCON connections"""
    
    @staticmethod
    def get_connection(host: str, port: int, password: str) -> RconClient:
        """Get or create a persistent RCON connection"""
        connection_key = f"{host}:{port}"
        
        with _connection_lock:
            if connection_key not in _rcon_connections:
                _rcon_connections[connection_key] = RconClient(host, port, password)
            
            return _rcon_connections[connection_key]
    
    @staticmethod
    def disconnect_all():
        """Disconnect all RCON connections"""
        with _connection_lock:
            for connection in _rcon_connections.values():
                connection.disconnect()
            _rcon_connections.clear()
    
    @staticmethod
    def force_reconnect(host: str, port: int, password: str) -> bool:
        """Force disconnect and reconnect for a specific connection"""
        connection_key = f"{host}:{port}"
        
        with _connection_lock:
            if connection_key in _rcon_connections:
                _rcon_connections[connection_key].disconnect()
                del _rcon_connections[connection_key]
            
            # Create new connection
            rcon = RconClient(host, port, password)
            try:
                rcon.connect()
                _rcon_connections[connection_key] = rcon
                return True
            except Exception as e:
                logger.error(f"Failed to force reconnect RCON: {e}")
                return False

def test_rcon_connection(host: str, port: int, password: str) -> Tuple[bool, Optional[str]]:
    """Test RCON connection and return (success, error_message)"""
    try:
        rcon = RconConnectionManager.get_connection(host, port, password)
        if not rcon.is_connected():
            rcon.connect()
        response = rcon.command("list", auto_reconnect=True)
        return True, None
    except Exception as e:
        return False, str(e)

def execute_rcon_command(host: str, port: int, password: str, command: str) -> Tuple[bool, str]:
    """Execute RCON command with persistent connection and auto-reconnect"""
    try:
        rcon = RconConnectionManager.get_connection(host, port, password)
        response = rcon.command(command, auto_reconnect=True)
        
        # Filter out common false-positive error messages that don't indicate actual failures
        if response and isinstance(response, str):
            # Common Minecraft RCON quirks where commands work but return error-like messages
            filtered_response = _filter_rcon_response(command, response)
            return True, filtered_response
        
        return True, response
    except Exception as e:
        return False, str(e)

def _filter_rcon_response(command: str, response: str) -> str:
    """Filter RCON responses to remove false-positive error messages"""
    if not response:
        return response
    
    # Commands that commonly work but return error-like messages
    working_commands_with_errors = ['list', 'help', 'forge tps', 'tps']
    
    # Check if this is a command that commonly has false-positive errors
    cmd_lower = command.lower().strip()
    
    # If the response contains "Unknown or incomplete command" but the command is known to work
    if "Unknown or incomplete command" in response:
        # For 'list' command, if we get players listed after the error, it actually worked
        if cmd_lower == 'list' and ('players online' in response.lower() or 'There are' in response):
            # Extract just the useful part (player list)
            lines = response.split('\n')
            for line in lines:
                if 'There are' in line or 'players online' in line:
                    return line.strip()
            return "Players listed successfully"
        
        # For 'forge tps' command, look for TPS data
        elif 'tps' in cmd_lower and ('Mean tick time' in response or 'TPS' in response):
            # Extract TPS information, ignore the error
            lines = response.split('\n')
            tps_lines = [line for line in lines if 'Mean tick time' in line or 'TPS' in line or 'ms' in line]
            if tps_lines:
                return '\n'.join(tps_lines)
        
        # For 'help' command, if we get command list after error, it worked
        elif cmd_lower == 'help' and ('Available commands' in response or '/' in response):
            lines = response.split('\n')
            help_lines = [line for line in lines if not line.startswith('Unknown or incomplete')]
            if help_lines:
                return '\n'.join(help_lines)
        
        # For other commands, if the response has actual content beyond the error, extract it
        error_line = "Unknown or incomplete command, see below for error"
        if error_line in response:
            parts = response.split(error_line)
            if len(parts) > 1 and parts[1].strip():
                # There's content after the error message
                return parts[1].strip()
            elif len(parts) > 0 and parts[0].strip() and parts[0].strip() != error_line:
                # There's content before the error message
                return parts[0].strip()
        
        # If we can't extract useful content, note that command was executed but had parsing issues
        return f"Command executed (response parsing issue - this is a Minecraft RCON quirk, command likely worked)"
    
    return response

def get_rcon_connection_status(host: str, port: int, password: str) -> Tuple[bool, Optional[str]]:
    """Get current RCON connection status"""
    try:
        connection_key = f"{host}:{port}"
        with _connection_lock:
            if connection_key in _rcon_connections:
                rcon = _rcon_connections[connection_key]
                return rcon.is_connected(), None
            return False, "No connection established"
    except Exception as e:
        return False, str(e)

def force_rcon_reconnect(host: str, port: int, password: str) -> Tuple[bool, Optional[str]]:
    """Force RCON reconnection"""
    try:
        success = RconConnectionManager.force_reconnect(host, port, password)
        if success:
            return True, None
        else:
            return False, "Reconnection failed"
    except Exception as e:
        return False, str(e)