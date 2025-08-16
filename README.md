# VaultHunters Web Manager

A Flask-based web interface for managing VaultHunters Minecraft servers. Provides server control, log monitoring, configuration management, and backup downloads through a responsive Bootstrap interface.

## Features

- **Server Control**: Direct Java process management with Forge launcher support
- **RCON Console**: Dashboard-embedded console with VaultHunters-compatible commands
- **Real-time Log Monitoring**: Server-Sent Events streaming with latest + debug/crash toggle
- **Configuration Management**: Multi-category editor with atomic file operations and automatic backups
- **Backup Management**: Download and inspect backups with cleanup tools
- **Real-time Monitoring**: Accurate server status and player counts using mcstatus
- **Dark Mode Support**: Universal dark/light theme toggle with persistent settings
- **Responsive Design**: Bootstrap-based UI for desktop, tablet, and mobile
- **Security**: CSRF protection, input validation, and file access restrictions

## Requirements

- Python 3.7+
- VaultHunters Minecraft server installation
- Linux/Unix system with Java 8+
- Dependencies automatically installed via `requirements.txt`

## Installation

1. Clone and setup the project:
```bash
cd /home/minecraft/
git clone <repository-url> vaulthunters_web_manager
cd vaulthunters_web_manager
```

2. Set up Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Configure the application:
```bash
cp config.py.example config.py
```

Edit `config.py` with your server paths and settings:
```python
MINECRAFT_SERVER_PATH = "/home/minecraft/vaulthunters"
BACKUP_PATH = "/home/minecraft/backups"
JAVA_EXECUTABLE = "java"
MINECRAFT_SERVER_HOST = "localhost"
MINECRAFT_SERVER_PORT = 25565
HOST = "0.0.0.0"
PORT = 8080
SECRET_KEY = "change-this-to-a-random-secret"
```

4. Create systemd service:
```bash
sudo systemctl edit --force --full vaulthunters_web_manager.service
```

Add the following content:
```ini
[Unit]
Description=VaultHunters Web Manager
After=network.target

[Service]
Type=simple
User=minecraft
Group=minecraft
WorkingDirectory=/home/minecraft/vaulthunters_web_manager
Environment=PATH=/usr/bin:/usr/local/bin
ExecStart=/home/minecraft/vaulthunters_web_manager/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

5. Enable and start the service:
```bash
sudo systemctl enable vaulthunters_web_manager.service
sudo systemctl start vaulthunters_web_manager.service
```

## Configuration

### Server Setup

Ensure your VaultHunters server directory contains:
- `server.properties` with RCON enabled:
  ```properties
  enable-rcon=true
  rcon.port=25575
  rcon.password=your-secure-password
  ```
- Forge launcher files (user_jvm_args.txt and libraries directory)
- Java 8+ installed and accessible

### RCON Setup

Configure RCON in your Minecraft server's `server.properties`:
```properties
enable-rcon=true
rcon.port=25575
rcon.password=your-secure-password
```

The RCON password is entered via a secure modal in the web interface.

## Usage

1. Navigate to `http://your-server-ip:8080`

2. **Server Control Panel**: Start, stop, and restart server with real-time status monitoring

3. **RCON Console**: Execute Minecraft commands with VaultHunters-compatible quick commands

4. **Log Viewer**: Real-time log streaming with latest + debug/crash toggle

5. **Configuration Editor**: Multi-category editor for server properties, bans & whitelist, and config files

6. **Backup Manager**: View, download, and manage server backups

## File Structure

```
vaulthunters_web_manager/
├── app.py                    # Main Flask application
├── config.py.example        # Configuration template
├── config.py                # Configuration settings
├── routes.py                # Web routes and API endpoints
├── requirements.txt         # Python dependencies
├── services/                # Backend service modules
│   ├── system_control.py   # Server control with mcstatus integration
│   ├── log_service.py      # Log management with journal access
│   ├── config_manager.py   # Configuration handling with validation
│   ├── backup_manager.py   # Backup operations
│   ├── rcon_client.py      # Custom RCON client
│   └── server_properties.py # Server properties parser
├── static/
│   ├── css/style.css       # Styles with dark mode support
│   └── js/app.js          # Frontend JavaScript with CSRF
├── templates/
│   ├── base.html          # Base template with dark mode
│   ├── index.html         # Dashboard with real-time status
│   ├── console.html       # RCON console interface
│   ├── logs.html          # Log viewer with auto-refresh
│   ├── config.html        # Multi-category config editor
│   ├── backups.html       # Backup manager
│   └── errors/            # Error page templates
└── venv/                   # Python virtual environment
```

## Security

- Web interface runs under the same user as your Minecraft server
- No root privileges required
- CSRF protection with Flask-WTF
- Path validation using `os.path.realpath()`
- Input validation with file size limits
- File access restrictions within configured directories
- Secure session management

## Troubleshooting

### Web Manager Won't Start
```bash
sudo systemctl status vaulthunters_web_manager.service
sudo journalctl -u vaulthunters_web_manager.service -f
```

### Server Control Not Working
- Verify `JAVA_EXECUTABLE` path in `config.py`
- Check `SERVER_JAR` filename matches your server jar
- Ensure `MINECRAFT_SERVER_PATH` is correct
- Verify Java version compatibility (Java 8+ required)

### RCON Console Not Working
- Verify `enable-rcon=true` in server.properties
- Check `rcon.port` and `rcon.password` are set
- Ensure Minecraft server is running
- Test connectivity: `telnet localhost 25575`

## License

MIT License