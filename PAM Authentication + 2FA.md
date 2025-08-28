PAM Authentication + 2FA

## ⚠️ **IMPLEMENTATION UPDATE**: PAM Abandoned for Security Reasons

**Original Plan**: Linux PAM integration with system accounts  
**Actual Implementation**: Simple file-based authentication  
**Reason**: PAM requires elevated privileges and creates security risks

---

## Current Implementation (File-Based Authentication)

**Active System**:
```python
# Simple JSON-based user authentication
from services.auth_manager import AuthManager

# Authenticate against local database
result = AuthManager.authenticate_user(username, password)

# Users stored in data/users.json with:
# - Salted password hashes (SHA-256)
# - User roles (admin/user) 
# - Active/inactive status
```

**Benefits**:
- No system privileges required
- Web-specific passwords (isolated from system)
- Easy user management via AuthManager methods
- No PAM configuration complexity
- Secure password hashing with salt

**Default Users**:
- `admin:admin123` (admin role)
- `ingemar:minecraft123` (admin role)

---

## Original PAM Design (Abandoned)

Core Implementation:
# Using python-pam for Linux account validation
import pam
import pyotp

def authenticate_user(username, password, totp_token=None):
    # First: Validate against Linux accounts
    if not pam.authenticate(username, password):
        return False

    # Second: Validate 2FA if enabled
    if totp_token:
        return validate_totp(username, totp_token)
    return True

Benefits:
- Leverages existing user accounts (adduser minecraft-admin)
- Respects Linux password policies and expiration
- No duplicate credential management
- Works with existing SSH key users

sudo Group Integration

Enhanced Security:
# Check if user is in authorized groups
import grp

def user_authorized(username):
    try:
        # Check if user is in sudo or custom minecraft-admins group
        sudo_group = grp.getgrnam('sudo')
        return username in sudo_group.gr_mem
    except KeyError:
        return False

2FA Implementation Options

TOTP (Google Authenticator/Authy):
- Store TOTP secrets in /home/minecraft/.vhwm-secrets/
- QR code generation for initial setup
- Backup codes for recovery

Hardware Keys (Advanced):
- WebAuthn/FIDO2 support
- YubiKey integration
- Fallback to TOTP

Configuration Extension

[authentication]
enabled = true
method = "pam"  # Use Linux accounts
require_2fa = true
allowed_groups = ["sudo", "minecraft-admins"]
totp_issuer = "VaultHunters Manager"
backup_codes_count = 10

This approach provides enterprise-grade security while maintaining simplicity - users manage one password (Linux
account) plus 2FA, and administrators use familiar adduser/usermod commands for access control.

## Implementation Plan

### Phase 1: Basic Authentication ✅ **COMPLETED (Modified Approach)**
**Goal**: ~~Replace basic authentication with PAM-based Linux account validation~~ **Implemented simple file-based authentication**

**Original Tasks**:
1. ~~Add python-pam dependency to requirements.txt~~ **Removed PAM approach**
2. ~~Create `services/auth_manager.py` with PAM authentication functions~~ **Created with file-based auth**
3. Update Flask app to use session-based authentication ✅ **COMPLETED**
4. Add login/logout routes and templates ✅ **COMPLETED**
5. Implement authentication middleware for protected routes ✅ **COMPLETED**
6. ~~Test with existing Linux user accounts~~ **Implemented web-specific user accounts**

**Actual Implementation**:
- ✅ **Simple JSON-based user database** (`data/users.json`)
- ✅ **Salted password hashing** (SHA-256 with random salt)
- ✅ **Session management** with Flask's built-in sessions
- ✅ **Login/logout functionality** with professional UI
- ✅ **Route protection** with `@login_required` decorator
- ✅ **User management methods** (add_user, list_users)

**Deliverables**:
- ✅ Basic login form with username/password
- ✅ Session management (Flask built-in, not Flask-Session)
- ✅ Protection for all admin routes
- ✅ Logout functionality
- ✅ **Bonus**: Default admin users created (`admin:admin123`, `ingemar:minecraft123`)

**Why PAM Was Abandoned**:
- **Security concerns**: Required elevated system privileges
- **Complexity**: PAM configuration, permissions, group management
- **Attack surface**: Web vulnerabilities could lead to system access
- **Operational burden**: System user management affects web app
- **Deployment issues**: Different across Linux distributions

**Current Status**: Phase 1 complete with a **simpler, more secure approach**

### Phase 2: Role-Based Authorization ✅ **COMPLETED**
**Goal**: ~~Restrict access to users in authorized groups (sudo, minecraft-admins)~~ **Implement role-based access control**

**Updated Tasks**:
1. ~~Implement group membership validation in `auth_manager.py`~~ ✅ **Role validation implemented**
2. ~~Add configuration options for allowed groups~~ ✅ **Role-based access control implemented**
3. ~~Create custom `minecraft-admins` group setup instructions~~ ✅ **User management interface created**
4. ~~Update authentication flow to check group membership~~ ✅ **Role-based route protection implemented**
5. ✅ **User role display in UI implemented**
6. ✅ **Password change functionality implemented**

**Actual Implementation**:
- ✅ **Role-based decorators** (`@admin_required`, `@role_required`) in `auth_manager.py`
- ✅ **User management interface** with full CRUD operations (`/users`, `/users/add`, `/users/<username>/edit`)
- ✅ **Role validation methods** (`has_role()`, `is_admin()`, `get_user_info()`)
- ✅ **Enhanced navigation** with role badges and admin-only "Users" menu
- ✅ **User profile management** (`/profile`, `/profile/password`)
- ✅ **Password change functionality** with current password verification
- ✅ **Security protections** (prevent self-deletion, last admin protection)
- ✅ **Professional UI templates** for all user management functions

**Deliverables**:
- ✅ **Role-based access control** (admin/user roles)
- ✅ **User management interface** with Bootstrap UI
- ✅ **Web-based user administration** with complete functionality
- ✅ **Enhanced user experience** with role display and dropdown navigation

**Current Status**: Phase 2 complete with **comprehensive role-based authorization**

### Phase 3: TOTP 2FA Implementation (Compatible with File-Based Auth)
**Goal**: Add optional TOTP-based two-factor authentication

**Updated Tasks**:
1. Add pyotp and qrcode dependencies
2. ~~Create TOTP secret storage in `/home/minecraft/.vhwm-secrets/`~~ **Store TOTP secrets in user JSON database**
3. Implement 2FA setup workflow with QR code generation
4. Add TOTP validation to authentication flow
5. Create 2FA management UI (enable/disable, regenerate)
6. Implement backup code generation and validation
7. **New**: Extend `AuthManager` to support 2FA fields in user records

**Deliverables**:
- 2FA setup page with QR code
- TOTP validation during login
- Backup codes for recovery
- 2FA management interface
- **Enhanced**: 2FA secrets stored securely in JSON database

### Phase 4: Security Hardening & Polish (Updated for File-Based Auth)
**Goal**: Add security features and improve user experience

**Updated Tasks**:
1. Implement session timeout and renewal
2. Add rate limiting for login attempts
3. Create audit logging for authentication events
4. Add "Remember Me" functionality with secure tokens
5. ~~Implement password change integration with Linux accounts~~ **Web-based password change functionality**
6. Add security headers and CSRF protection enhancement
7. Create comprehensive testing suite
8. **New**: Implement account lockout after failed attempts
9. **New**: Add password strength requirements
10. **New**: User activity logging

**Deliverables**:
- Session security improvements
- Brute force protection
- Audit trail
- Production-ready security features
- **Enhanced**: Web-based user account management
- **Enhanced**: Comprehensive authentication logging

### Phase 5: Advanced Features (Optional)
**Goal**: Enterprise features for enhanced security

**Tasks**:
1. WebAuthn/FIDO2 hardware key support
2. LDAP/Active Directory integration option
3. OAuth2/OIDC provider support
4. Multi-session management
5. Advanced audit reporting

**Dependencies**:
- Phase 1 must complete before Phase 2
- Phase 2 must complete before Phase 3
- Phases 3-5 can be implemented independently after Phase 2
