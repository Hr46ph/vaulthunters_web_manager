#!/usr/bin/env python3

import os
import logging
from datetime import datetime
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
    
    # Initialize extensions - disable automatic CSRF for manual control
    # csrf = CSRFProtect(app)  # Disabled - using manual CSRF validation
    
    # Configure logging
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = logging.FileHandler('logs/vaulthunter_web.log')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('VaultHunter Web Manager startup')
    
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
    
    # Context processors
    @app.context_processor
    def inject_common_vars():
        return {
            'current_year': datetime.now().year,
            'app_name': 'VaultHunter Web Manager'
        }
    
    # Register routes
    from routes import main_bp
    app.register_blueprint(main_bp)
    
    return app

def main():
    """Entry point for running the application"""
    config_name = os.environ.get('FLASK_ENV', 'production')
    app = create_app(config_name)
    
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 8080)
    debug = app.config.get('DEBUG', False)
    
    print(f"Starting VaultHunter Web Manager on {host}:{port}")
    print(f"Debug mode: {debug}")
    print(f"Environment: {config_name}")
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    main()