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

**Important Security Note**: This application should be run as the same user running the VaultHunters Minecraft server. This user should not have sudo privileges. This user only needs sudo for managing the Web Manager systemd service. For this I will provide a special sudoers file. Do not install or run this as the root user.

### Prerequisites

- A regular user account that will own and run both the Minecraft server and web manager. Common usernames are `minecraft` or your personal username.
- A second user account with sudo privileges to create systemd unit file for the web manager application and to place the restricted sudo permissions file for the other account.

Technically, you can do everything with a default user account that has unlimited sudo with 'nopasswd', or even as root itself. You shouldn't. For any Java application, especially Minecraft servers exposed to the internet this is a HUGE security risk. There have been major security vulnerabilities in Java and in Minecraft servers in general, which have been actively used in the past. You take a massive risk by running all this as root, or with an unrestricted user account.

### Installation Steps

1. **Log in as the user running Minecraft server** and clone the project:
```bash
# Replace 'minecraft' with the username running the server
cd /home/minecraft/
git clone https://github.com/Hr46ph/vaulthunters_web_manager.git
cd vaulthunters_web_manager
```
If the git command is not available, use your distributions' package manager to install it.

2. **Set up Python virtual environment** (as regular user):
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. **Configure the application** (as regular user):
```bash
cp config.toml.example config.toml
```

Edit `config.toml` with your server paths and settings. The configuration uses TOML format which is more user-friendly than Python code:

```toml
[server]
minecraft_server_path = "/home/minecraft/vaulthunters"
backup_path = "/home/minecraft/backups" 
java_executable = "java"
server_jar = "forge-1.18.2-40.2.21-universal.jar"
minecraft_server_host = "localhost"
minecraft_server_port = 25565

[jvm]
# Adjust memory based on your system (4G minimum, 8G recommended for VaultHunters)
memory_min = "4G"
memory_max = "8G"

[web]
host = "0.0.0.0"
port = 8080
# IMPORTANT: Change this to a random secret key!
secret_key = "change-this-to-a-random-secret-key"
debug = false
```

**Important**: The JVM optimization flags are pre-configured with Aikar's flags, which are specifically optimized for Minecraft servers and reduce lag spikes caused by garbage collection.

4. **Create systemd service** (requires sudo):
```bash
sudo systemctl edit --force --full vaulthunters_web_manager.service
```

Add the following content (replace `minecraft` with your username):
```ini
[Unit]
Description=VaultHunters Web Manager
After=network.target
Wants=network.target

[Service]
Type=simple
User=minecraft
Group=minecraft
WorkingDirectory=/home/minecraft/vaulthunters_web_manager
Environment=PATH=/home/minecraft/vaulthunters_web_manager/venv/bin:/usr/bin:/usr/local/bin
ExecStart=/home/minecraft/vaulthunters_web_manager/venv/bin/python /home/minecraft/vaulthunters_web_manager/app.py
KillMode=process
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

5. **Create limited sudo permissions** for service management (requires sudo):

This step allows your regular user to manage the web service without full root access:

```bash
# Replace 'minecraft' with your username
sudo visudo -f /etc/sudoers.d/minecraft
```

Add the following content (replace `minecraft` with your actual username):
```
minecraft ALL=NOPASSWD: /bin/systemctl start vaulthunters_web_manager.service, \
                        /bin/systemctl stop vaulthunters_web_manager.service, \
                        /bin/systemctl restart vaulthunters_web_manager.service, \
                        /bin/systemctl status vaulthunters_web_manager.service
minecraft ALL=NOPASSWD: /bin/journalctl -u vaulthunters_web_manager.service -n * --no-pager
```

**What this does**: Allows your user to start/stop/restart the web service and view its logs without entering a password, while keeping all other system operations secure.

6. **Enable and start the service** (requires sudo):
```bash
sudo systemctl enable vaulthunters_web_manager.service
sudo systemctl start vaulthunters_web_manager.service
```

After this setup, you can manage the service as your regular user:
```bash
# These commands now work without sudo prompts
sudo systemctl status vaulthunters_web_manager.service
sudo systemctl restart vaulthunters_web_manager.service
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
├── config.toml.example      # Configuration template (TOML format)
├── config.toml              # Configuration settings (TOML format)
├── config.py                # Configuration loader
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
- Verify `java_executable` path in `config.toml`
- Check `server_jar` filename matches your server jar
- Ensure `minecraft_server_path` is correct
- Verify Java version compatibility (Java 8+ required)

### RCON Console Not Working
- Verify `enable-rcon=true` in server.properties
- Check `rcon.port` and `rcon.password` are set
- Ensure Minecraft server is running
- Test connectivity: `telnet localhost 25575`

## License

MIT License