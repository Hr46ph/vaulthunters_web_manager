# VaultHunters Web Manager

**Important Note**: Linux only. No Windows support.

A Flask-based web interface for managing VaultHunters Minecraft servers. Provides server control, log monitoring, configuration management, and backup downloads through a responsive Bootstrap interface.

## Features

- **Server Control**: Direct Java process management with Forge launcher support
- **RCON Console**: Dashboard-embedded console with VaultHunters-compatible commands
- **Real-time Log Monitoring**: Server-Sent Events streaming with latest + debug/crash toggle
- **Configuration Management**: Multi-category editor with atomic file operations and automatic backups
- **Backup Management**: Download and inspect backups with cleanup tools
- **Real-time Monitoring**: Accurate server status and player counts using mcstatus
- **Performance Monitoring**: System load averages, memory breakdown charts, CPU per-core monitoring, and swap usage tracking
- **System Analytics**: Interactive Chart.js dashboards with TPS history, lag spike detection, and system health indicators
- **Dark Mode Support**: Universal dark/light theme toggle with persistent settings
- **Responsive Design**: Bootstrap-based UI for desktop, tablet, and mobile
- **Security**: CSRF protection, input validation, and file access restrictions

## Requirements

- Python 3.7+
- VaultHunters Minecraft server installation
- Linux/Unix system with Java 8+
- Dependencies automatically installed via `requirements.txt`

## Screenshots
Dashboard with clean overview:
<img width="1271" height="1200" alt="image" src="https://github.com/user-attachments/assets/75ae2299-9b15-477c-aa42-97e91adc4eb3" />

Dedicated Monitoring & performance statistics with lag spike graphs:
<img width="1271" height="1705" alt="image" src="https://github.com/user-attachments/assets/64afd64c-8f3f-4f44-b203-14b84ad80fd5" />

Dedicated Logging page with keyword highlighting and filtering:
<img width="1271" height="1086" alt="image" src="https://github.com/user-attachments/assets/bc208cf4-420a-480b-b1df-1a6ade04c63f" />

Config viewing and editing:
<img width="1271" height="753" alt="image" src="https://github.com/user-attachments/assets/42c5944a-a434-4719-8330-55c2272657d7" />

Bans and whitelist editing:
<img width="1271" height="581" alt="image" src="https://github.com/user-attachments/assets/8bd90232-cd32-404a-a731-f287b59ba82b" />

Mod Config viewing and editing:
<img width="1271" height="744" alt="image" src="https://github.com/user-attachments/assets/390ff493-830c-4dd0-86a0-7cb68bd18500" />

Reviewing and editing of user_jvm_args.txt with single-button optimization with Aikar's Flags:
<img width="1271" height="779" alt="image" src="https://github.com/user-attachments/assets/dfa1e62a-7fa3-44ad-85e3-38796ea8d3f3" />

Reviewing and editing of unix_args.txt:
<img width="1271" height="779" alt="image" src="https://github.com/user-attachments/assets/d20541fc-c74f-4190-8bff-9a61beebc940" />

## Installation

### Quick Install (Recommended)

**Automated Installation Script:**
```bash
# Download the script first
curl -fsSL https://raw.githubusercontent.com/Hr46ph/vaulthunters_web_manager/main/install.sh -o install.sh
```
```bash
# Then run it like this
sudo bash ./install.sh
```

Once installed, you can delete the script.
```bash
rm install.sh
```

This script will:
- Test system requirements and sudo permissions
- Prompt for the Minecraft server user (creates if needed)
- Detect existing VaultHunters server or prompt for location
- Clone the project and set up the virtual environment
- Create systemd service and limited sudoers permissions
- Generate secure configuration with random secret key
- Test port availability and start the service

**Quick Uninstall:**
```bash
# Download the script first
curl -fsSL https://raw.githubusercontent.com/Hr46ph/vaulthunters_web_manager/main/uninstall.sh -o uninstall.sh
```
```bash
# Then run it like this
sudo bash ./uninstall.sh
```

Once uninstalled, you can delete the script.
```bash
rm uninstall.sh
```

### Manual Installation (Advanced Users)

For advanced users who prefer manual installation or need custom configuration:

**Important Security Note**: This application should be run as the same user running the VaultHunters Minecraft server. This user should not have full sudo privileges. This user only needs sudo for managing the Web Manager systemd service. For this I will provide a special sudoers file. Do not install or run this as the root user.

**Prerequisites:**
- A regular user account that will own and run both the Minecraft server and web manager. Common usernames are `minecraft` or your personal username.
- A second user account with full sudo privileges to create the systemd unit file for the web manager application and to place the restricted sudo permissions file for the other account, running the web manager and minecraft server.

**Important Security Note**: Technically, you can do everything with a default user account that has unlimited sudo with 'nopasswd', or even as root itself. You shouldn't. For any Java application, especially Minecraft servers exposed to the internet this is a HUGE security risk. There have been major security vulnerabilities in Java and in Minecraft servers in general, which have been actively used in the past. You take a massive risk by running all this as root, or with an unrestricted user account.

**Manual Installation Steps:**

1. **Log in as the user running Minecraft server** and clone the project:
```bash
cd
git clone https://github.com/Hr46ph/vaulthunters_web_manager.git
cd vaulthunters_web_manager
```
If the git command is not available, use your distributions' package manager to install it.

2. **Set up Python virtual environment** (as the minecraft user):
```bash
# Inside the vaulthunters_web_manager directory
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. **Configure the application** (as minecraft user):
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

4. **Create systemd service** (as your regular user, requires sudo):
```bash
sudo systemctl edit --force --full vaulthunters_web_manager.service
```

Add the following content (replace `minecraft` with the username running the minecraft server):
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

5. **Create limited sudo permissions** for service management (as your regular user, requires sudo):

This step allows your minecraft user to manage the web service without full root access:

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

If you want the web manager to automatically start, run the enable command. If you want to start it manually now, and in the future after system reboots, only run the start command.

6. **Enable and start the service** (as your regular user, requires sudo):
```bash
sudo systemctl enable vaulthunters_web_manager.service
sudo systemctl start vaulthunters_web_manager.service
```

After this setup, you can manage the service with your minecraft user:
```bash
# These commands now work without password prompts
sudo systemctl status vaulthunters_web_manager.service
sudo systemctl restart vaulthunters_web_manager.service
```

## Configuration

### Server Setup

After setting up the web manager, you can review and edit your VaultHunters minecraft configuration files with via the webUI.

### RCON Setup

Configure RCON in your Minecraft server's `server.properties`:
```properties
enable-rcon=true
rcon.port=25575
rcon.password=your-secure-password
```

The RCON password is read from the configuration files and used transparently for the Web RCON feature.

## Usage

1. Navigate to `http://your-server-ip:8080`. Change the port if you changed it to something else

2. **Server Control Panel**: Start, stop, and restart server with real-time status monitoring

3. **RCON Console**: Execute Minecraft commands with VaultHunters-compatible quick commands

4. **Log Viewer**: Real-time log streaming with latest + debug/crash toggle

5. **Monitoring Dashboard**: System performance analytics with real-time charts for:
   - TPS (Ticks Per Second) history and lag spike detection
   - System memory breakdown (used/buffers/cache) with swap usage
   - CPU usage per core with system load averages
   - Server health status indicators and performance events

6. **Configuration Editor**: Multi-category editor for server properties, bans & whitelist, and config files. Quick button to add Aikar's Flags to optimize for VaultHunters. Review the memory requirements.

7. **Backup Manager**: Create, view, download, restore and manage server backups (partly implemented)

## Security

- Web interface runs under the same user as your Minecraft server
- No root privileges required apart from harmless commands to start the web manager and view journal logs
- CSRF protection with Flask-WTF
- Path validation using `os.path.realpath()`
- Input validation with file size limits
- File access restrictions within configured directories
- Secure session management

**Important**: This web application has no authentication and opens RCON console to your server transparently. This web application is NOT secure and should never be exposed to the internet. If run locally, consider setting it to 127.0.0.1 to prevent access via LAN or WiFi.

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
