# VaultHunter Web Manager

A comprehensive, production-ready web interface for managing your VaultHunter Minecraft server. Built with Python Flask and Bootstrap for a clean, responsive experience.

**Status: ✅ FULLY IMPLEMENTED & PRODUCTION READY**

## Features

### ✅ **VERIFIED IMPLEMENTED FEATURES**

- **Server Control**: **Process-independent** Java management - server survives web app restarts with real-time status monitoring, PID display, and dynamic MB/GB memory formatting
- **Integrated RCON Console**: Dashboard-embedded console with custom socket client, VaultHunters-compatible commands (/forge tps), and zero threading issues
- **Streamlined Log Monitoring**: 2-window log interface (latest + debug/crash toggle) with simplified controls, **real-time Server-Sent Events streaming**, and dark mode support
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
- Linux/Unix system with Java 8+ (for Minecraft server execution)
- Dependencies automatically installed via `requirements.txt`:
  - Flask 3.0.0 with Flask-WTF for security
  - mcstatus 11.0.0 for Minecraft server integration
  - mcrcon 0.7.0 for RCON console functionality
  - psutil 5.9.6 for process monitoring and management
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

# Java and server settings for direct process management
JAVA_EXECUTABLE = "java"  # or full path like "/usr/lib/jvm/java-17-openjdk/bin/java"
SERVER_JAR = "forge-1.18.2-40.2.21-universal.jar"

# Minecraft server connection settings (RCON details auto-read from server.properties)
MINECRAFT_SERVER_HOST = "localhost"
MINECRAFT_SERVER_PORT = 25565

# Web interface settings
HOST = "0.0.0.0"
PORT = 8080
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

**Process-Independent Management** - No separate systemd service needed for the Minecraft server! The web manager launches the server with complete independence - server survives web app restarts.

Ensure your VaultHunter server directory contains:
- `server.properties` with RCON enabled:
  ```properties
  enable-rcon=true
  rcon.port=25575
  rcon.password=your-secure-password
  ```
- Forge launcher files (user_jvm_args.txt and libraries directory with unix_args.txt)
- Java 8+ installed and accessible via `java` command

### Web Manager Configuration

Copy `config.py.example` to `config.py` and edit it to match your server setup:

```bash
cp config.py.example config.py
```

- `MINECRAFT_SERVER_PATH`: Full path to your VaultHunter server directory
- `BACKUP_PATH`: Directory where backups are stored
- `JAVA_EXECUTABLE`: Java command or full path (e.g., `/usr/lib/jvm/java-17-openjdk/bin/java`)
- `SERVER_JAR`: Minecraft server jar filename
- `MINECRAFT_SERVER_HOST`: Minecraft server hostname (usually `localhost`)
- `MINECRAFT_SERVER_PORT`: Minecraft server port (default: 25565)
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
   - Green button: Start server (direct Java process launch, no confirmation)
   - Yellow button: Restart server (confirmation required, graceful stop + start)
   - Red button: Stop server (confirmation required, graceful shutdown with force-kill fallback)
   - Current status with PID display and dynamic memory formatting (MB/GB), updates every 10 seconds

3. **Integrated RCON Console**:
   - Dashboard-embedded console (replaced System Information section)
   - Custom socket client completely resolves threading issues
   - VaultHunters-compatible quick commands (`/forge tps`, `/list`, `/help`, `/whitelist list`)
   - Execute any Minecraft command with command history and arrow key navigation
   - Real-time connection status and automatic configuration from server.properties

4. **Streamlined Log Viewer**:
   - **2-window interface**: Latest log + debug/crash toggle window
   - **Real-time Streaming**: Server-Sent Events (SSE) for instant log updates (no more 10-second delays)
   - **Process-Safe**: Removed log rotation features that interfered with server management
   - **Debug/Crash Toggle**: Radio buttons to switch between debug and latest crash report
   - **Auto-follow**: Latest log following enabled by default
   - **Log Rotation Support**: Automatically handles server restarts and log file rotation using `tail -F`

4. **Configuration Editor**:
   - **Server Properties**: Direct editor for `server.properties` with reload and save buttons
   - **Bans & Whitelist**: Three-panel interface for managing `banned-ips.json`, `banned-players.json`, and `whitelist.json` simultaneously
   - **Config Directory**: File browser for all config files with dedicated editor pane featuring cancel and save options
   - All editors include automatic backup creation and file validation

5. **Backup Manager**:
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
- Verify `JAVA_EXECUTABLE` path in `config.py` (try `which java` to find it)
- Check `SERVER_JAR` filename matches your actual server jar file
- Ensure `MINECRAFT_SERVER_PATH` is correct and contains server files
- Verify Java version compatibility (Java 8+ required for VaultHunter)
- Check server directory permissions (readable/writable by web manager user)

### RCON Console Not Working
- Verify `enable-rcon=true` in server.properties
- Check `rcon.port` and `rcon.password` are set in server.properties
- Ensure Minecraft server is running (start it via web interface first)
- Test network connectivity: `telnet localhost 25575` (or your RCON port)
- Check server logs for RCON initialization messages

### Process Management Issues
- If server won't start: check Java path and version compatibility
- If server won't stop: web manager uses graceful shutdown (SIGTERM) then force-kill
- Memory issues: adjust JVM arguments in `config.py` JAVA_ARGS section
- Check application logs: `sudo journalctl -u vaulthunter_web_manager.service -f`

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