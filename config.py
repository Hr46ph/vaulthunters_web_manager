import os
from datetime import timedelta

class Config:
    # Server paths - adjust these to match your setup
    MINECRAFT_SERVER_PATH = os.environ.get('MINECRAFT_SERVER_PATH', '/home/minecraft/vaulthunter')
    BACKUP_PATH = os.environ.get('BACKUP_PATH', '/home/minecraft/backups')
    SERVICE_NAME = os.environ.get('SERVICE_NAME', 'vaulthunters')
    
    # Minecraft server connection settings
    MINECRAFT_SERVER_HOST = os.environ.get('MINECRAFT_SERVER_HOST', 'localhost')
    MINECRAFT_SERVER_PORT = int(os.environ.get('MINECRAFT_SERVER_PORT', 25565))
    MINECRAFT_QUERY_PORT = int(os.environ.get('MINECRAFT_QUERY_PORT', 25565))
    MINECRAFT_RCON_PORT = int(os.environ.get('MINECRAFT_RCON_PORT', 25575))
    
    # Web interface settings
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 8080))
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-to-a-random-secret-key')
    
    # Flask settings
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    TESTING = False
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Set to True when using HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    
    # File upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Log file paths (relative to MINECRAFT_SERVER_PATH)
    LOG_FILES = {
        'server': 'logs/latest.log',
        'debug': 'logs/debug.log',
        'crash': 'crash-reports',
    }
    
    # Config files that can be edited (relative to MINECRAFT_SERVER_PATH)
    EDITABLE_CONFIGS = [
        'server.properties',
        'bukkit.yml',
        'spigot.yml',
        'paper.yml',
        'config/paper-global.yml',
        'config/paper-world-defaults.yml'
    ]
    
    # Backup file extensions allowed for download
    ALLOWED_BACKUP_EXTENSIONS = {'.zip', '.tar.gz', '.tar', '.7z'}
    
    # Rate limiting (requests per minute)
    RATE_LIMIT_SERVER_CONTROL = 5
    RATE_LIMIT_CONFIG_SAVE = 10
    RATE_LIMIT_BACKUP_DOWNLOAD = 3
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}