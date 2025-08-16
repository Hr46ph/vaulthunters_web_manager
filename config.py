#!/usr/bin/env python3

import os
import toml
from typing import Dict, Any

def load_toml_config() -> Dict[str, Any]:
    """Load configuration from config.toml file"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.toml')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please copy config.toml.example to config.toml and customize it for your environment."
        )
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return toml.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load configuration from {config_path}: {e}")

def create_flask_config(toml_config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert TOML config to Flask configuration format"""
    server_config = toml_config.get('server', {})
    web_config = toml_config.get('web', {})
    security_config = toml_config.get('security', {})
    jvm_config = toml_config.get('jvm', {})
    logs_config = toml_config.get('logs', {})
    files_config = toml_config.get('files', {})
    
    return {
        # Server settings
        'MINECRAFT_SERVER_PATH': server_config.get('minecraft_server_path', '/home/minecraft/vaulthunters'),
        'BACKUP_PATH': server_config.get('backup_path', '/home/minecraft/backups'),
        'JAVA_EXECUTABLE': server_config.get('java_executable', 'java'),
        'SERVER_JAR': server_config.get('server_jar', 'forge-1.18.2-40.2.21-universal.jar'),
        'MINECRAFT_SERVER_HOST': server_config.get('minecraft_server_host', 'localhost'),
        'MINECRAFT_SERVER_PORT': server_config.get('minecraft_server_port', 25565),
        
        # JVM settings
        'MEMORY_MIN': jvm_config.get('memory_min', '4G'),
        'MEMORY_MAX': jvm_config.get('memory_max', '8G'),
        'OPTIMIZATION_FLAGS': jvm_config.get('optimization_flags', []),
        'SYSTEM_PROPERTIES': jvm_config.get('system_properties', []),
        
        # Web interface
        'HOST': web_config.get('host', '0.0.0.0'),
        'PORT': web_config.get('port', 8080),
        'SECRET_KEY': web_config.get('secret_key', 'change-this-to-a-random-secret-key'),
        'DEBUG': web_config.get('debug', False),
        
        # Security
        'SESSION_COOKIE_SECURE': security_config.get('session_cookie_secure', False),
        'SESSION_COOKIE_HTTPONLY': security_config.get('session_cookie_httponly', True),
        'SESSION_COOKIE_SAMESITE': security_config.get('session_cookie_samesite', 'Lax'),
        'CSRF_ENABLED': security_config.get('csrf_enabled', True),
        'CSRF_TIME_LIMIT': security_config.get('csrf_time_limit', 3600),
        'MAX_CONTENT_LENGTH': security_config.get('max_file_size_mb', 16) * 1024 * 1024,
        
        # Logs
        'LOG_FILES': {
            'server': logs_config.get('server_log', 'logs/latest.log'),
            'debug': logs_config.get('debug_log', 'logs/debug.log'),
            'crash_reports': logs_config.get('crash_reports', 'crash-reports')
        },
        
        # Files
        'EDITABLE_CONFIGS': files_config.get('editable_configs', [
            'server.properties',
            'whitelist.json',
            'banned-players.json', 
            'banned-ips.json',
            'ops.json'
        ]),
        'ALLOWED_BACKUP_EXTENSIONS': files_config.get('allowed_backup_extensions', ['.zip', '.tar.gz', '.tar', '.7z'])
    }

class Config:
    """Base configuration class"""
    
    def __init__(self):
        self.toml_config = load_toml_config()
        flask_config = create_flask_config(self.toml_config)
        
        # Apply all configuration values to this class
        for key, value in flask_config.items():
            setattr(self, key, value)

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True

# Configuration dictionary for Flask factory pattern
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}