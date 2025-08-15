"""
Server.properties parser service for VaultHunter Web Manager.

Reads and parses Minecraft server.properties files to extract configuration.
"""

import os
import logging
from typing import Dict, Optional, Union
from flask import current_app

class ServerPropertiesParser:
    """Parser for Minecraft server.properties files."""
    
    def __init__(self, server_path: Optional[str] = None):
        """Initialize parser with optional server path."""
        self.server_path = server_path or current_app.config.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunter')
        self.properties_file = os.path.join(self.server_path, 'server.properties')
        self._properties = {}
        self._loaded = False
        
    def load_properties(self) -> bool:
        """Load properties from server.properties file."""
        try:
            if not os.path.exists(self.properties_file):
                current_app.logger.warning(f'server.properties not found at: {self.properties_file}')
                return False
                
            self._properties = {}
            with open(self.properties_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                        
                    # Parse key=value pairs
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        self._properties[key] = value
                    else:
                        current_app.logger.warning(f'Invalid line in server.properties:{line_num}: {line}')
                        
            self._loaded = True
            current_app.logger.info(f'Loaded {len(self._properties)} properties from server.properties')
            return True
            
        except Exception as e:
            current_app.logger.error(f'Failed to load server.properties: {e}')
            return False
    
    def get_property(self, key: str, default: Union[str, int, bool, None] = None) -> Union[str, int, bool, None]:
        """Get a property value with optional default."""
        if not self._loaded:
            self.load_properties()
            
        value = self._properties.get(key)
        if value is None:
            return default
            
        # Convert string values to appropriate types based on default type
        if default is not None:
            if isinstance(default, bool):
                return value.lower() in ('true', 'yes', '1', 'on')
            elif isinstance(default, int):
                try:
                    return int(value)
                except ValueError:
                    return default
                    
        return value
    
    def get_server_port(self) -> int:
        """Get server port (default 25565)."""
        return self.get_property('server-port', 25565)
    
    def get_query_port(self) -> int:
        """Get query port (default same as server port)."""
        query_port = self.get_property('query.port', self.get_server_port())
        return query_port if isinstance(query_port, int) else self.get_server_port()
    
    def is_rcon_enabled(self) -> bool:
        """Check if RCON is enabled."""
        return self.get_property('enable-rcon', False)
    
    def get_rcon_port(self) -> int:
        """Get RCON port (default 25575)."""
        return self.get_property('rcon.port', 25575)
    
    def get_rcon_password(self) -> str:
        """Get RCON password."""
        return self.get_property('rcon.password', '')
    
    def get_max_players(self) -> int:
        """Get max players (default 20)."""
        return self.get_property('max-players', 20)
    
    def get_server_name(self) -> str:
        """Get server name/MOTD."""
        return self.get_property('motd', 'A Minecraft Server')
    
    def is_whitelist_enabled(self) -> bool:
        """Check if whitelist is enabled."""
        return self.get_property('white-list', False)
    
    def is_pvp_enabled(self) -> bool:
        """Check if PvP is enabled."""
        return self.get_property('pvp', True)
    
    def get_difficulty(self) -> str:
        """Get difficulty setting."""
        return self.get_property('difficulty', 'easy')
    
    def get_gamemode(self) -> str:
        """Get default gamemode."""
        return self.get_property('gamemode', 'survival')
    
    def get_level_name(self) -> str:
        """Get world/level name."""
        return self.get_property('level-name', 'world')
    
    def get_all_properties(self) -> Dict[str, str]:
        """Get all loaded properties as dictionary."""
        if not self._loaded:
            self.load_properties()
        return self._properties.copy()
    
    def reload(self) -> bool:
        """Force reload properties from file."""
        self._loaded = False
        return self.load_properties()