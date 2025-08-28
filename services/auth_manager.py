#!/usr/bin/env python3

import os
import json
import hashlib
import secrets
import logging
from functools import wraps
from flask import session, request, redirect, url_for, flash, current_app

logger = logging.getLogger(__name__)

class AuthManager:
    """Simple file-based authentication manager for VaultHunters Web Manager"""
    
    USERS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.json')
    
    @staticmethod
    def _ensure_users_file():
        """Ensure users file and directory exist"""
        os.makedirs(os.path.dirname(AuthManager.USERS_FILE), exist_ok=True)
        if not os.path.exists(AuthManager.USERS_FILE):
            # Create default admin users as mentioned in documentation
            default_users = {
                "admin": {
                    "password_hash": AuthManager._hash_password("admin123"),
                    "created_at": "2025-08-28",
                    "role": "admin",
                    "active": True
                },
                "ingemar": {
                    "password_hash": AuthManager._hash_password("minecraft123"),
                    "created_at": "2025-08-28",
                    "role": "admin",
                    "active": True
                }
            }
            with open(AuthManager.USERS_FILE, 'w') as f:
                json.dump(default_users, f, indent=2)
            logger.info(f"Created default users file with admin users (admin:admin123, ingemar:minecraft123)")
    
    @staticmethod
    def _hash_password(password):
        """Hash password using SHA-256 with salt"""
        salt = secrets.token_hex(32)
        password_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
        return f"{salt}:{password_hash}"
    
    @staticmethod
    def _verify_password(password, stored_hash):
        """Verify password against stored hash"""
        try:
            salt, password_hash = stored_hash.split(':')
            test_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
            return test_hash == password_hash
        except Exception:
            return False
    
    @staticmethod
    def authenticate_user(username, password):
        """
        Authenticate user against local user database
        
        Args:
            username (str): Username to authenticate
            password (str): Password to validate
            
        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            AuthManager._ensure_users_file()
            
            logger.info(f"Attempting authentication for user: {username}")
            
            # Load users database
            with open(AuthManager.USERS_FILE, 'r') as f:
                users = json.load(f)
            
            # Check if user exists
            if username not in users:
                logger.warning(f"User {username} not found in users database")
                return False
            
            user_data = users[username]
            
            # Check if user is active
            if not user_data.get('active', True):
                logger.warning(f"User {username} account is disabled")
                return False
            
            # Verify password
            if AuthManager._verify_password(password, user_data['password_hash']):
                logger.info(f"Authentication successful for user: {username}")
                return True
            else:
                logger.warning(f"Invalid password for user: {username}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error for user {username}: {e}", exc_info=True)
            return False
    
    @staticmethod
    def login_user(username):
        """
        Log in user by creating session
        
        Args:
            username (str): Username to log in
        """
        session.clear()
        session['user_id'] = username
        session['logged_in'] = True
        session.permanent = True
        logger.info(f"User logged in: {username}")
    
    @staticmethod
    def logout_user():
        """Log out current user by clearing session"""
        username = session.get('user_id', 'unknown')
        session.clear()
        logger.info(f"User logged out: {username}")
    
    @staticmethod
    def is_authenticated():
        """
        Check if current user is authenticated
        
        Returns:
            bool: True if user is logged in, False otherwise
        """
        return session.get('logged_in', False) and session.get('user_id') is not None
    
    @staticmethod
    def get_current_user():
        """
        Get current authenticated user
        
        Returns:
            str: Username if authenticated, None otherwise
        """
        if AuthManager.is_authenticated():
            return session.get('user_id')
        return None
    
    @staticmethod
    def get_user_info(username=None):
        """
        Get user information including role
        
        Args:
            username (str): Username to get info for, None for current user
            
        Returns:
            dict: User info (without password hash) or None if not found
        """
        if username is None:
            username = AuthManager.get_current_user()
        
        if not username:
            return None
            
        try:
            AuthManager._ensure_users_file()
            
            with open(AuthManager.USERS_FILE, 'r') as f:
                users = json.load(f)
            
            if username not in users:
                return None
                
            user_data = users[username]
            return {
                "username": username,
                "role": user_data.get("role", "user"),
                "active": user_data.get("active", True),
                "created_at": user_data.get("created_at", "unknown")
            }
            
        except Exception as e:
            logger.error(f"Error getting user info for {username}: {e}")
            return None
    
    @staticmethod
    def has_role(role, username=None):
        """
        Check if user has specified role
        
        Args:
            role (str): Role to check for (admin, user)
            username (str): Username to check, None for current user
            
        Returns:
            bool: True if user has role, False otherwise
        """
        user_info = AuthManager.get_user_info(username)
        if not user_info:
            return False
        return user_info.get("role") == role
    
    @staticmethod
    def is_admin(username=None):
        """
        Check if user has admin role
        
        Args:
            username (str): Username to check, None for current user
            
        Returns:
            bool: True if user is admin, False otherwise
        """
        return AuthManager.has_role("admin", username)
    
    @staticmethod
    def add_user(username, password, role="user"):
        """
        Add a new user to the authentication system
        
        Args:
            username (str): Username for the new user
            password (str): Password for the new user
            role (str): Role for the user (admin, user)
            
        Returns:
            bool: True if user added successfully, False otherwise
        """
        try:
            AuthManager._ensure_users_file()
            
            # Load existing users
            with open(AuthManager.USERS_FILE, 'r') as f:
                users = json.load(f)
            
            # Check if user already exists
            if username in users:
                logger.warning(f"User {username} already exists")
                return False
            
            # Add new user
            users[username] = {
                "password_hash": AuthManager._hash_password(password),
                "created_at": "2025-08-28",
                "role": role,
                "active": True
            }
            
            # Save users file
            with open(AuthManager.USERS_FILE, 'w') as f:
                json.dump(users, f, indent=2)
            
            logger.info(f"User {username} added successfully with role {role}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding user {username}: {e}")
            return False
    
    @staticmethod
    def list_users():
        """
        List all users in the system
        
        Returns:
            dict: Dictionary of users and their info (without password hashes)
        """
        try:
            AuthManager._ensure_users_file()
            
            with open(AuthManager.USERS_FILE, 'r') as f:
                users = json.load(f)
            
            # Remove password hashes for security
            safe_users = {}
            for username, user_data in users.items():
                safe_users[username] = {
                    "role": user_data.get("role", "user"),
                    "active": user_data.get("active", True),
                    "created_at": user_data.get("created_at", "unknown")
                }
            
            return safe_users
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return {}
    
    @staticmethod
    def change_password(username, current_password, new_password):
        """
        Change password for a user
        
        Args:
            username (str): Username to change password for
            current_password (str): Current password for verification
            new_password (str): New password to set
            
        Returns:
            bool: True if password changed successfully, False otherwise
        """
        try:
            AuthManager._ensure_users_file()
            
            # Load users database
            with open(AuthManager.USERS_FILE, 'r') as f:
                users = json.load(f)
            
            # Check if user exists
            if username not in users:
                logger.warning(f"User {username} not found for password change")
                return False
            
            # Verify current password
            user_data = users[username]
            if not AuthManager._verify_password(current_password, user_data['password_hash']):
                logger.warning(f"Invalid current password for user {username}")
                return False
            
            # Update password
            users[username]['password_hash'] = AuthManager._hash_password(new_password)
            
            # Save users file
            with open(AuthManager.USERS_FILE, 'w') as f:
                json.dump(users, f, indent=2)
            
            logger.info(f"Password changed successfully for user {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error changing password for {username}: {e}")
            return False
    
    @staticmethod
    def update_user(username, role=None, active=None):
        """
        Update user properties (admin only)
        
        Args:
            username (str): Username to update
            role (str): New role for the user (optional)
            active (bool): New active status (optional)
            
        Returns:
            bool: True if user updated successfully, False otherwise
        """
        try:
            AuthManager._ensure_users_file()
            
            # Load users database
            with open(AuthManager.USERS_FILE, 'r') as f:
                users = json.load(f)
            
            # Check if user exists
            if username not in users:
                logger.warning(f"User {username} not found for update")
                return False
            
            # Update properties
            if role is not None:
                users[username]['role'] = role
                logger.info(f"Updated role for {username} to {role}")
            
            if active is not None:
                users[username]['active'] = active
                logger.info(f"Updated active status for {username} to {active}")
            
            # Save users file
            with open(AuthManager.USERS_FILE, 'w') as f:
                json.dump(users, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating user {username}: {e}")
            return False
    
    @staticmethod
    def delete_user(username):
        """
        Delete a user (admin only)
        
        Args:
            username (str): Username to delete
            
        Returns:
            bool: True if user deleted successfully, False otherwise
        """
        try:
            AuthManager._ensure_users_file()
            
            # Load users database
            with open(AuthManager.USERS_FILE, 'r') as f:
                users = json.load(f)
            
            # Check if user exists
            if username not in users:
                logger.warning(f"User {username} not found for deletion")
                return False
            
            # Don't allow deleting the last admin user
            admin_count = sum(1 for user_data in users.values() 
                            if user_data.get('role') == 'admin' and user_data.get('active', True))
            
            if users[username].get('role') == 'admin' and admin_count <= 1:
                logger.warning(f"Cannot delete last admin user {username}")
                return False
            
            # Delete user
            del users[username]
            
            # Save users file
            with open(AuthManager.USERS_FILE, 'w') as f:
                json.dump(users, f, indent=2)
            
            logger.info(f"User {username} deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting user {username}: {e}")
            return False


def login_required(f):
    """
    Decorator to require authentication for routes
    
    Args:
        f: Function to decorate
        
    Returns:
        Decorated function that redirects to login if not authenticated
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AuthManager.is_authenticated():
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator to require admin role for routes
    
    Args:
        f: Function to decorate
        
    Returns:
        Decorated function that checks for admin role
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AuthManager.is_authenticated():
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('main.login'))
        
        if not AuthManager.is_admin():
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def role_required(required_role):
    """
    Decorator to require specific role for routes
    
    Args:
        required_role (str): Role required to access the route
        
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not AuthManager.is_authenticated():
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('main.login'))
            
            if not AuthManager.has_role(required_role):
                flash(f'You need {required_role} role to access this page.', 'error')
                return redirect(url_for('main.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator