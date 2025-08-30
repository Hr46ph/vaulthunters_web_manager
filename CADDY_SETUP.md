# Caddy Setup Instructions

## Installation

Since Caddy is not currently installed, you can install it using one of these methods:

### Option 1: Official Installation Script (Recommended)
```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

### Option 2: Download Binary (Alternative)
```bash
# Download latest Caddy binary for Linux
curl -o caddy.tar.gz https://caddyserver.com/api/download?os=linux&arch=amd64
tar -xzf caddy.tar.gz
sudo mv caddy /usr/local/bin/
sudo chmod +x /usr/local/bin/caddy
```

## Configuration

The Caddyfile has been created at `/home/natie/vaulthunters_web_manager/Caddyfile` with the following setup:

- **Frontend (HTTPS)**: `:8889` (listens on all interfaces with TLS termination)
- **Backend (HTTP)**: `127.0.0.1:8081` (Flask application)
- **Security headers**: HSTS, XSS protection, clickjacking protection
- **Compression**: Gzip encoding enabled
- **Logging**: Access logs to `/var/log/caddy/vaulthunters_access.log`

## Running Caddy

### Development/Testing
```bash
cd /home/natie/vaulthunters_web_manager
caddy run
```

### Production (as systemd service)
```bash
# Create caddy user and directories
sudo groupadd --system caddy
sudo useradd --system --gid caddy --create-home --home-dir /var/lib/caddy --shell /usr/sbin/nologin caddy

# Create log directory
sudo mkdir -p /var/log/caddy
sudo chown caddy:caddy /var/log/caddy

# Install Caddy service
sudo caddy add-package systemd
sudo systemctl daemon-reload
sudo systemctl enable caddy
sudo systemctl start caddy
```

## Configuration Updates

The Flask configuration (`config.toml`) has been updated:

- **Port changed**: `8889` → `8081` (backend port for Caddy)
- **SSL disabled**: `ssl_enabled = false` (Caddy handles TLS)
- **Redirect disabled**: `ssl_redirect = false` (Caddy handles redirects)

## Testing

1. Start Flask application on port 8081:
   ```bash
   source venv/bin/activate
   python app.py
   ```

2. Start Caddy (in another terminal):
   ```bash
   cd /home/natie/vaulthunters_web_manager
   caddy run
   ```

3. Access the application:
   - **HTTPS**: `https://localhost:8889` (through Caddy)
   - **HTTP Backend**: `http://127.0.0.1:8081` (direct Flask - for testing only)

## Production Notes

For production deployment:

1. Replace `localhost:8889` in Caddyfile with your actual domain
2. Caddy will automatically obtain Let's Encrypt certificates for real domains
3. Update firewall rules to allow port 8889 (or 443 for real domains)
4. Consider running both Flask and Caddy as systemd services

## Architecture Benefits

- **Performance**: Caddy handles TLS efficiently, Flask focuses on application logic
- **Security**: Professional TLS implementation with automatic certificate management
- **Scalability**: Reverse proxy architecture allows for load balancing in the future
- **Maintenance**: Automatic certificate renewal, no manual SSL management