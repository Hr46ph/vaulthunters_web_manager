#!/usr/bin/env python3

import os
import logging
import subprocess
import signal
import atexit
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException
from config import config

def create_app(config_name=None):
    """Application factory pattern"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))
    
    # Configure session settings - use default Flask sessions
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    
    # Initialize CSRF protection based on config
    csrf = None
    if app.config.get('CSRF_ENABLED', True):
        csrf = CSRFProtect(app)
        
        # Configure CSRF settings from config.toml
        app.config['WTF_CSRF_TIME_LIMIT'] = app.config.get('CSRF_TIME_LIMIT', 3600)
        
        app.logger.info(f'CSRF protection enabled (time limit: {app.config["WTF_CSRF_TIME_LIMIT"]}s)')
    
    # Configure logging
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = logging.FileHandler('logs/vaulthunters_web.log')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('VaultHunters Web Manager startup')
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403
    
    # CSRF error handler
    @app.errorhandler(400)
    def csrf_error(error):
        # Check if this is a CSRF error
        if 'CSRF' in str(error.description):
            app.logger.warning(f'CSRF validation failed: {error.description}')
            if request.is_json:
                return jsonify({'error': 'CSRF token validation failed'}), 400
            else:
                flash('Security validation failed. Please try again.', 'error')
                return render_template('errors/csrf.html'), 400
        return render_template('errors/400.html'), 400
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        app.logger.error(f'HTTP Error {error.code}: {error.description}')
        return render_template('errors/generic.html', 
                             error_code=error.code, 
                             error_message=error.description), error.code
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        app.logger.error(f'Unhandled exception: {error}', exc_info=True)
        return render_template('errors/500.html'), 500
    
    # HTTPS redirect middleware
    @app.before_request
    def force_https():
        """Redirect HTTP requests to HTTPS when SSL is enabled"""
        if (app.config.get('SSL_ENABLED', False) and 
            app.config.get('SSL_REDIRECT', True) and
            not request.is_secure and
            request.headers.get('X-Forwarded-Proto', 'http') != 'https'):
            
            # Build HTTPS URL
            if request.url.startswith('http://'):
                return redirect(request.url.replace('http://', 'https://', 1), code=301)
    
    # Context processors
    @app.context_processor
    def inject_common_vars():
        from flask_wtf.csrf import generate_csrf
        from services.auth_manager import AuthManager
        
        context_vars = {
            'current_year': datetime.now().year,
            'app_name': 'VaultHunters Web Manager'
        }
        
        # Add user context
        if AuthManager.is_authenticated():
            user_info = AuthManager.get_user_info()
            if user_info:
                context_vars.update({
                    'current_user_info': user_info,
                    'is_admin': AuthManager.is_admin()
                })
        
        # Add CSRF token if CSRF is enabled
        if app.config.get('CSRF_ENABLED', True):
            try:
                context_vars['csrf_token'] = generate_csrf()
            except Exception as e:
                app.logger.warning(f'Failed to generate CSRF token: {e}')
                context_vars['csrf_token'] = ''
        else:
            context_vars['csrf_token'] = ''
            
        return context_vars
    
    # Metrics storage functionality moved to system_control.py
    
    # Register routes
    from routes import main_bp
    app.register_blueprint(main_bp)
    
    return app

# Global variable to track Caddy process
caddy_process = None

def start_caddy():
    """Start Caddy reverse proxy"""
    global caddy_process
    
    # Ensure logs directory exists for Caddy logging
    if not os.path.exists('logs'):
        os.makedirs('logs')
        print("📁 Created logs directory for Caddy")
    
    # Check if Caddy is available
    try:
        result = subprocess.run(['caddy', 'version'], capture_output=True, check=True, text=True)
        print(f"📦 Found Caddy: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  Caddy not found - running Flask directly without HTTPS")
        return False
    
    # Check if Caddyfile exists
    if not os.path.exists('Caddyfile'):
        print("⚠️  Caddyfile not found - running Flask directly without HTTPS")
        return False
    
    # Stop any existing Caddy instance first
    try:
        subprocess.run(['caddy', 'stop'], capture_output=True, check=False)
        print("🛑 Stopped any existing Caddy instance")
    except:
        pass
    
    try:
        # Start Caddy with better error handling
        print("🚀 Starting Caddy reverse proxy...")
        caddy_process = subprocess.Popen(
            ['caddy', 'run', '--config', 'Caddyfile'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd()  # Ensure proper working directory
        )
        
        # Wait a moment for Caddy to start
        import time
        time.sleep(3)
        
        # Check if process is still running (should be for 'caddy run')
        if caddy_process.poll() is not None:
            # Process terminated - get output to see what went wrong
            stdout, stderr = caddy_process.communicate()
            print(f"❌ Caddy failed to start. Output:")
            if stdout:
                for line in stdout.splitlines():
                    print(f"   {line}")
            if stderr:
                for line in stderr.splitlines():
                    print(f"   {line}")
            caddy_process = None
            return False
        
        # Verify Caddy is actually running by checking if port 8889 is bound
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # 5 second timeout
                result = s.connect_ex(('127.0.0.1', 8889))
                if result == 0:
                    print(f"✅ Caddy reverse proxy started successfully (pid={caddy_process.pid})")
                    print("🌐 HTTPS available at https://0.0.0.0:8889") 
                    print("📝 Caddy logs: logs/caddy_access.log")
                    return True
                else:
                    print("❌ Caddy started but port 8889 not accessible")
                    return False
        except Exception as e:
            print(f"❌ Error checking Caddy status: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error starting Caddy: {e}")
        caddy_process = None
        return False

def stop_caddy():
    """Stop Caddy reverse proxy"""
    global caddy_process
    
    try:
        if caddy_process and caddy_process.poll() is None:
            # Process is still running, terminate it
            caddy_process.terminate()
            caddy_process.wait(timeout=5)
            print("✅ Caddy reverse proxy stopped")
        else:
            # Try the stop command as fallback
            subprocess.run(['caddy', 'stop'], capture_output=True, check=False)
            print("✅ Caddy reverse proxy stopped")
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        # Force kill if terminate doesn't work
        if caddy_process:
            try:
                caddy_process.kill()
                caddy_process.wait(timeout=2)
            except:
                pass
        print("✅ Caddy reverse proxy stopped (forced)")
    
    caddy_process = None

def cleanup_on_exit():
    """Cleanup function to stop Caddy on application exit"""
    stop_caddy()

# Register cleanup function
atexit.register(cleanup_on_exit)

def signal_handler(signum, frame):
    """Handle system signals to ensure proper cleanup"""
    print(f"\n📡 Received signal {signum}, shutting down gracefully...")
    stop_caddy()
    exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def main():
    """Entry point for running the application"""
    config_name = os.environ.get('FLASK_ENV', 'production')
    app = create_app(config_name)
    
    host = app.config.get('HOST', '127.0.0.1')
    port = app.config.get('PORT', 8081)
    debug = app.config.get('DEBUG', False)
    
    # Start Caddy reverse proxy first
    caddy_started = start_caddy()
    
    # SSL configuration (only used if Caddy is not available)
    ssl_enabled = app.config.get('SSL_ENABLED', False) and not caddy_started
    ssl_context = None
    
    if ssl_enabled:
        cert_path = app.config.get('SSL_CERT_PATH', 'certs/server.crt')
        key_path = app.config.get('SSL_KEY_PATH', 'certs/server.key')
        
        # Check if certificate files exist
        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            print(f"❌ SSL Error: Certificate files not found!")
            print(f"   Certificate: {cert_path}")
            print(f"   Private key: {key_path}")
            print("   Run ./generate_ssl_cert.py to create certificates")
            return
        
        ssl_context = (cert_path, key_path)
        protocol = "https"
    else:
        protocol = "http"
    
    print(f"🚀 Starting VaultHunters Web Manager Flask backend on {protocol}://{host}:{port}")
    print(f"Debug mode: {debug}")
    print(f"Environment: {config_name}")
    
    if caddy_started:
        print("💡 Access the application via Caddy reverse proxy at https://localhost:8889")
    elif ssl_enabled:
        print(f"SSL enabled: {cert_path}, {key_path}")
        print("⚠️  Using self-signed certificate - browsers will show warnings")
    else:
        print("⚠️  Running HTTP only - no HTTPS available")
    
    try:
        app.run(host=host, port=port, debug=debug, ssl_context=ssl_context)
    finally:
        # Ensure Caddy is stopped when Flask shuts down
        stop_caddy()

if __name__ == '__main__':
    main()