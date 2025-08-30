#!/usr/bin/env python3

"""
Development runner - HTTP only (fast startup)
For SSL testing, use a production WSGI server like gunicorn
"""

import os
from app import create_app

def main():
    """Run the app with SSL disabled for fast development"""
    config_name = os.environ.get('FLASK_ENV', 'development')
    app = create_app(config_name)
    
    # Override SSL settings for development
    app.config['SSL_ENABLED'] = False
    app.config['SSL_REDIRECT'] = False
    
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 8080)
    debug = True  # Force debug mode for development
    
    print("=" * 50)
    print("DEVELOPMENT SERVER - HTTP ONLY")
    print("=" * 50)
    print(f"Starting VaultHunters Web Manager on http://{host}:{port}")
    print(f"Debug mode: {debug}")
    print(f"Environment: {config_name}")
    print("SSL disabled for faster development")
    print("=" * 50)
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    main()