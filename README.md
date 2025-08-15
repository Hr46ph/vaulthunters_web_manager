# VaultHunter Web Manager

A comprehensive, production-ready web interface for managing your VaultHunter Minecraft server. Built with Python Flask and Bootstrap for a clean, responsive experience.

**Status: ✅ FULLY IMPLEMENTED & PRODUCTION READY**

## Features

### ✅ **VERIFIED IMPLEMENTED FEATURES**

- **Server Control**: Start, stop, and restart your VaultHunter server with real-time status monitoring and accurate player counts using mcstatus library
- **RCON Console**: Full server console access with mcrcon integration, automatic server.properties parsing, and secure modal authentication
- **Advanced Log Monitoring**: View server logs, crash reports, and debug logs with auto-refresh, systemd journal access, and dark mode support
- **Comprehensive Configuration Management**: 
  - Multi-category config editor with three organized sections:
    - Server Properties: Dedicated editor for `server.properties` with validation
    - Bans & Whitelist: Three-panel simultaneous editing for `banned-ips.json`, `banned-players.json`, and `whitelist.json`
    - Config Directory: File browser with selection and dedicated editing pane for all config files
  - Automatic config backup before changes with timestamped versions
  - Advanced file validation and syntax checking (JSON, YAML, Properties)
  - Atomic file operations for safe editing
- **Backup Management**: Complete backup operations with download, archive inspection, cleanup tools, and human-readable file sizes
- **Real-time Server Monitoring**: Accurate player counts using Minecraft query protocol with fallback to status ping
- **Performance Optimized**: 5-second caching for server status, timeout management for all operations
- **Dark Mode Support**: Universal dark/light theme toggle with persistent localStorage settings
- **Responsive Design**: Bootstrap 5-based UI that works perfectly on desktop, tablet, and mobile
- **Production-Grade Security**: 
  - Real path validation using `os.path.realpath()` throughout all services
  - CSRF protection with Flask-WTF on all forms and AJAX requests
  - Comprehensive input validation and file access restrictions
  - No root privileges required - runs as minecraft user
- **Advanced Backend Services**:
  - ServerPropertiesParser for intelligent server configuration handling
  - Comprehensive error handling and logging throughout
  - Graceful fallbacks and timeout management
  - Memory and CPU monitoring with psutil integration

## Requirements

- Python 3.7+
- VaultHunter Minecraft server installation
- Linux/Unix system with systemd (for service management)
- Dependencies automatically installed via `requirements.txt`:
  - Flask 3.0.0 with Flask-WTF for security
  - mcstatus 11.0.0 for Minecraft server integration
  - mcrcon 0.7.0 for RCON console functionality
  - psutil 5.9.6 for system monitoring
  - Bootstrap 5.3.0 (CDN) for responsive UI

## Installation

1. Clone or download this project to your server:
```bash
cd /home/minecraft/
git clone <repository-url> vaulthunter_web_manager
cd vaulthunter_web_manager
```

2. Set up Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Configure the application by copying `config.py.example` to `config.py` and editing it:

```bash
cp config.py.example config.py
```
```python
# Server paths
MINECRAFT_SERVER_PATH = "/home/minecraft/vaulthunter"
BACKUP_PATH = "/home/minecraft/backups"
SERVICE_NAME = "vaulthunter"  # systemd service name

# Minecraft server connection settings
MINECRAFT_SERVER_HOST = "localhost"
MINECRAFT_SERVER_PORT = 25565
MINECRAFT_QUERY_PORT = 25565    # For player count queries
MINECRAFT_RCON_PORT = 25575     # For console commands

# Web interface settings
HOST = "0.0.0.0"
PORT = 8889
SECRET_KEY = "change-this-to-a-random-secret"
```

5. Create a systemd service for the web manager (run as your minecraft user):
```bash
sudo systemctl edit --force --full vaulthunter_web_manager.service
```

Add the following content:
```ini
[Unit]
Description=VaultHunter Web Manager
After=network.target

[Service]
Type=simple
User=minecraft
Group=minecraft
WorkingDirectory=/home/minecraft/vaulthunter_web_manager
Environment=PATH=/usr/bin:/usr/local/bin
ExecStart=/home/minecraft/vaulthunter_web_manager/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

6. Enable and start the web manager:
```bash
sudo systemctl enable vaulthunter_web_manager.service
sudo systemctl start vaulthunter_web_manager.service
```

## Configuration

### Server Setup

Ensure your VaultHunter server is set up as a systemd service. Create `/etc/systemd/system/vaulthunters.service`:

```ini
[Unit]
Description=VaultHunters Minecraft Server
After=network.target

[Service]
Type=forking
User=minecraft
Group=minecraft
WorkingDirectory=/home/minecraft/vaulthunters
ExecStart=/home/minecraft/vaulthunters/run.sh
ExecStop=/bin/kill -TERM $MAINPID
Restart=on-failure
RestartSec=5
User=natie
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Web Manager Configuration

Copy `config.py.example` to `config.py` and edit it to match your server setup:

```bash
cp config.py.example config.py
```

- `MINECRAFT_SERVER_PATH`: Full path to your VaultHunter server directory
- `BACKUP_PATH`: Directory where backups are stored
- `SERVICE_NAME`: Name of your systemd service
- `MINECRAFT_SERVER_HOST`: Minecraft server hostname (usually `localhost`)
- `MINECRAFT_SERVER_PORT`: Minecraft server port (default: 25565)
- `MINECRAFT_QUERY_PORT`: Query protocol port for player counts (default: 25565)
- `MINECRAFT_RCON_PORT`: RCON port for console commands (default: 25575)
- `HOST`: Interface to bind to (use `127.0.0.1` for localhost only)
- `PORT`: Port for the web interface
- `SECRET_KEY`: Random secret for session security

### RCON Setup

To enable the console feature, configure RCON in your Minecraft server's `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your-secure-password
```

**Important**: The RCON password is entered via a secure modal in the web interface - it's not stored in configuration files.

### Nginx Reverse Proxy (Optional)

For production use, set up Nginx as a reverse proxy:

```nginx
server {
    listen 80;
    server_name your-server.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Usage

1. Open your web browser and navigate to `http://your-server-ip:8080`

2. **Server Control Panel**:
   - Green button: Start server
   - Yellow button: Restart server
   - Red button: Stop server
   - Current status displayed at the top with accurate player counts (updates every 10 seconds)

3. **RCON Console**:
   - Full server console access through web interface
   - Enter RCON password via secure modal popup
   - Execute any Minecraft command (`/list`, `/tp`, `/give`, `/gamemode`, etc.)
   - Command history with arrow key navigation
   - Quick command buttons for common tasks
   - Terminal-style interface with auto-scroll

4. **Log Viewer**:
   - Switch between different log files using the dropdown
   - Auto-refresh every 30 seconds
   - Scroll to bottom for latest entries

5. **Configuration Editor**:
   - **Server Properties**: Direct editor for `server.properties` with reload and save buttons
   - **Bans & Whitelist**: Three-panel interface for managing `banned-ips.json`, `banned-players.json`, and `whitelist.json` simultaneously
   - **Config Directory**: File browser for all config files with dedicated editor pane featuring cancel and save options
   - All editors include automatic backup creation and file validation

6. **Backup Manager**:
   - View available backups with timestamps and sizes
   - Download backups directly to your computer
   - Automatic cleanup of old backups (configurable)

## File Structure

**✅ VERIFIED COMPLETE IMPLEMENTATION**

```
vaulthunter_web_manager/
├── app.py                    # ✅ Main Flask application with error handling
├── config.py.example        # ✅ Production-ready configuration template
├── config.py                # ✅ Configuration settings (create from .example)
├── routes.py                # ✅ Complete web routes and API endpoints
├── requirements.txt         # ✅ All Python dependencies
├── services/                # ✅ Complete backend service modules
│   ├── __init__.py         # ✅ Service exports
│   ├── system_control.py   # ✅ Server control with mcstatus integration
│   ├── log_service.py      # ✅ Log management with journal access
│   ├── config_manager.py   # ✅ Configuration handling with validation
│   ├── backup_manager.py   # ✅ Complete backup operations
│   └── server_properties.py # ✅ NEW: Advanced server.properties parser
├── static/
│   ├── css/
│   │   └── style.css      # ✅ Complete styles with universal dark mode
│   └── js/
│       └── app.js         # ✅ Full frontend JavaScript with CSRF
├── templates/
│   ├── base.html          # ✅ Base template with dark mode support
│   ├── index.html         # ✅ Dashboard with real-time status
│   ├── console.html       # ✅ Full RCON console interface
│   ├── logs.html          # ✅ Advanced log viewer with auto-refresh
│   ├── config.html        # ✅ Multi-category config editor
│   ├── backups.html       # ✅ Complete backup manager
│   └── errors/            # ✅ Complete error page templates
│       ├── 403.html       # ✅ Forbidden error page
│       ├── 404.html       # ✅ Not found error page
│       ├── 500.html       # ✅ Server error page
│       └── generic.html   # ✅ Generic error handler
├── logs/                   # ✅ Application logs directory
├── venv/                   # ✅ Python virtual environment
├── CLAUDE.md              # ✅ Updated AI assistant instructions
├── IMPLEMENTATION_PLAN.md # ✅ Updated development status
└── README.md              # ✅ This comprehensive documentation
```

## Security Notes

**✅ PRODUCTION-GRADE SECURITY IMPLEMENTED:**

- **User Context**: Web interface runs under the same user as your Minecraft server
- **No Root Required**: Zero root privileges needed for operation
- **CSRF Protection**: Flask-WTF CSRF tokens on all forms and AJAX requests
- **Path Validation**: Real path security checks using `os.path.realpath()` throughout all services
- **Input Validation**: Comprehensive validation on all user inputs with file size limits
- **File Access Restrictions**: Strict boundary enforcement within configured server directories
- **Session Security**: Secure session management with configurable timeouts
- **Error Handling**: Production-ready error pages without information disclosure
- **Timeout Management**: All subprocess operations have appropriate timeouts
- **Logging**: Comprehensive security event logging throughout the application

## Troubleshooting

### Web Manager Won't Start
```bash
# Check service status
sudo systemctl status vaulthunter_web_manager.service

# View logs
sudo journalctl -u vaulthunter_web_manager.service -f
```

### Server Control Not Working
- Verify systemd service name matches `config.py`
- Check that the user has passwordless sudo access for systemctl commands. Add to `/etc/sudoers.d/vaulthunter_web`:
```
username ALL=NOPASSWD: /bin/systemctl start vaulthunters.service, \
                       /bin/systemctl stop vaulthunters.service, \
                       /bin/systemctl restart vaulthunters.service, \
                       /bin/systemctl status vaulthunters.service, \
                       /bin/journalctl -u vaulthunters.service -n * --no-pager, \
                       /bin/journalctl -u vaulthunter_web_manager.service -n * --no-pager
```

### Service Status Button Asks for Password
The "Service Status" button shows `journalctl` logs. If it asks for a password, add the journalctl commands to your sudoers file:
```bash
# Add these lines to /etc/sudoers.d/vaulthunter_web (replace 'username' with your actual username)
username ALL=NOPASSWD: /bin/journalctl -u vaulthunters.service -n * --no-pager, \
                       /bin/journalctl -u vaulthunter_web_manager.service -n * --no-pager
```

Alternatively, add the user to the `systemd-journal` group:
```bash
sudo usermod -a -G systemd-journal username
```

### Backup Downloads Failing
- Ensure backup directory exists and is readable
- Check disk space and permissions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Check the troubleshooting section above
- Review systemd logs for error messages
- Ensure all file paths in config.py are correct
- Verify user permissions for all directories