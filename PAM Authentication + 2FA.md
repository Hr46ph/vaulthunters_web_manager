PAM Authentication + 2FA

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

### Phase 1: Basic PAM Authentication
**Goal**: Replace basic authentication with PAM-based Linux account validation

**Tasks**:
1. Add python-pam dependency to requirements.txt
2. Create `services/auth_manager.py` with PAM authentication functions
3. Update Flask app to use session-based authentication
4. Add login/logout routes and templates
5. Implement authentication middleware for protected routes
6. Test with existing Linux user accounts

**Deliverables**:
- Basic login form with username/password
- Session management with Flask-Session
- Protection for all admin routes
- Logout functionality

### Phase 2: Group-Based Authorization  
**Goal**: Restrict access to users in authorized groups (sudo, minecraft-admins)

**Tasks**:
1. Implement group membership validation in `auth_manager.py`
2. Add configuration options for allowed groups
3. Create custom `minecraft-admins` group setup instructions
4. Update authentication flow to check group membership
5. Add user role display in UI

**Deliverables**:
- Group-based access control
- Configuration for allowed groups
- Admin documentation for user management

### Phase 3: TOTP 2FA Implementation
**Goal**: Add optional TOTP-based two-factor authentication

**Tasks**:
1. Add pyotp and qrcode dependencies
2. Create TOTP secret storage in `/home/minecraft/.vhwm-secrets/`
3. Implement 2FA setup workflow with QR code generation
4. Add TOTP validation to authentication flow
5. Create 2FA management UI (enable/disable, regenerate)
6. Implement backup code generation and validation

**Deliverables**:
- 2FA setup page with QR code
- TOTP validation during login
- Backup codes for recovery
- 2FA management interface

### Phase 4: Security Hardening & Polish
**Goal**: Add security features and improve user experience

**Tasks**:
1. Implement session timeout and renewal
2. Add rate limiting for login attempts
3. Create audit logging for authentication events
4. Add "Remember Me" functionality with secure tokens
5. Implement password change integration with Linux accounts
6. Add security headers and CSRF protection enhancement
7. Create comprehensive testing suite

**Deliverables**:
- Session security improvements
- Brute force protection
- Audit trail
- Production-ready security features

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
