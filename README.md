# VaultHunter Web Manager

A simple, lightweight web interface for managing your VaultHunter Minecraft server. Built with Python Flask and Bootstrap for a clean, responsive experience.

## Features

- **Server Control**: Start, stop, and restart your VaultHunter server
- **Log Monitoring**: View server logs, crash reports, and debug logs
- **Configuration Management**: Edit server properties through the web interface
- **Backup Downloads**: Download and manage server backups directly from the browser
- **User-Friendly Interface**: Clean Bootstrap-based UI that works on desktop and mobile
- **Secure**: Runs under the same user account as your Minecraft server (no root required)

## Requirements

- Python 3.7+
- VaultHunter Minecraft server installation
- Linux/Unix system with systemd (for service management)

## Installation

1. Clone or download this project to your server:
```bash
cd /home/minecraft/
git clone <repository-url> vaulthunter-web-manager
cd vaulthunter-web-manager
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

# Web interface settings
HOST = "0.0.0.0"
PORT = 8889
SECRET_KEY = "change-this-to-a-random-secret"
```

5. Create a systemd service for the web manager (run as your minecraft user):
```bash
sudo systemctl edit --force --full vaulthunter-web.service
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
WorkingDirectory=/home/minecraft/vaulthunter-web-manager
Environment=PATH=/usr/bin:/usr/local/bin
ExecStart=/home/minecraft/vaulthunter-web-manager/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

6. Enable and start the web manager:
```bash
sudo systemctl enable vaulthunter-web.service
sudo systemctl start vaulthunter-web.service
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
- `HOST`: Interface to bind to (use `127.0.0.1` for localhost only)
- `PORT`: Port for the web interface
- `SECRET_KEY`: Random secret for session security

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
   - Current status displayed at the top

3. **Log Viewer**:
   - Switch between different log files using the dropdown
   - Auto-refresh every 30 seconds
   - Scroll to bottom for latest entries

4. **Configuration Editor**:
   - Select configuration file from dropdown
   - Edit directly in the web interface
   - Save changes with validation

5. **Backup Manager**:
   - View available backups with timestamps and sizes
   - Download backups directly to your computer
   - Automatic cleanup of old backups (configurable)

## File Structure

```
vaulthunter-web-manager/
├── app.py                 # Main Flask application
├── config.py             # Configuration settings
├── requirements.txt      # Python dependencies
├── static/
│   ├── css/
│   │   └── style.css    # Custom styles
│   └── js/
│       └── app.js       # Frontend JavaScript
├── templates/
│   ├── base.html        # Base template
│   ├── index.html       # Dashboard
│   ├── logs.html        # Log viewer
│   ├── config.html      # Configuration editor
│   └── backups.html     # Backup manager
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
sudo systemctl status vaulthunter-web.service

# View logs
sudo journalctl -u vaulthunter-web.service -f
```

### Server Control Not Working
- Verify systemd service name matches `config.py`
- Check that the user has passwordless sudo access for systemctl commands. Add to `/etc/sudoers.d/vaulthunter-web`:
```
username ALL=NOPASSWD: /bin/systemctl start vaulthunters.service, \
                       /bin/systemctl stop vaulthunters.service, \
                       /bin/systemctl restart vaulthunters.service, \
                       /bin/systemctl status vaulthunters.service
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