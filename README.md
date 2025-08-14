# VaultHunter Web Manager

A simple, lightweight web interface for managing your VaultHunter Minecraft server. Built with Python Flask and Bootstrap for a clean, responsive experience.

## Features

- **Server Control**: Start, stop, and restart your VaultHunter server with real-time status monitoring and accurate player counts
- **RCON Console**: Full server console access with RCON authentication for executing commands, managing players, and server administration
- **Advanced Log Monitoring**: View server logs, crash reports, and debug logs with auto-refresh and dark mode support
- **Comprehensive Configuration Management**: 
  - Organized config editor with three categories:
    - Server Properties editor for `server.properties`
    - Bans & Whitelist manager with three-panel view for `banned-ips.json`, `banned-players.json`, and `whitelist.json`
    - Config Directory browser with file selection and editing interface
  - Automatic config backup before changes
  - File validation and syntax checking
- **Backup Management**: Download, view, and manage server backups with file size information and cleanup tools
- **Real-time Server Monitoring**: Accurate player counts and server status using Minecraft query protocol
- **Dark Mode Support**: Full dark/light theme toggle with consistent styling across all pages
- **Responsive Design**: Clean Bootstrap-based UI that works perfectly on desktop, tablet, and mobile
- **Security First**: Runs under the same user account as your Minecraft server (no root required) with CSRF protection and session-based RCON authentication

## Requirements

- Python 3.7+
- VaultHunter Minecraft server installation
- Linux/Unix system with systemd (for service management)

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

4. Configure the application by editing `config.py`:
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

Edit `config.py` to match your server setup:

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

```
vaulthunter_web_manager/
├── app.py                    # Main Flask application
├── config.py                # Configuration settings
├── routes.py                # Web routes and API endpoints
├── requirements.txt         # Python dependencies
├── services/                # Backend service modules
│   ├── __init__.py         # Service exports
│   ├── system_control.py   # Server control and status
│   ├── log_service.py      # Log file management
│   ├── config_manager.py   # Configuration file handling
│   └── backup_manager.py   # Backup operations
├── static/
│   ├── css/
│   │   └── style.css      # Custom styles with dark mode
│   └── js/
│       └── app.js         # Frontend JavaScript and dark mode
├── templates/
│   ├── base.html          # Base template with dark mode support
│   ├── index.html         # Dashboard with server control
│   ├── console.html       # RCON console interface
│   ├── logs.html          # Advanced log viewer
│   ├── config.html        # Multi-category config editor
│   ├── backups.html       # Backup manager
│   └── errors/            # Error page templates
│       ├── 403.html
│       ├── 404.html
│       ├── 500.html
│       └── generic.html
├── CLAUDE.md              # AI assistant instructions
├── IMPLEMENTATION_PLAN.md # Development roadmap
└── README.md
```

## Security Notes

- The web interface runs under the same user as your Minecraft server
- No root privileges required
- Uses session-based authentication
- Input validation on all forms
- File access restricted to configured directories

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