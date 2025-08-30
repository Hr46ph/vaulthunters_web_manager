# VaultHunters Web Manager

A Flask-based web application for managing VaultHunters Minecraft servers. Provides server control, log monitoring, configuration management, and backup downloads through a web interface.

## Features

- **Server Control**: Start, stop, restart Minecraft server processes
- **RCON Console**: Execute server commands through integrated console
- **Log Monitoring**: Real-time log viewing with Server-Sent Events
- **Configuration Editor**: Edit server.properties and mod configurations
- **Configuration Checker**: Actively checks your server.properties for application compatibility and will ask to apply the changes 
- **Backup Management**: Download and manage server backups
- **Status Monitoring**: Real-time server status and player counts
- **Security**: CSRF protection and input validation

## Requirements

- **Python 3.10** minimum, 3.12+ recommended
- **Java 17** only! (requirement for Vaulthunters modpack)
- **Caddy** web server for TLS termination and reverse proxy
- Recent Linux kernel 6.x with systemd (required for systemd service, can run manually without, or init script if you make them yourself)

**Note**: Caddy should simply be installed, not enabled or running! The application starts a caddy user session as an integral part of the application.

## Screenshots

<img width="1576" height="1491" alt="image" src="https://github.com/user-attachments/assets/f3883b82-dd1f-40b4-82ba-9ed2113c1abb" />

<img width="1576" height="637" alt="image" src="https://github.com/user-attachments/assets/05ac8052-61ed-403d-9aa9-76403a986a14" />

<img width="1576" height="948" alt="image" src="https://github.com/user-attachments/assets/7c928280-de10-40bd-a918-bc1709728ce6" />

<img width="1576" height="971" alt="image" src="https://github.com/user-attachments/assets/611a887f-8989-4ec1-9125-655c8a48e5f1" />

<img width="1576" height="840" alt="image" src="https://github.com/user-attachments/assets/ad589d21-da4b-4703-ad88-c3da3e3a2c2f" />

## Installation

### Automated Installation

Download and run manually:

```bash
wget https://raw.githubusercontent.com/Hr46ph/vaulthunters_web_manager/main/install.sh
# Reviewing the file is strongly recommended
sh ./install.sh
# or chmod and run directly:
chmod +x install.sh
./install.sh
```

### Manual Installation

1. Clone the repository:
```bash
git clone --branch v1.0.0 https://github.com/Hr46ph/vaulthunters_web_manager.git
cd vaulthunters_web_manager
```

2. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Copy and configure settings:
```bash
cp config.toml.example config.toml
# Edit config.toml with your server paths and settings
```

4. Run the application:
```bash
python app.py
```

## Configuration

The application uses `config.toml` for configuration. Key settings include:

- **Server paths**: Minecraft server directory and backup location
- **Web interface**: Host, port, and security settings
- **Memory settings**: Java heap allocation based on system RAM
- **File permissions**: Editable configuration files

See `config.toml.example` for detailed configuration options.

## Usage

Access the web interface at `https://localhost:8889` (HTTPS via Caddy reverse proxy).

### Service Management

If installed via the automated installer:

```bash
sudo systemctl status vaulthunters_web_manager.service
sudo systemctl restart vaulthunters_web_manager.service
sudo systemctl stop vaulthunters_web_manager.service
```

### View Logs

If installed via the automated installer:

```bash
sudo journalctl -u vaulthunters_web_manager.service -f
```

## Architecture

- **Caddy Reverse Proxy**: TLS termination and HTTPS handling with automatic certificate management
- **Flask Backend**: HTTP application server running on localhost for security
- **Direct Process Management**: Controls Minecraft server processes without requiring systemd
- **Real-time Updates**: Server-Sent Events for live log streaming and status updates
- **Security**: Flask-WTF CSRF protection and input validation
- **Process Independence**: Web application restarts don't affect running Minecraft server

## Development

1. Clone and set up virtual environment (see Manual Installation)
2. Copy `config.toml.example` to `config.toml`
3. Configure paths for your development environment
4. Run with `python app.py`

## Uninstallation

Use the uninstaller script:

```bash
curl -fsSL https://raw.githubusercontent.com/Hr46ph/vaulthunters_web_manager/main/uninstall.sh | bash
```

## License

This project is open source. See the repository for license details.

## Support

- Check the [Issues](https://github.com/Hr46ph/vaulthunters_web_manager/issues) page for common problems
- Review `RCON_HELP.md` for VaultHunters-specific commands
- Examine service logs for troubleshooting: `journalctl -u vaulthunters_web_manager.service`

