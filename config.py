"""
VaultHunters Web Manager Configuration

Loads configuration from config.toml file with fallback to environment variables.
"""

import os
import toml
from datetime import timedelta

class Config:
    def __init__(self):
        # Load TOML config file
        config_path = os.path.join(os.path.dirname(__file__), 'config.toml')
        try:
            with open(config_path, 'r') as f:
                self.toml_config = toml.load(f)
        except FileNotFoundError:
            print(f"Warning: {config_path} not found. Using environment variables and defaults.")
            self.toml_config = {}
        except Exception as e:
            print(f"Error loading {config_path}: {e}. Using environment variables and defaults.")
            self.toml_config = {}
    
    def _get_config(self, section, key, env_var, default, type_converter=str):
        """Get config value with precedence: env var > toml > default"""
        # Environment variable has highest precedence
        env_value = os.environ.get(env_var)
        if env_value is not None:
            return type_converter(env_value)
        
        # TOML config second
        try:
            toml_value = self.toml_config.get(section, {}).get(key)
            if toml_value is not None:
                return type_converter(toml_value)
        except (KeyError, TypeError):
            pass
        
        # Default fallback
        return default
    
    @property
    def MINECRAFT_SERVER_PATH(self):
        return self._get_config('server', 'minecraft_server_path', 'MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunters')
    
    @property 
    def BACKUP_PATH(self):
        return self._get_config('server', 'backup_path', 'BACKUP_PATH', '/home/minecraft/backups')
    
    @property
    def JAVA_EXECUTABLE(self):
        return self._get_config('server', 'java_executable', 'JAVA_EXECUTABLE', 'java')
    
    @property
    def SERVER_JAR(self):
        return self._get_config('server', 'server_jar', 'SERVER_JAR', 'forge-1.18.2-40.2.21-universal.jar')
    
    @property
    def MINECRAFT_SERVER_HOST(self):
        return self._get_config('server', 'minecraft_server_host', 'MINECRAFT_SERVER_HOST', 'localhost')
    
    @property
    def MINECRAFT_SERVER_PORT(self):
        return self._get_config('server', 'minecraft_server_port', 'MINECRAFT_SERVER_PORT', 25565, int)
    
    @property
    def FORGE_STARTUP_COMMAND(self):
        """Get Forge launcher startup command from TOML configuration"""
        try:
            forge_config = self.toml_config.get('forge', {})
            startup_command = forge_config.get('startup_command', [])
            if startup_command:
                return startup_command
        except Exception:
            pass
        
        # Fallback to your original Forge launcher command
        return [
            '@user_jvm_args.txt',
            '@libraries/net/minecraftforge/forge/1.18.2-40.2.9/unix_args.txt'
        ]
    
    @property
    def HOST(self):
        return self._get_config('web', 'host', 'HOST', '0.0.0.0')
    
    @property
    def PORT(self):
        return self._get_config('web', 'port', 'PORT', 8080, int)
    
    @property
    def SECRET_KEY(self):
        return self._get_config('web', 'secret_key', 'SECRET_KEY', 'change-this-to-a-random-secret-key')
    
    @property
    def DEBUG(self):
        debug_val = self._get_config('web', 'debug', 'DEBUG', False)
        if isinstance(debug_val, str):
            return debug_val.lower() == 'true'
        return debug_val
    
    @property
    def TESTING(self):
        return False
    
    @property
    def PERMANENT_SESSION_LIFETIME(self):
        hours = self._get_config('security', 'session_lifetime_hours', 'SESSION_LIFETIME_HOURS', 24, int)
        return timedelta(hours=hours)
    
    @property
    def SESSION_COOKIE_SECURE(self):
        return self._get_config('security', 'session_cookie_secure', 'SESSION_COOKIE_SECURE', False, bool)
    
    @property
    def SESSION_COOKIE_HTTPONLY(self):
        return self._get_config('security', 'session_cookie_httponly', 'SESSION_COOKIE_HTTPONLY', True, bool)
    
    @property
    def SESSION_COOKIE_SAMESITE(self):
        return self._get_config('security', 'session_cookie_samesite', 'SESSION_COOKIE_SAMESITE', 'Lax')
    
    @property
    def WTF_CSRF_ENABLED(self):
        return self._get_config('security', 'csrf_enabled', 'WTF_CSRF_ENABLED', True, bool)
    
    @property
    def WTF_CSRF_TIME_LIMIT(self):
        return self._get_config('security', 'csrf_time_limit', 'WTF_CSRF_TIME_LIMIT', 3600, int)
    
    @property
    def MAX_CONTENT_LENGTH(self):
        mb = self._get_config('security', 'max_file_size_mb', 'MAX_FILE_SIZE_MB', 16, int)
        return mb * 1024 * 1024
    
    @property
    def LOG_FILES(self):
        try:
            logs_config = self.toml_config.get('logs', {})
            return {
                'server': logs_config.get('server_log', 'logs/latest.log'),
                'debug': logs_config.get('debug_log', 'logs/debug.log'),
                'crash': logs_config.get('crash_reports', 'crash-reports'),
            }
        except Exception:
            return {
                'server': 'logs/latest.log',
                'debug': 'logs/debug.log',
                'crash': 'crash-reports',
            }
    
    @property
    def EDITABLE_CONFIGS(self):
        try:
            return self.toml_config.get('files', {}).get('editable_configs', [
                'server.properties',
                'whitelist.json',
                'banned-players.json', 
                'banned-ips.json',
                'ops.json'
            ])
        except Exception:
            return [
                'server.properties',
                'whitelist.json',
                'banned-players.json',
                'banned-ips.json', 
                'ops.json'
            ]
    
    @property
    def ALLOWED_BACKUP_EXTENSIONS(self):
        try:
            extensions = self.toml_config.get('files', {}).get('allowed_backup_extensions', ['.zip', '.tar.gz', '.tar', '.7z'])
            return set(extensions)
        except Exception:
            return {'.zip', '.tar.gz', '.tar', '.7z'}
    
    @property
    def RATE_LIMIT_SERVER_CONTROL(self):
        return self._get_config('rate_limiting', 'server_control', 'RATE_LIMIT_SERVER_CONTROL', 5, int)
    
    @property
    def RATE_LIMIT_CONFIG_SAVE(self):
        return self._get_config('rate_limiting', 'config_save', 'RATE_LIMIT_CONFIG_SAVE', 10, int)
    
    @property
    def RATE_LIMIT_BACKUP_DOWNLOAD(self):
        return self._get_config('rate_limiting', 'backup_download', 'RATE_LIMIT_BACKUP_DOWNLOAD', 3, int)
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    @property
    def DEBUG(self):
        return True

class ProductionConfig(Config):
    @property
    def DEBUG(self):
        return False
    
    @property
    def SESSION_COOKIE_SECURE(self):
        return True

class TestingConfig(Config):
    @property
    def TESTING(self):
        return True
    
    @property
    def WTF_CSRF_ENABLED(self):
        return False

# Create instances
_development_config = DevelopmentConfig()
_production_config = ProductionConfig()
_testing_config = TestingConfig()

config = {
    'development': _development_config,
    'production': _production_config,
    'testing': _testing_config,
    'default': _development_config
}