#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Variables to track what to remove
REMOVE_SERVICE=false
REMOVE_PROJECT=false
REMOVE_USER=false
REMOVE_SUDOERS=false
CREATE_BACKUP=false
MINECRAFT_USER=""
PROJECT_DIR=""

# Function to test sudo permissions
test_sudo_permissions() {
    print_info "Testing sudo permissions..."
    
    if ! sudo -n true 2>/dev/null; then
        if ! sudo -v; then
            print_error "This script requires sudo permissions to remove systemd services and sudoers files."
            print_error "Please run this script as a user with sudo privileges."
            exit 1
        fi
    fi
    
    print_success "Sudo permissions verified"
}

# Function to detect existing installation
detect_installation() {
    print_info "Detecting existing VaultHunters Web Manager installation..."
    
    # Check for systemd service
    if systemctl list-unit-files | grep -q "vaulthunters_web_manager.service"; then
        print_success "Found systemd service: vaulthunters_web_manager.service"
        SERVICE_EXISTS=true
        
        # Get user from service file
        if [ -f "/etc/systemd/system/vaulthunters_web_manager.service" ]; then
            DETECTED_USER=$(grep "^User=" /etc/systemd/system/vaulthunters_web_manager.service | cut -d'=' -f2)
            DETECTED_PROJECT_DIR=$(grep "^WorkingDirectory=" /etc/systemd/system/vaulthunters_web_manager.service | cut -d'=' -f2)
            
            if [ -n "$DETECTED_USER" ]; then
                print_info "Detected service user: $DETECTED_USER"
                MINECRAFT_USER="$DETECTED_USER"
            fi
            
            if [ -n "$DETECTED_PROJECT_DIR" ]; then
                print_info "Detected project directory: $DETECTED_PROJECT_DIR"
                PROJECT_DIR="$DETECTED_PROJECT_DIR"
            fi
        fi
    else
        SERVICE_EXISTS=false
        print_warning "No systemd service found"
    fi
    
    # Ask for user if not detected
    if [ -z "$MINECRAFT_USER" ]; then
        read -p "Enter the username that was used for the Minecraft server (default: minecraft): " MINECRAFT_USER
        MINECRAFT_USER=${MINECRAFT_USER:-minecraft}
    fi
    
    # Ask for project directory if not detected
    if [ -z "$PROJECT_DIR" ]; then
        local default_dir="/home/$MINECRAFT_USER/vaulthunters_web_manager"
        read -p "Enter the project directory path (default: $default_dir): " PROJECT_DIR
        PROJECT_DIR=${PROJECT_DIR:-$default_dir}
    fi
    
    # Check if user exists
    if id "$MINECRAFT_USER" &>/dev/null; then
        USER_EXISTS=true
        print_info "User $MINECRAFT_USER exists"
    else
        USER_EXISTS=false
        print_warning "User $MINECRAFT_USER does not exist"
    fi
    
    # Check if project directory exists
    if [ -d "$PROJECT_DIR" ]; then
        PROJECT_EXISTS=true
        print_info "Project directory exists: $PROJECT_DIR"
    else
        PROJECT_EXISTS=false
        print_warning "Project directory does not exist: $PROJECT_DIR"
    fi
    
    # Check if sudoers file exists
    if [ -f "/etc/sudoers.d/$MINECRAFT_USER" ]; then
        SUDOERS_EXISTS=true
        print_info "Sudoers file exists: /etc/sudoers.d/$MINECRAFT_USER"
    else
        SUDOERS_EXISTS=false
        print_warning "Sudoers file does not exist: /etc/sudoers.d/$MINECRAFT_USER"
    fi
}

# Function to ask what to remove
ask_removal_options() {
    echo
    print_info "Please select what you want to remove:"
    echo
    
    # Ask about service removal
    if [ "$SERVICE_EXISTS" = true ]; then
        read -p "Remove systemd service? (Y/n): " remove_service
        if [[ ! $remove_service =~ ^[Nn]$ ]]; then
            REMOVE_SERVICE=true
        fi
    fi
    
    # Ask about project directory removal
    if [ "$PROJECT_EXISTS" = true ]; then
        read -p "Remove project directory ($PROJECT_DIR)? (Y/n): " remove_project
        if [[ ! $remove_project =~ ^[Nn]$ ]]; then
            REMOVE_PROJECT=true
            
            # Ask about backup if removing project
            read -p "Create backup of project directory before removal? (Y/n): " create_backup
            if [[ ! $create_backup =~ ^[Nn]$ ]]; then
                CREATE_BACKUP=true
            fi
        fi
    fi
    
    # Ask about sudoers file removal
    if [ "$SUDOERS_EXISTS" = true ]; then
        read -p "Remove sudoers file for $MINECRAFT_USER? (Y/n): " remove_sudoers
        if [[ ! $remove_sudoers =~ ^[Nn]$ ]]; then
            REMOVE_SUDOERS=true
        fi
    fi
    
    # Ask about user removal
    if [ "$USER_EXISTS" = true ]; then
        echo
        print_warning "USER REMOVAL IS DANGEROUS!"
        print_warning "This will remove the user account and ALL their files including:"
        print_warning "- Home directory (/home/$MINECRAFT_USER)"
        print_warning "- Minecraft server files"
        print_warning "- Any other files owned by this user"
        echo
        read -p "Remove user $MINECRAFT_USER and ALL their files? (y/N): " remove_user
        if [[ $remove_user =~ ^[Yy]$ ]]; then
            REMOVE_USER=true
            
            # Double confirmation for user removal
            echo
            print_error "FINAL WARNING: This will permanently delete ALL files for user $MINECRAFT_USER"
            read -p "Are you absolutely sure? Type 'DELETE' to confirm: " final_confirm
            if [ "$final_confirm" != "DELETE" ]; then
                print_info "User removal cancelled"
                REMOVE_USER=false
            fi
        fi
    fi
}

# Function to display removal summary
display_removal_summary() {
    echo
    print_info "Removal Summary:"
    echo "=================="
    
    if [ "$REMOVE_SERVICE" = true ]; then
        echo "✓ Stop and remove systemd service"
    fi
    
    if [ "$CREATE_BACKUP" = true ]; then
        echo "✓ Create backup of project directory"
    fi
    
    if [ "$REMOVE_PROJECT" = true ]; then
        echo "✓ Remove project directory: $PROJECT_DIR"
    fi
    
    if [ "$REMOVE_SUDOERS" = true ]; then
        echo "✓ Remove sudoers file: /etc/sudoers.d/$MINECRAFT_USER"
    fi
    
    if [ "$REMOVE_USER" = true ]; then
        echo "✓ Remove user $MINECRAFT_USER and ALL their files"
    fi
    
    echo
    read -p "Proceed with removal? (y/N): " proceed
    if [[ ! $proceed =~ ^[Yy]$ ]]; then
        print_info "Uninstallation cancelled"
        exit 0
    fi
}

# Function to stop and remove systemd service
remove_systemd_service() {
    if [ "$REMOVE_SERVICE" = true ]; then
        print_info "Stopping and removing systemd service..."
        
        # Stop the service if running
        if systemctl is-active --quiet vaulthunters_web_manager.service; then
            sudo systemctl stop vaulthunters_web_manager.service
            print_success "Service stopped"
        fi
        
        # Disable the service
        if systemctl is-enabled --quiet vaulthunters_web_manager.service; then
            sudo systemctl disable vaulthunters_web_manager.service
            print_success "Service disabled"
        fi
        
        # Remove service file
        if [ -f "/etc/systemd/system/vaulthunters_web_manager.service" ]; then
            sudo rm -f /etc/systemd/system/vaulthunters_web_manager.service
            sudo systemctl daemon-reload
            print_success "Service file removed"
        fi
    fi
}

# Function to create backup
create_project_backup() {
    if [ "$CREATE_BACKUP" = true ] && [ -d "$PROJECT_DIR" ]; then
        print_info "Creating backup of project directory..."
        
        local backup_name="vaulthunters_web_manager_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
        local backup_path="/tmp/$backup_name"
        
        tar -czf "$backup_path" -C "$(dirname "$PROJECT_DIR")" "$(basename "$PROJECT_DIR")"
        
        if [ $? -eq 0 ]; then
            print_success "Backup created: $backup_path"
            print_info "You can restore it later with: tar -xzf $backup_path -C $(dirname "$PROJECT_DIR")"
        else
            print_error "Failed to create backup"
            read -p "Continue without backup? (y/N): " continue_without_backup
            if [[ ! $continue_without_backup =~ ^[Yy]$ ]]; then
                print_error "Uninstallation cancelled"
                exit 1
            fi
        fi
    fi
}

# Function to remove project directory
remove_project_directory() {
    if [ "$REMOVE_PROJECT" = true ] && [ -d "$PROJECT_DIR" ]; then
        print_info "Removing project directory: $PROJECT_DIR"
        
        sudo rm -rf "$PROJECT_DIR"
        
        if [ $? -eq 0 ]; then
            print_success "Project directory removed"
        else
            print_error "Failed to remove project directory"
        fi
    fi
}

# Function to remove sudoers file
remove_sudoers_file() {
    if [ "$REMOVE_SUDOERS" = true ] && [ -f "/etc/sudoers.d/$MINECRAFT_USER" ]; then
        print_info "Removing sudoers file for $MINECRAFT_USER..."
        
        sudo rm -f "/etc/sudoers.d/$MINECRAFT_USER"
        
        if [ $? -eq 0 ]; then
            print_success "Sudoers file removed"
        else
            print_error "Failed to remove sudoers file"
        fi
    fi
}

# Function to remove user
remove_user_account() {
    if [ "$REMOVE_USER" = true ] && id "$MINECRAFT_USER" &>/dev/null; then
        print_warning "Removing user $MINECRAFT_USER and ALL their files..."
        
        # Kill all processes owned by the user
        sudo pkill -u "$MINECRAFT_USER" || true
        sleep 2
        
        # Remove user and home directory
        sudo userdel -r "$MINECRAFT_USER"
        
        if [ $? -eq 0 ]; then
            print_success "User $MINECRAFT_USER and their files removed"
        else
            print_error "Failed to remove user (may need manual cleanup)"
        fi
    fi
}

# Function to display final information
display_final_info() {
    echo
    print_success "Uninstallation completed!"
    echo
    
    if [ "$CREATE_BACKUP" = true ]; then
        print_info "Don't forget to remove the backup file from /tmp/ when no longer needed"
    fi
    
    if [ "$REMOVE_USER" = false ] && [ "$USER_EXISTS" = true ]; then
        print_info "User $MINECRAFT_USER was preserved and may still have files in /home/$MINECRAFT_USER"
    fi
    
    print_info "VaultHunters Web Manager has been uninstalled"
}

# Main uninstall function
main() {
    echo "=============================================="
    echo "VaultHunters Web Manager Uninstaller"
    echo "=============================================="
    echo
    
    print_warning "This script will help you remove VaultHunters Web Manager"
    print_warning "Please read all prompts carefully before proceeding"
    echo
    
    # Step 1: Test sudo permissions
    test_sudo_permissions
    
    # Step 2: Detect existing installation
    detect_installation
    
    # Step 3: Ask what to remove
    ask_removal_options
    
    # Step 4: Display summary and confirm
    display_removal_summary
    
    # Step 5: Perform removal
    print_info "Starting uninstallation process..."
    
    # Stop and remove service first
    remove_systemd_service
    
    # Create backup if requested
    create_project_backup
    
    # Remove project directory
    remove_project_directory
    
    # Remove sudoers file
    remove_sudoers_file
    
    # Remove user (dangerous - done last)
    remove_user_account
    
    # Display final information
    display_final_info
}

# Run main function
main "$@"