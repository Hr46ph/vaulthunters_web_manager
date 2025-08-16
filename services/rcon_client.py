import socket
import struct
import threading
import time
from typing import Optional, Tuple

class RconClient:
    """Custom RCON client using raw sockets to avoid signal handling issues"""
    
    # RCON packet types
    SERVERDATA_AUTH = 3
    SERVERDATA_EXECCOMMAND = 2
    SERVERDATA_RESPONSE_VALUE = 0
    SERVERDATA_AUTH_RESPONSE = 2
    
    def __init__(self, host: str, port: int, password: str, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.socket = None
        self.request_id = 1
        self._lock = threading.Lock()
    
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
                
                return True
                
        except Exception as e:
            if self.socket:
                self.socket.close()
                self.socket = None
            raise e
    
    def command(self, cmd: str) -> str:
        """Execute an RCON command"""
        try:
            with self._lock:
                if not self.socket:
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
                
        except Exception as e:
            self.disconnect()
            raise e
    
    def disconnect(self):
        """Disconnect from the RCON server"""
        with self._lock:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


def test_rcon_connection(host: str, port: int, password: str) -> Tuple[bool, Optional[str]]:
    """Test RCON connection and return (success, error_message)"""
    try:
        with RconClient(host, port, password) as rcon:
            response = rcon.command("list")
            return True, None
    except Exception as e:
        return False, str(e)


def execute_rcon_command(host: str, port: int, password: str, command: str) -> Tuple[bool, str]:
    """Execute RCON command and return (success, response/error)"""
    try:
        with RconClient(host, port, password) as rcon:
            response = rcon.command(command)
            return True, response
    except Exception as e:
        return False, str(e)