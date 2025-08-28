#!/usr/bin/env python3

import os
import logging
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

def main():
    """Entry point for running the application"""
    config_name = os.environ.get('FLASK_ENV', 'production')
    app = create_app(config_name)
    
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 8080)
    debug = app.config.get('DEBUG', False)
    
    print(f"Starting VaultHunters Web Manager on {host}:{port}")
    print(f"Debug mode: {debug}")
    print(f"Environment: {config_name}")
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    main()