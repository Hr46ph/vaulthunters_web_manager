## Optimal Caddy Configuration

```caddyfile
{
    auto_https off
    skip_install_trust
    storage file_system {
        root {\$HOME}/.local/share/caddy
    }
    debug
}

eend.int.pribi.nl:8889 {
    tls /path/to/cert.pem /path/to/key.pem

    # WebSocket support
    @websocket path /socket.io/* /ws/*
    handle @websocket {
        reverse_proxy 127.0.0.1:8081 {
            transport http {
                websocket
            }
        }
    }

    # Main reverse proxy configuration
    reverse_proxy 127.0.0.1:8081 {
        header_up Host {host}
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-Port {port}
        header_up X-Forwarded-For {remote_host}
        header_up X-Real-IP {remote_host}

        # Timeout settings
        timeout 30s
        read_timeout 30s
        write_timeout 30s
        dial_timeout 5s

        # Handle redirects properly
        transport http {
            disable_redirects
        }
    }

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
        X-Frame-Options "DENY"
        -Server
    }

    # Logging configuration
    log {
        output file /home/natie/vaulthunters_web_manager/logs/caddy_access.log {
            roll_size 100MiB
            roll_keep 10
        }
    }
}
```

## Flask Application Configuration

```python
from flask import Flask, request, url_for
from flask_login import LoginManager

app = Flask(__name__)

# Configure Flask to work behind a proxy
app.config.update(
    # Trust proxy headers for URL generation
    PREFERRED_URL_SCHEME='https',
    TRUSTED_PROXIES=['127.0.0.1'],  # Trust Caddy's IP

    # Session configuration
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',

    # Static files configuration
    STATIC_URL_PATH='/static',
    STATIC_FOLDER='static'
)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.request_loader = load_user_from_request  # You'll need to define this

# Middleware to handle proxy headers
@app.before_request
def handle_proxy():
    # Set the correct scheme based on X-Forwarded-Proto header
    scheme = request.headers.get('X-Forwarded-Proto', 'http')
    if scheme == 'https':
        request.environ['wsgi.url_scheme'] = 'https'

    # Set the correct host if we have X-Forwarded-Host
    if 'X-Forwarded-Host' in request.headers:
        request.environ['HTTP_HOST'] = request.headers['X-Forwarded-Host']

    # For authentication endpoints, ensure proper redirect URLs
    if request.path.startswith('/login'):
        # Get the original host from headers
        host = request.headers.get('X-Forwarded-Host', request.host)
        scheme = request.headers.get('X-Forwarded-Proto', 'http')

        # Store these for redirect generation
        request.environ['REAL_SCHEME'] = scheme
        request.environ['REAL_HOST'] = host

# Example route that needs authentication
@app.route('/console/status')
def console_status():
    # Your status checking logic here
    if not current_user.is_authenticated:
        # Generate proper absolute URL for login redirect
        host = request.environ.get('REAL_HOST', request.host)
        scheme = request.environ.get('REAL_SCHEME', 'http')
        return redirect(f"{scheme}://{host}/login")
    return jsonify({"status": "ok"})

# WebSocket route example
@app.route('/ws')
def websocket_endpoint():
    # Your WebSocket handling logic
    pass
```

## Common Issues and Solutions

1. Redirect Loops
Problem: Infinite redirect loops between Caddy and Flask
Solution: Configure Flask to generate proper absolute URLs:

```python
from werkzeug.urls import url_parse

def get_base_url():
    scheme = request.environ.get('wsgi.url_scheme', 'http')
    host = request.headers.get('X-Forwarded-Host', request.host)
    return f"{scheme}://{host}"

@app.route('/login')
def login():
    # Generate proper absolute URLs
    redirect_url = get_base_url() + url_for('dashboard')
    return redirect(redirect_url)
```

2. Static Files Not Loading
Problem: Static files return 404 errors
Solution: Ensure Flask serves static files correctly:

```python
# Configure static files properly
app = Flask(__name__,
           static_url_path='/static',
           static_folder='static')

@app.route('/static/<path\:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)
```

3. WebSocket Connection Issues
Problem: WebSocket connections fail or disconnect
Solution: Ensure proper WebSocket support in Caddy and Flask:

```
# In your Caddyfile
transport http {
    websocket
}
```

```python
# In your Flask app with Flask-SocketIO
from flask_socketio import SocketIO
socketio = SocketIO(app, cors_allowed_origins=[
    "https://eend.int.pribi.nl",
    "http://localhost:8081"
])
```

4. Session/Cookie Issues
Problem: Session cookies not working properly
Solution: Configure session cookies to work behind a proxy:

```python
from flask import session

@app.before_request
def configure_session():
    # Configure session cookie attributes
    session.permanent = True
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
```

## Best Practices

Security Headers: Always include security headers in your Caddy configuration
Timeout Settings: Configure appropriate timeout values for your application
Logging: Maintain comprehensive logs for troubleshooting
Certificate Management: Keep certificates updated and properly configured
Performance Tuning: Adjust buffer sizes and timeouts based on your application's needs

# Performance tuning example
```
reverse_proxy 127.0.0.1:8081 {
    header_up X-Forwarded-* {http.request.header.x_forwarded_*}
    transport http {
        dial_timeout 5s
        read_timeout 60s
        write_timeout 60s
        tls_timeout 30s
        max_conns_per_host 100
    }
}
```

