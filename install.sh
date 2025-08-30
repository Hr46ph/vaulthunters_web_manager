#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project repository URL
REPO_URL="https://github.com/Hr46ph/vaulthunters_web_manager.git"
DEFAULT_PORT=8889

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to test sudo permissions
test_sudo_permissions() {
    print_info "Testing sudo permissions..."
    
    if ! sudo -n true 2>/dev/null; then
        if ! sudo -v; then
            print_error "This script requires sudo permissions to create systemd services and sudoers files."
            print_error "Please run this script as a user with sudo privileges."
            exit 1
        fi
    fi
    
    print_success "Sudo permissions verified"
}

# Function to test required commands
test_required_commands() {
    print_info "Checking required commands..."
    
    local required_commands=("git" "python3" "systemctl" "useradd" "usermod" "visudo" "caddy")
    local missing_commands=()
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_commands+=("$cmd")
        fi
    done
    
    if [ ${#missing_commands[@]} -ne 0 ]; then
        print_error "Missing required commands: ${missing_commands[*]}"
        print_error "Please install the following packages:"
        print_error "- git"
        print_error "- python3 and python3-venv"
        print_error "- systemd"
        print_error "- sudo"
        print_error "- caddy (web server for TLS termination)"
        exit 1
    fi
    
    # Check if python3-venv is available
    if ! python3 -m venv --help &> /dev/null; then
        print_error "python3-venv is not available. Please install python3-venv package."
        exit 1
    fi
    
    print_success "All required commands are available"
}

# Function to ask for minecraft user
ask_for_minecraft_user() {
    print_info "Please specify the user that will run the Minecraft server:"
    read -p "Enter username (default: minecraft): " MINECRAFT_USER
    MINECRAFT_USER=${MINECRAFT_USER:-minecraft}
    
    print_info "Using username: $MINECRAFT_USER"
}

# Function to detect user type and handle user creation
detect_and_handle_user() {
    local current_user=$(whoami)
    
    if [ "$MINECRAFT_USER" = "$current_user" ]; then
        print_info "Using current user ($current_user) for Minecraft server"
        USER_TYPE="current"
        MINECRAFT_HOME=$(eval echo ~$current_user)
    elif id "$MINECRAFT_USER" &>/dev/null; then
        print_info "User $MINECRAFT_USER already exists"
        USER_TYPE="existing"
        MINECRAFT_HOME=$(eval echo ~$MINECRAFT_USER)
    else
        print_info "User $MINECRAFT_USER does not exist and will be created"
        USER_TYPE="new"
        MINECRAFT_HOME="/home/$MINECRAFT_USER"
        create_minecraft_user
    fi
}

# Function to create new minecraft user
create_minecraft_user() {
    print_info "Creating user $MINECRAFT_USER..."
    
    sudo useradd -m -s /bin/bash "$MINECRAFT_USER"
    
    if [ $? -eq 0 ]; then
        print_success "User $MINECRAFT_USER created successfully"
        print_info "User home directory: $MINECRAFT_HOME"
    else
        print_error "Failed to create user $MINECRAFT_USER"
        exit 1
    fi
}

# Function to check for VaultHunters server
check_vaulthunters_server() {
    if [ "$USER_TYPE" = "current" ] || [ "$USER_TYPE" = "existing" ]; then
        print_info "Checking for existing VaultHunters server..."
        
        read -p "Do you have an existing VaultHunters server? (y/N): " has_server
        
        if [[ $has_server =~ ^[Yy]$ ]]; then
            # Check default location first
            if [ -d "$MINECRAFT_HOME/vaulthunters" ] || [ -d "$MINECRAFT_HOME/VaultHunters" ]; then
                if [ -d "$MINECRAFT_HOME/vaulthunters" ]; then
                    SERVER_PATH="$MINECRAFT_HOME/vaulthunters"
                else
                    SERVER_PATH="$MINECRAFT_HOME/VaultHunters"
                fi
                print_success "Found VaultHunters server at: $SERVER_PATH"
            else
                print_warning "VaultHunters server not found in default location ($MINECRAFT_HOME/vaulthunters)"
                read -p "Enter the full path to your VaultHunters server directory: " SERVER_PATH
                
                if [ ! -d "$SERVER_PATH" ]; then
                    print_error "Directory $SERVER_PATH does not exist"
                    exit 1
                fi
            fi
        else
            SERVER_PATH="$MINECRAFT_HOME/vaulthunters"
            print_info "Will use default server path: $SERVER_PATH"
        fi
    else
        SERVER_PATH="$MINECRAFT_HOME/vaulthunters"
        print_info "Will use default server path for new user: $SERVER_PATH"
    fi
    
    # Set backup path
    BACKUP_PATH="$MINECRAFT_HOME/backups"
}

# Function to clone the project
clone_project() {
    local project_dir="$MINECRAFT_HOME/vaulthunters_web_manager"
    
    print_info "Cloning VaultHunters Web Manager..."
    
    if [ -d "$project_dir" ]; then
        print_warning "Directory $project_dir already exists"
        read -p "Do you want to remove it and clone fresh? (y/N): " remove_existing
        
        if [[ $remove_existing =~ ^[Yy]$ ]]; then
            sudo rm -rf "$project_dir"
        else
            print_error "Installation cancelled"
            exit 1
        fi
    fi
    
    # Clone as the minecraft user
    sudo -u "$MINECRAFT_USER" git clone "$REPO_URL" "$project_dir"
    
    if [ $? -eq 0 ]; then
        print_success "Project cloned successfully to $project_dir"
        PROJECT_DIR="$project_dir"
    else
        print_error "Failed to clone project"
        exit 1
    fi
}

# Function to create virtual environment
create_virtual_environment() {
    print_info "Creating Python virtual environment..."
    
    local venv_dir="$PROJECT_DIR/venv"
    
    # Create venv as minecraft user
    sudo -u "$MINECRAFT_USER" python3 -m venv "$venv_dir"
    
    if [ $? -eq 0 ]; then
        print_success "Virtual environment created at $venv_dir"
    else
        print_error "Failed to create virtual environment"
        exit 1
    fi
    
    # Install requirements as minecraft user
    print_info "Installing Python dependencies..."
    sudo -u "$MINECRAFT_USER" bash -c "cd '$PROJECT_DIR' && source venv/bin/activate && pip install -r requirements.txt"
    
    if [ $? -eq 0 ]; then
        print_success "Python dependencies installed successfully"
    else
        print_error "Failed to install Python dependencies"
        exit 1
    fi
}

# Function to test port availability
test_port_availability() {
    local port=$1
    
    if command -v ss &> /dev/null; then
        ss -tuln | grep -q ":$port "
    elif command -v netstat &> /dev/null; then
        netstat -tuln | grep -q ":$port "
    else
        # Fallback: try to bind to the port
        python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', $port))
    s.close()
    exit(0)
except:
    exit(1)
"
    fi
    
    return $?
}

# Function to get available port
get_available_port() {
    local port=$DEFAULT_PORT
    
    print_info "Testing port availability..."
    
    if test_port_availability $port; then
        print_error "Port $port is already in use"
        while true; do
            read -p "Enter an alternative port number: " port
            
            if [[ ! $port =~ ^[0-9]+$ ]] || [ $port -lt 1024 ] || [ $port -gt 65535 ]; then
                print_error "Please enter a valid port number (1024-65535)"
                continue
            fi
            
            if test_port_availability $port; then
                print_error "Port $port is already in use"
                continue
            else
                break
            fi
        done
    fi
    
    WEB_PORT=$port
    print_success "Using port $WEB_PORT for web interface"
}

# Function to create systemd service file
create_systemd_service() {
    print_info "Creating systemd service file..."
    
    local service_content="[Unit]
Description=VaultHunters Web Manager
After=network.target
Wants=network.target

[Service]
Type=simple
User=$MINECRAFT_USER
Group=$MINECRAFT_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin:/usr/bin:/usr/local/bin
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/app.py
KillMode=process
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target"

    echo "$service_content" | sudo tee /etc/systemd/system/vaulthunters_web_manager.service > /dev/null
    
    if [ $? -eq 0 ]; then
        print_success "Systemd service file created"
        sudo systemctl daemon-reload
    else
        print_error "Failed to create systemd service file"
        exit 1
    fi
}

# Function to create sudoers file
create_sudoers_file() {
    print_info "Creating sudoers file for $MINECRAFT_USER..."
    
    local sudoers_content="$MINECRAFT_USER ALL=NOPASSWD: /bin/systemctl start vaulthunters_web_manager.service, \\
                        /bin/systemctl stop vaulthunters_web_manager.service, \\
                        /bin/systemctl restart vaulthunters_web_manager.service, \\
                        /bin/systemctl status vaulthunters_web_manager.service
$MINECRAFT_USER ALL=NOPASSWD: /bin/journalctl -u vaulthunters_web_manager.service -n * --no-pager"

    echo "$sudoers_content" | sudo EDITOR='tee' visudo -f "/etc/sudoers.d/$MINECRAFT_USER"
    
    if [ $? -eq 0 ]; then
        print_success "Sudoers file created for $MINECRAFT_USER"
    else
        print_error "Failed to create sudoers file"
        exit 1
    fi
}

# Function to create default config.toml
create_default_config() {
    print_info "Creating default config.toml..."
    
    # Generate a random secret key
    local secret_key=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    local config_content="[server]
minecraft_server_path = \"$SERVER_PATH\"
backup_path = \"$BACKUP_PATH\"
java_executable = \"java\"
server_jar = \"forge-1.18.2-40.2.21-universal.jar\"
minecraft_server_host = \"localhost\"
minecraft_server_port = 25565

[jvm]
# Adjust memory based on your system (4G minimum, 8G recommended for VaultHunters)
memory_min = \"4G\"
memory_max = \"8G\"

[web]
host = \"0.0.0.0\"
port = $WEB_PORT
# Random secret key generated during installation
secret_key = \"$secret_key\"
debug = false"

    sudo -u "$MINECRAFT_USER" bash -c "echo '$config_content' > '$PROJECT_DIR/config.toml'"
    
    if [ $? -eq 0 ]; then
        print_success "Default config.toml created with generated secret key"
    else
        print_error "Failed to create config.toml"
        exit 1
    fi
}

# Function to enable and start service
enable_and_start_service() {
    print_info "Enabling and starting VaultHunters Web Manager service..."
    
    sudo systemctl enable vaulthunters_web_manager.service
    sudo systemctl start vaulthunters_web_manager.service
    
    if [ $? -eq 0 ]; then
        print_success "Service enabled and started"
        
        # Wait a moment and check status
        sleep 2
        if sudo systemctl is-active --quiet vaulthunters_web_manager.service; then
            print_success "Service is running successfully"
        else
            print_warning "Service may not be running properly. Check with: sudo systemctl status vaulthunters_web_manager.service"
        fi
    else
        print_error "Failed to enable/start service"
        exit 1
    fi
}

# Function to display final information
display_final_info() {
    print_success "Installation completed successfully!"
    echo
    print_info "Configuration Summary:"
    echo "  - Minecraft User: $MINECRAFT_USER"
    echo "  - Project Directory: $PROJECT_DIR"
    echo "  - Server Path: $SERVER_PATH"
    echo "  - Backup Path: $BACKUP_PATH"
    echo "  - Web Interface Port: $WEB_PORT"
    echo
    print_info "Next Steps:"
    echo "  1. Edit $PROJECT_DIR/config.toml if needed"
    echo "  2. Ensure your VaultHunters server is set up with RCON enabled"
    echo "  3. Access the web interface at: https://$(ip route get 1 2>/dev/null | awk '{print $7}' | head -1 || echo 'localhost'):$WEB_PORT"
    echo
    print_info "Service Management Commands (run as $MINECRAFT_USER):"
    echo "  - sudo systemctl status vaulthunters_web_manager.service"
    echo "  - sudo systemctl restart vaulthunters_web_manager.service"
    echo "  - sudo systemctl stop vaulthunters_web_manager.service"
    echo "  - sudo systemctl start vaulthunters_web_manager.service"
    echo
    print_info "View service logs:"
    echo "  - sudo journalctl -u vaulthunters_web_manager.service -f"
}

# Main installation function
main() {
    echo "=========================================="
    echo "VaultHunters Web Manager Installer"
    echo "=========================================="
    echo
    
    # Step 1: Test sudo permissions
    test_sudo_permissions
    
    # Step 2: Test required commands
    test_required_commands
    
    # Step 3: Ask for minecraft user
    ask_for_minecraft_user
    
    # Step 4: Detect and handle user
    detect_and_handle_user
    
    # Step 5: Check for VaultHunters server
    check_vaulthunters_server
    
    # Step 6: Get available port
    get_available_port
    
    # Step 7: Clone project
    clone_project
    
    # Step 8: Create virtual environment
    create_virtual_environment
    
    # Step 9: Create systemd service
    create_systemd_service
    
    # Step 10: Create sudoers file
    create_sudoers_file
    
    # Step 11: Create default config
    create_default_config
    
    # Step 12: Enable and start service
    enable_and_start_service
    
    # Step 13: Display final information
    display_final_info
}

# Run main function
main "$@"
